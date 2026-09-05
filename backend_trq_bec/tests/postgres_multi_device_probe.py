"""Probe do fluxo de dispositivos contra PostgreSQL descartavel."""

from __future__ import annotations

import base64
import os
import time
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
    DeviceApprovalRequest,
    EnrollDeviceRequest,
    Principal,
)
from trq_bec.server.provider import UnavailablePQCProvider
from trq_bec.server.redis_state import MemoryDistributedState
from trq_bec.server.service import CouponSecurityService
from trq_bec.server.store import PostgresStore


def b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class ProbeNotifier:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def send_new_device_approval(self, uid, device, approval_token, ttl_seconds):
        self.tokens.append(approval_token)
        return "SENT"


class ProbeSessionRevoker:
    def __init__(self) -> None:
        self.uids: list[str] = []

    def revoke_all(self, uid: str) -> None:
        self.uids.append(uid)


def request(key_id: str) -> EnrollDeviceRequest:
    private = Ed25519PrivateKey.generate()
    return EnrollDeviceRequest(
        device_key_id=key_id,
        public_key_b64u=b64u(private.public_key().public_bytes_raw()),
        algorithm="ED25519_LAB",
        storage_profile="EXPO_SECURE_STORE_LAB",
        device_name=key_id,
        platform="android",
        app_version="probe-1",
    )


def main() -> None:
    database_url = os.environ.get("TRQ_BEC_DATABASE_URL", "")
    database_name = database_url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not database_name.startswith("trq_bec_devices_probe"):
        raise RuntimeError("PROBE_REQUIRES_A_DISPOSABLE_DATABASE")

    settings = ServerSettings(
        environment="test",
        database_url=database_url,
        policy_version="device-probe-policy",
        device_max_pending_per_account=1,
    )
    crypto = DevelopmentCryptoProvider()
    crypto.generate_signing_key(settings.issuer_key_id, "token-signing")
    crypto.generate_signing_key(settings.checkpoint_key_id, "checkpoint-signing")
    pool = ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=4,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    store = PostgresStore(pool, crypto)
    notifier = ProbeNotifier()
    revoker = ProbeSessionRevoker()
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
        policy=PolicyEngine(Policy("device-probe-policy", 7_000, 3_500, 7_000)),
        device_security_notifier=notifier,
        account_session_revoker=revoker,
    )
    principal = Principal(
        "device-probe-user",
        "institution",
        "device-probe@example.invalid",
        {"role": "institution", "auth_time": int(time.time())},
    )
    store.set_access_account(
        AccessAccountRecord(
            firebase_uid=principal.uid,
            email=principal.email,
            role="institution",
            status="ACTIVE",
            allow_entrepreneur_fallback=False,
            permissions=default_permissions("institution"),
        )
    )

    try:
        first = service.enroll_device(principal, request("device:pg-probe-first"))
        if first.device_status != "PENDING_APPROVAL":
            raise AssertionError("FIRST_INSTITUTION_DEVICE_NOT_PENDING")
        with pool.connection() as conn, conn.transaction():
            conn.execute(
                """
                UPDATE device_keys
                   SET approval_expires_at = %s
                 WHERE device_key_id = 'device:pg-probe-first'
                """,
                (datetime.now(timezone.utc) - timedelta(seconds=1),),
            )
        service.list_account_devices(principal)
        second = service.enroll_device(principal, request("device:pg-probe-expired"))
        if second.device_status != "PENDING_APPROVAL":
            raise AssertionError("SECOND_DEVICE_NOT_PENDING")

        with pool.connection() as conn, conn.transaction():
            conn.execute(
                """
                UPDATE device_keys
                   SET approval_expires_at = %s
                 WHERE device_key_id = 'device:pg-probe-expired'
                """,
                (datetime.now(timezone.utc) - timedelta(seconds=1),),
            )

        replacement = service.enroll_device(
            principal, request("device:pg-probe-replacement")
        )
        if replacement.device_status != "PENDING_APPROVAL":
            raise AssertionError("HISTORY_DID_NOT_REQUIRE_APPROVAL")
        with pool.connection() as conn:
            expired = conn.execute(
                """
                SELECT status, approval_token_hash, approval_expires_at
                  FROM device_keys
                 WHERE device_key_id = 'device:pg-probe-expired'
                """
            ).fetchone()
        if tuple(expired.values()) != ("ACTIVE", None, None):
            raise AssertionError(f"COOLDOWN_DEVICE_NOT_ACTIVATED:{expired}")

        service.approve_account_device(
            principal,
            DeviceApprovalRequest(approval_token=notifier.tokens[-1]),
        )
        revoked = service.revoke_all_account_devices(principal)
        if revoked.revoked_devices != 3 or revoker.uids != [principal.uid]:
            raise AssertionError("REVOKE_ALL_MISMATCH")

        after_history = service.enroll_device(
            principal, request("device:pg-probe-after-revoke")
        )
        if after_history.device_status != "PENDING_APPROVAL":
            raise AssertionError("POST_REVOKE_DEVICE_WAS_IMPLICITLY_ACTIVE")

        with pool.connection() as conn:
            forbidden_index = conn.execute(
                """
                SELECT 1 FROM pg_indexes
                 WHERE tablename = 'device_keys'
                   AND indexname = 'uq_device_keys_one_active_per_uid'
                """
            ).fetchone()
        if forbidden_index is not None:
            raise AssertionError("LEGACY_SINGLE_DEVICE_INDEX_PRESENT")
        print(
            "POSTGRES_MULTI_DEVICE_PROBE_OK "
            "institution_first=PENDING cooldown=ACTIVE additional=PENDING "
            "post_revoke=PENDING"
        )
    finally:
        pool.close()


if __name__ == "__main__":
    main()
