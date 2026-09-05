"""Smoke transacional dos lotes do marketplace em PostgreSQL real.

Execute apenas contra um banco descartavel cujo nome comece com
``trq_bec_batch_probe``. As migracoes devem ser aplicadas antes do probe.
"""

from __future__ import annotations

import base64
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from trq_bec.crypto import DevelopmentCryptoProvider, LAB_SUITE_ID, SuiteRegistry
from trq_bec.policy import Policy, PolicyEngine
from trq_bec.protocol import EnvelopeService
from trq_bec.risk import ContextRiskEngine
from trq_bec.server.access_control import default_permissions
from trq_bec.server.config import ServerSettings
from trq_bec.server.models import (
    AccessAccountRecord,
    EnrollDeviceRequest,
    IssueCouponRequest,
    MerchantStatusRequest,
    OfferBatchActionRequest,
    Principal,
    ProductBatchArchiveRequest,
    ProductCreateRequest,
)
from trq_bec.server.provider import UnavailablePQCProvider
from trq_bec.server.redis_state import MemoryDistributedState
from trq_bec.server.service import CouponSecurityService, ServiceError
from trq_bec.server.store import PostgresStore


def b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def main() -> None:
    database_url = os.environ.get("TRQ_BEC_DATABASE_URL", "")
    database_name = database_url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not database_name.startswith("trq_bec_batch_probe"):
        raise RuntimeError("PROBE_REQUIRES_A_DISPOSABLE_DATABASE")

    settings = ServerSettings(
        environment="test",
        database_url=database_url,
        issuer="trq-bec.batch-probe",
        audience="app-liberrotas",
        policy_version="batch-probe-policy-1",
        lab_suite_enabled=True,
        live_offer_max_ttl_seconds=21_600,
        database_pool_min=2,
        database_pool_max=8,
    )
    crypto = DevelopmentCryptoProvider()
    crypto.generate_signing_key(settings.issuer_key_id, "token-signing")
    crypto.generate_signing_key(settings.checkpoint_key_id, "checkpoint-signing")
    pool = ConnectionPool(
        conninfo=database_url,
        min_size=2,
        max_size=8,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    store = PostgresStore(pool, crypto)
    service = CouponSecurityService(
        settings=settings,
        store=store,
        distributed=MemoryDistributedState(),
        signing_provider=crypto,
        pqc_provider=UnavailablePQCProvider(),
        envelopes=EnvelopeService(
            crypto,
            SuiteRegistry({LAB_SUITE_ID}),
            max_ttl_seconds=settings.live_offer_max_ttl_seconds,
        ),
        risk=ContextRiskEngine({"firebase-backend"}),
        policy=PolicyEngine(
            Policy("batch-probe-policy-1", 7_000, 3_500, 7_000)
        ),
    )
    admin = Principal(
        "batch-probe-admin",
        "admin",
        "admin@probe.invalid",
        {"role": "admin", "admin": True, "auth_time": int(time.time())},
    )
    merchant = Principal(
        "batch-probe-merchant",
        "entrepreneur",
        "merchant@probe.invalid",
        {"role": "entrepreneur", "auth_time": int(time.time())},
    )

    try:
        store.set_access_account(
            AccessAccountRecord(
                firebase_uid=admin.uid,
                email=admin.email,
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
                display_name="Empreendedor Batch Probe",
                establishment_id="EST-BATCH-PROBE",
                establishment_name="Feira Batch Probe",
                status="ACTIVE",
            ),
        )
        private_key = Ed25519PrivateKey.generate()
        service.enroll_device(
            merchant,
            EnrollDeviceRequest(
                device_key_id="device:batch-probe",
                public_key_b64u=b64u(private_key.public_key().public_bytes_raw()),
                algorithm="ED25519_LAB",
                storage_profile="EXPO_SECURE_STORE_LAB",
            ),
        )

        def create_product(title: str):
            return service.create_product(
                merchant,
                ProductCreateRequest(
                    title=title,
                    description="Produto do probe PostgreSQL",
                    price_minor=5_000,
                    currency="BRL",
                    stock_quantity=10,
                ),
            )

        def issue(product_id: str):
            return service.issue_coupon(
                merchant,
                IssueCouponRequest(
                    product_id=product_id,
                    discount_type="PERCENT",
                    discount_value=20,
                    maximum_redemptions=5,
                    valid_until=datetime.now(timezone.utc) + timedelta(minutes=60),
                    purpose="LIVE_FAIR_DISCOUNT",
                    device_key_id="device:batch-probe",
                ),
            )

        archive_product = create_product("Produto para arquivar")
        archive_offer = issue(archive_product.product_id)
        archive_request = ProductBatchArchiveRequest(
            client_request_id="pg-product-archive-001",
            product_ids=[archive_product.product_id],
        )
        archived = service.archive_products_batch(merchant, archive_request)
        archived_retry = service.archive_products_batch(merchant, archive_request)
        if archived_retry.model_dump() != archived.model_dump():
            raise AssertionError("PRODUCT_ARCHIVE_RETRY_RESPONSE_CHANGED")
        if store.get_token(archive_offer.qr_payload.token_ref).status != "REVOKED":
            raise AssertionError("PRODUCT_ARCHIVE_DID_NOT_REVOKE_TOKEN")

        different_product = create_product("Produto para conflito")
        try:
            service.archive_products_batch(
                merchant,
                ProductBatchArchiveRequest(
                    client_request_id=archive_request.client_request_id,
                    product_ids=[different_product.product_id],
                ),
            )
        except ServiceError as exc:
            if exc.status_code != 409 or exc.code != "BATCH_CLIENT_REQUEST_ID_REUSED":
                raise
        else:
            raise AssertionError("PRODUCT_ARCHIVE_ID_REUSE_NOT_REJECTED")

        products = [create_product(f"Oferta concorrente {index}") for index in range(2)]
        issued = [issue(product.product_id) for product in products]
        offer_ids = [item.offer_id for item in issued]
        original_tokens = [item.qr_payload.token_ref for item in issued]
        increase_request = OfferBatchActionRequest(
            client_request_id="pg-offer-increase-001",
            action="INCREASE_DISCOUNT",
            offer_ids=offer_ids,
            discount_type="PERCENT",
            discount_delta=5,
            device_key_id="device:batch-probe",
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent = list(
                executor.map(
                    lambda _: service.batch_offer_actions(merchant, increase_request),
                    range(2),
                )
            )
        if concurrent[0].model_dump() != concurrent[1].model_dump():
            raise AssertionError("CONCURRENT_RETRY_RESPONSE_CHANGED")
        if any(item.offer.discount_value != 25 for item in concurrent[0].items):
            raise AssertionError("CONCURRENT_RETRY_APPLIED_DISCOUNT_TWICE")
        new_tokens = [item.qr_payload.token_ref for item in concurrent[0].items]
        if any(store.get_token(token).status != "REVOKED" for token in original_tokens):
            raise AssertionError("ROTATION_DID_NOT_REVOKE_OLD_TOKEN")
        if any(store.get_token(token).status != "ISSUED" for token in new_tokens):
            raise AssertionError("ROTATION_DID_NOT_PERSIST_NEW_TOKEN")

        extend_request = OfferBatchActionRequest(
            client_request_id="pg-offer-extend-001",
            action="EXTEND_VALIDITY",
            offer_ids=offer_ids,
            extension_minutes=10,
            device_key_id="device:batch-probe",
        )
        extended = service.batch_offer_actions(merchant, extend_request)
        extended_retry = service.batch_offer_actions(merchant, extend_request)
        if extended_retry.model_dump() != extended.model_dump():
            raise AssertionError("EXTEND_RETRY_RESPONSE_CHANGED")

        delete_request = OfferBatchActionRequest(
            client_request_id="pg-offer-delete-001",
            action="DELETE",
            offer_ids=offer_ids,
        )
        deleted = service.batch_offer_actions(merchant, delete_request)
        deleted_retry = service.batch_offer_actions(merchant, delete_request)
        if deleted_retry.model_dump() != deleted.model_dump():
            raise AssertionError("DELETE_RETRY_RESPONSE_CHANGED")

        with pool.connection() as conn:
            idempotency_count = int(
                conn.execute(
                    "SELECT count(*) AS total FROM marketplace_batch_idempotency"
                ).fetchone()["total"]
            )
            batch_audits = int(
                conn.execute(
                    """
                    SELECT count(*) AS total FROM audit_events
                     WHERE event_type IN (
                       'PRODUCT_BATCH_ARCHIVED',
                       'OFFER_BATCH_DISCOUNT_INCREASED',
                       'OFFER_BATCH_VALIDITY_EXTENDED',
                       'OFFER_BATCH_REVOKED'
                     )
                    """
                ).fetchone()["total"]
            )
            issued_tokens = int(
                conn.execute(
                    """
                    SELECT count(*) AS total FROM coupon_tokens
                     WHERE offer_id = ANY(%s) AND status = 'ISSUED'
                    """,
                    (offer_ids,),
                ).fetchone()["total"]
            )
        if idempotency_count != 4:
            raise AssertionError(f"IDEMPOTENCY_ROW_COUNT_MISMATCH:{idempotency_count}")
        if batch_audits != 4:
            raise AssertionError(f"BATCH_AUDIT_COUNT_MISMATCH:{batch_audits}")
        if issued_tokens != 0:
            raise AssertionError(f"DELETE_LEFT_ISSUED_TOKENS:{issued_tokens}")
        print(
            "POSTGRES_BATCH_IDEMPOTENCY_PROBE_OK "
            "operations=4 concurrent_retry=1 exact_qr_replay=1"
        )
    finally:
        pool.close()


if __name__ == "__main__":
    main()
