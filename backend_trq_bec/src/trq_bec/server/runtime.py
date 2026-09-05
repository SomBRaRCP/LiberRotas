"""Build and close concrete backend infrastructure."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..crypto import LAB_SUITE_ID, SuiteRegistry
from ..policy import Policy, PolicyEngine
from ..protocol import EnvelopeService
from ..risk import ContextRiskEngine
from .auth import FirebaseAuthenticator
from .account_security import (
    FirebaseAccountSessionRevoker,
    SmtpDeviceSecurityEmailNotifier,
)
from .config import ServerSettings
from .community import FirebaseCommunityPublisher
from .email_verification import (
    FirebasePublicIdentityProvisioner,
    SmtpEmailVerificationSender,
)
from .institution_provisioning import FirebaseInstitutionIdentityProvisioner
from .staff_provisioning import FirebaseStaffIdentityProvisioner
from .media_storage import build_storage_provider
from .provider import FileEd25519Provider, UnavailablePQCProvider
from .redis_state import RedisDistributedState
from .service import CouponSecurityService
from .store import PostgresStore


@dataclass(slots=True)
class Runtime:
    pool: ConnectionPool
    distributed: RedisDistributedState
    store: PostgresStore
    service: CouponSecurityService
    authenticator: FirebaseAuthenticator
    pqc_provider: UnavailablePQCProvider

    def close(self) -> None:
        try:
            self.distributed.client.close()
        finally:
            self.pool.close()


def build_runtime(settings: ServerSettings) -> Runtime:
    missing = [
        name
        for name, value in (
            ("issuer_private_key_path", settings.issuer_private_key_path),
            ("checkpoint_private_key_path", settings.checkpoint_private_key_path),
            ("audit_hmac_key_path", settings.audit_hmac_key_path),
        )
        if value is None
    ]
    if missing:
        raise RuntimeError(f"backend key configuration missing: {', '.join(missing)}")

    pool = ConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.database_pool_min,
        max_size=settings.database_pool_max,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    pool.open(wait=True, timeout=15)
    distributed = RedisDistributedState(settings.redis_url)
    if not distributed.ping():
        pool.close()
        raise RuntimeError("Redis health check failed")

    signing = FileEd25519Provider(
        settings.issuer_key_id,
        settings.issuer_private_key_path,
        settings.checkpoint_key_id,
        settings.checkpoint_private_key_path,
        settings.audit_hmac_key_path,
    )
    pqc = UnavailablePQCProvider(settings.pqc_provider_name, settings.pqc_provider_version)
    if settings.pqc_provider_approved:
        pool.close()
        distributed.client.close()
        raise RuntimeError("PQC provider marked approved but no audited adapter is installed")

    suites = SuiteRegistry({LAB_SUITE_ID} if settings.lab_suite_enabled else set())
    envelopes = EnvelopeService(
        signing,
        suites,
        max_ttl_seconds=max(300, settings.token_ttl_seconds, settings.live_offer_max_ttl_seconds),
    )
    policy = PolicyEngine(
        Policy(
            version=settings.policy_version,
            q_min_bps=7_000,
            low_risk_bps=3_500,
            high_risk_bps=7_000,
            profile="LAB" if settings.lab_suite_enabled else "PRODUCTION",
        )
    )
    store = PostgresStore(pool, signing)
    media_storage = build_storage_provider(settings)
    service = CouponSecurityService(
        settings=settings,
        store=store,
        distributed=distributed,
        signing_provider=signing,
        pqc_provider=pqc,
        envelopes=envelopes,
        risk=ContextRiskEngine({"firebase-backend"}),
        policy=policy,
        media_storage=media_storage,
        community_publisher=FirebaseCommunityPublisher(),
        institution_provisioner=FirebaseInstitutionIdentityProvisioner(),
        staff_provisioner=FirebaseStaffIdentityProvisioner(),
        device_security_notifier=SmtpDeviceSecurityEmailNotifier(settings),
        account_session_revoker=FirebaseAccountSessionRevoker(),
        public_identity_provisioner=FirebasePublicIdentityProvisioner(),
        email_verification_sender=SmtpEmailVerificationSender(settings),
    )
    authenticator = FirebaseAuthenticator(settings)
    return Runtime(pool, distributed, store, service, authenticator, pqc)
