"""Probe explícito da Fase 1 contra PostgreSQL e Redis reais.

Este arquivo não faz parte da suíte unitária padrão. Execute somente em um
banco temporário com TRQ_BEC_DATABASE_URL apontando para ele.
"""

from __future__ import annotations

import base64
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from trq_bec.server.config import get_settings
from trq_bec.server.access_control import default_permissions
from trq_bec.server.models import (
    AccessAccountRecord,
    AuthorizeRedemptionRequest,
    BeginRedemptionRequest,
    EnrollDeviceRequest,
    IssueCouponRequest,
    MerchantStatusRequest,
    Principal,
    ProductCreateRequest,
)
from trq_bec.server.runtime import build_runtime


def b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def principal(uid: str, role: str, *, admin: bool = False) -> Principal:
    claims = {"role": role, "auth_time": int(time.time())}
    if admin:
        claims["admin"] = True
    return Principal(uid, role, None, claims)


def enroll(service, actor: Principal, key_id: str, private_key: Ed25519PrivateKey) -> None:
    service.enroll_device(
        actor,
        EnrollDeviceRequest(
            device_key_id=key_id,
            public_key_b64u=b64u(private_key.public_key().public_bytes_raw()),
            algorithm="ED25519_LAB",
            storage_profile="EXPO_SECURE_STORE_LAB",
        ),
    )


def main() -> None:
    settings = get_settings()
    if not settings.database_url.rsplit("/", 1)[-1].startswith("trq_bec_phase1_probe"):
        raise RuntimeError("PROBE_REQUIRES_A_TEMPORARY_DATABASE")
    runtime = build_runtime(settings)
    service = runtime.service
    try:
        admin = principal("probe-admin", "admin", admin=True)
        merchant = principal("probe-merchant", "entrepreneur")
        service.store.set_access_account(
            AccessAccountRecord(
                firebase_uid=admin.uid,
                email=None,
                role="admin",
                status="ACTIVE",
                allow_entrepreneur_fallback=False,
                permissions=default_permissions("admin"),
            )
        )
        service.set_merchant_status(
            admin,
            MerchantStatusRequest(
                firebase_uid=merchant.uid,
                display_name="Empreendedor Probe",
                establishment_id="EST-PROBE-01",
                establishment_name="Feira Probe",
                status="ACTIVE",
            ),
        )
        merchant_key = Ed25519PrivateKey.generate()
        enroll(service, merchant, "device:probe-merchant", merchant_key)
        product = service.create_product(
            merchant,
            ProductCreateRequest(
                title="Produto concorrente",
                description="Probe PostgreSQL real",
                price_minor=5_000,
                currency="BRL",
                stock_quantity=1,
            ),
        )
        issued = service.issue_coupon(
            merchant,
            IssueCouponRequest(
                product_id=product.product_id,
                discount_type="PERCENT",
                discount_value=20,
                maximum_redemptions=1,
                valid_until=datetime.now(timezone.utc) + timedelta(minutes=5),
                purpose="LIVE_FAIR_DISCOUNT",
                device_key_id="device:probe-merchant",
            ),
        )

        attempts: list[tuple[Principal, AuthorizeRedemptionRequest]] = []
        for index in range(100):
            buyer = principal(f"probe-buyer-{index}", "visitor")
            service.store.set_access_account(
                AccessAccountRecord(
                    firebase_uid=buyer.uid,
                    email=None,
                    role="visitor",
                    status="ACTIVE",
                    allow_entrepreneur_fallback=False,
                    permissions=default_permissions("visitor"),
                )
            )
            private_key = Ed25519PrivateKey.generate()
            device_key_id = f"device:probe-buyer-{index:03d}"
            enroll(service, buyer, device_key_id, private_key)
            begin = service.begin_redemption(
                buyer,
                BeginRedemptionRequest(qr_payload=issued.qr_payload, device_key_id=device_key_id),
            )
            message = base64.urlsafe_b64decode(
                begin.proof_message_b64u + "=" * (-len(begin.proof_message_b64u) % 4)
            )
            attempts.append(
                (
                    buyer,
                    AuthorizeRedemptionRequest(
                        operation_id=begin.operation_id,
                        session_id=begin.session_id,
                        challenge_id=begin.challenge.challenge_id,
                        device_key_id=device_key_id,
                        device_proof_b64u=b64u(private_key.sign(message)),
                    ),
                )
            )

        with ThreadPoolExecutor(max_workers=32) as executor:
            results = list(executor.map(lambda item: service.authorize_redemption(*item), attempts))
        allowed = [item for item in results if item.decision == "ALLOW"]
        denied = [item for item in results if item.decision == "DENY"]
        if len(allowed) != 1 or len(denied) != 99:
            raise AssertionError(f"EXPECTED_1_ALLOW_99_DENY:{len(allowed)}:{len(denied)}")

        with runtime.pool.connection() as connection:
            row = connection.execute(
                """
                SELECT p.stock_quantity, o.redeemed_count, o.status,
                       (SELECT count(*) FROM coupon_redemptions r WHERE r.offer_id = o.offer_id) AS redemptions
                FROM products p JOIN live_offers o ON o.product_id = p.product_id
                WHERE o.offer_id = %s
                """,
                (issued.offer_id,),
            ).fetchone()
        expected = (0, 1, "EXHAUSTED", 1)
        actual = (
            int(row["stock_quantity"]),
            int(row["redeemed_count"]),
            row["status"],
            int(row["redemptions"]),
        )
        if actual != expected:
            raise AssertionError(f"POSTGRES_COMMIT_MISMATCH:{actual}")

        denied_index = next(index for index, item in enumerate(results) if item.decision == "DENY")
        repeated = service.authorize_redemption(*attempts[denied_index])
        if not repeated.idempotent or repeated.reason_codes != results[denied_index].reason_codes:
            raise AssertionError("DENIAL_IDEMPOTENCY_FAILED")
        print("POSTGRES_PHASE1_PROBE_OK allow=1 deny=99 stock=0 redemptions=1")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
