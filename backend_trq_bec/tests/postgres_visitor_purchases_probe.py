"""Compra e histórico reais, somente em banco trq_bec_purchases_probe* já migrado."""
from __future__ import annotations

import base64
import time
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trq_bec.server.access_control import default_permissions
from trq_bec.server.config import get_settings
from trq_bec.server.models import (
    AccessAccountRecord, AuthorizeRedemptionRequest, BeginRedemptionRequest,
    EnrollDeviceRequest, IssueCouponRequest, Principal, ProductCreateRequest,
)
from trq_bec.server.runtime import build_runtime


def b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def main() -> None:
    settings = get_settings()
    if not settings.database_url.rsplit("/", 1)[-1].startswith("trq_bec_purchases_probe"):
        raise RuntimeError("PROBE_REQUIRES_A_TEMPORARY_DATABASE")
    runtime = build_runtime(settings)
    service = runtime.service
    service.device_security_notifier = None  # Probe isolado não envia e-mails.
    try:
        actors = {}
        for uid, role in (("purchases-seller", "entrepreneur"), ("purchases-visitor", "visitor"), ("purchases-other", "visitor")):
            service.store.set_access_account(AccessAccountRecord(
                firebase_uid=uid, email=None, role=role, status="ACTIVE",
                allow_entrepreneur_fallback=False, permissions=default_permissions(role),
            ))
            actors[role if uid != "purchases-other" else "other"] = Principal(uid, role, None, {"role": role, "auth_time": int(time.time()), "email_verified": True})
        seller, visitor = actors["entrepreneur"], actors["visitor"]
        # Fixture exclusiva do banco temporário; as operações abaixo usam a autorização normal.
        with runtime.pool.connection() as conn, conn.transaction():
            conn.execute("""
                INSERT INTO merchant_accounts(firebase_uid, display_name, establishment_id, establishment_name, status)
                VALUES (%s, 'Vendedor do probe', 'EST-PURCHASES-PROBE', 'Banca do probe', 'ACTIVE')
            """, (seller.uid,))
        keys = {}
        for actor in (seller, visitor):
            key = Ed25519PrivateKey.generate()
            keys[actor.uid] = key
            service.enroll_device(actor, EnrollDeviceRequest(
                device_key_id="device:" + actor.uid,
                public_key_b64u=b64u(key.public_key().public_bytes_raw()),
                algorithm="ED25519_LAB", storage_profile="EXPO_SECURE_STORE_LAB",
            ))
        # Simula o prazo decorrido no banco temporário e usa a ativação normal do serviço.
        with runtime.pool.connection() as conn, conn.transaction():
            conn.execute("UPDATE device_keys SET approval_expires_at = %s WHERE firebase_uid = %s AND status = 'PENDING_APPROVAL'",
                         (datetime.now(timezone.utc) - timedelta(seconds=1), seller.uid))
        service.list_account_devices(seller)
        product = service.create_product(seller, ProductCreateRequest(
            title="Produto do probe", description="Histórico PostgreSQL", price_minor=5000,
            currency="BRL", stock_quantity=10,
        ))
        issued = service.issue_coupon(seller, IssueCouponRequest(
            product_id=product.product_id, discount_type="PERCENT", discount_value=20,
            maximum_redemptions=8, valid_until=datetime.now(timezone.utc) + timedelta(minutes=5),
            device_key_id="device:" + seller.uid,
        ))
        qr = service.get_offer_qr(seller, issued.offer_id, quantity=3)
        assert service.get_visitor_purchases(visitor, 20, 0).total_purchases == 0
        begin = service.begin_redemption(visitor, BeginRedemptionRequest(qr_payload=qr.qr_payload, device_key_id="device:" + visitor.uid))
        assert service.get_visitor_purchases(visitor, 20, 0).total_purchases == 0
        message = base64.urlsafe_b64decode(begin.proof_message_b64u + "=" * (-len(begin.proof_message_b64u) % 4))
        command = AuthorizeRedemptionRequest(
            operation_id=begin.operation_id, session_id=begin.session_id,
            challenge_id=begin.challenge.challenge_id, device_key_id="device:" + visitor.uid,
            device_proof_b64u=b64u(keys[visitor.uid].sign(message)),
        )
        assert service.authorize_redemption(visitor, command).decision == "ALLOW"
        assert service.authorize_redemption(visitor, command).idempotent
        report = service.get_visitor_purchases(visitor, 1, 0)
        assert report.total_purchases == 1 and report.total_units == 3 and not report.has_more
        assert report.totals[0].spent_amount_minor == 12000 and report.totals[0].saved_amount_minor == 3000
        assert report.items[0].product_title == product.title and report.items[0].establishment_name == "Banca do probe"
        assert not service.get_visitor_purchases(visitor, 1, 1).items
        assert service.get_visitor_purchases(actors["other"], 20, 0).total_purchases == 0
        with runtime.pool.connection() as conn, conn.transaction():
            conn.execute("UPDATE products SET price_minor = 99999, status = 'ARCHIVED' WHERE product_id = %s", (product.product_id,))
        assert service.get_visitor_purchases(visitor, 20, 0).totals == report.totals
        with runtime.pool.connection() as conn, conn.transaction():
            conn.execute("UPDATE coupon_redemptions SET original_amount_minor = NULL, final_amount_minor = NULL, snapshot_quality = 'LEGACY_UNAVAILABLE' WHERE buyer_uid = %s", (visitor.uid,))
        legacy = service.get_visitor_purchases(visitor, 20, 0)
        assert legacy.items[0].final_amount_minor is None
        assert legacy.totals[0].amounts_unavailable_count == 1 and legacy.totals[0].saved_amount_minor == 3000
        print("POSTGRES_VISITOR_PURCHASES_PROBE_OK quantity=3 spent=12000 saved=3000 private=true idempotent=true legacy=true")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
