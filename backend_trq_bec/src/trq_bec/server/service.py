"""Authoritative coupon issuance and redemption service."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..canonical import domain_message, sha3_hex
from ..contracts import CryptoEnvelope, Decision, Intent, Observation, ReplayStatus
from ..crypto.registry import LAB_SUITE_ID
from ..errors import ContractError, CryptoError, LedgerError
from ..policy import PolicyEngine
from ..protocol.envelope import EnvelopeService, device_proof_message
from ..risk import ContextRiskEngine
from .access_control import (
    ACCESS_ROLES,
    PANEL_BY_ROLE,
    PANEL_PERMISSION_BY_ROLE,
    default_permissions,
)
from .account_security import AccountSessionRevoker, DeviceSecurityEmailNotifier
from .community import (
    CommunityDocumentConflict,
    CommunityDocumentForbidden,
    CommunityDocumentNotFound,
    CommunityPublishError,
    CommunityPublisher,
)
from .config import ServerSettings
from .directory import is_reserved_display_name, normalize_display_name
from .email_verification import (
    EmailVerificationSender,
    PublicIdentityProvisioner,
    PublicIdentityProvisioningError,
)
from .institution_provisioning import (
    InstitutionEmailExists,
    InstitutionIdentityProvisioner,
    InstitutionProvisioningError,
    InstitutionProvisioningRollbackError,
)
from .staff_provisioning import (
    StaffEmailExists,
    StaffIdentityProvisioner,
    StaffProvisioningError,
    StaffProvisioningRollbackError,
)
from .models import (
    AccessAccountRecord,
    AccessAccountStatusRequest,
    AccountDeviceListResponse,
    AccountDeviceResponse,
    AccessAccountSummaryRecord,
    AccessAccountSummaryResponse,
    AccessAuditEventRecord,
    AccessAuditEventResponse,
    AccessSessionResponse,
    AdminAccountListResponse,
    AdminOperationsSummaryResponse,
    AuthorizationResponse,
    BeginRedemptionRequest,
    BeginRedemptionResponse,
    CatalogFeedResponse,
    CatalogMerchantProfileResponse,
    CatalogMerchantRecord,
    CatalogMerchantSummary,
    CatalogOfferRecord,
    CatalogOfferSummary,
    CatalogProductItem,
    CatalogProductRecord,
    ChallengeResponse,
    CommunityDocumentResponse,
    CommunityContentMutationResponse,
    CommunityCommentDeleteResponse,
    CommunityCommentCreateRequest,
    CommunityCommentListResponse,
    CommunityCommentLikeResponse,
    CommunityCommentRecord,
    CommunityCommentResponse,
    CommunityCommentUpdateRequest,
    CommunityPostCreateRequest,
    CommunityPostUpdateRequest,
    CompactQrPayload,
    CuratedPlaceCreateRequest,
    DeviceRecord,
    DeviceApprovalRequest,
    DeviceApprovalResponse,
    DeviceApprovalResendRequest,
    DeviceApprovalResendResponse,
    EmailVerificationQueueResponse,
    EnrollDeviceRequest,
    EnrollDeviceResponse,
    HealthResponse,
    InstitutionCreateRequest,
    InstitutionApplicationListResponse,
    InstitutionApplicationRecord,
    InstitutionApplicationResponse,
    InstitutionApplicationStatusUpdateRequest,
    EntrepreneurFundedEventListResponse,
    EntrepreneurFundedEventReportResponse,
    EntrepreneurFundedEventResponse,
    InstitutionEventProductAllocationUpdateRequest,
    InstitutionEventSellerAllocationUpdateRequest,
    InstitutionFundedEventCreateRequest,
    InstitutionFundedEventListResponse,
    InstitutionFundedEventProductAllocationResponse,
    InstitutionFundedEventProductReportResponse,
    InstitutionFundedEventRecord,
    InstitutionFundedEventReportResponse,
    InstitutionFundedEventResponse,
    InstitutionFundedEventSellerAllocationResponse,
    InstitutionFundedEventSellerReportResponse,
    InstitutionGroupCreateRequest,
    InstitutionGroupListResponse,
    InstitutionGroupRecord,
    InstitutionGroupResponse,
    InstitutionMembershipListResponse,
    InstitutionMembershipRecord,
    InstitutionMembershipResponse,
    InstitutionListResponse,
    InstitutionProfileRecord,
    InstitutionProfileUpdateRequest,
    InstitutionReportSummaryResponse,
    InstitutionSalesCurrencyTotalResponse,
    InstitutionSalesReportResponse,
    InstitutionSellerInvitationCreateRequest,
    InstitutionSellerSalesResponse,
    InstitutionResponse,
    IssueCouponRequest,
    IssueCouponResponse,
    LiveFairCreateRequest,
    MediaAssetListResponse,
    MediaAssetRecord,
    MediaAssetResponse,
    MediaVariantRecord,
    MediaCleanupResponse,
    MediaStorageHealth,
    MediaUploadAuthorizationResponse,
    MediaUploadCreateRequest,
    MerchantRecord,
    MerchantResponse,
    MerchantStatusRequest,
    OfferListResponse,
    OfferPreviewResponse,
    OfferQrResponse,
    OfferRecord,
    OfferStatusRequest,
    OfferBatchActionRequest,
    OfferBatchActionResponse,
    OfferBatchActionItemResponse,
    OfferBatchMutationRecord,
    OperationRecord,
    Principal,
    PreviewCouponRequest,
    ProductCreateRequest,
    ProductListResponse,
    ProductRecord,
    PrivilegedAccountValidationRecord,
    ProductResponse,
    ProductStockRequest,
    ProductBatchActivateRequest,
    ProductBatchActivateResponse,
    ProductBatchArchiveRequest,
    ProductBatchArchiveResponse,
    PublicProfileUpsertRequest,
    PublicRegistrationRequest,
    PublicInstitutionApplicationCreateRequest,
    PublicInstitutionApplicationCreatedResponse,
    PublicProfileResponse,
    PublicProfileRecord,
    RevokeAllDevicesResponse,
    GlobalSearchResponse,
    GlobalSearchItemResponse,
    MessageIdentityResponse,
    DirectMessageCreateRequest,
    ConversationMessageCreateRequest,
    SupportRequestCreateRequest,
    PrivateMessageResponse,
    PrivateMessageRecord,
    ConversationResponse,
    ConversationRecord,
    ConversationListResponse,
    ConversationDetailResponse,
    ConversationReadResponse,
    MessageBlockResponse,
    MessageBlockListResponse,
    SecurityAccountListResponse,
    SecurityMonitoringSummaryResponse,
    StaffAccountCreateRequest,
    StaffAccountValidationRequest,
    ServerTimeResponse,
    SupportAccountListResponse,
    SupportAccountSummaryResponse,
    TokenRecord,
    TrqBecSecurityStatusResponse,
    AuthorizeRedemptionRequest,
)
from .provider import PostQuantumProvider, verify_device_signature
from .public_media import (
    DurableStorePublicMediaRepository,
    PublicMediaError,
    PublicMediaReadService,
)
from .redis_state import DistributedState
try:
    from .media_processing import MediaProcessingError, process_image
except ModuleNotFoundError as exc:
    if exc.name != "PIL":
        raise
    class MediaProcessingError(RuntimeError):  # type: ignore[no-redef]
        def __init__(self, code: str) -> None:
            super().__init__(code)
            self.code = code

    process_image = None  # type: ignore[assignment]
from .media_storage import (
    DisabledStorageProvider,
    MediaObjectNotFound,
    MediaStorageError,
    StorageProvider,
)
from .store import DurableStore, StoreConflict, StoreNotFound


_MEDIA_ROLE_ENTITY = {
    "avatar": "user",
    "entrepreneur_logo": "entrepreneur",
    "institution_logo": "institution",
    "product_image": "product",
    "post_image": "post",
    "fair_cover": "fair",
    "support_attachment": "support",
}
_IMAGE_EXTENSION_CONTENT_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_DANGEROUS_INTERMEDIATE_EXTENSIONS = {
    "bat",
    "cmd",
    "com",
    "exe",
    "htm",
    "html",
    "jar",
    "jpeg",
    "jpg",
    "js",
    "msi",
    "mjs",
    "pdf",
    "php",
    "png",
    "ps1",
    "py",
    "scr",
    "sh",
    "svg",
    "vbs",
    "webp",
    "zip",
}
_PUBLIC_MEDIA_ROLES = {
    "avatar",
    "entrepreneur_logo",
    "institution_logo",
    "product_image",
    "post_image",
    "fair_cover",
}


class ServiceError(RuntimeError):
    def __init__(self, code: str, status_code: int, message: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.message = message or code


class CouponSecurityService:
    def __init__(
        self,
        *,
        settings: ServerSettings,
        store: DurableStore,
        distributed: DistributedState,
        signing_provider,
        pqc_provider: PostQuantumProvider,
        envelopes: EnvelopeService,
        risk: ContextRiskEngine,
        policy: PolicyEngine,
        media_storage: StorageProvider | None = None,
        community_publisher: CommunityPublisher | None = None,
        institution_provisioner: InstitutionIdentityProvisioner | None = None,
        staff_provisioner: StaffIdentityProvisioner | None = None,
        device_security_notifier: DeviceSecurityEmailNotifier | None = None,
        account_session_revoker: AccountSessionRevoker | None = None,
        public_identity_provisioner: PublicIdentityProvisioner | None = None,
        email_verification_sender: EmailVerificationSender | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.distributed = distributed
        self.signing_provider = signing_provider
        self.pqc_provider = pqc_provider
        self.envelopes = envelopes
        self.risk = risk
        self.policy = policy
        self.media_storage = media_storage or DisabledStorageProvider()
        self.public_media = PublicMediaReadService(
            DurableStorePublicMediaRepository(store),
            self.media_storage,
            settings.gcs_download_url_expiration_seconds,
        )
        self.community_publisher = community_publisher
        self.institution_provisioner = institution_provisioner
        self.staff_provisioner = staff_provisioner
        self.device_security_notifier = device_security_notifier
        self.account_session_revoker = account_session_revoker
        self.public_identity_provisioner = public_identity_provisioner
        self.email_verification_sender = email_verification_sender

    def health(self) -> HealthResponse:
        database_ok = redis_ok = False
        try:
            database_ok = self.store.ping()
        except Exception:
            pass
        try:
            redis_ok = self.distributed.ping()
        except Exception:
            pass
        pq = self.pqc_provider.status()
        return HealthResponse(
            status="ok" if database_ok and redis_ok else "degraded",
            database=database_ok,
            redis=redis_ok,
            crypto_provider=f"{pq.name}:{pq.version}" if pq.ready else "LAB_ED25519_PQ_BLOCKED",
            pqc_ready=pq.ready,
            media_storage=MediaStorageHealth(
                provider="gcs",
                enabled=self.media_storage.enabled,
                configured=self.media_storage.configured,
                status=(
                    "ok"
                    if self.media_storage.enabled and self.media_storage.configured
                    else "disabled"
                ),
            ),
        )

    @staticmethod
    def server_time() -> ServerTimeResponse:
        server_time_ms = time.time_ns() // 1_000_000
        return ServerTimeResponse(
            server_time_ms=server_time_ms,
            server_time_iso=datetime.fromtimestamp(
                server_time_ms / 1000,
                tz=timezone.utc,
            ),
            timezone="UTC",
        )

    def register_public_account(
        self,
        principal: Principal,
        request: PublicRegistrationRequest,
    ) -> EmailVerificationQueueResponse:
        """Provisiona somente a própria conta pública, nunca funções privilegiadas."""

        if not principal.email:
            raise ServiceError("PUBLIC_IDENTITY_EMAIL_REQUIRED", 409)
        existing = self.store.get_access_account(principal.uid)
        if existing is not None:
            if existing.role != request.role:
                raise ServiceError("PUBLIC_ROLE_CONFLICT", 409)
            if existing.status == "SUSPENDED":
                raise ServiceError("ACCOUNT_SUSPENDED", 403)
            if existing.status == "DISABLED":
                raise ServiceError("ACCOUNT_DISABLED", 403)
        if self.public_identity_provisioner is None:
            raise ServiceError("PUBLIC_IDENTITY_PROVISIONER_UNAVAILABLE", 503)

        try:
            identity = self.public_identity_provisioner.provision(
                principal.uid,
                request.role,
            )
        except PublicIdentityProvisioningError as exc:
            code = str(exc)
            status_code = 409 if code in {
                "PUBLIC_ROLE_CONFLICT",
                "PUBLIC_ROLE_PROTECTED",
            } else 503
            if code in {
                "PUBLIC_IDENTITY_DISABLED",
                "PUBLIC_IDENTITY_EMAIL_REQUIRED",
                "PUBLIC_IDENTITY_NOT_FOUND",
            }:
                status_code = 403
            raise ServiceError(code, status_code) from exc

        if identity.email.casefold() != principal.email.casefold():
            raise ServiceError("PUBLIC_IDENTITY_EMAIL_MISMATCH", 409)

        self.store.set_access_account(
            AccessAccountRecord(
                firebase_uid=principal.uid,
                email=identity.email,
                role=request.role,
                status="ACTIVE",
                allow_entrepreneur_fallback=False,
                permissions=default_permissions(request.role),
            )
        )
        if request.role == "entrepreneur":
            establishment_name = request.establishment_name or request.display_name
            try:
                self.store.set_merchant_status(
                    MerchantRecord(
                        firebase_uid=principal.uid,
                        display_name=request.display_name,
                        establishment_id=(
                            "EST-"
                            + hashlib.sha256(principal.uid.encode("utf-8"))
                            .hexdigest()[:16]
                            .upper()
                        ),
                        establishment_name=establishment_name,
                        status="ACTIVE",
                    ),
                    operation_id=f"public-registration:{uuid.uuid4()}",
                    suite_id=LAB_SUITE_ID,
                    key_ref_token=self._issuer_key_ref(),
                    event_type="PUBLIC_ENTREPRENEUR_REGISTERED",
                    result="ACTIVE",
                    reason_codes=("EMAIL_VERIFICATION_REQUIRED",)
                    if not identity.email_verified
                    else (),
                    evidence_refs=(),
                    details={
                        "account_ref": self._actor_ref(principal.uid),
                    },
                )
            except StoreConflict as exc:
                raise ServiceError(str(exc), 409) from exc

        if request.role == "visitor":
            return EmailVerificationQueueResponse(
                status="NOT_REQUIRED",
                role="visitor",
            )
        if identity.email_verified:
            return EmailVerificationQueueResponse(
                status="ALREADY_VERIFIED",
                role=request.role,
            )
        self.store.enqueue_email_verification(
            principal.uid,
            identity.email,
            datetime.now(timezone.utc),
        )
        return EmailVerificationQueueResponse(status="QUEUED", role=request.role)

    def resend_public_email_verification(
        self,
        principal: Principal,
    ) -> EmailVerificationQueueResponse:
        account = self.store.get_access_account(principal.uid)
        if account is None or account.role not in {"entrepreneur", "visitor"}:
            raise ServiceError("PUBLIC_ACCOUNT_NOT_PROVISIONED", 409)
        if account.status != "ACTIVE":
            raise ServiceError("ACCOUNT_NOT_ACTIVE", 403)
        if account.role == "visitor":
            return EmailVerificationQueueResponse(
                status="NOT_REQUIRED",
                role="visitor",
            )
        if principal.claims.get("email_verified") is True:
            return EmailVerificationQueueResponse(
                status="ALREADY_VERIFIED",
                role=account.role,
            )
        email = account.email or principal.email
        if not email:
            raise ServiceError("PUBLIC_IDENTITY_EMAIL_REQUIRED", 409)
        self.store.enqueue_email_verification(
            principal.uid,
            email,
            datetime.now(timezone.utc),
        )
        return EmailVerificationQueueResponse(status="QUEUED", role=account.role)

    def process_email_verification_queue(self, limit: int = 10) -> int:
        """Processa lotes pequenos; falhas permanecem rastreáveis sem expor o link."""

        if self.email_verification_sender is None:
            return 0
        now = datetime.now(timezone.utc)
        queued = self.store.claim_due_email_verifications(
            now,
            max(1, min(limit, 50)),
            timedelta(minutes=5),
        )
        for item in queued:
            result = self.email_verification_sender.send(
                item.firebase_uid,
                item.email,
            )
            finished_at = datetime.now(timezone.utc)
            if result in {"SENT", "ALREADY_VERIFIED"}:
                status = "SENT"
                next_attempt_at = finished_at
            elif result in {"NOT_CONFIGURED", "SMTP_IP_UNAUTHORIZED"}:
                status = "PENDING"
                next_attempt_at = finished_at + timedelta(minutes=15)
            elif item.attempt_count >= 5:
                status = "FAILED"
                next_attempt_at = finished_at
            else:
                status = "PENDING"
                retry_minutes = min(30, 2 ** max(0, item.attempt_count - 1))
                next_attempt_at = finished_at + timedelta(minutes=retry_minutes)
            self.store.finish_email_verification(
                item.queue_id,
                status,
                result,
                finished_at,
                next_attempt_at,
            )
        return len(queued)

    @staticmethod
    def _pending_access(state: str, reason: str) -> AccessSessionResponse:
        return AccessSessionResponse(
            access_state=state,
            role=None,
            panel="access_pending",
            permissions=[],
            reason=reason,
        )

    def resolve_access(self, principal: Principal) -> AccessSessionResponse:
        """Combina token verificado, Custom Claims e autorização persistida."""

        account = self.store.get_access_account(principal.uid)
        if account is None:
            return self._pending_access("PENDING", "ACCESS_NOT_PROVISIONED")

        claim_role = principal.role if principal.role in ACCESS_ROLES else None
        if principal.role is not None and claim_role is None:
            return self._pending_access("PENDING", "CUSTOM_CLAIM_UNRECOGNIZED")
        fallback_allowed = (
            principal.role is None
            and account.allow_entrepreneur_fallback
            and account.role == "entrepreneur"
        )
        effective_role = "entrepreneur" if fallback_allowed else claim_role

        if effective_role is None:
            return self._pending_access("PENDING", "CUSTOM_CLAIM_REQUIRED")
        if effective_role != account.role:
            return self._pending_access("DENIED", "ROLE_CLAIM_MISMATCH")
        if account.status == "SUSPENDED":
            return self._pending_access("SUSPENDED", "ACCOUNT_SUSPENDED")
        if account.status == "DISABLED":
            return self._pending_access("DENIED", "ACCOUNT_DISABLED")
        if effective_role in {"admin", "support", "security"}:
            validation = self.store.get_privileged_account_validation(
                principal.uid
            )
            if validation is None:
                return self._pending_access(
                    "PENDING",
                    "STAFF_AUTHORITY_VALIDATION_REQUIRED",
                )
            if validation.requested_role != effective_role:
                return self._pending_access(
                    "DENIED",
                    "STAFF_AUTHORITY_ROLE_MISMATCH",
                )
            if validation.validation_state == "PENDING":
                return self._pending_access(
                    "PENDING",
                    "STAFF_AUTHORITY_VALIDATION_REQUIRED",
                )
            if validation.validation_state != "APPROVED":
                return self._pending_access(
                    "DENIED",
                    "STAFF_AUTHORITY_REVOKED",
                )
            if (
                validation.account_origin == "ADMIN_INVITATION"
                and principal.claims.get("staff_validated") is not True
            ):
                return self._pending_access(
                    "PENDING",
                    "STAFF_VALIDATED_CLAIM_REQUIRED",
                )
        if (
            effective_role == "entrepreneur"
            and principal.claims.get("email_verified") is False
        ):
            return self._pending_access("PENDING", "EMAIL_VERIFICATION_REQUIRED")
        if account.status == "PENDING":
            return self._pending_access("PENDING", "ACCOUNT_ACCESS_PENDING")
        if account.status != "ACTIVE":
            return self._pending_access("DENIED", "ACCOUNT_DISABLED")
        if effective_role == "admin" and not principal.is_admin:
            return self._pending_access("DENIED", "ADMIN_CLAIM_REQUIRED")

        permissions = tuple(sorted(set(account.permissions)))
        panel_permission = PANEL_PERMISSION_BY_ROLE[effective_role]
        if panel_permission not in permissions:
            return self._pending_access("DENIED", "PANEL_PERMISSION_REQUIRED")
        if effective_role == "entrepreneur" and self.store.get_active_merchant(principal.uid) is None:
            return self._pending_access("PENDING", "MERCHANT_ACCOUNT_INACTIVE")

        return AccessSessionResponse(
            access_state="AUTHORIZED",
            role=effective_role,
            panel=PANEL_BY_ROLE[effective_role],
            permissions=list(permissions),
            reason="ACCESS_GRANTED",
        )

    def _require_authorized_access(self, principal: Principal) -> AccessSessionResponse:
        access = self.resolve_access(principal)
        if access.access_state != "AUTHORIZED":
            raise ServiceError(access.reason, 403)
        return access

    def _require_permission(self, principal: Principal, permission: str) -> AccessSessionResponse:
        access = self._require_authorized_access(principal)
        if permission not in access.permissions:
            raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
        return access

    def _require_entrepreneur_permission(
        self,
        principal: Principal,
        permission: str,
    ) -> AccessSessionResponse:
        access = self._require_authorized_access(principal)
        if access.role != "entrepreneur":
            raise ServiceError("ENTREPRENEUR_ACCESS_REQUIRED", 403)
        if permission not in access.permissions:
            raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
        return access

    def _require_live_fair_manager_permission(
        self,
        principal: Principal,
    ) -> AccessSessionResponse:
        access = self._require_authorized_access(principal)
        if access.role not in {"entrepreneur", "institution"}:
            raise ServiceError("LIVE_FAIR_MANAGER_ACCESS_REQUIRED", 403)
        if "locations.publish" not in access.permissions:
            raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
        return access

    def _community_publisher(self) -> CommunityPublisher:
        if self.community_publisher is None:
            raise ServiceError("COMMUNITY_PUBLISHER_UNAVAILABLE", 503)
        return self.community_publisher

    def _require_public_member_permission(
        self, principal: Principal, permission: str
    ) -> AccessSessionResponse:
        access = self._require_permission(principal, permission)
        if access.role not in {"visitor", "entrepreneur", "institution"}:
            raise ServiceError("PUBLIC_MEMBER_ACCESS_REQUIRED", 403)
        return access

    def _rate_limit(self, principal: Principal, action: str) -> None:
        try:
            limited = self.distributed.rate_is_high(
                f"{action}:{self._actor_ref(principal.uid)}",
                self.settings.rate_window_seconds,
                self.settings.rate_high_threshold,
            )
        except Exception as exc:
            raise ServiceError("RATE_STORE_UNAVAILABLE", 503) from exc
        if limited:
            raise ServiceError("RATE_LIMIT_EXCEEDED", 429)

    def _rate_limit_public(self, subject_ref: str, action: str) -> None:
        """Limita formulários anônimos sem persistir IP ou e-mail em texto claro no Redis."""

        try:
            limited = self.distributed.rate_is_high(
                f"{action}:{subject_ref}",
                self.settings.rate_window_seconds,
                max(3, min(5, self.settings.rate_high_threshold)),
            )
        except Exception as exc:
            raise ServiceError("RATE_STORE_UNAVAILABLE", 503) from exc
        if limited:
            raise ServiceError("RATE_LIMIT_EXCEEDED", 429)

    @staticmethod
    def _public_profile_response(profile: PublicProfileRecord) -> PublicProfileResponse:
        return PublicProfileResponse(
            uid=profile.firebase_uid,
            display_name=profile.display_name,
            role=profile.role,
            city=profile.city,
            address=profile.address,
            category=profile.category,
            interests=list(profile.interests),
            avatar_uri=profile.avatar_uri,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def _public_media_uri(self, media_id: str) -> str:
        return (
            f"{self.settings.public_api_url.rstrip('/')}/v1/public/media/"
            f"{media_id}"
        )

    def _media_id_from_public_uri(self, uri: str | None) -> str | None:
        if not uri:
            return None
        prefix = f"{self.settings.public_api_url.rstrip('/')}/v1/public/media/"
        if not uri.startswith(prefix):
            return None
        candidate = uri[len(prefix):]
        try:
            parsed = uuid.UUID(candidate)
        except (ValueError, AttributeError):
            return None
        return str(parsed) if str(parsed) == candidate.lower() else None

    def _validated_avatar_uri(
        self,
        principal: Principal,
        requested_uri: str | None,
        current_profile: PublicProfileRecord | None,
    ) -> str | None:
        if requested_uri is None:
            return None
        current_uri = current_profile.avatar_uri if current_profile else None
        stable_profile_uri = (
            f"{self.settings.public_api_url.rstrip('/')}/v1/public/profile/"
            f"{principal.uid}/avatar"
        )
        if requested_uri == stable_profile_uri:
            requested_uri = current_uri
        media_id = self._media_id_from_public_uri(requested_uri)
        if media_id is None:
            # Perfis antigos podem conservar a URL ja cadastrada ate o usuario
            # escolher uma nova imagem. Novas URLs externas sao recusadas.
            if current_uri and requested_uri == current_uri:
                return current_uri
            raise ServiceError("AVATAR_MEDIA_REFERENCE_REQUIRED", 422)
        record = self.store.get_media_asset(media_id)
        if record is None or record.status != "ready":
            raise ServiceError("AVATAR_MEDIA_NOT_READY", 409)
        if record.owner_user_id != principal.uid:
            raise ServiceError("AVATAR_MEDIA_NOT_OWNED", 403)
        if (
            record.entity_type != "user"
            or record.entity_id != principal.uid
            or record.media_role != "avatar"
            or record.visibility != "public_processed"
            or record.moderation_status != "approved"
        ):
            raise ServiceError("AVATAR_MEDIA_REFERENCE_INVALID", 422)
        return self._public_media_uri(media_id)

    def upsert_public_profile(
        self,
        principal: Principal,
        request: PublicProfileUpsertRequest,
        *,
        request_id: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> PublicProfileResponse:
        access = self._require_authorized_access(principal)
        permission = (
            "institution.profile.manage" if access.role == "institution" else "profile.manage"
        )
        if access.role not in {"visitor", "entrepreneur", "institution"}:
            raise ServiceError("PUBLIC_PROFILE_ROLE_REQUIRED", 403)
        if permission not in access.permissions:
            raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
        self._rate_limit(principal, "profile")
        normalized_name = normalize_display_name(request.display_name)
        if len(normalized_name) < 3:
            raise ServiceError("DISPLAY_NAME_INVALID", 422)
        if is_reserved_display_name(normalized_name):
            raise ServiceError("DISPLAY_NAME_RESERVED", 409)
        current_profile = self.store.get_public_profile(principal.uid)
        avatar_uri = self._validated_avatar_uri(
            principal, request.avatar_uri, current_profile
        )
        now = datetime.now(timezone.utc)
        profile = PublicProfileRecord(
            firebase_uid=principal.uid,
            display_name=request.display_name,
            normalized_name=normalized_name,
            role=access.role,
            city=request.city,
            address=request.address,
            category=request.category,
            interests=tuple(request.interests),
            avatar_uri=avatar_uri,
            created_at=now,
            updated_at=now,
        )
        try:
            stored = self.store.upsert_public_profile(profile)
        except StoreConflict as exc:
            code = str(exc)
            status = 409 if code == "DISPLAY_NAME_ALREADY_IN_USE" else 403
            raise ServiceError(code, status) from exc
        except Exception as exc:
            raise ServiceError("PUBLIC_PROFILE_STORE_UNAVAILABLE", 503) from exc
        try:
            self._community_publisher().upsert_public_profile(stored)
        except CommunityPublishError as exc:
            raise ServiceError("PUBLIC_PROFILE_FIRESTORE_SYNC_FAILED", 503) from exc

        previous_media_id = self._media_id_from_public_uri(
            current_profile.avatar_uri if current_profile else None
        )
        current_media_id = self._media_id_from_public_uri(stored.avatar_uri)
        if previous_media_id and previous_media_id != current_media_id:
            try:
                self.delete_media_asset(
                    principal,
                    previous_media_id,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            except ServiceError:
                # Nao bloqueia o perfil ja salvo. O proximo upload ou a rotina
                # administrativa removera o objeto substituido com seguranca.
                try:
                    self.store.mark_media_status(
                        previous_media_id,
                        principal.uid,
                        "orphaned",
                        "AVATAR_REPLACED_CLEANUP_PENDING",
                        datetime.now(timezone.utc),
                    )
                except Exception:
                    pass
        return self._public_profile_response(stored)

    def get_public_profile(
        self, principal: Principal, uid: str
    ) -> PublicProfileResponse:
        self._require_permission(principal, "directory.search")
        profile = self.store.get_public_profile(uid)
        if profile is None:
            raise ServiceError("PUBLIC_PROFILE_NOT_FOUND", 404)
        return self._public_profile_response(profile)

    def search(
        self,
        principal: Principal,
        query: str,
        types: tuple[str, ...],
        limit: int,
    ) -> GlobalSearchResponse:
        self._require_permission(principal, "directory.search")
        self._rate_limit(principal, "search")
        normalized_query = normalize_display_name(query)
        if len(normalized_query) < 2:
            raise ServiceError("SEARCH_QUERY_INVALID", 422)
        allowed_types = {"PROFILE", "PRODUCT", "OFFER", "POST"}
        normalized_types = tuple(dict.fromkeys(item.upper() for item in types))
        if not normalized_types or any(item not in allowed_types for item in normalized_types):
            raise ServiceError("SEARCH_TYPE_INVALID", 422)
        try:
            records = self.store.search_directory(normalized_query, normalized_types, limit)
        except Exception as exc:
            raise ServiceError("SEARCH_UNAVAILABLE", 503) from exc
        return GlobalSearchResponse(
            query=query,
            items=[
                GlobalSearchItemResponse(
                    type=record.type,
                    id=record.item_id,
                    title=record.title,
                    subtitle=record.subtitle,
                    owner_uid=record.owner_uid,
                    route=record.route,
                    status=record.status,
                    created_at=record.created_at,
                )
                for record in records
            ],
        )

    @staticmethod
    def _support_identity() -> MessageIdentityResponse:
        return MessageIdentityResponse(
            uid="support",
            display_name="Suporte LiberRotas",
            role="support",
            avatar_uri=None,
        )

    def _public_message_identity(self, uid: str) -> MessageIdentityResponse:
        profile = self.store.get_public_profile(uid)
        if profile is None:
            return MessageIdentityResponse(
                uid=uid,
                display_name="Perfil indisponível",
                role="unavailable",
                avatar_uri=None,
            )
        return MessageIdentityResponse(
            uid=profile.firebase_uid,
            display_name=profile.display_name,
            role=profile.role,
            avatar_uri=profile.avatar_uri,
        )

    def _conversation_response(
        self,
        principal: Principal,
        conversation: ConversationRecord,
        *,
        support_actor: bool,
    ) -> ConversationResponse:
        if conversation.kind == "SUPPORT":
            counterpart = (
                self._public_message_identity(conversation.requester_uid or "unavailable")
                if support_actor
                else self._support_identity()
            )
            blocked_by_me = False
            blocked_me = False
        else:
            other_uid = next(
                (uid for uid in conversation.participant_uids if uid != principal.uid),
                principal.uid,
            )
            counterpart = self._public_message_identity(other_uid)
            blocked_by_me, blocked_me = self.store.get_message_block_state(
                principal.uid, other_uid
            )
        return ConversationResponse(
            conversation_id=conversation.conversation_id,
            kind=conversation.kind,
            status=conversation.status,
            subject=conversation.subject,
            counterpart=counterpart,
            last_message=conversation.last_message,
            last_message_at=conversation.last_message_at,
            unread_count=conversation.unread_count,
            blocked_by_me=blocked_by_me,
            blocked_me=blocked_me,
            can_message=(
                conversation.status not in {"RESOLVED", "CLOSED"}
                and not blocked_by_me
                and not blocked_me
                and counterpart.role != "unavailable"
            ),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    def _private_message_response(
        self,
        principal: Principal,
        conversation: ConversationRecord,
        message: PrivateMessageRecord,
    ) -> PrivateMessageResponse:
        is_support_sender = (
            conversation.kind == "SUPPORT"
            and message.sender_uid not in conversation.participant_uids
        )
        sender = (
            self._support_identity()
            if is_support_sender
            else self._public_message_identity(message.sender_uid)
        )
        return PrivateMessageResponse(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            sender=sender,
            content=message.body,
            media_id=message.media_id,
            mine=message.sender_uid == principal.uid,
            created_at=message.created_at,
        )

    def _message_record(
        self,
        principal: Principal,
        conversation_id: str,
        content: str,
        client_message_id: str | None,
        media_id: str | None = None,
    ) -> PrivateMessageRecord:
        return PrivateMessageRecord(
            message_id=f"MSG-{uuid.uuid4().hex.upper()}",
            conversation_id=conversation_id,
            sender_uid=principal.uid,
            client_message_id=client_message_id or f"CLIENT-{uuid.uuid4().hex}",
            body=content,
            media_id=media_id,
            created_at=datetime.now(timezone.utc),
        )

    def _validate_private_message_media(
        self,
        principal: Principal,
        conversation_id: str,
        media_id: str,
    ) -> None:
        record = self.store.get_media_asset(media_id)
        if (
            record is None
            or record.status != "ready"
            or record.owner_user_id != principal.uid
            or record.entity_type != "support"
            or record.entity_id != conversation_id
            or record.media_role != "support_attachment"
            or record.detected_content_type
            not in self.settings.gcs_allowed_image_type_list
        ):
            raise ServiceError("MESSAGE_MEDIA_FORBIDDEN", 403)

    def _conversation_detail(
        self,
        principal: Principal,
        conversation: ConversationRecord,
        *,
        support_actor: bool,
        limit: int = 200,
    ) -> ConversationDetailResponse:
        try:
            messages = self.store.list_private_messages(
                principal.uid,
                conversation.conversation_id,
                support_inbox=support_actor,
                limit=limit,
            )
        except StoreNotFound as exc:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404) from exc
        return ConversationDetailResponse(
            conversation=self._conversation_response(
                principal, conversation, support_actor=support_actor
            ),
            messages=[
                self._private_message_response(principal, conversation, message)
                for message in messages
            ],
        )

    def create_direct_message(
        self, principal: Principal, request: DirectMessageCreateRequest
    ) -> ConversationDetailResponse:
        self._require_public_member_permission(principal, "messaging.use")
        self._rate_limit(principal, "message")
        try:
            conversation = self.store.create_direct_conversation(
                f"CONV-{uuid.uuid4().hex.upper()}",
                principal.uid,
                request.recipient_uid,
            )
            self.store.send_private_message(
                self._message_record(
                    principal,
                    conversation.conversation_id,
                    request.content,
                    request.client_message_id,
                ),
                support_actor=False,
            )
            conversation = self.store.get_conversation(
                principal.uid, conversation.conversation_id, support_inbox=False
            )
        except StoreConflict as exc:
            code = str(exc)
            status = 404 if code == "MESSAGE_RECIPIENT_NOT_AVAILABLE" else 409
            raise ServiceError(code, status) from exc
        except StoreNotFound as exc:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404) from exc
        if conversation is None:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404)
        return self._conversation_detail(principal, conversation, support_actor=False)

    def list_message_conversations(
        self, principal: Principal, limit: int
    ) -> ConversationListResponse:
        self._require_public_member_permission(principal, "messaging.use")
        conversations = self.store.list_conversations(
            principal.uid, support_inbox=False, limit=limit
        )
        return ConversationListResponse(
            conversations=[
                self._conversation_response(principal, item, support_actor=False)
                for item in conversations
            ]
        )

    def get_message_conversation(
        self, principal: Principal, conversation_id: str, limit: int
    ) -> ConversationDetailResponse:
        self._require_public_member_permission(principal, "messaging.use")
        conversation = self.store.get_conversation(
            principal.uid, conversation_id, support_inbox=False
        )
        if conversation is None:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404)
        return self._conversation_detail(
            principal, conversation, support_actor=False, limit=limit
        )

    def send_conversation_message(
        self,
        principal: Principal,
        conversation_id: str,
        request: ConversationMessageCreateRequest,
        *,
        support_actor: bool = False,
    ) -> PrivateMessageResponse:
        if support_actor:
            self._require_role_permission(
                principal,
                "support",
                "support.requests.manage",
                "SUPPORT_ACCESS_REQUIRED",
            )
        else:
            self._require_public_member_permission(principal, "messaging.use")
        self._rate_limit(principal, "message")
        conversation = self.store.get_conversation(
            principal.uid, conversation_id, support_inbox=support_actor
        )
        if conversation is None:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404)
        media_id = str(request.media_id) if request.media_id is not None else None
        if media_id is not None:
            self._validate_private_message_media(
                principal,
                conversation_id,
                media_id,
            )
        try:
            message = self.store.send_private_message(
                self._message_record(
                    principal,
                    conversation_id,
                    request.content,
                    request.client_message_id,
                    media_id,
                ),
                support_actor=support_actor,
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        except StoreNotFound as exc:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404) from exc
        return self._private_message_response(principal, conversation, message)

    def _community_comment_response(
        self,
        principal: Principal,
        record: CommunityCommentRecord,
    ) -> CommunityCommentResponse:
        return CommunityCommentResponse(
            comment_id=record.comment_id,
            post_id=record.post_id,
            parent_comment_id=record.parent_comment_id,
            author=self._public_message_identity(record.author_uid),
            content=record.body,
            mine=record.author_uid == principal.uid,
            liked_by_me=record.liked_by_viewer,
            like_count=record.like_count,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def list_post_comments(
        self,
        principal: Principal,
        post_id: str,
        limit: int,
    ) -> CommunityCommentListResponse:
        access = self._require_authorized_access(principal)
        if access.role not in {"visitor", "entrepreneur"}:
            raise ServiceError("COMMUNITY_COMMENT_ROLE_REQUIRED", 403)
        try:
            comments = self.store.list_community_comments(
                post_id,
                principal.uid,
                limit,
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        return CommunityCommentListResponse(
            comments=[
                self._community_comment_response(principal, comment)
                for comment in comments
            ]
        )

    def create_post_comment(
        self,
        principal: Principal,
        post_id: str,
        request: CommunityCommentCreateRequest,
    ) -> CommunityCommentResponse:
        self._require_public_member_permission(principal, "feed.publish")
        self._rate_limit(principal, "comment")
        record = CommunityCommentRecord(
            comment_id=f"CMT-{uuid.uuid4().hex.upper()}",
            post_id=post_id,
            author_uid=principal.uid,
            parent_comment_id=request.parent_comment_id,
            client_comment_id=(
                request.client_comment_id or f"CLIENT-{uuid.uuid4().hex}"
            ),
            body=request.content,
            like_count=0,
            liked_by_viewer=False,
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )
        try:
            saved = self.store.create_community_comment(record)
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        return self._community_comment_response(principal, saved)

    def update_post_comment(
        self,
        principal: Principal,
        comment_id: str,
        request: CommunityCommentUpdateRequest,
    ) -> CommunityCommentResponse:
        self._require_public_member_permission(principal, "feed.publish")
        try:
            updated = self.store.update_community_comment(
                comment_id,
                principal.uid,
                request.content,
                datetime.now(timezone.utc),
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 403) from exc
        return self._community_comment_response(principal, updated)

    def delete_post_comment(
        self,
        principal: Principal,
        comment_id: str,
    ) -> CommunityCommentDeleteResponse:
        self._require_public_member_permission(principal, "feed.publish")
        try:
            self.store.delete_community_comment(comment_id, principal.uid)
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 403) from exc
        return CommunityCommentDeleteResponse(comment_id=comment_id, status="deleted")

    def set_post_comment_like(
        self,
        principal: Principal,
        comment_id: str,
        *,
        liked: bool,
    ) -> CommunityCommentLikeResponse:
        self._require_public_member_permission(principal, "feed.publish")
        self._rate_limit(principal, "comment-like")
        try:
            current_liked, like_count = self.store.set_community_comment_like(
                comment_id,
                principal.uid,
                liked,
                datetime.now(timezone.utc),
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        return CommunityCommentLikeResponse(
            comment_id=comment_id,
            liked=current_liked,
            like_count=like_count,
        )

    def mark_conversation_read(
        self, principal: Principal, conversation_id: str
    ) -> ConversationReadResponse:
        self._require_public_member_permission(principal, "messaging.use")
        read_at = datetime.now(timezone.utc)
        try:
            self.store.mark_conversation_read(
                principal.uid,
                conversation_id,
                support_inbox=False,
                read_at=read_at,
            )
        except StoreNotFound as exc:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404) from exc
        return ConversationReadResponse(conversation_id=conversation_id, read_at=read_at)

    def create_support_request(
        self, principal: Principal, request: SupportRequestCreateRequest
    ) -> ConversationDetailResponse:
        self._require_public_member_permission(principal, "support.requests.create")
        self._rate_limit(principal, "support-request")
        try:
            conversation = self.store.create_support_conversation(
                f"CONV-{uuid.uuid4().hex.upper()}", principal.uid, request.subject
            )
            self.store.send_private_message(
                self._message_record(
                    principal,
                    conversation.conversation_id,
                    request.content,
                    request.client_message_id,
                ),
                support_actor=False,
            )
            conversation = self.store.get_conversation(
                principal.uid, conversation.conversation_id, support_inbox=False
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        if conversation is None:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404)
        return self._conversation_detail(principal, conversation, support_actor=False)

    @staticmethod
    def _institution_application_response(
        record: InstitutionApplicationRecord,
    ) -> InstitutionApplicationResponse:
        return InstitutionApplicationResponse(
            application_id=record.application_id,
            organization_type=record.organization_type,
            organization_name=record.organization_name,
            contact_name=record.contact_name,
            email=record.email,
            phone=record.phone,
            registration_number=record.registration_number,
            city=record.city,
            state=record.state,
            website_or_social=record.website_or_social,
            description=record.description,
            status=record.status,
            support_notes=record.support_notes,
            reviewed_by_uid=record.reviewed_by_uid,
            provisioned_uid=record.provisioned_uid,
            reviewed_at=record.reviewed_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def create_public_institution_application(
        self,
        request: PublicInstitutionApplicationCreateRequest,
        source_ref: str,
    ) -> PublicInstitutionApplicationCreatedResponse:
        self._rate_limit_public(source_ref or "unavailable", "institution-application-source")
        self._rate_limit_public(request.email, "institution-application-email")
        now = datetime.now(timezone.utc)
        record = InstitutionApplicationRecord(
            application_id=uuid.uuid4(),
            organization_type=request.organization_type,
            organization_name=request.organization_name,
            contact_name=request.contact_name,
            email=request.email,
            phone=request.phone,
            registration_number=request.registration_number,
            city=request.city,
            state=request.state,
            website_or_social=request.website_or_social,
            description=request.description,
            status="NEW",
            support_notes=None,
            reviewed_by_uid=None,
            provisioned_uid=None,
            reviewed_at=None,
            created_at=now,
            updated_at=now,
        )
        try:
            created = self.store.create_institution_application(record)
        except StoreConflict as exc:
            raise ServiceError("INSTITUTION_APPLICATION_CONFLICT", 409) from exc
        return PublicInstitutionApplicationCreatedResponse(
            application_id=created.application_id,
            status="NEW",
            created_at=created.created_at,
        )

    def list_institution_applications(
        self,
        principal: Principal,
        status: str | None,
        limit: int,
    ) -> InstitutionApplicationListResponse:
        access = self._require_permission(principal, "support.requests.manage")
        if access.role != "support":
            raise ServiceError("SUPPORT_ACCESS_REQUIRED", 403)
        records = self.store.list_institution_applications(status, limit)
        return InstitutionApplicationListResponse(
            applications=[self._institution_application_response(item) for item in records]
        )

    def update_institution_application_status(
        self,
        principal: Principal,
        application_id: uuid.UUID,
        request: InstitutionApplicationStatusUpdateRequest,
    ) -> InstitutionApplicationResponse:
        access = self._require_permission(principal, "support.requests.manage")
        if access.role != "support":
            raise ServiceError("SUPPORT_ACCESS_REQUIRED", 403)
        application = self.store.get_institution_application(application_id)
        if application is None:
            raise ServiceError("INSTITUTION_APPLICATION_NOT_FOUND", 404)
        if request.status == "APPROVED":
            self._require_role_permission(
                principal,
                "support",
                "support.institutions.create",
                "SUPPORT_ACCESS_REQUIRED",
            )
            if not self._auth_is_recent(principal):
                raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)
            if application.status == "APPROVED":
                raise ServiceError("INSTITUTION_APPLICATION_NOT_APPROVABLE", 409)
            self._provision_institution(
                principal,
                InstitutionCreateRequest(
                    email=application.email,
                    name=application.organization_name,
                    description=application.description,
                    city=f"{application.city}/{application.state}",
                ),
                application_id=application.application_id,
                application_support_notes=request.support_notes,
            )
            approved = self.store.get_institution_application(application_id)
            if approved is None or approved.status != "APPROVED":
                raise ServiceError("INSTITUTION_APPLICATION_RECONCILIATION_REQUIRED", 503)
            return self._institution_application_response(approved)
        if application.status == "APPROVED":
            raise ServiceError("INSTITUTION_APPLICATION_FINALIZED", 409)
        try:
            record = self.store.update_institution_application_status(
                application_id,
                request.status,
                request.support_notes,
                principal.uid,
                datetime.now(timezone.utc),
            )
        except StoreNotFound as exc:
            raise ServiceError("INSTITUTION_APPLICATION_NOT_FOUND", 404) from exc
        return self._institution_application_response(record)

    def list_support_requests(
        self, principal: Principal, limit: int
    ) -> ConversationListResponse:
        self._require_role_permission(
            principal,
            "support",
            "support.requests.manage",
            "SUPPORT_ACCESS_REQUIRED",
        )
        conversations = self.store.list_conversations(
            principal.uid, support_inbox=True, limit=limit
        )
        return ConversationListResponse(
            conversations=[
                self._conversation_response(principal, item, support_actor=True)
                for item in conversations
            ]
        )

    def get_support_request(
        self, principal: Principal, conversation_id: str, limit: int
    ) -> ConversationDetailResponse:
        self._require_role_permission(
            principal,
            "support",
            "support.requests.manage",
            "SUPPORT_ACCESS_REQUIRED",
        )
        conversation = self.store.get_conversation(
            principal.uid, conversation_id, support_inbox=True
        )
        if conversation is None:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404)
        read_at = datetime.now(timezone.utc)
        try:
            self.store.mark_conversation_read(
                principal.uid,
                conversation_id,
                support_inbox=True,
                read_at=read_at,
            )
        except StoreNotFound as exc:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404) from exc
        conversation = self.store.get_conversation(
            principal.uid, conversation_id, support_inbox=True
        )
        if conversation is None:
            raise ServiceError("CONVERSATION_NOT_FOUND", 404)
        return self._conversation_detail(
            principal, conversation, support_actor=True, limit=limit
        )

    def resolve_support_request(
        self, principal: Principal, conversation_id: str
    ) -> ConversationResponse:
        self._require_role_permission(
            principal,
            "support",
            "support.requests.manage",
            "SUPPORT_ACCESS_REQUIRED",
        )
        try:
            conversation = self.store.resolve_support_conversation(
                principal.uid, conversation_id, datetime.now(timezone.utc)
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        return self._conversation_response(principal, conversation, support_actor=True)

    def list_message_blocks(
        self, principal: Principal, limit: int
    ) -> MessageBlockListResponse:
        self._require_public_member_permission(principal, "messaging.use")
        blocks = self.store.list_message_blocks(principal.uid, limit)
        responses: list[MessageBlockResponse] = []
        for block in blocks:
            profile = self.store.get_public_profile(block.blocked_uid)
            if profile is not None:
                responses.append(
                    MessageBlockResponse(
                        profile=self._public_profile_response(profile),
                        blocked_at=block.created_at,
                    )
                )
        return MessageBlockListResponse(blocks=responses)

    def block_profile(
        self, principal: Principal, blocked_uid: str
    ) -> MessageBlockResponse:
        self._require_public_member_permission(principal, "messaging.use")
        try:
            block = self.store.set_message_block(
                principal.uid, blocked_uid, datetime.now(timezone.utc)
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        profile = self.store.get_public_profile(block.blocked_uid)
        if profile is None:
            raise ServiceError("MESSAGE_BLOCK_TARGET_INVALID", 409)
        return MessageBlockResponse(
            profile=self._public_profile_response(profile),
            blocked_at=block.created_at,
        )

    def unblock_profile(self, principal: Principal, blocked_uid: str) -> None:
        self._require_public_member_permission(principal, "messaging.use")
        self.store.delete_message_block(principal.uid, blocked_uid)

    def _media_audit_details(
        self,
        principal: Principal,
        record: MediaAssetRecord,
        *,
        request_id: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        details: dict[str, Any] = {
            "actor_ref": self._actor_ref(principal.uid),
            "media_id": record.media_id,
            "entity_type": record.entity_type,
            "entity_ref": hashlib.sha256(
                record.entity_id.encode("utf-8")
            ).hexdigest()[:24],
            "media_role": record.media_role,
            "object_key": record.object_key,
            "declared_content_type": record.declared_content_type,
            "declared_size_bytes": record.declared_size_bytes,
            "role": principal.role,
            "status": record.status,
            "request_id": request_id[:128],
        }
        if ip_address:
            details["ip_ref"] = self.signing_provider.pseudonymize(
                "media-ip", ip_address
            )
        if user_agent:
            details["user_agent_ref"] = hashlib.sha256(
                user_agent[:512].encode("utf-8")
            ).hexdigest()[:24]
        return details

    @staticmethod
    def _media_visibility(media_role: str) -> str:
        return (
            "public_processed"
            if media_role in _PUBLIC_MEDIA_ROLES
            else "restricted"
        )

    @staticmethod
    def _media_extension(filename: str, content_type: str) -> str:
        path = Path(filename)
        suffix = path.suffix.lower()
        # O nome original nunca entra na object key. A validacao de uma unica
        # extensao bloqueia nomes enganosos como foto.jpg.exe e foto.exe.jpg.
        intermediate = [
            segment.lower()
            for segment in path.name.split(".")[1:-1]
            if segment
        ]
        if not suffix or any(
            segment in _DANGEROUS_INTERMEDIATE_EXTENSIONS
            for segment in intermediate
        ):
            raise ServiceError("MEDIA_FILENAME_INVALID", 422)
        if _IMAGE_EXTENSION_CONTENT_TYPE.get(suffix) != content_type:
            raise ServiceError("MEDIA_FILENAME_TYPE_MISMATCH", 422)
        return ".jpg" if suffix == ".jpeg" else suffix

    def _authorize_media_upload(
        self,
        principal: Principal,
        request: MediaUploadCreateRequest,
    ) -> AccessSessionResponse:
        access = self._require_authorized_access(principal)
        required_entity = _MEDIA_ROLE_ENTITY.get(request.media_role)
        if required_entity != request.entity_type:
            raise ServiceError("MEDIA_ROLE_ENTITY_MISMATCH", 422)

        if access.role in {"visitor", "entrepreneur", "institution"}:
            if "media.upload" not in access.permissions:
                raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
        elif access.role == "support":
            if "media.support" not in access.permissions:
                raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
        else:
            raise ServiceError("MEDIA_UPLOAD_ROLE_REQUIRED", 403)

        allowed_roles = {
            "visitor": {"avatar", "post_image", "support_attachment"},
            "entrepreneur": {
                "avatar",
                "entrepreneur_logo",
                "product_image",
                "post_image",
                "fair_cover",
                "support_attachment",
            },
            "institution": {
                "institution_logo",
                "fair_cover",
                "support_attachment",
            },
            "support": {"support_attachment"},
        }
        if request.media_role not in allowed_roles.get(access.role or "", set()):
            raise ServiceError("MEDIA_ROLE_FORBIDDEN", 403)

        if request.media_role == "post_image":
            if request.entity_id is not None:
                raise ServiceError("MEDIA_POST_MUST_START_AS_DRAFT", 422)
            if "feed.publish" not in access.permissions:
                raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
        elif request.media_role == "avatar":
            if request.entity_id not in {None, principal.uid}:
                raise ServiceError("MEDIA_ENTITY_NOT_OWNED", 403)
            if "profile.manage" not in access.permissions:
                raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
            active_profile = self.store.get_public_profile(principal.uid)
            active_media_id = self._media_id_from_public_uri(
                active_profile.avatar_uri if active_profile else None
            )
            for ready_avatar in self.store.list_media_assets(
                "user", principal.uid, self.settings.media_max_avatar_images + 5, 0
            ):
                if ready_avatar.media_id == active_media_id:
                    continue
                try:
                    self.store.mark_media_status(
                        ready_avatar.media_id,
                        principal.uid,
                        "orphaned",
                        "AVATAR_DRAFT_REPLACED",
                        datetime.now(timezone.utc),
                    )
                except StoreConflict:
                    pass
            # Mantem uma vaga temporaria para trocar a foto. Depois que o
            # perfil passa a apontar para a nova imagem, o cliente exclui a
            # anterior; em estado normal continua existindo apenas um avatar.
            if (
                self.store.count_ready_media("user", principal.uid, "avatar")
                >= self.settings.media_max_avatar_images + 1
            ):
                raise ServiceError("MEDIA_ENTITY_IMAGE_LIMIT_REACHED", 409)
        elif request.media_role == "entrepreneur_logo":
            if request.entity_id not in {None, principal.uid}:
                raise ServiceError("MEDIA_ENTITY_NOT_OWNED", 403)
            if "profile.manage" not in access.permissions:
                raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
            if (
                self.store.count_ready_media(
                    "entrepreneur", principal.uid, "entrepreneur_logo"
                )
                >= self.settings.media_max_logo_images
            ):
                raise ServiceError("MEDIA_ENTITY_IMAGE_LIMIT_REACHED", 409)
        elif request.media_role == "institution_logo":
            if request.entity_id not in {None, principal.uid}:
                raise ServiceError("MEDIA_ENTITY_NOT_OWNED", 403)
            if "institution.profile.manage" not in access.permissions:
                raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
            if (
                self.store.count_ready_media(
                    "institution", principal.uid, "institution_logo"
                )
                >= self.settings.media_max_logo_images
            ):
                raise ServiceError("MEDIA_ENTITY_IMAGE_LIMIT_REACHED", 409)
        elif request.media_role == "product_image":
            if request.entity_id is None:
                raise ServiceError("MEDIA_ENTITY_ID_REQUIRED", 422)
            if "marketplace.manage" not in access.permissions:
                raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
            if (
                self.store.get_product_for_offer(
                    principal.uid, request.entity_id
                )
                is None
            ):
                raise ServiceError("MEDIA_ENTITY_NOT_OWNED", 403)
            if (
                self.store.count_ready_media(
                    "product", request.entity_id, "product_image"
                )
                >= self.settings.media_max_product_images
            ):
                raise ServiceError("MEDIA_ENTITY_IMAGE_LIMIT_REACHED", 409)
        elif request.media_role == "fair_cover":
            if request.entity_id is None:
                raise ServiceError("MEDIA_ENTITY_ID_REQUIRED", 422)
            fair_permission = (
                "institution.groups.manage"
                if access.role == "institution"
                else "locations.publish"
            )
            if fair_permission not in access.permissions:
                raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
            try:
                owns_fair = self._community_publisher().owns_live_fair(
                    principal.uid, request.entity_id
                )
            except CommunityPublishError as exc:
                raise ServiceError("COMMUNITY_FIRESTORE_READ_FAILED", 503) from exc
            if not owns_fair:
                raise ServiceError("MEDIA_ENTITY_NOT_OWNED", 403)
            if (
                self.store.count_ready_media(
                    "fair", request.entity_id, "fair_cover"
                )
                >= self.settings.media_max_fair_cover_images
            ):
                raise ServiceError("MEDIA_ENTITY_IMAGE_LIMIT_REACHED", 409)
        elif request.media_role == "support_attachment":
            if request.entity_id is None:
                raise ServiceError("MEDIA_ENTITY_ID_REQUIRED", 422)
            support_inbox = access.role == "support"
            if (
                self.store.get_conversation(
                    principal.uid,
                    request.entity_id,
                    support_inbox=support_inbox,
                )
                is None
            ):
                raise ServiceError("MEDIA_ENTITY_NOT_OWNED", 403)
        return access

    def _same_media_request(
        self,
        record: MediaAssetRecord,
        request: MediaUploadCreateRequest,
        owner_uid: str,
    ) -> bool:
        expected_entity_id = (
            owner_uid
            if request.media_role
            in {"avatar", "entrepreneur_logo", "institution_logo"}
            else request.entity_id
        )
        entity_matches = (
            record.entity_id in {record.media_id, f"pending:{record.media_id}"}
            if expected_entity_id is None
            else record.entity_id == expected_entity_id
        )
        return (
            record.entity_type == request.entity_type
            and entity_matches
            and record.media_role == request.media_role
            and record.original_filename == request.original_filename
            and record.declared_content_type == request.content_type
            and record.declared_size_bytes == request.size_bytes
        )

    def _media_upload_response(
        self, record: MediaAssetRecord
    ) -> MediaUploadAuthorizationResponse:
        try:
            upload_url, required_headers = self.media_storage.create_upload_url(
                record.object_key,
                record.declared_content_type,
                record.media_id,
                self.settings.gcs_signed_url_expiration_seconds,
            )
        except MediaStorageError as exc:
            raise ServiceError(exc.code, 503) from exc
        return MediaUploadAuthorizationResponse(
            media_id=record.media_id,
            object_key=record.object_key,
            upload_url=upload_url,
            expires_in=self.settings.gcs_signed_url_expiration_seconds,
            required_headers=required_headers,
        )

    def create_media_upload(
        self,
        principal: Principal,
        request: MediaUploadCreateRequest,
        *,
        request_id: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> MediaUploadAuthorizationResponse:
        self._authorize_media_upload(principal, request)
        if not self.media_storage.enabled or not self.media_storage.configured:
            raise ServiceError("MEDIA_STORAGE_DISABLED", 503)
        self._rate_limit(principal, "media-upload")
        if request.size_bytes > self.settings.gcs_upload_max_size_bytes:
            raise ServiceError("MEDIA_FILE_TOO_LARGE", 413)
        if request.content_type not in self.settings.gcs_allowed_image_type_list:
            raise ServiceError("MEDIA_IMAGE_TYPE_NOT_ALLOWED", 415)
        extension = self._media_extension(
            request.original_filename, request.content_type
        )

        existing = self.store.get_media_asset_by_client_request(
            principal.uid, request.client_request_id
        )
        now = datetime.now(timezone.utc)
        if existing is not None:
            if not self._same_media_request(existing, request, principal.uid):
                raise ServiceError("MEDIA_CLIENT_REQUEST_ID_REUSED", 409)
            if existing.status != "pending" or existing.upload_expires_at <= now:
                raise ServiceError("MEDIA_UPLOAD_NOT_PENDING", 409)
            return self._media_upload_response(existing)

        if (
            self.store.count_pending_media(principal.uid)
            >= self.settings.media_max_pending_per_user
        ):
            raise ServiceError("MEDIA_PENDING_LIMIT_REACHED", 429)

        media_id = str(uuid.uuid4())
        owner_segment = hashlib.sha256(
            principal.uid.encode("utf-8")
        ).hexdigest()[:24]
        entity_value = (
            principal.uid
            if request.media_role
            in {"avatar", "entrepreneur_logo", "institution_logo"}
            else request.entity_id or media_id
        )
        entity_segment = hashlib.sha256(
            entity_value.encode("utf-8")
        ).hexdigest()[:20]
        object_key = (
            f"media/{request.entity_type}/{owner_segment}/"
            f"{now:%Y/%m}/{entity_segment}/{media_id}{extension}"
        )
        record = MediaAssetRecord(
            media_id=media_id,
            owner_user_id=principal.uid,
            entity_type=request.entity_type,
            entity_id=entity_value,
            media_role=request.media_role,
            bucket_name=self.settings.gcs_bucket_name or "",
            object_key=object_key,
            original_filename=request.original_filename,
            declared_content_type=request.content_type,
            detected_content_type=None,
            declared_size_bytes=request.size_bytes,
            size_bytes=None,
            checksum_sha256=None,
            crc32c=None,
            object_generation=None,
            width=None,
            height=None,
            status="pending",
            visibility=self._media_visibility(request.media_role),
            moderation_status="pending",
            rejection_reason=None,
            client_request_id=request.client_request_id,
            upload_expires_at=now
            + timedelta(seconds=self.settings.media_pending_expiration_seconds),
            created_at=now,
            uploaded_at=None,
            confirmed_at=None,
            deleted_at=None,
            created_by=principal.uid,
            deleted_by=None,
        )
        try:
            stored = self.store.create_media_asset(record)
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        details = self._media_audit_details(
            principal,
            stored,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        try:
            self._append_event(
                operation_id=f"media-request:{media_id}",
                event_type="MEDIA_UPLOAD_REQUESTED",
                result="PENDING",
                details=details,
            )
            response = self._media_upload_response(stored)
            self._append_event(
                operation_id=f"media-url:{media_id}",
                event_type="MEDIA_UPLOAD_URL_ISSUED",
                result="ISSUED",
                details=details,
            )
            return response
        except ServiceError as exc:
            try:
                self.store.mark_media_status(
                    media_id,
                    principal.uid,
                    "rejected",
                    exc.code[:80],
                    datetime.now(timezone.utc),
                )
            except Exception:
                pass
            raise
        except Exception as exc:
            raise ServiceError("MEDIA_AUDIT_UNAVAILABLE", 503) from exc

    def _authorize_media_access(
        self,
        principal: Principal,
        record: MediaAssetRecord,
        *,
        write: bool = False,
    ) -> AccessSessionResponse:
        access = self._require_authorized_access(principal)
        if record.owner_user_id == principal.uid:
            return access
        if access.role == "admin" and "media.admin" in access.permissions:
            return access
        if (
            not write
            and record.visibility == "public_processed"
            and record.status == "ready"
        ):
            return access
        if (
            not write
            and record.media_role == "support_attachment"
        ):
            support_inbox = access.role == "support"
            if support_inbox and "media.support" not in access.permissions:
                raise ServiceError("MEDIA_ACCESS_FORBIDDEN", 403)
            conversation = self.store.get_conversation(
                principal.uid,
                record.entity_id,
                support_inbox=support_inbox,
            )
            if conversation is not None:
                return access
        try:
            self._append_event(
                operation_id=f"media-access-denied:{uuid.uuid4()}",
                event_type="MEDIA_ACCESS_DENIED",
                result="DENIED",
                reason_codes=("MEDIA_ACCESS_FORBIDDEN",),
                details={
                    "actor_ref": self._actor_ref(principal.uid),
                    "media_id": record.media_id,
                    "entity_type": record.entity_type,
                    "media_role": record.media_role,
                    "object_key": record.object_key,
                    "role": access.role,
                },
            )
        except Exception:
            pass
        raise ServiceError("MEDIA_ACCESS_FORBIDDEN", 403)

    def _media_asset_response(
        self,
        record: MediaAssetRecord,
        *,
        include_download_url: bool,
    ) -> MediaAssetResponse:
        download_url = None
        download_expires_in = None
        if include_download_url and record.status == "ready":
            try:
                download_url = self.media_storage.create_download_url(
                    record.object_key,
                    self.settings.gcs_download_url_expiration_seconds,
                )
                download_expires_in = (
                    self.settings.gcs_download_url_expiration_seconds
                )
            except MediaStorageError as exc:
                raise ServiceError(exc.code, 503) from exc
        return MediaAssetResponse(
            media_id=record.media_id,
            owner_user_id=record.owner_user_id,
            entity_type=record.entity_type,
            entity_id=record.entity_id,
            media_role=record.media_role,
            declared_content_type=record.declared_content_type,
            detected_content_type=record.detected_content_type,
            declared_size_bytes=record.declared_size_bytes,
            size_bytes=record.size_bytes,
            checksum_sha256=record.checksum_sha256,
            width=record.width,
            height=record.height,
            status=record.status,
            visibility=record.visibility,
            moderation_status=record.moderation_status,
            created_at=record.created_at,
            uploaded_at=record.uploaded_at,
            confirmed_at=record.confirmed_at,
            deleted_at=record.deleted_at,
            download_url=download_url,
            download_expires_in=download_expires_in,
        )

    def get_media_asset(
        self, principal: Principal, media_id: str
    ) -> MediaAssetResponse:
        record = self.store.get_media_asset(media_id)
        if record is None or record.status == "deleted":
            raise ServiceError("MEDIA_ASSET_NOT_FOUND", 404)
        self._authorize_media_access(principal, record)
        return self._media_asset_response(
            record, include_download_url=record.status == "ready"
        )

    def get_public_media_download_url(
        self,
        media_id: str,
        variant: str | None = None,
    ) -> str:
        try:
            return self.public_media.resolve_asset(media_id, variant)
        except PublicMediaError as exc:
            raise ServiceError(exc.code, exc.status_code) from exc

    def get_public_entity_media_download_url(
        self,
        entity_type: str,
        entity_id: str,
        media_role: str,
        variant: str,
    ) -> str:
        try:
            return self.public_media.resolve_entity(
                entity_type,
                entity_id,
                media_role,
                variant,
            )
        except PublicMediaError as exc:
            raise ServiceError(exc.code, exc.status_code) from exc

    def get_public_profile_avatar_download_url(
        self,
        uid: str,
        variant: str | None = "thumbnail",
    ) -> str:
        profile = self.store.get_public_profile(uid)
        media_id = self._media_id_from_public_uri(
            profile.avatar_uri if profile else None
        )
        if media_id is None:
            raise ServiceError("MEDIA_ASSET_NOT_FOUND", 404)
        return self.get_public_media_download_url(media_id, variant)

    def confirm_media_upload(
        self,
        principal: Principal,
        media_id: str,
        *,
        request_id: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> MediaAssetResponse:
        record = self.store.get_media_asset(media_id)
        if record is None:
            raise ServiceError("MEDIA_ASSET_NOT_FOUND", 404)
        if record.owner_user_id != principal.uid:
            self._authorize_media_access(principal, record, write=True)
            raise ServiceError("MEDIA_ACCESS_FORBIDDEN", 403)
        self._authorize_media_access(principal, record, write=True)
        if record.status == "ready":
            return self._media_asset_response(record, include_download_url=True)
        if record.status not in {"pending", "processing"}:
            raise ServiceError("MEDIA_UPLOAD_NOT_PENDING", 409)
        now = datetime.now(timezone.utc)
        if record.upload_expires_at <= now:
            raise ServiceError("MEDIA_UPLOAD_EXPIRED", 409)

        try:
            metadata = self.media_storage.get_metadata(record.object_key)
        except MediaObjectNotFound as exc:
            raise ServiceError("MEDIA_OBJECT_NOT_FOUND", 409) from exc
        except MediaStorageError as exc:
            raise ServiceError(exc.code, 503) from exc

        uploaded_media_id = (
            metadata.metadata.get("media-id")
            or metadata.metadata.get("media_id")
            or metadata.metadata.get("mediaId")
        )
        rejection_code: str | None = None
        if metadata.bucket_name != record.bucket_name:
            rejection_code = "MEDIA_BUCKET_MISMATCH"
        elif metadata.object_key != record.object_key:
            rejection_code = "MEDIA_OBJECT_KEY_MISMATCH"
        elif uploaded_media_id != record.media_id:
            rejection_code = "MEDIA_OBJECT_ID_MISMATCH"
        elif (
            record.status == "pending"
            and metadata.size_bytes != record.declared_size_bytes
        ):
            rejection_code = "MEDIA_OBJECT_SIZE_MISMATCH"
        elif metadata.size_bytes > self.settings.gcs_upload_max_size_bytes:
            rejection_code = "MEDIA_FILE_TOO_LARGE"
        elif (
            record.status == "pending"
            and (metadata.content_type or "").lower()
            != record.declared_content_type
        ):
            rejection_code = "MEDIA_OBJECT_TYPE_MISMATCH"
        elif (metadata.content_type or "").lower() not in (
            self.settings.gcs_allowed_image_type_list
        ):
            rejection_code = "MEDIA_OBJECT_TYPE_MISMATCH"

        if rejection_code is not None:
            try:
                self.media_storage.delete_object(
                    record.object_key, metadata.generation
                )
            except MediaStorageError:
                pass
            try:
                rejected = self.store.mark_media_status(
                    record.media_id,
                    record.owner_user_id,
                    "rejected",
                    rejection_code[:80],
                    now,
                )
                self._append_event(
                    operation_id=f"media-reject:{record.media_id}:{record.version}",
                    event_type="MEDIA_UPLOAD_REJECTED",
                    result="REJECTED",
                    reason_codes=(rejection_code,),
                    details=self._media_audit_details(
                        principal,
                        rejected,
                        request_id=request_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    ),
                )
            except Exception:
                pass
            raise ServiceError(rejection_code, 422)

        global MediaProcessingError, process_image
        if process_image is None:
            try:
                from .media_processing import (
                    MediaProcessingError as processing_error_type,
                    process_image as image_processor,
                )
            except ImportError as exc:
                # GCS desativado continua permitindo a inicializacao local
                # antes de a nova dependencia ser instalada.
                raise ServiceError(
                    "MEDIA_IMAGE_PROCESSOR_UNAVAILABLE", 503
                ) from exc
            MediaProcessingError = processing_error_type  # type: ignore[misc]
            process_image = image_processor

        if record.status == "pending":
            try:
                processing = self.store.mark_media_processing(
                    record.media_id,
                    record.owner_user_id,
                    now,
                    metadata.size_bytes,
                    record.declared_content_type,
                    metadata.crc32c,
                    metadata.generation,
                )
            except StoreConflict as exc:
                raise ServiceError(str(exc), 409) from exc
        else:
            # Recuperacao idempotente de uma confirmacao interrompida depois
            # de entrar em processing. A precondicao usa a geracao atual.
            processing = replace(
                record,
                size_bytes=metadata.size_bytes,
                detected_content_type=(metadata.content_type or "").lower(),
                crc32c=metadata.crc32c,
                object_generation=metadata.generation,
            )

        try:
            self._append_event(
                operation_id=f"media-processing-start:{processing.media_id}",
                event_type="MEDIA_PROCESSING_STARTED",
                result="PROCESSING",
                details=self._media_audit_details(
                    principal,
                    processing,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ),
            )
        except Exception:
            # A transicao versionada permanece rastreavel no PostgreSQL e a
            # confirmacao pode ser recuperada operacionalmente. A URL assinada
            # nunca e incluida no evento.
            pass

        try:
            raw_bytes = self.media_storage.download_bytes(
                processing.object_key, processing.object_generation
            )
            already_processed = (
                metadata.metadata.get("processed", "").lower() == "true"
            )
            if (
                not already_processed
                and len(raw_bytes) != processing.declared_size_bytes
            ):
                raise MediaProcessingError("MEDIA_OBJECT_SIZE_MISMATCH")
            processed = process_image(
                raw_bytes,
                (
                    processing.detected_content_type
                    if already_processed
                    else processing.declared_content_type
                )
                or processing.declared_content_type,
                max_pixels=self.settings.media_image_max_pixels,
                max_dimension=self.settings.media_image_max_dimension,
            )
            if len(processed.data) > self.settings.gcs_upload_max_size_bytes:
                raise MediaProcessingError("MEDIA_PROCESSED_FILE_TOO_LARGE")
            final_metadata = self.media_storage.replace_object(
                processing.object_key,
                processed.data,
                processed.content_type,
                processing.media_id,
                processing.object_generation,
            )
            variant_records: list[MediaVariantRecord] = []
            uploaded_variant_objects: list[tuple[str, int | None]] = []
            try:
                for variant in processed.variants:
                    variant_object_key = (
                        f"{processing.object_key.rsplit('.', 1)[0]}."
                        f"{variant.variant}.webp"
                    )
                    variant_metadata = self.media_storage.put_derived_object(
                        variant_object_key,
                        variant.data,
                        variant.content_type,
                        processing.media_id,
                        variant.variant,
                        variant.checksum_sha256,
                    )
                    uploaded_variant_objects.append(
                        (variant_object_key, variant_metadata.generation)
                    )
                    variant_records.append(
                        MediaVariantRecord(
                            media_id=processing.media_id,
                            variant=variant.variant,
                            bucket_name=variant_metadata.bucket_name,
                            object_key=variant_object_key,
                            content_type=variant.content_type,
                            size_bytes=len(variant.data),
                            checksum_sha256=variant.checksum_sha256,
                            crc32c=variant_metadata.crc32c,
                            object_generation=variant_metadata.generation,
                            width=variant.width,
                            height=variant.height,
                            created_at=now,
                        )
                    )
                if variant_records:
                    self.store.replace_media_variants(
                        processing.media_id,
                        variant_records,
                    )
            except Exception:
                for object_key, generation in uploaded_variant_objects:
                    try:
                        self.media_storage.delete_object(object_key, generation)
                    except MediaStorageError:
                        pass
                raise
            ready = self.store.mark_media_ready(
                processing.media_id,
                processing.owner_user_id,
                processed.content_type,
                len(processed.data),
                processed.checksum_sha256,
                final_metadata.crc32c,
                final_metadata.generation,
                processed.width,
                processed.height,
                now,
            )
            try:
                self._append_event(
                    operation_id=f"media-processing-complete:{ready.media_id}",
                    event_type="MEDIA_PROCESSING_COMPLETED",
                    result="READY",
                    details={
                        **self._media_audit_details(
                            principal,
                            ready,
                            request_id=request_id,
                            ip_address=ip_address,
                            user_agent=user_agent,
                        ),
                        "detected_content_type": ready.detected_content_type,
                        "size_bytes": ready.size_bytes,
                        "width": ready.width,
                        "height": ready.height,
                    },
                )
            except Exception:
                pass
        except MediaProcessingError as exc:
            try:
                self.media_storage.delete_object(
                    processing.object_key, processing.object_generation
                )
            except MediaStorageError:
                pass
            try:
                quarantined = self.store.mark_media_status(
                    processing.media_id,
                    processing.owner_user_id,
                    "quarantined",
                    exc.code[:80],
                    datetime.now(timezone.utc),
                )
                self._append_event(
                    operation_id=f"media-quarantine:{processing.media_id}",
                    event_type="MEDIA_QUARANTINED",
                    result="QUARANTINED",
                    reason_codes=(exc.code,),
                    details=self._media_audit_details(
                        principal,
                        quarantined,
                        request_id=request_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    ),
                )
            except Exception:
                pass
            raise ServiceError(exc.code, 422) from exc
        except MediaStorageError as exc:
            try:
                quarantined = self.store.mark_media_status(
                    processing.media_id,
                    processing.owner_user_id,
                    "quarantined",
                    exc.code[:80],
                    datetime.now(timezone.utc),
                )
                self._append_event(
                    operation_id=f"media-quarantine:{processing.media_id}",
                    event_type="MEDIA_QUARANTINED",
                    result="QUARANTINED",
                    reason_codes=(exc.code,),
                    details=self._media_audit_details(
                        principal,
                        quarantined,
                        request_id=request_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    ),
                )
            except Exception:
                pass
            raise ServiceError(exc.code, 503) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc

        try:
            self._append_event(
                operation_id=f"media-confirm:{ready.media_id}",
                event_type="MEDIA_UPLOAD_CONFIRMED",
                result="READY",
                details={
                    **self._media_audit_details(
                        principal,
                        ready,
                        request_id=request_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    ),
                    "detected_content_type": ready.detected_content_type,
                    "size_bytes": ready.size_bytes,
                    "width": ready.width,
                    "height": ready.height,
                    "checksum_sha256": ready.checksum_sha256,
                },
            )
        except Exception as exc:
            raise ServiceError("MEDIA_AUDIT_UNAVAILABLE", 503) from exc
        return self._media_asset_response(ready, include_download_url=True)

    def list_media_assets(
        self,
        principal: Principal,
        *,
        entity_type: str,
        entity_id: str,
        limit: int,
        offset: int,
    ) -> MediaAssetListResponse:
        self._require_authorized_access(principal)
        records = self.store.list_media_assets(
            entity_type, entity_id, limit + 1, offset
        )
        items: list[MediaAssetResponse] = []
        for record in records:
            if record.status == "deleted":
                continue
            try:
                self._authorize_media_access(principal, record)
            except ServiceError:
                continue
            items.append(
                self._media_asset_response(
                    record, include_download_url=record.status == "ready"
                )
            )
        has_more = len(items) > limit
        return MediaAssetListResponse(
            items=items[:limit],
            has_more=has_more,
        )

    def delete_media_asset(
        self,
        principal: Principal,
        media_id: str,
        *,
        request_id: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        record = self.store.get_media_asset(media_id)
        if record is None or record.status == "deleted":
            return
        self._authorize_media_access(principal, record, write=True)
        try:
            for variant in self.store.list_media_variants(record.media_id):
                self.media_storage.delete_object(
                    variant.object_key,
                    variant.object_generation,
                )
            self.media_storage.delete_object(
                record.object_key, record.object_generation
            )
            deleted = self.store.mark_media_deleted(
                record.media_id,
                principal.uid,
                datetime.now(timezone.utc),
            )
            self._append_event(
                operation_id=f"media-delete:{record.media_id}:{record.version}",
                event_type=(
                    "MEDIA_ADMIN_ACTION"
                    if principal.uid != record.owner_user_id
                    else "MEDIA_DELETED"
                ),
                result="DELETED",
                details={
                    **self._media_audit_details(
                        principal,
                        deleted,
                        request_id=request_id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    ),
                    "action": "delete",
                    "previous_status": record.status,
                    "new_status": deleted.status,
                },
            )
        except MediaStorageError as exc:
            raise ServiceError(exc.code, 503) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc

    def cleanup_expired_media(
        self, principal: Principal, limit: int
    ) -> MediaCleanupResponse:
        access = self._require_authorized_access(principal)
        if access.role != "admin" or "media.admin" not in access.permissions:
            raise ServiceError("MEDIA_ADMIN_ACCESS_REQUIRED", 403)
        if not self._auth_is_recent(principal):
            raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)
        now = datetime.now(timezone.utc)
        expired = self.store.list_expired_pending_media(
            now, limit
        )
        remaining = max(0, limit - len(expired))
        orphaned_records = (
            self.store.list_orphaned_media(
                now
                - timedelta(
                    seconds=self.settings.media_orphan_retention_seconds
                ),
                remaining,
            )
            if remaining
            else []
        )
        candidates = [*expired, *orphaned_records]
        cleaned = 0
        failed = 0
        for record in candidates:
            try:
                for variant in self.store.list_media_variants(record.media_id):
                    self.media_storage.delete_object(
                        variant.object_key,
                        variant.object_generation,
                    )
                self.media_storage.delete_object(
                    record.object_key, record.object_generation
                )
                cleaned_record = (
                    self.store.mark_media_deleted(
                        record.media_id,
                        principal.uid,
                        datetime.now(timezone.utc),
                    )
                    if record.status == "orphaned"
                    else self.store.mark_media_status(
                        record.media_id,
                        record.owner_user_id,
                        "orphaned",
                        "MEDIA_UPLOAD_EXPIRED",
                        datetime.now(timezone.utc),
                    )
                )
                self._append_event(
                    operation_id=(
                        f"media-orphan-cleanup:{record.media_id}:{record.status}"
                    ),
                    event_type="MEDIA_ORPHAN_CLEANUP",
                    result="CLEANED",
                    reason_codes=("MEDIA_UPLOAD_EXPIRED",),
                    details={
                        "actor_ref": self._actor_ref(principal.uid),
                        "owner_ref": self._actor_ref(record.owner_user_id),
                        "media_id": cleaned_record.media_id,
                        "entity_type": cleaned_record.entity_type,
                        "media_role": cleaned_record.media_role,
                        "previous_status": record.status,
                        "new_status": cleaned_record.status,
                    },
                )
                cleaned += 1
            except Exception:
                # A limpeza e repetivel e versionada. Uma falha isolada nao
                # permite apagar os demais objetos validamente expirados.
                failed += 1
        return MediaCleanupResponse(
            scanned=len(candidates),
            cleaned=cleaned,
            failed=failed,
        )

    def create_community_post(
        self,
        principal: Principal,
        request: CommunityPostCreateRequest,
    ) -> CommunityDocumentResponse:
        access = self._require_authorized_access(principal)
        if access.role not in {"entrepreneur", "visitor"}:
            raise ServiceError("COMMUNITY_POST_ROLE_REQUIRED", 403)
        if "feed.publish" not in access.permissions:
            raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
        created_at = datetime.now(timezone.utc)
        document_id = uuid.uuid4().hex
        media_record: MediaAssetRecord | None = None
        if request.media is not None:
            media_record = self.store.get_media_asset(request.media.media_id)
            if media_record is None or media_record.status != "ready":
                raise ServiceError("COMMUNITY_POST_MEDIA_NOT_READY", 409)
            if (
                media_record.owner_user_id != principal.uid
                or media_record.entity_type != "post"
                or media_record.media_role != "post_image"
                or media_record.detected_content_type
                not in self.settings.gcs_allowed_image_type_list
            ):
                raise ServiceError("COMMUNITY_POST_MEDIA_FORBIDDEN", 403)
            try:
                media_record = self.store.associate_media(
                    media_record.media_id,
                    principal.uid,
                    "post",
                    document_id,
                )
            except StoreConflict as exc:
                raise ServiceError(str(exc), 409) from exc
        try:
            published_document_id = self._community_publisher().create_post(
                principal.uid,
                principal.email,
                access.role,
                request,
                int(created_at.timestamp() * 1000),
                document_id,
            )
        except CommunityPublishError as exc:
            if media_record is not None:
                try:
                    self.store.mark_media_status(
                        media_record.media_id,
                        principal.uid,
                        "orphaned",
                        "COMMUNITY_FIRESTORE_WRITE_FAILED",
                        datetime.now(timezone.utc),
                    )
                except Exception:
                    pass
            raise ServiceError("COMMUNITY_FIRESTORE_WRITE_FAILED", 503) from exc
        if published_document_id != document_id:
            raise ServiceError("COMMUNITY_FIRESTORE_ID_MISMATCH", 503)
        try:
            self.store.index_community_post(
                document_id, principal.uid, request.text, created_at
            )
        except Exception:
            # O documento autoritativo ja existe no Firestore e sera entregue
            # ao Feed. Nao devolvemos uma falsa falha que levaria o usuario a
            # publicar a mesma foto novamente; a busca pode ser reconciliada.
            try:
                self._append_event(
                    operation_id=f"community-index:{document_id}",
                    event_type="COMMUNITY_SEARCH_INDEX_FAILED",
                    result="DEGRADED",
                    reason_codes=("COMMUNITY_SEARCH_INDEX_FAILED",),
                    details={
                        "actor_ref": self._actor_ref(principal.uid),
                        "document_id": document_id,
                        "has_media": request.media is not None,
                    },
                )
            except Exception:
                pass
        return CommunityDocumentResponse(document_id=document_id, status="approved")

    def update_community_post(
        self,
        principal: Principal,
        post_id: str,
        request: CommunityPostUpdateRequest,
    ) -> CommunityContentMutationResponse:
        self._require_public_member_permission(principal, "feed.publish")
        updated_at_ms = int(time.time() * 1000)
        try:
            self._community_publisher().update_post(
                principal.uid,
                post_id,
                request,
                updated_at_ms,
            )
        except CommunityDocumentNotFound as exc:
            raise ServiceError("COMMUNITY_POST_NOT_FOUND", 404) from exc
        except CommunityDocumentForbidden as exc:
            raise ServiceError("COMMUNITY_POST_FORBIDDEN", 403) from exc
        except CommunityPublishError as exc:
            raise ServiceError("COMMUNITY_FIRESTORE_WRITE_FAILED", 503) from exc
        try:
            self.store.update_community_post(post_id, principal.uid, request.text)
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 403) from exc
        return CommunityContentMutationResponse(document_id=post_id, status="updated")

    def delete_community_post(
        self,
        principal: Principal,
        post_id: str,
    ) -> CommunityContentMutationResponse:
        self._require_public_member_permission(principal, "feed.publish")
        try:
            self._community_publisher().delete_post(principal.uid, post_id)
        except CommunityDocumentNotFound as exc:
            raise ServiceError("COMMUNITY_POST_NOT_FOUND", 404) from exc
        except CommunityDocumentForbidden as exc:
            raise ServiceError("COMMUNITY_POST_FORBIDDEN", 403) from exc
        except CommunityPublishError as exc:
            raise ServiceError("COMMUNITY_FIRESTORE_WRITE_FAILED", 503) from exc
        try:
            self.store.delete_community_post(post_id, principal.uid)
        except StoreNotFound:
            # O Firestore e a fonte do Feed. Se o indice ja foi removido, a
            # exclusao continua concluida e idempotente para o usuario.
            pass
        except StoreConflict as exc:
            raise ServiceError(str(exc), 403) from exc
        return CommunityContentMutationResponse(document_id=post_id, status="deleted")

    def create_curated_place(
        self,
        principal: Principal,
        request: CuratedPlaceCreateRequest,
    ) -> CommunityDocumentResponse:
        self._require_entrepreneur_permission(principal, "locations.publish")
        try:
            document_id = self._community_publisher().create_place(
                principal.uid,
                principal.email,
                request,
                int(time.time() * 1000),
            )
        except CommunityDocumentConflict as exc:
            raise ServiceError("CURATED_PLACE_ALREADY_EXISTS", 409) from exc
        except CommunityPublishError as exc:
            raise ServiceError("COMMUNITY_FIRESTORE_WRITE_FAILED", 503) from exc
        return CommunityDocumentResponse(document_id=document_id, status="approved")

    def delete_curated_place(
        self,
        principal: Principal,
        place_id: str,
    ) -> CommunityContentMutationResponse:
        self._require_entrepreneur_permission(principal, "locations.publish")
        try:
            self._community_publisher().delete_place(principal.uid, place_id)
        except CommunityDocumentNotFound as exc:
            raise ServiceError("CURATED_PLACE_NOT_FOUND", 404) from exc
        except CommunityDocumentForbidden as exc:
            raise ServiceError("CURATED_PLACE_NOT_OWNED", 403) from exc
        except CommunityPublishError as exc:
            raise ServiceError("COMMUNITY_FIRESTORE_WRITE_FAILED", 503) from exc
        return CommunityContentMutationResponse(document_id=place_id, status="deleted")

    def create_live_fair(
        self,
        principal: Principal,
        request: LiveFairCreateRequest,
    ) -> CommunityDocumentResponse:
        self._require_live_fair_manager_permission(principal)
        now_ms = int(time.time() * 1000)
        if request.starts_at_ms < now_ms - 30 * 60 * 1000:
            raise ServiceError("LIVE_FAIR_START_INVALID", 409)
        if request.ends_at_ms <= now_ms:
            raise ServiceError("LIVE_FAIR_END_INVALID", 409)
        status = "scheduled" if request.starts_at_ms > now_ms else "live"
        try:
            document_id = self._community_publisher().create_live_fair(
                principal.uid,
                principal.email,
                request,
                now_ms,
                status,
            )
        except CommunityPublishError as exc:
            raise ServiceError("COMMUNITY_FIRESTORE_WRITE_FAILED", 503) from exc
        return CommunityDocumentResponse(document_id=document_id, status=status)

    def end_live_fair(self, principal: Principal, fair_id: str) -> CommunityDocumentResponse:
        self._require_live_fair_manager_permission(principal)
        try:
            self._community_publisher().end_live_fair(
                principal.uid,
                fair_id,
                int(time.time() * 1000),
            )
        except CommunityDocumentNotFound as exc:
            raise ServiceError("LIVE_FAIR_NOT_FOUND", 404) from exc
        except CommunityDocumentForbidden as exc:
            raise ServiceError("LIVE_FAIR_NOT_OWNED", 403) from exc
        except CommunityDocumentConflict as exc:
            raise ServiceError("LIVE_FAIR_NOT_ACTIVE", 409) from exc
        except CommunityPublishError as exc:
            raise ServiceError("COMMUNITY_FIRESTORE_WRITE_FAILED", 503) from exc
        return CommunityDocumentResponse(document_id=fair_id, status="ended")

    def delete_live_fair(
        self,
        principal: Principal,
        fair_id: str,
    ) -> CommunityContentMutationResponse:
        self._require_live_fair_manager_permission(principal)
        try:
            self._community_publisher().delete_live_fair(principal.uid, fair_id)
        except CommunityDocumentNotFound as exc:
            raise ServiceError("LIVE_FAIR_NOT_FOUND", 404) from exc
        except CommunityDocumentForbidden as exc:
            raise ServiceError("LIVE_FAIR_NOT_OWNED", 403) from exc
        except CommunityPublishError as exc:
            raise ServiceError("COMMUNITY_FIRESTORE_WRITE_FAILED", 503) from exc
        return CommunityContentMutationResponse(document_id=fair_id, status="deleted")

    def _actor_ref(self, uid: str) -> str:
        return self.signing_provider.pseudonymize("actor", uid)

    @staticmethod
    def _marketplace_batch_command_hash(
        operation_kind: str,
        request: ProductBatchActivateRequest | ProductBatchArchiveRequest | OfferBatchActionRequest,
    ) -> str:
        command = request.model_dump(
            mode="json",
            exclude={"client_request_id"},
            exclude_none=True,
        )
        return sha3_hex(
            {"operation_kind": operation_kind, "command": command},
            "LiberRotas/marketplace-batch-command/v1",
        )

    def _device_ref(self, key_id: str) -> str:
        return self.signing_provider.pseudonymize("device", key_id)

    def _issuer_key_ref(self) -> str:
        return self.signing_provider.key_ref_token(self.settings.issuer_key_id)

    def _auth_is_recent(self, principal: Principal) -> bool:
        now = int(time.time())
        try:
            auth_time = int(principal.claims.get("auth_time"))
        except (TypeError, ValueError):
            auth_time = 0
        auth_age = now - auth_time
        return (
            auth_time > 0
            and auth_age >= -60
            and auth_age <= self.settings.device_enrollment_max_auth_age_seconds
        )

    def _require_role_permission(
        self,
        principal: Principal,
        role: str,
        permission: str,
        role_error: str,
    ) -> AccessSessionResponse:
        access = self._require_authorized_access(principal)
        if access.role != role:
            raise ServiceError(role_error, 403)
        if permission not in access.permissions:
            raise ServiceError("ACCOUNT_PERMISSION_REQUIRED", 403)
        return access

    @staticmethod
    def _institution_response(profile: InstitutionProfileRecord) -> InstitutionResponse:
        return InstitutionResponse(
            firebase_uid=profile.firebase_uid,
            email=profile.email,
            name=profile.name,
            description=profile.description,
            city=profile.city,
            status=profile.status,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    @staticmethod
    def _institution_group_response(group: InstitutionGroupRecord) -> InstitutionGroupResponse:
        return InstitutionGroupResponse(
            group_id=group.group_id,
            owner_uid=group.owner_uid,
            name=group.name,
            description=group.description,
            city=group.city,
            status=group.status,
            created_at=group.created_at,
            updated_at=group.updated_at,
            closed_at=group.closed_at,
        )

    @staticmethod
    def _institution_membership_response(
        membership: InstitutionMembershipRecord,
    ) -> InstitutionMembershipResponse:
        return InstitutionMembershipResponse(
            membership_id=membership.membership_id,
            group_id=membership.group_id,
            group_name=membership.group_name,
            institution_name=membership.institution_name,
            seller_uid=membership.seller_uid,
            seller_name=membership.seller_name,
            status=membership.status,
            invited_at=membership.invited_at,
            responded_at=membership.responded_at,
            active_from=membership.active_from,
            ended_at=membership.ended_at,
            updated_at=membership.updated_at,
        )

    @staticmethod
    def _institution_currency_total_response(total) -> InstitutionSalesCurrencyTotalResponse:
        return InstitutionSalesCurrencyTotalResponse(
            currency=total.currency,
            gross_original_amount_minor=total.gross_original_amount_minor,
            gross_final_amount_minor=total.gross_final_amount_minor,
            total_discount_amount_minor=total.total_discount_amount_minor,
        )

    @staticmethod
    def _institution_funded_event_response(
        event: InstitutionFundedEventRecord,
    ) -> InstitutionFundedEventResponse:
        return InstitutionFundedEventResponse(
            event_id=event.event_id,
            group_id=event.group_id,
            group_name=event.group_name,
            name=event.name,
            description=event.description,
            funding_source=event.funding_source,
            budget_amount_minor=event.budget_amount_minor,
            currency=event.currency,
            end_mode=event.end_mode,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            coupon_limit=event.coupon_limit,
            current_coupon_redemptions=event.current_coupon_redemptions,
            status=event.status,
            end_reason=event.end_reason,
            created_at=event.created_at,
            updated_at=event.updated_at,
            activated_at=event.activated_at,
            ended_at=event.ended_at,
            seller_allocations=[
                InstitutionFundedEventSellerAllocationResponse(
                    membership_id=seller.membership_id,
                    seller_uid=seller.seller_uid,
                    seller_name=seller.seller_name,
                    allocated_amount_minor=seller.allocated_amount_minor,
                    allocation_mode=seller.allocation_mode,
                    product_allocation_configured=bool(
                        seller.product_allocations
                    ),
                    product_allocations=[
                        InstitutionFundedEventProductAllocationResponse(
                            product_id=product.product_id,
                            product_title=product.product_title,
                            allocated_amount_minor=product.allocated_amount_minor,
                            allocation_mode=product.allocation_mode,
                        )
                        for product in seller.product_allocations
                    ],
                )
                for seller in event.seller_allocations
            ],
        )

    @staticmethod
    def _entrepreneur_funded_event_response(
        event: InstitutionFundedEventRecord,
        seller_uid: str,
    ) -> EntrepreneurFundedEventResponse:
        seller = next(
            (
                allocation
                for allocation in event.seller_allocations
                if allocation.seller_uid == seller_uid
            ),
            None,
        )
        if seller is None:
            raise ServiceError("INSTITUTION_FUNDED_EVENT_NOT_FOUND", 404)
        return EntrepreneurFundedEventResponse(
            event_id=event.event_id,
            institution_name=event.institution_name,
            group_name=event.group_name,
            name=event.name,
            description=event.description,
            allocated_amount_minor=seller.allocated_amount_minor,
            currency=event.currency,
            end_mode=event.end_mode,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            coupon_limit=event.coupon_limit,
            current_coupon_redemptions=event.current_coupon_redemptions,
            status=event.status,
            product_allocation_configured=bool(seller.product_allocations),
            product_allocations=[
                InstitutionFundedEventProductAllocationResponse(
                    product_id=product.product_id,
                    product_title=product.product_title,
                    allocated_amount_minor=product.allocated_amount_minor,
                    allocation_mode=product.allocation_mode,
                )
                for product in seller.product_allocations
            ],
        )

    @staticmethod
    def _access_account_summary_response(
        account: AccessAccountSummaryRecord,
    ) -> AccessAccountSummaryResponse:
        return AccessAccountSummaryResponse(
            firebase_uid=account.firebase_uid,
            email=account.email,
            role=account.role,
            status=account.status,
            permissions=list(account.permissions),
            created_at=account.created_at,
            updated_at=account.updated_at,
            authority_validation_state=account.authority_validation_state,
            protection_level=account.protection_level,
            account_origin=account.account_origin,
            authority_validated_at=account.authority_validated_at,
            authority_validated_by_uid=account.authority_validated_by_uid,
            created_by_uid=account.created_by_uid,
        )

    @staticmethod
    def _support_account_summary_response(
        account: AccessAccountSummaryRecord,
    ) -> SupportAccountSummaryResponse:
        return SupportAccountSummaryResponse(
            firebase_uid=account.firebase_uid,
            email=account.email,
            role=account.role,
            status=account.status,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )

    @staticmethod
    def _access_audit_event_response(
        event: AccessAuditEventRecord,
    ) -> AccessAuditEventResponse:
        return AccessAuditEventResponse(
            event_id=event.event_id,
            actor_uid=event.actor_uid,
            target_uid=event.target_uid,
            event_type=event.event_type,
            previous_status=event.previous_status,
            new_status=event.new_status,
            reason=event.reason,
            created_at=event.created_at,
        )

    def _institution_identity_provisioner(self) -> InstitutionIdentityProvisioner:
        if self.institution_provisioner is None:
            raise ServiceError("INSTITUTION_PROVISIONER_UNAVAILABLE", 503)
        return self.institution_provisioner

    def _staff_identity_provisioner(self) -> StaffIdentityProvisioner:
        if self.staff_provisioner is None:
            raise ServiceError("STAFF_PROVISIONER_UNAVAILABLE", 503)
        return self.staff_provisioner

    @staticmethod
    def _rollback_institution_identity(
        provisioner: InstitutionIdentityProvisioner,
        firebase_uid: str,
    ) -> None:
        try:
            provisioner.rollback(firebase_uid)
        except InstitutionProvisioningError as exc:
            raise ServiceError("INSTITUTION_PROVISION_ROLLBACK_FAILED", 503) from exc
        except Exception as exc:
            raise ServiceError("INSTITUTION_PROVISION_ROLLBACK_FAILED", 503) from exc

    @staticmethod
    def _rollback_staff_identity(
        provisioner: StaffIdentityProvisioner,
        firebase_uid: str,
    ) -> None:
        try:
            provisioner.rollback(firebase_uid)
        except StaffProvisioningError as exc:
            raise ServiceError("STAFF_PROVISION_ROLLBACK_FAILED", 503) from exc
        except Exception as exc:
            raise ServiceError("STAFF_PROVISION_ROLLBACK_FAILED", 503) from exc

    def create_staff_account(
        self,
        principal: Principal,
        request: StaffAccountCreateRequest,
    ) -> AccessAccountSummaryResponse:
        self._require_role_permission(
            principal,
            "admin",
            "admin.staff_accounts.manage",
            "ADMIN_STAFF_ACCESS_REQUIRED",
        )
        if not self._auth_is_recent(principal):
            raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)

        provisioner = self._staff_identity_provisioner()
        try:
            identity = provisioner.provision(
                request.email.casefold(),
                request.display_name,
                request.role,
            )
        except StaffEmailExists as exc:
            raise ServiceError("STAFF_EMAIL_EXISTS", 409) from exc
        except StaffProvisioningRollbackError as exc:
            raise ServiceError("STAFF_PROVISION_ROLLBACK_FAILED", 503) from exc
        except StaffProvisioningError as exc:
            code = str(exc)
            if code == "STAFF_ROLE_INVALID":
                raise ServiceError(code, 422) from exc
            raise ServiceError("STAFF_PROVISION_FAILED", 503) from exc
        except Exception as exc:
            raise ServiceError("STAFF_PROVISION_FAILED", 503) from exc

        now = datetime.now(timezone.utc)
        account = AccessAccountRecord(
            firebase_uid=identity.firebase_uid,
            email=identity.email.casefold(),
            role=request.role,
            status="PENDING",
            allow_entrepreneur_fallback=False,
            permissions=default_permissions(request.role),
        )
        validation = PrivilegedAccountValidationRecord(
            firebase_uid=identity.firebase_uid,
            requested_role=request.role,
            validation_state="PENDING",
            protection_level="PRIVILEGED",
            account_origin="ADMIN_INVITATION",
            created_by_uid=principal.uid,
            validated_by_uid=None,
            validation_reason=None,
            validated_at=None,
            created_at=now,
            updated_at=now,
        )
        try:
            created = self.store.create_staff_account(
                account,
                validation,
                actor_uid=principal.uid,
                event_id=f"access:{uuid.uuid4()}",
                queue_id=uuid.uuid4(),
            )
        except StoreConflict as exc:
            self._rollback_staff_identity(
                provisioner,
                identity.firebase_uid,
            )
            code = str(exc)
            status_code = (
                403 if code == "ADMIN_STAFF_ACCESS_REQUIRED" else 409
            )
            raise ServiceError(code, status_code) from exc
        except Exception as exc:
            self._rollback_staff_identity(
                provisioner,
                identity.firebase_uid,
            )
            raise ServiceError("ACCESS_STORE_WRITE_FAILED", 503) from exc
        return self._access_account_summary_response(created)

    def list_staff_accounts(
        self,
        principal: Principal,
        limit: int,
    ) -> AdminAccountListResponse:
        self._require_role_permission(
            principal,
            "admin",
            "admin.staff_accounts.manage",
            "ADMIN_STAFF_ACCESS_REQUIRED",
        )
        staff_accounts = self.store.list_staff_accounts(limit)
        return AdminAccountListResponse(
            accounts=[
                self._access_account_summary_response(account)
                for account in staff_accounts
            ]
        )

    def validate_staff_account(
        self,
        principal: Principal,
        target_uid: str,
        request: StaffAccountValidationRequest,
    ) -> AccessAccountSummaryResponse:
        self._require_role_permission(
            principal,
            "admin",
            "admin.staff_accounts.manage",
            "ADMIN_STAFF_ACCESS_REQUIRED",
        )
        if not self._auth_is_recent(principal):
            raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)
        if target_uid == principal.uid:
            raise ServiceError("STAFF_SELF_VALIDATION_FORBIDDEN", 403)

        target = self.store.get_access_account(target_uid)
        validation = self.store.get_privileged_account_validation(target_uid)
        if target is None or validation is None:
            raise ServiceError("STAFF_ACCOUNT_NOT_FOUND", 404)
        if (
            target.status != "PENDING"
            or validation.validation_state != "PENDING"
            or validation.requested_role != target.role
        ):
            raise ServiceError("STAFF_VALIDATION_STATE_INVALID", 409)

        provisioner = self._staff_identity_provisioner()
        try:
            identity = provisioner.inspect(target_uid)
        except StaffProvisioningError as exc:
            code = str(exc)
            status_code = 404 if code == "STAFF_IDENTITY_NOT_FOUND" else 503
            raise ServiceError(code, status_code) from exc
        if identity.disabled:
            raise ServiceError("STAFF_IDENTITY_DISABLED", 409)
        if not identity.email_verified:
            raise ServiceError("STAFF_EMAIL_VERIFICATION_REQUIRED", 409)
        if identity.role != target.role:
            raise ServiceError("STAFF_IDENTITY_ROLE_MISMATCH", 409)
        if target.email and identity.email.casefold() != target.email.casefold():
            raise ServiceError("STAFF_IDENTITY_EMAIL_MISMATCH", 409)

        try:
            provisioner.set_validated(target_uid, target.role, True)
        except StaffProvisioningError as exc:
            raise ServiceError("STAFF_CLAIM_UPDATE_FAILED", 503) from exc
        try:
            approved = self.store.approve_staff_account(
                principal.uid,
                target_uid,
                request.reason,
                event_id=f"access:{uuid.uuid4()}",
                approved_at=datetime.now(timezone.utc),
            )
        except (StoreConflict, StoreNotFound) as exc:
            try:
                provisioner.set_validated(target_uid, target.role, False)
            except StaffProvisioningError as rollback_exc:
                raise ServiceError(
                    "STAFF_VALIDATION_RECONCILIATION_REQUIRED",
                    503,
                ) from rollback_exc
            code = str(exc)
            status_code = 404 if code == "STAFF_ACCOUNT_NOT_FOUND" else 409
            if code == "ADMIN_STAFF_ACCESS_REQUIRED":
                status_code = 403
            raise ServiceError(code, status_code) from exc
        except Exception as exc:
            try:
                provisioner.set_validated(target_uid, target.role, False)
            except StaffProvisioningError as rollback_exc:
                raise ServiceError(
                    "STAFF_VALIDATION_RECONCILIATION_REQUIRED",
                    503,
                ) from rollback_exc
            raise ServiceError("ACCESS_STORE_WRITE_FAILED", 503) from exc
        return self._access_account_summary_response(approved)

    def create_institution(
        self,
        principal: Principal,
        request: InstitutionCreateRequest,
    ) -> InstitutionResponse:
        self._require_role_permission(
            principal,
            "admin",
            "admin.institutions.manage",
            "ADMIN_ACCESS_REQUIRED",
        )
        if not self._auth_is_recent(principal):
            raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)

        return self._provision_institution(principal, request)

    def create_support_institution(
        self,
        principal: Principal,
        request: InstitutionCreateRequest,
    ) -> InstitutionResponse:
        self._require_role_permission(
            principal,
            "support",
            "support.institutions.create",
            "SUPPORT_ACCESS_REQUIRED",
        )
        if not self._auth_is_recent(principal):
            raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)

        return self._provision_institution(principal, request)

    def _provision_institution(
        self,
        principal: Principal,
        request: InstitutionCreateRequest,
        *,
        application_id: uuid.UUID | None = None,
        application_support_notes: str | None = None,
    ) -> InstitutionResponse:

        provisioner = self._institution_identity_provisioner()
        try:
            identity = provisioner.provision(request.email.casefold(), request.name)
        except InstitutionEmailExists as exc:
            raise ServiceError("INSTITUTION_EMAIL_EXISTS", 409) from exc
        except InstitutionProvisioningRollbackError as exc:
            raise ServiceError("INSTITUTION_PROVISION_ROLLBACK_FAILED", 503) from exc
        except InstitutionProvisioningError as exc:
            raise ServiceError("INSTITUTION_PROVISION_FAILED", 503) from exc
        except Exception as exc:
            raise ServiceError("INSTITUTION_PROVISION_FAILED", 503) from exc

        sender = self.email_verification_sender
        if sender is None or not hasattr(sender, "send_password_setup"):
            self._rollback_institution_identity(provisioner, identity.firebase_uid)
            raise ServiceError("INSTITUTION_FIRST_ACCESS_EMAIL_NOT_CONFIGURED", 503)
        try:
            delivery_result = sender.send_password_setup(
                identity.firebase_uid,
                identity.email.casefold(),
            )
        except Exception as exc:
            self._rollback_institution_identity(provisioner, identity.firebase_uid)
            raise ServiceError("INSTITUTION_FIRST_ACCESS_EMAIL_FAILED", 503) from exc
        if delivery_result != "SENT":
            self._rollback_institution_identity(provisioner, identity.firebase_uid)
            code = (
                "INSTITUTION_FIRST_ACCESS_EMAIL_NOT_CONFIGURED"
                if delivery_result == "NOT_CONFIGURED"
                else "INSTITUTION_FIRST_ACCESS_EMAIL_FAILED"
            )
            raise ServiceError(code, 503)

        now = datetime.now(timezone.utc)
        profile = InstitutionProfileRecord(
            firebase_uid=identity.firebase_uid,
            email=identity.email.casefold(),
            name=request.name,
            description=request.description,
            city=request.city,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        try:
            created = self.store.create_institution(
                profile,
                actor_uid=principal.uid,
                event_id=f"access:{uuid.uuid4()}",
                application_id=application_id,
                application_support_notes=application_support_notes,
            )
        except StoreConflict as exc:
            self._rollback_institution_identity(provisioner, identity.firebase_uid)
            code = str(exc)
            if code in {
                "ADMIN_ACCESS_REQUIRED",
                "SUPPORT_ACCESS_REQUIRED",
                "INSTITUTION_CREATOR_ACCESS_REQUIRED",
            }:
                raise ServiceError(code, 403) from exc
            if code not in {
                "INSTITUTION_ACCOUNT_EXISTS",
                "INSTITUTION_APPLICATION_NOT_APPROVABLE",
            }:
                code = "INSTITUTION_ACCOUNT_EXISTS"
            raise ServiceError(code, 409) from exc
        except Exception as exc:
            self._rollback_institution_identity(provisioner, identity.firebase_uid)
            raise ServiceError("ACCESS_STORE_WRITE_FAILED", 503) from exc
        return self._institution_response(created)

    def list_institutions(self, principal: Principal, limit: int) -> InstitutionListResponse:
        self._require_role_permission(
            principal,
            "admin",
            "admin.institutions.manage",
            "ADMIN_ACCESS_REQUIRED",
        )
        return InstitutionListResponse(
            institutions=[
                self._institution_response(profile)
                for profile in self.store.list_institutions(limit)
            ]
        )

    def list_admin_accounts(
        self,
        principal: Principal,
        limit: int,
    ) -> AdminAccountListResponse:
        self._require_role_permission(
            principal,
            "admin",
            "admin.accounts.manage",
            "ADMIN_ACCESS_REQUIRED",
        )
        return AdminAccountListResponse(
            accounts=[
                self._access_account_summary_response(account)
                for account in self.store.list_access_accounts(limit)
            ]
        )

    def admin_operations_summary(
        self,
        principal: Principal,
    ) -> AdminOperationsSummaryResponse:
        self._require_role_permission(
            principal,
            "admin",
            "admin.marketplace.manage",
            "ADMIN_ACCESS_REQUIRED",
        )
        try:
            summary = self.store.get_admin_operations_summary()
        except Exception as exc:
            raise ServiceError("OPERATIONS_SUMMARY_UNAVAILABLE", 503) from exc
        health = self.health()
        server_time = self.server_time()
        return AdminOperationsSummaryResponse(
            accounts_total=summary.accounts_total,
            accounts_by_role=summary.accounts_by_role,
            accounts_by_status=summary.accounts_by_status,
            institutions_total=summary.institutions_total,
            groups_total=summary.groups_total,
            groups_active=summary.groups_active,
            merchants_active=summary.merchants_active,
            merchants_suspended=summary.merchants_suspended,
            products_active=summary.products_active,
            offers_active=summary.offers_active,
            health_status=health.status,
            database_ok=health.database,
            redis_ok=health.redis,
            pqc_ready=health.pqc_ready,
            server_time_iso=server_time.server_time_iso,
        )

    def get_institution_profile(self, principal: Principal) -> InstitutionResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.profile.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        profile = self.store.get_institution_profile(principal.uid)
        if profile is None:
            raise ServiceError("INSTITUTION_PROFILE_NOT_FOUND", 404)
        return self._institution_response(profile)

    def update_institution_profile(
        self,
        principal: Principal,
        request: InstitutionProfileUpdateRequest,
    ) -> InstitutionResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.profile.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        if not request.model_fields_set:
            raise ServiceError("INSTITUTION_PROFILE_FIELDS_REQUIRED", 422)
        if "name" in request.model_fields_set and request.name is None:
            raise ServiceError("INSTITUTION_PROFILE_NAME_REQUIRED", 422)
        updates = {
            field: getattr(request, field)
            for field in request.model_fields_set
        }
        try:
            profile = self.store.update_institution_profile(
                principal.uid,
                updates,
                datetime.now(timezone.utc),
            )
        except StoreNotFound as exc:
            raise ServiceError("INSTITUTION_PROFILE_NOT_FOUND", 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            status_code = 403 if code == "INSTITUTION_PROFILE_ACCESS_REQUIRED" else 409
            raise ServiceError(code, status_code) from exc
        return self._institution_response(profile)

    def institution_report_summary(
        self,
        principal: Principal,
    ) -> InstitutionReportSummaryResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.reports.read",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        summary = self.store.get_institution_report_summary(principal.uid)
        return InstitutionReportSummaryResponse(
            total_groups=summary.total_groups,
            active_groups=summary.active_groups,
            closed_groups=summary.closed_groups,
            last_group_created_at=summary.last_group_created_at,
            generated_at=datetime.now(timezone.utc),
        )

    def create_institution_group(
        self,
        principal: Principal,
        request: InstitutionGroupCreateRequest,
    ) -> InstitutionGroupResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.groups.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        now = datetime.now(timezone.utc)
        group = InstitutionGroupRecord(
            group_id=f"IGRP-{secrets.token_hex(8).upper()}",
            owner_uid=principal.uid,
            name=request.name,
            description=request.description,
            city=request.city,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
            closed_at=None,
        )
        try:
            created = self.store.create_institution_group(group)
        except StoreConflict as exc:
            if str(exc) == "INSTITUTION_GROUP_ACCESS_REQUIRED":
                raise ServiceError("INSTITUTION_ACCESS_REQUIRED", 403) from exc
            raise ServiceError(str(exc), 409) from exc
        return self._institution_group_response(created)

    def list_institution_groups(
        self,
        principal: Principal,
        limit: int,
    ) -> InstitutionGroupListResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.groups.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        return InstitutionGroupListResponse(
            groups=[
                self._institution_group_response(group)
                for group in self.store.list_institution_groups(principal.uid, limit)
            ]
        )

    def close_institution_group(
        self,
        principal: Principal,
        group_id: str,
    ) -> InstitutionGroupResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.groups.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        try:
            group = self.store.close_institution_group(
                principal.uid,
                group_id,
                datetime.now(timezone.utc),
            )
        except StoreNotFound as exc:
            raise ServiceError("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED", 404) from exc
        except StoreConflict as exc:
            raise ServiceError("INSTITUTION_ACCESS_REQUIRED", 403) from exc
        return self._institution_group_response(group)

    def invite_institution_seller(
        self,
        principal: Principal,
        group_id: str,
        request: InstitutionSellerInvitationCreateRequest,
    ) -> InstitutionMembershipResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.groups.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        normalized_name = normalize_display_name(request.seller_name)
        if len(normalized_name) < 3:
            raise ServiceError("SELLER_NAME_INVALID", 422)
        now = datetime.now(timezone.utc)
        try:
            membership = self.store.invite_institution_seller(
                principal.uid,
                group_id,
                normalized_name,
                f"IGM-{secrets.token_hex(10).upper()}",
                now,
                f"membership-invite:{uuid.uuid4()}",
            )
        except StoreNotFound as exc:
            code = str(exc)
            raise ServiceError(code, 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            status = 403 if code == "INSTITUTION_GROUP_ACCESS_REQUIRED" else 409
            raise ServiceError(code, status) from exc
        return self._institution_membership_response(membership)

    def list_institution_group_memberships(
        self,
        principal: Principal,
        group_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> InstitutionMembershipListResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.groups.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        try:
            memberships, has_more = self.store.list_institution_group_memberships(
                principal.uid, group_id, status, limit, offset
            )
        except StoreNotFound as exc:
            raise ServiceError("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED", 404) from exc
        return InstitutionMembershipListResponse(
            memberships=[self._institution_membership_response(item) for item in memberships],
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    def list_entrepreneur_institution_memberships(
        self,
        principal: Principal,
        status: str | None,
        limit: int,
        offset: int,
    ) -> InstitutionMembershipListResponse:
        self._require_role_permission(
            principal,
            "entrepreneur",
            "institution.memberships.respond",
            "ENTREPRENEUR_ACCESS_REQUIRED",
        )
        memberships, has_more = self.store.list_entrepreneur_institution_memberships(
            principal.uid, status, limit, offset
        )
        return InstitutionMembershipListResponse(
            memberships=[self._institution_membership_response(item) for item in memberships],
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    def respond_institution_invitation(
        self,
        principal: Principal,
        membership_id: str,
        decision: str,
    ) -> InstitutionMembershipResponse:
        self._require_role_permission(
            principal,
            "entrepreneur",
            "institution.memberships.respond",
            "ENTREPRENEUR_ACCESS_REQUIRED",
        )
        now = datetime.now(timezone.utc)
        try:
            membership = self.store.respond_institution_invitation(
                principal.uid,
                membership_id,
                decision,
                now,
                f"membership-{decision.lower()}:{uuid.uuid4()}",
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            status = 403 if code == "INSTITUTION_MEMBERSHIP_ACCESS_REQUIRED" else 409
            raise ServiceError(code, status) from exc
        return self._institution_membership_response(membership)

    def leave_institution_membership(
        self,
        principal: Principal,
        membership_id: str,
    ) -> InstitutionMembershipResponse:
        self._require_role_permission(
            principal,
            "entrepreneur",
            "institution.memberships.respond",
            "ENTREPRENEUR_ACCESS_REQUIRED",
        )
        try:
            membership = self.store.leave_institution_membership(
                principal.uid,
                membership_id,
                datetime.now(timezone.utc),
                f"membership-left:{uuid.uuid4()}",
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        return self._institution_membership_response(membership)

    def remove_institution_group_member(
        self,
        principal: Principal,
        group_id: str,
        membership_id: str,
    ) -> InstitutionMembershipResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.groups.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        try:
            membership = self.store.remove_institution_group_member(
                principal.uid,
                group_id,
                membership_id,
                datetime.now(timezone.utc),
                f"membership-removed:{uuid.uuid4()}",
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            status = 403 if code == "INSTITUTION_GROUP_ACCESS_REQUIRED" else 409
            raise ServiceError(code, status) from exc
        return self._institution_membership_response(membership)

    def institution_sales_report(
        self,
        principal: Principal,
        group_id: str | None,
        period_from: datetime | None,
        period_to: datetime | None,
        limit: int,
        offset: int,
    ) -> InstitutionSalesReportResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.reports.read",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        now = datetime.now(timezone.utc)
        effective_to = period_to or now
        effective_from = period_from or (effective_to - timedelta(days=30))
        if effective_from.tzinfo is None or effective_to.tzinfo is None:
            raise ServiceError("REPORT_TIMEZONE_REQUIRED", 422)
        effective_from = effective_from.astimezone(timezone.utc)
        effective_to = effective_to.astimezone(timezone.utc)
        if effective_from >= effective_to:
            raise ServiceError("REPORT_PERIOD_INVALID", 422)
        if effective_to > now + timedelta(minutes=5):
            raise ServiceError("REPORT_FUTURE_PERIOD_NOT_ALLOWED", 422)
        if effective_to - effective_from > timedelta(days=366):
            raise ServiceError("REPORT_PERIOD_TOO_LARGE", 422)
        try:
            report = self.store.get_institution_sales_report(
                principal.uid,
                group_id,
                effective_from,
                effective_to,
                limit,
                offset,
            )
        except StoreNotFound as exc:
            raise ServiceError("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED", 404) from exc
        return InstitutionSalesReportResponse(
            period_from=effective_from,
            period_to=effective_to,
            group_filter=group_id,
            confirmed_redemptions=report.confirmed_redemptions,
            units_sold=report.units_sold,
            amounts_unavailable_count=report.amounts_unavailable_count,
            totals_by_currency=[
                self._institution_currency_total_response(total)
                for total in report.totals_by_currency
            ],
            sellers=[
                InstitutionSellerSalesResponse(
                    group_name=seller.group_name,
                    seller_name=seller.seller_name,
                    membership_status=seller.membership_status,
                    active_from=seller.active_from,
                    ended_at=seller.ended_at,
                    confirmed_redemptions=seller.confirmed_redemptions,
                    units_sold=seller.units_sold,
                    amounts_unavailable_count=seller.amounts_unavailable_count,
                    totals_by_currency=[
                        self._institution_currency_total_response(total)
                        for total in seller.totals_by_currency
                    ],
                )
                for seller in report.sellers
            ],
            limit=limit,
            offset=offset,
            has_more=report.has_more,
            generated_at=now,
            financial_notice=(
                "Valores finais esperados de resgates confirmados no LiberRotas; "
                "este relatorio nao comprova recebimento ou liquidacao financeira."
            ),
        )

    def create_institution_funded_event(
        self,
        principal: Principal,
        request: InstitutionFundedEventCreateRequest,
    ) -> InstitutionFundedEventResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.events.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        now = datetime.now(timezone.utc)
        starts_at = request.starts_at.astimezone(timezone.utc)
        ends_at = (
            request.ends_at.astimezone(timezone.utc)
            if request.ends_at is not None
            else None
        )
        event = InstitutionFundedEventRecord(
            event_id=f"IEVT-{secrets.token_hex(10).upper()}",
            owner_uid=principal.uid,
            institution_name="",
            group_id=request.group_id,
            group_name="",
            name=request.name,
            description=request.description,
            funding_source=request.funding_source,
            budget_amount_minor=request.budget_amount_minor,
            currency=request.currency,
            end_mode=request.end_mode,
            starts_at=starts_at,
            ends_at=ends_at,
            coupon_limit=request.coupon_limit,
            current_coupon_redemptions=0,
            status="DRAFT",
            end_reason=None,
            created_at=now,
            updated_at=now,
            activated_at=None,
            ended_at=None,
            seller_allocations=(),
        )
        try:
            created = self.store.create_institution_funded_event(event)
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            status = (
                403
                if code
                in {
                    "INSTITUTION_EVENT_ACCESS_REQUIRED",
                    "INSTITUTION_GROUP_ACCESS_REQUIRED",
                }
                else 409
            )
            raise ServiceError(code, status) from exc
        return self._institution_funded_event_response(created)

    def list_institution_funded_events(
        self,
        principal: Principal,
        limit: int,
    ) -> InstitutionFundedEventListResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.events.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        return InstitutionFundedEventListResponse(
            events=[
                self._institution_funded_event_response(event)
                for event in self.store.list_institution_funded_events(
                    principal.uid,
                    limit,
                )
            ]
        )

    def set_institution_event_seller_allocations(
        self,
        principal: Principal,
        event_id: str,
        request: InstitutionEventSellerAllocationUpdateRequest,
    ) -> InstitutionFundedEventResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.events.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        try:
            event = self.store.set_institution_event_seller_allocations(
                principal.uid,
                event_id,
                tuple(
                    (
                        allocation.seller_uid,
                        allocation.allocated_amount_minor,
                    )
                    for allocation in request.allocations
                ),
                datetime.now(timezone.utc),
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            raise ServiceError(
                code,
                403 if code == "INSTITUTION_EVENT_ACCESS_REQUIRED" else 409,
            ) from exc
        return self._institution_funded_event_response(event)

    def activate_institution_funded_event(
        self,
        principal: Principal,
        event_id: str,
    ) -> InstitutionFundedEventResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.events.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        try:
            event = self.store.activate_institution_funded_event(
                principal.uid,
                event_id,
                datetime.now(timezone.utc),
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            raise ServiceError(
                code,
                403 if code == "INSTITUTION_EVENT_ACCESS_REQUIRED" else 409,
            ) from exc
        return self._institution_funded_event_response(event)

    def end_institution_funded_event(
        self,
        principal: Principal,
        event_id: str,
    ) -> InstitutionFundedEventResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.events.manage",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        try:
            event = self.store.end_institution_funded_event(
                principal.uid,
                event_id,
                datetime.now(timezone.utc),
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            raise ServiceError(
                code,
                403 if code == "INSTITUTION_EVENT_ACCESS_REQUIRED" else 409,
            ) from exc
        return self._institution_funded_event_response(event)

    def list_entrepreneur_funded_events(
        self,
        principal: Principal,
        limit: int,
    ) -> EntrepreneurFundedEventListResponse:
        self._require_role_permission(
            principal,
            "entrepreneur",
            "institution.event_allocations.manage",
            "ENTREPRENEUR_ACCESS_REQUIRED",
        )
        return EntrepreneurFundedEventListResponse(
            events=[
                self._entrepreneur_funded_event_response(event, principal.uid)
                for event in self.store.list_entrepreneur_funded_events(
                    principal.uid,
                    limit,
                )
            ]
        )

    def set_institution_event_product_allocations(
        self,
        principal: Principal,
        event_id: str,
        request: InstitutionEventProductAllocationUpdateRequest,
    ) -> EntrepreneurFundedEventResponse:
        self._require_role_permission(
            principal,
            "entrepreneur",
            "institution.event_allocations.manage",
            "ENTREPRENEUR_ACCESS_REQUIRED",
        )
        try:
            event = self.store.set_institution_event_product_allocations(
                principal.uid,
                event_id,
                tuple(
                    (
                        allocation.product_id,
                        allocation.allocated_amount_minor,
                    )
                    for allocation in request.allocations
                ),
                datetime.now(timezone.utc),
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        return self._entrepreneur_funded_event_response(event, principal.uid)

    def entrepreneur_funded_event_report(
        self,
        principal: Principal,
        event_id: str,
    ) -> EntrepreneurFundedEventReportResponse:
        self._require_role_permission(
            principal,
            "entrepreneur",
            "institution.event_allocations.manage",
            "ENTREPRENEUR_ACCESS_REQUIRED",
        )
        generated_at = datetime.now(timezone.utc)
        events = self.store.list_entrepreneur_funded_events(principal.uid, 100)
        event = next((item for item in events if item.event_id == event_id), None)
        if event is None:
            raise ServiceError("INSTITUTION_FUNDED_EVENT_NOT_FOUND", 404)
        try:
            report = self.store.get_institution_funded_event_report(
                event.owner_uid,
                event_id,
                generated_at,
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        seller = next(
            (item for item in report.sellers if item.seller_uid == principal.uid),
            None,
        )
        if seller is None:
            raise ServiceError("INSTITUTION_FUNDED_EVENT_NOT_FOUND", 404)
        return EntrepreneurFundedEventReportResponse(
            event=self._entrepreneur_funded_event_response(report.event, principal.uid),
            confirmed_redemptions=seller.confirmed_redemptions,
            units_sold=seller.units_sold,
            gross_original_amount_minor=seller.gross_original_amount_minor,
            gross_final_amount_minor=seller.gross_final_amount_minor,
            discount_used_minor=seller.discount_used_minor,
            amount_due_minor=seller.amount_due_minor,
            unfunded_discount_minor=seller.unfunded_discount_minor,
            remaining_budget_minor=seller.remaining_budget_minor,
            products=[
                InstitutionFundedEventProductReportResponse(
                    product_id=product.product_id,
                    product_title=product.product_title,
                    allocated_amount_minor=product.allocated_amount_minor,
                    confirmed_redemptions=product.confirmed_redemptions,
                    units_sold=product.units_sold,
                    gross_original_amount_minor=product.gross_original_amount_minor,
                    gross_final_amount_minor=product.gross_final_amount_minor,
                    discount_used_minor=product.discount_used_minor,
                    amount_due_minor=product.amount_due_minor,
                    unfunded_discount_minor=product.unfunded_discount_minor,
                    remaining_budget_minor=product.remaining_budget_minor,
                )
                for product in seller.products
            ],
            generated_at=generated_at,
            financial_notice=(
                "O valor a receber representa descontos de cupons confirmados, "
                "limitados pela verba atribuida ao empreendedor e ao produto. "
                "Este relatorio nao executa pagamentos nem comprova liquidacao."
            ),
        )

    def institution_funded_event_report(
        self,
        principal: Principal,
        event_id: str,
    ) -> InstitutionFundedEventReportResponse:
        self._require_role_permission(
            principal,
            "institution",
            "institution.reports.read",
            "INSTITUTION_ACCESS_REQUIRED",
        )
        generated_at = datetime.now(timezone.utc)
        try:
            report = self.store.get_institution_funded_event_report(
                principal.uid,
                event_id,
                generated_at,
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        return InstitutionFundedEventReportResponse(
            event=self._institution_funded_event_response(report.event),
            confirmed_redemptions=report.confirmed_redemptions,
            units_sold=report.units_sold,
            gross_original_amount_minor=report.gross_original_amount_minor,
            gross_final_amount_minor=report.gross_final_amount_minor,
            discount_used_minor=report.discount_used_minor,
            amount_due_minor=report.amount_due_minor,
            unfunded_discount_minor=report.unfunded_discount_minor,
            remaining_budget_minor=report.remaining_budget_minor,
            sellers=[
                InstitutionFundedEventSellerReportResponse(
                    seller_uid=seller.seller_uid,
                    seller_name=seller.seller_name,
                    allocated_amount_minor=seller.allocated_amount_minor,
                    confirmed_redemptions=seller.confirmed_redemptions,
                    units_sold=seller.units_sold,
                    gross_original_amount_minor=(
                        seller.gross_original_amount_minor
                    ),
                    gross_final_amount_minor=seller.gross_final_amount_minor,
                    discount_used_minor=seller.discount_used_minor,
                    amount_due_minor=seller.amount_due_minor,
                    unfunded_discount_minor=seller.unfunded_discount_minor,
                    remaining_budget_minor=seller.remaining_budget_minor,
                    products=[
                        InstitutionFundedEventProductReportResponse(
                            product_id=product.product_id,
                            product_title=product.product_title,
                            allocated_amount_minor=(
                                product.allocated_amount_minor
                            ),
                            confirmed_redemptions=(
                                product.confirmed_redemptions
                            ),
                            units_sold=product.units_sold,
                            gross_original_amount_minor=(
                                product.gross_original_amount_minor
                            ),
                            gross_final_amount_minor=(
                                product.gross_final_amount_minor
                            ),
                            discount_used_minor=product.discount_used_minor,
                            amount_due_minor=product.amount_due_minor,
                            unfunded_discount_minor=(
                                product.unfunded_discount_minor
                            ),
                            remaining_budget_minor=(
                                product.remaining_budget_minor
                            ),
                        )
                        for product in seller.products
                    ],
                )
                for seller in report.sellers
            ],
            generated_at=generated_at,
            financial_notice=(
                "O valor a pagar representa descontos de cupons confirmados, "
                "limitados pela verba atribuida. Este relatorio nao executa "
                "pagamentos nem comprova liquidacao financeira."
            ),
        )

    def list_support_accounts(
        self,
        principal: Principal,
        limit: int,
    ) -> SupportAccountListResponse:
        self._require_role_permission(
            principal,
            "support",
            "support.accounts.read",
            "SUPPORT_ACCESS_REQUIRED",
        )
        return SupportAccountListResponse(
            accounts=[
                self._support_account_summary_response(account)
                for account in self.store.list_access_accounts(limit)
            ]
        )

    def list_security_accounts(
        self,
        principal: Principal,
        limit: int,
        events_limit: int,
    ) -> SecurityAccountListResponse:
        self._require_role_permission(
            principal,
            "security",
            "security.audit.read",
            "SECURITY_ACCESS_REQUIRED",
        )
        return SecurityAccountListResponse(
            accounts=[
                self._access_account_summary_response(account)
                for account in self.store.list_access_accounts(limit)
            ],
            recent_events=[
                self._access_audit_event_response(event)
                for event in self.store.list_access_audit_events(events_limit)
            ],
        )

    def security_monitoring_summary(
        self,
        principal: Principal,
        events_limit: int,
    ) -> SecurityMonitoringSummaryResponse:
        self._require_role_permission(
            principal,
            "security",
            "security.audit.read",
            "SECURITY_ACCESS_REQUIRED",
        )
        try:
            summary = self.store.get_security_monitoring_summary()
            recent_events = self.store.list_access_audit_events(events_limit)
        except Exception as exc:
            raise ServiceError("SECURITY_MONITORING_UNAVAILABLE", 503) from exc
        health = self.health()
        server_time = self.server_time()
        return SecurityMonitoringSummaryResponse(
            accounts_total=summary.accounts_total,
            active_accounts=summary.active_accounts,
            suspended_accounts=summary.suspended_accounts,
            pending_accounts=summary.pending_accounts,
            disabled_accounts=summary.disabled_accounts,
            recent_events_total=summary.recent_events_total,
            last_event_at=summary.last_event_at,
            recent_events=[
                self._access_audit_event_response(event)
                for event in recent_events
            ],
            health_status=health.status,
            database_ok=health.database,
            redis_ok=health.redis,
            pqc_ready=health.pqc_ready,
            server_time_iso=server_time.server_time_iso,
        )

    def trq_bec_security_status(
        self,
        principal: Principal,
    ) -> TrqBecSecurityStatusResponse:
        self._require_role_permission(
            principal,
            "security",
            "security.trq_bec.monitor",
            "SECURITY_ACCESS_REQUIRED",
        )
        try:
            summary = self.store.get_trq_bec_security_status()
        except Exception as exc:
            raise ServiceError("TRQ_BEC_MONITORING_UNAVAILABLE", 503) from exc
        health = self.health()
        provider = self.pqc_provider.status()
        return TrqBecSecurityStatusResponse(
            policy_version=self.settings.policy_version,
            environment=self.settings.environment,
            lab_suite_enabled=self.settings.lab_suite_enabled,
            token_revocation_checks_enabled=(
                self.settings.firebase_check_revoked
            ),
            database_ok=health.database,
            redis_ok=health.redis,
            pqc_provider_name=provider.name,
            pqc_provider_version=provider.version,
            pqc_ready=provider.ready,
            privileged_accounts_total=summary.privileged_accounts_total,
            official_accounts_total=summary.official_accounts_total,
            privileged_accounts_pending_validation=(
                summary.privileged_accounts_pending_validation
            ),
            access_events_total=summary.access_events_total,
            access_events_last_24h=summary.access_events_last_24h,
            audit_events_total=summary.audit_events_total,
            audit_checkpoints_total=summary.audit_checkpoints_total,
            devices_active=summary.devices_active,
            devices_pending=summary.devices_pending,
            devices_revoked=summary.devices_revoked,
            device_notifications_failed=(
                summary.device_notifications_failed
            ),
            email_verifications_pending=(
                summary.email_verifications_pending
            ),
            email_verifications_failed=summary.email_verifications_failed,
            latest_schema_migration=summary.latest_schema_migration,
            server_time_iso=self.server_time().server_time_iso,
        )

    def update_security_account_status(
        self,
        principal: Principal,
        target_uid: str,
        request: AccessAccountStatusRequest,
    ) -> AccessAccountSummaryResponse:
        self._require_role_permission(
            principal,
            "security",
            "security.incidents.manage",
            "SECURITY_ACCESS_REQUIRED",
        )
        if not self._auth_is_recent(principal):
            raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)

        target = self.store.get_access_account(target_uid)
        if target is None:
            raise ServiceError("ACCESS_ACCOUNT_NOT_FOUND", 404)
        if target_uid == principal.uid:
            raise ServiceError("SELF_STATUS_CHANGE_FORBIDDEN", 403)
        validation = self.store.get_privileged_account_validation(target_uid)
        if (
            target.role in {"admin", "security"}
            or (
                validation is not None
                and validation.protection_level == "SYSTEM"
            )
        ):
            raise ServiceError("PROTECTED_ACCOUNT_STATUS_CHANGE", 403)
        if target.status not in {"ACTIVE", "SUSPENDED"}:
            raise ServiceError("ACCOUNT_STATUS_TRANSITION_FORBIDDEN", 409)

        try:
            updated = self.store.update_access_account_status(
                principal.uid,
                target_uid,
                request.status,
                request.reason,
                event_id=f"access:{uuid.uuid4()}",
            )
        except StoreNotFound as exc:
            raise ServiceError("ACCESS_ACCOUNT_NOT_FOUND", 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            status_code = 403 if code in {
                "SECURITY_ACCESS_REQUIRED",
                "SELF_STATUS_CHANGE_FORBIDDEN",
                "PROTECTED_ACCOUNT_STATUS_CHANGE",
            } else 409
            raise ServiceError(code, status_code) from exc
        return self._access_account_summary_response(updated)

    def _append_event(
        self,
        *,
        operation_id: str,
        event_type: str,
        result: str,
        reason_codes: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        details: dict[str, Any] | None = None,
    ):
        return self.store.append_audit(
            operation_id=operation_id,
            suite_id=LAB_SUITE_ID,
            key_ref_token=self._issuer_key_ref(),
            event_type=event_type,
            result=result,
            reason_codes=reason_codes,
            evidence_refs=evidence_refs,
            details=details or {},
        )

    def enroll_device(self, principal: Principal, request: EnrollDeviceRequest) -> EnrollDeviceResponse:
        access = self._require_authorized_access(principal)
        assert access.role is not None
        device_role = access.role
        self._activate_due_devices(principal)
        approval_token = secrets.token_urlsafe(32)
        approval_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.device_auto_activation_delay_seconds
        )
        try:
            device, created, is_additional = self.store.enroll_device(
                principal.uid,
                request.device_key_id,
                request.public_key_b64u,
                request.algorithm,
                request.storage_profile,
                self._auth_is_recent(principal),
                device_name=request.device_name,
                platform=request.platform,
                model_name=request.model_name,
                app_version=request.app_version,
                approval_token_hash=self._device_approval_hash(approval_token),
                approval_expires_at=approval_expires_at,
                max_pending_devices=self.settings.device_max_pending_per_account,
                requires_approval=device_role != "visitor",
                first_device_requires_approval=(
                    device_role in {"entrepreneur", "institution"}
                ),
                operation_id=f"enroll:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="DEVICE_ENROLLMENT",
                reason_codes=(),
                evidence_refs=(),
                details={
                    "actor_ref": self._actor_ref(principal.uid),
                    "device_ref": self._device_ref(request.device_key_id),
                    "algorithm": request.algorithm,
                    "platform": request.platform,
                },
            )
        except StoreConflict as exc:
            code = str(exc)
            if code == "RECENT_AUTHENTICATION_REQUIRED":
                status_code = 403
            elif code == "PENDING_DEVICE_LIMIT_REACHED":
                status_code = 429
            else:
                status_code = 409
            raise ServiceError(code, status_code) from exc

        notification_status = device.notification_status
        notify_new_device = created and (
            is_additional
            or device_role in {"visitor", "entrepreneur", "institution"}
        )
        if notify_new_device:
            notification_status = self._send_device_approval(
                principal.uid,
                device,
                approval_token,
                activation_delay_seconds=(
                    0 if device_role == "visitor" else None
                ),
            )
        return EnrollDeviceResponse(
            device_key_id=device.device_key_id,
            status="ENROLLED" if created else "ALREADY_ENROLLED",
            key_ref=self._device_ref(device.device_key_id),
            device_status=device.status,
            is_new_device=created,
            is_additional_device=is_additional,
            notification_status=notification_status,
        )

    @staticmethod
    def _device_approval_hash(approval_token: str) -> str:
        return hashlib.sha256(
            b"LiberRotas/device-approval/v1\x00" + approval_token.encode("ascii")
        ).hexdigest()

    def _send_device_approval(
        self,
        uid: str,
        device: DeviceRecord,
        approval_token: str,
        activation_delay_seconds: int | None = None,
    ) -> str:
        if self.device_security_notifier is None:
            notification_status = "NOT_CONFIGURED"
        else:
            try:
                notification_status = self.device_security_notifier.send_new_device_approval(
                    uid,
                    device,
                    approval_token,
                    (
                        self.settings.device_auto_activation_delay_seconds
                        if activation_delay_seconds is None
                        else activation_delay_seconds
                    ),
                )
            except Exception:
                notification_status = "FAILED"
        if notification_status not in {
            "PENDING",
            "SENT",
            "NOT_CONFIGURED",
            "FAILED",
        }:
            notification_status = "FAILED"
        try:
            self.store.set_device_notification_status(
                uid,
                device.device_key_id,
                notification_status,
            )
        except Exception:
            # O resultado da entrega continua verdadeiro mesmo se a gravacao
            # do estado informativo falhar. O login nunca depende deste update.
            pass
        return notification_status

    def _account_device_response(self, device: DeviceRecord) -> AccountDeviceResponse:
        if device.created_at is None or device.last_seen_at is None:
            raise ServiceError("DEVICE_RECORD_INCOMPLETE", 503)
        return AccountDeviceResponse(
            device_key_id=device.device_key_id,
            key_ref=self._device_ref(device.device_key_id),
            device_name=device.device_name,
            platform=device.platform,
            model_name=device.model_name,
            app_version=device.app_version,
            storage_profile=device.storage_profile,
            status=device.status,
            notification_status=device.notification_status,
            created_at=device.created_at,
            last_seen_at=device.last_seen_at,
            revoked_at=device.revoked_at,
            approval_expires_at=device.approval_expires_at,
            approval_last_sent_at=device.approval_last_sent_at,
            approved_at=device.approved_at,
        )

    def _activate_due_devices(self, principal: Principal) -> None:
        try:
            self.store.activate_due_devices(
                principal.uid,
                datetime.now(timezone.utc),
                operation_id=f"device-auto-activation:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="DEVICE_AUTO_ACTIVATION",
                reason_codes=("SECURITY_COOLDOWN_COMPLETED",),
                evidence_refs=(),
                details={"actor_ref": self._actor_ref(principal.uid)},
            )
        except Exception as exc:
            raise ServiceError("DEVICE_AUTO_ACTIVATION_FAILED", 503) from exc

    def list_account_devices(self, principal: Principal) -> AccountDeviceListResponse:
        self._require_authorized_access(principal)
        self._activate_due_devices(principal)
        return AccountDeviceListResponse(
            devices=[
                self._account_device_response(device)
                for device in self.store.list_devices(principal.uid, 100)
            ]
        )

    def approve_account_device(
        self, principal: Principal, request: DeviceApprovalRequest
    ) -> DeviceApprovalResponse:
        self._require_authorized_access(principal)
        self._activate_due_devices(principal)
        try:
            device = self.store.approve_device(
                principal.uid,
                self._device_approval_hash(request.approval_token),
                datetime.now(timezone.utc),
                operation_id=f"device-approval:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="DEVICE_APPROVAL",
                reason_codes=(),
                evidence_refs=(),
                details={"actor_ref": self._actor_ref(principal.uid)},
            )
        except StoreConflict as exc:
            raise ServiceError("DEVICE_APPROVAL_INVALID_OR_EXPIRED", 400) from exc
        return DeviceApprovalResponse(
            status="DEVICE_APPROVED",
            device_key_id=device.device_key_id,
            device_status="ACTIVE",
        )

    def resend_device_approval(
        self, principal: Principal, request: DeviceApprovalResendRequest
    ) -> DeviceApprovalResendResponse:
        self._require_authorized_access(principal)
        self._activate_due_devices(principal)
        if not self._auth_is_recent(principal):
            raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)
        approval_token = secrets.token_urlsafe(32)
        approval_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.device_approval_ttl_seconds
        )
        try:
            device = self.store.rotate_device_approval(
                principal.uid,
                request.device_key_id,
                self._device_approval_hash(approval_token),
                approval_expires_at,
                self.settings.device_approval_resend_cooldown_seconds,
                operation_id=f"device-approval-resend:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="DEVICE_APPROVAL_RESEND",
                reason_codes=(),
                evidence_refs=(),
                details={
                    "actor_ref": self._actor_ref(principal.uid),
                    "device_ref": self._device_ref(request.device_key_id),
                },
            )
        except StoreNotFound as exc:
            raise ServiceError("DEVICE_NOT_FOUND", 404) from exc
        except StoreConflict as exc:
            code = str(exc)
            raise ServiceError(code, 429 if code == "APPROVAL_RESEND_COOLDOWN" else 409) from exc
        notification_status = self._send_device_approval(
            principal.uid,
            device,
            approval_token,
        )
        return DeviceApprovalResendResponse(
            device_key_id=device.device_key_id,
            device_status="PENDING_APPROVAL",
            notification_status=notification_status,
        )

    def revoke_all_account_devices(self, principal: Principal) -> RevokeAllDevicesResponse:
        self._require_authorized_access(principal)
        if not self._auth_is_recent(principal):
            raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)
        if self.account_session_revoker is None:
            raise ServiceError("SESSION_REVOCATION_UNAVAILABLE", 503)
        operation_id = f"revoke-devices:{uuid.uuid4()}"
        try:
            revoked_devices = self.store.revoke_all_devices(
                principal.uid,
                operation_id=operation_id,
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="DEVICE_KEYS_REVOKED",
                reason_codes=("USER_REQUESTED_PASSWORD_CHANGE",),
                evidence_refs=(),
                details={"actor_ref": self._actor_ref(principal.uid)},
            )
        except Exception as exc:
            raise ServiceError("DEVICE_REVOCATION_FAILED", 503) from exc
        try:
            self.account_session_revoker.revoke_all(principal.uid)
        except Exception as exc:
            # As chaves protegidas ja ficaram revogadas. Como o refresh token
            # ainda e valido quando o Firebase falha, a operacao pode ser
            # repetida com seguranca ate as sessoes tambem serem invalidadas.
            raise ServiceError("SESSION_REVOCATION_FAILED", 503) from exc
        try:
            self._append_event(
                operation_id=operation_id,
                event_type="FIREBASE_SESSIONS_REVOKED",
                result="REVOKED",
                reason_codes=("USER_REQUESTED_PASSWORD_CHANGE",),
                details={
                    "actor_ref": self._actor_ref(principal.uid),
                    "revoked_device_count": revoked_devices,
                },
            )
        except Exception:
            # A sessao Firebase e as chaves locais ja foram revogadas. Uma
            # indisponibilidade tardia do ledger nao pode converter esse
            # resultado de seguranca em uma falsa falha/rollback ao cliente.
            pass
        return RevokeAllDevicesResponse(
            status="ALL_DEVICES_REVOKED",
            revoked_devices=revoked_devices,
            sessions_revoked=True,
        )

    def prepare_account_deletion(self, principal: Principal) -> None:
        """Encerra recursos comerciais antes de o cliente apagar o Firebase Auth."""

        if not self._auth_is_recent(principal):
            raise ServiceError("RECENT_AUTHENTICATION_REQUIRED", 403)
        try:
            self.store.close_account(
                principal.uid,
                operation_id=f"account-closure:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="ACCOUNT_CLOSURE",
                result="CLOSED",
                reason_codes=("USER_REQUESTED_ACCOUNT_DELETION",),
                evidence_refs=(),
                details={"actor_ref": self._actor_ref(principal.uid)},
            )
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError("ACCOUNT_CLOSURE_FAILED", 503) from exc

    @staticmethod
    def _merchant_response(merchant: MerchantRecord) -> MerchantResponse:
        return MerchantResponse(
            firebase_uid=merchant.firebase_uid,
            display_name=merchant.display_name,
            establishment_id=merchant.establishment_id,
            establishment_name=merchant.establishment_name,
            status=merchant.status,
        )

    @staticmethod
    def _product_response(product: ProductRecord) -> ProductResponse:
        return ProductResponse(
            product_id=product.product_id,
            title=product.title,
            description=product.description,
            price_minor=product.price_minor,
            currency=product.currency,
            stock_quantity=product.stock_quantity,
            status=product.status,
        )

    @staticmethod
    def _catalog_merchant_summary(merchant: CatalogMerchantRecord) -> CatalogMerchantSummary:
        return CatalogMerchantSummary(
            firebase_uid=merchant.firebase_uid,
            display_name=merchant.display_name,
            establishment_name=merchant.establishment_name,
        )

    @staticmethod
    def _catalog_offer_summary(offer: CatalogOfferRecord) -> CatalogOfferSummary:
        return CatalogOfferSummary(
            offer_id=offer.offer_id,
            original_amount_minor=offer.original_amount_minor,
            discount_amount_minor=offer.discount_amount_minor,
            final_amount_minor=offer.final_amount_minor,
            currency=offer.currency,
            remaining_redemptions=offer.remaining_redemptions,
            expires_at=offer.expires_at,
            created_at=offer.created_at,
            updated_at=offer.updated_at,
            status=offer.status,
            status_reason=offer.status_reason,
            ended_at=offer.ended_at,
        )

    @classmethod
    def _catalog_product_item(cls, product: CatalogProductRecord) -> CatalogProductItem:
        return CatalogProductItem(
            product_id=product.product_id,
            title=product.title,
            description=product.description,
            price_minor=product.price_minor,
            currency=product.currency,
            stock_quantity=product.stock_quantity,
            created_at=product.created_at,
            updated_at=product.updated_at,
            status=product.status,
            status_reason=product.status_reason,
            ended_at=product.ended_at,
            merchant=cls._catalog_merchant_summary(product.merchant),
            offers=[cls._catalog_offer_summary(offer) for offer in product.offers],
        )

    def _require_active_merchant(self, principal: Principal) -> MerchantRecord:
        self._require_entrepreneur_permission(principal, "marketplace.manage")
        merchant = self.store.get_active_merchant(principal.uid)
        if merchant is None:
            raise ServiceError("MERCHANT_ACCOUNT_INACTIVE", 403)
        return merchant

    def set_merchant_status(self, principal: Principal, request: MerchantStatusRequest) -> MerchantResponse:
        if not principal.is_admin:
            raise ServiceError("ADMIN_CLAIM_REQUIRED", 403)
        self._require_permission(principal, "admin.marketplace.manage")
        try:
            merchant = self.store.set_merchant_status(
                MerchantRecord(
                    firebase_uid=request.firebase_uid,
                    display_name=request.display_name,
                    establishment_id=request.establishment_id,
                    establishment_name=request.establishment_name,
                    status=request.status,
                ),
                operation_id=f"merchant:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="MERCHANT_APPROVED" if request.status == "ACTIVE" else "MERCHANT_SUSPENDED",
                result=request.status,
                reason_codes=(),
                evidence_refs=(),
                details={
                    "admin_ref": self._actor_ref(principal.uid),
                    "merchant_ref": self._actor_ref(request.firebase_uid),
                    "establishment_id": request.establishment_id,
                },
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        return self._merchant_response(merchant)

    def create_product(self, principal: Principal, request: ProductCreateRequest) -> ProductResponse:
        self._require_active_merchant(principal)
        now = int(time.time())
        product_record = ProductRecord(
            product_id=f"PROD-{secrets.token_hex(8).upper()}",
            merchant_uid=principal.uid,
            title=request.title,
            description=request.description,
            price_minor=request.price_minor,
            currency=request.currency,
            stock_quantity=request.stock_quantity,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        try:
            product = self.store.create_product(
                product_record,
                operation_id=f"product:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="PRODUCT_CREATED",
                result="ACTIVE",
                reason_codes=(),
                evidence_refs=(),
                details={
                    "merchant_ref": self._actor_ref(principal.uid),
                    "product_id": product_record.product_id,
                    "price_minor": product_record.price_minor,
                    "currency": product_record.currency,
                    "stock_quantity": product_record.stock_quantity,
                },
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        return self._product_response(product)

    def list_products(self, principal: Principal) -> ProductListResponse:
        self._require_active_merchant(principal)
        return ProductListResponse(
            products=[
                self._product_response(item)
                for item in self.store.list_products(principal.uid)
                if item.status != "ARCHIVED"
            ]
        )

    def list_catalog_feed(self, principal: Principal, limit: int) -> CatalogFeedResponse:
        del principal  # O catálogo exige autenticação, mas não depende da função do usuário.
        return CatalogFeedResponse(
            items=[
                self._catalog_product_item(product)
                for product in self.store.list_public_catalog(limit)
            ]
        )

    def get_catalog_merchant_profile(
        self,
        principal: Principal,
        firebase_uid: str,
        limit: int,
    ) -> CatalogMerchantProfileResponse:
        del principal  # Qualquer identidade Firebase válida pode consultar dados públicos.
        result = self.store.get_public_merchant_catalog(firebase_uid, limit)
        if result is None:
            raise ServiceError("MERCHANT_PUBLIC_PROFILE_NOT_FOUND", 404)
        merchant, products = result
        return CatalogMerchantProfileResponse(
            merchant=self._catalog_merchant_summary(merchant),
            products=[self._catalog_product_item(product) for product in products],
        )

    def update_product_stock(
        self,
        principal: Principal,
        product_id: str,
        request: ProductStockRequest,
    ) -> ProductResponse:
        self._require_active_merchant(principal)
        try:
            product = self.store.update_product_stock(
                principal.uid,
                product_id,
                request.stock_quantity,
                operation_id=f"stock:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="PRODUCT_STOCK_UPDATED",
                result="UPDATED",
                reason_codes=(),
                evidence_refs=(),
                details={
                    "merchant_ref": self._actor_ref(principal.uid),
                    "product_id": product_id,
                    "stock_quantity": request.stock_quantity,
                },
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        return self._product_response(product)

    def archive_products_batch(
        self,
        principal: Principal,
        request: ProductBatchArchiveRequest,
    ) -> ProductBatchArchiveResponse:
        self._require_active_merchant(principal)
        operation_kind = "PRODUCT_ARCHIVE"
        command_hash = self._marketplace_batch_command_hash(operation_kind, request)
        try:
            prior = self.store.get_marketplace_batch_response(
                principal.uid,
                request.client_request_id,
                operation_kind,
                command_hash,
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        if prior is not None:
            return ProductBatchArchiveResponse.model_validate(prior)
        operation_id = f"product-batch:{uuid.uuid4()}"

        def response_factory(products: list[ProductRecord]) -> dict[str, Any]:
            return ProductBatchArchiveResponse(
                operation_id=operation_id,
                archived_count=len(products),
                products=[self._product_response(product) for product in products],
            ).model_dump(mode="json")

        try:
            response = self.store.archive_products_batch(
                principal.uid,
                tuple(request.product_ids),
                client_request_id=request.client_request_id,
                operation_kind=operation_kind,
                command_hash=command_hash,
                batch_operation_id=operation_id,
                response_factory=response_factory,
                operation_id=operation_id,
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="PRODUCT_BATCH_ARCHIVED",
                result="ARCHIVED",
                reason_codes=(),
                evidence_refs=(),
                details={
                    "merchant_ref": self._actor_ref(principal.uid),
                    "product_ids": list(request.product_ids),
                    "archived_count": len(request.product_ids),
                },
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        except Exception as exc:
            raise ServiceError("PRODUCT_BATCH_ARCHIVE_FAILED", 503) from exc
        return ProductBatchArchiveResponse.model_validate(response)

    def activate_products_batch(
        self,
        principal: Principal,
        request: ProductBatchActivateRequest,
    ) -> ProductBatchActivateResponse:
        self._require_active_merchant(principal)
        operation_kind = "PRODUCT_ACTIVATE"
        command_hash = self._marketplace_batch_command_hash(operation_kind, request)
        try:
            prior = self.store.get_marketplace_batch_response(
                principal.uid,
                request.client_request_id,
                operation_kind,
                command_hash,
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        if prior is not None:
            return ProductBatchActivateResponse.model_validate(prior)
        operation_id = f"product-activate-batch:{uuid.uuid4()}"

        def response_factory(products: list[ProductRecord]) -> dict[str, Any]:
            return ProductBatchActivateResponse(
                operation_id=operation_id,
                activated_count=len(products),
                products=[self._product_response(product) for product in products],
            ).model_dump(mode="json")

        product_stocks = tuple(
            (item.product_id, item.stock_quantity) for item in request.items
        )
        try:
            response = self.store.activate_products_batch(
                principal.uid,
                product_stocks,
                client_request_id=request.client_request_id,
                operation_kind=operation_kind,
                command_hash=command_hash,
                batch_operation_id=operation_id,
                response_factory=response_factory,
                operation_id=operation_id,
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="PRODUCT_BATCH_ACTIVATED",
                result="ACTIVE",
                reason_codes=(),
                evidence_refs=(),
                details={
                    "merchant_ref": self._actor_ref(principal.uid),
                    "product_ids": [item.product_id for item in request.items],
                    "stock_quantities": {
                        item.product_id: item.stock_quantity for item in request.items
                    },
                    "activated_count": len(request.items),
                },
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        except Exception as exc:
            raise ServiceError("PRODUCT_BATCH_ACTIVATE_FAILED", 503) from exc
        return ProductBatchActivateResponse.model_validate(response)

    def _offer_preview(self, offer: OfferRecord) -> OfferPreviewResponse:
        status = offer.status
        if status == "ACTIVE" and int(time.time()) >= offer.expires_at:
            status = "EXPIRED"
        # A oferta nunca pode anunciar mais resgates do que o estoque atual.
        # Isso também cobre reduções de estoque feitas depois da emissão do QR.
        remaining = (
            0
            if status in {"EXHAUSTED", "EXPIRED", "REVOKED", "CANCELLED"}
            else max(
                0,
                min(
                    offer.maximum_redemptions - offer.redeemed_count,
                    offer.stock_quantity,
                ),
            )
        )
        return OfferPreviewResponse(
            offer_id=offer.offer_id,
            product_id=offer.product_id,
            product_title=offer.product_title,
            merchant_name=offer.merchant_name,
            establishment_name=offer.establishment_name,
            original_amount_minor=offer.original_amount_minor,
            discount_type=offer.discount_type,
            discount_value=offer.discount_value,
            discount_amount_minor=offer.discount_amount_minor,
            final_amount_minor=offer.final_amount_minor,
            currency=offer.currency,
            maximum_redemptions=offer.maximum_redemptions,
            redeemed_count=offer.redeemed_count,
            remaining_redemptions=remaining,
            expires_at=offer.expires_at,
            purpose="LIVE_FAIR_DISCOUNT",
            status=status,
        )

    def _persist_offer_expiration(self, token_ref: str, offer_id: str) -> None:
        try:
            self.store.expire_offer(
                token_ref,
                operation_id=f"offer-expiry:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="OFFER_EXPIRED",
                result="EXPIRED",
                reason_codes=("OFFER_EXPIRED",),
                evidence_refs=(),
                details={"offer_id": offer_id},
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except Exception as exc:
            raise ServiceError("OFFER_EXPIRATION_COMMIT_FAILED", 503) from exc

    def list_offers(self, principal: Principal) -> OfferListResponse:
        self._require_active_merchant(principal)
        return OfferListResponse(offers=[self._offer_preview(item) for item in self.store.list_offers(principal.uid)])

    @staticmethod
    def _quantity_binding_value(
        token_ref: str,
        issuer_ref: str,
        expires_at: int,
        quantity: int,
    ) -> dict[str, Any]:
        return {
            "token_ref": token_ref,
            "issuer_ref": issuer_ref,
            "expires_at": expires_at,
            "quantity": quantity,
        }

    def _quantity_bound_qr(self, token: TokenRecord, quantity: int) -> CompactQrPayload:
        signature = self.signing_provider.sign(
            self.settings.issuer_key_id,
            domain_message(
                "TRQ-BEC/offer-purchase-quantity/v1",
                self._quantity_binding_value(
                    token.token_ref,
                    token.issuer_ref,
                    token.expires_at,
                    quantity,
                ),
            ),
            "token-signing",
        )
        return CompactQrPayload(
            token_ref=token.token_ref,
            issuer_ref=token.issuer_ref,
            expires_at=token.expires_at,
            quantity=quantity,
            quantity_proof_b64u=base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
        )

    def _verify_qr_quantity_binding(self, payload: CompactQrPayload) -> None:
        # QRs emitidos antes da quantidade autoritativa continuam válidos
        # exclusivamente para uma unidade.
        if payload.quantity_proof_b64u is None:
            if payload.quantity != 1:
                raise ServiceError("QR_QUANTITY_BINDING_REQUIRED", 400)
            return
        try:
            signature = base64.urlsafe_b64decode(
                payload.quantity_proof_b64u
                + "=" * (-len(payload.quantity_proof_b64u) % 4)
            )
        except (ValueError, TypeError) as exc:
            raise ServiceError("QR_QUANTITY_BINDING_INVALID", 400) from exc
        if len(signature) != 64 or not self.signing_provider.verify(
            self.settings.issuer_key_id,
            domain_message(
                "TRQ-BEC/offer-purchase-quantity/v1",
                self._quantity_binding_value(
                    payload.token_ref,
                    payload.issuer_ref,
                    payload.expires_at,
                    payload.quantity,
                ),
            ),
            signature,
            "token-signing",
        ):
            raise ServiceError("QR_QUANTITY_BINDING_INVALID", 400)

    def get_offer_qr(
        self,
        principal: Principal,
        offer_id: str,
        quantity: int = 1,
    ) -> OfferQrResponse:
        self._require_active_merchant(principal)
        offer = next(
            (
                item
                for item in self.store.list_offers(principal.uid)
                if item.offer_id == offer_id
            ),
            None,
        )
        if offer is None:
            raise ServiceError("OFFER_NOT_FOUND", 404)
        now = int(time.time())
        token = self.store.get_token(offer.token_ref)
        preview = self._offer_preview(offer)
        if (
            offer.status not in {"ACTIVE", "PAUSED"}
            or preview.status not in {"ACTIVE", "PAUSED"}
            or offer.merchant_status != "ACTIVE"
            or offer.product_status != "ACTIVE"
            or offer.stock_quantity <= 0
            or preview.remaining_redemptions <= 0
            or offer.expires_at <= now
            or token is None
            or token.token_ref != offer.token_ref
            or token.offer_id != offer.offer_id
            or token.issuer_uid != principal.uid
            or token.status != "ISSUED"
            or token.expires_at != offer.expires_at
            or token.expires_at <= now
        ):
            raise ServiceError("OFFER_QR_NOT_AVAILABLE", 409)
        if quantity > preview.remaining_redemptions:
            raise ServiceError("OFFER_QR_QUANTITY_EXCEEDS_AVAILABLE", 409)
        return OfferQrResponse(
            qr_payload=self._quantity_bound_qr(token, quantity),
            expires_at=token.expires_at,
            offer=preview.model_copy(update={"purchase_quantity": quantity}),
        )

    def revoke_offer(
        self,
        principal: Principal,
        offer_id: str,
    ) -> OfferPreviewResponse:
        self._require_active_merchant(principal)
        try:
            offer = self.store.revoke_offer(
                principal.uid,
                offer_id,
                operation_id=f"offer-revoke:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="OFFER_REVOKED_BY_OWNER",
                result="REVOKED",
                reason_codes=(),
                evidence_refs=(),
                details={
                    "merchant_ref": self._actor_ref(principal.uid),
                    "offer_id": offer_id,
                },
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        except Exception as exc:
            raise ServiceError("OFFER_REVOCATION_FAILED", 503) from exc
        return self._offer_preview(offer)

    def update_offer_status(
        self,
        principal: Principal,
        offer_id: str,
        request: OfferStatusRequest,
    ) -> OfferPreviewResponse:
        self._require_active_merchant(principal)
        try:
            offer = self.store.update_offer_status(
                principal.uid,
                offer_id,
                request.status,
                operation_id=f"offer-status:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type={
                    "ACTIVE": "OFFER_RESUMED",
                    "PAUSED": "OFFER_PAUSED",
                    "CANCELLED": "OFFER_CANCELLED",
                }[request.status],
                result=request.status,
                reason_codes=(),
                evidence_refs=(),
                details={"merchant_ref": self._actor_ref(principal.uid), "offer_id": offer_id},
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        return self._offer_preview(offer)

    def _offer_rotation_mutation(
        self,
        principal: Principal,
        offer: OfferRecord,
        *,
        new_discount_value: int,
        new_expires_at: int,
        now: int,
    ) -> tuple[OfferBatchMutationRecord, CompactQrPayload]:
        if offer.discount_type == "PERCENT":
            discount_amount = offer.original_amount_minor * new_discount_value // 100
        else:
            discount_amount = new_discount_value
        if discount_amount <= 0 or discount_amount >= offer.original_amount_minor:
            raise ServiceError("DISCOUNT_INVALID_FOR_AUTHORITATIVE_PRICE", 400)
        final_amount = offer.original_amount_minor - discount_amount
        ttl_seconds = new_expires_at - now
        if ttl_seconds < 30:
            raise ServiceError("OFFER_VALIDITY_TOO_SHORT", 400)
        if ttl_seconds > self.settings.live_offer_max_ttl_seconds:
            raise ServiceError("OFFER_VALIDITY_TOO_LONG", 400)
        intent = Intent(
            txn_id=f"offer-rotation:{uuid.uuid4()}",
            merchant_id=principal.uid,
            amount_minor=final_amount,
            currency=offer.currency,
            resource_ref=f"offer/{offer.offer_id}",
            purpose=offer.purpose,
        )
        envelope = None
        # O segundo pode virar entre o calculo e a emissao. Recalcular evita
        # alterar em um segundo o prazo exato solicitado para o lote.
        for _ in range(3):
            issuance_now = int(self.envelopes.clock())
            exact_ttl = new_expires_at - issuance_now
            if exact_ttl < 30:
                raise ServiceError("OFFER_VALIDITY_TOO_SHORT", 400)
            if exact_ttl > self.settings.live_offer_max_ttl_seconds:
                raise ServiceError("OFFER_VALIDITY_TOO_LONG", 400)
            candidate = self.envelopes.issue(
                intent,
                suite_id=LAB_SUITE_ID,
                key_id=self.settings.issuer_key_id,
                policy_version=self.settings.policy_version,
                issuer=self.settings.issuer,
                audience=self.settings.audience,
                ttl_seconds=exact_ttl,
            )
            if candidate.exp == new_expires_at:
                envelope = candidate
                break
        if envelope is None:
            raise ServiceError("SERVER_TIME_UNSTABLE", 503)
        token_ref = secrets.token_urlsafe(24)
        issuer_ref = self._actor_ref(principal.uid)
        token = TokenRecord(
            token_ref=token_ref,
            issuer_uid=principal.uid,
            issuer_ref=issuer_ref,
            coupon_id=None,
            offer_id=offer.offer_id,
            intent=intent.to_dict(),
            envelope=envelope.to_dict(),
            expires_at=envelope.exp,
            status="ISSUED",
            redeemed_operation_id=None,
        )
        mutation = OfferBatchMutationRecord(
            offer_id=offer.offer_id,
            expected_token_ref=offer.token_ref,
            expected_discount_type=offer.discount_type,
            expected_discount_value=offer.discount_value,
            expected_expires_at=offer.expires_at,
            new_discount_type=offer.discount_type,
            new_discount_value=new_discount_value,
            new_discount_amount_minor=discount_amount,
            new_final_amount_minor=final_amount,
            new_expires_at=envelope.exp,
            new_token=token,
        )
        return mutation, CompactQrPayload(
            token_ref=token_ref,
            issuer_ref=issuer_ref,
            expires_at=envelope.exp,
        )

    def batch_offer_actions(
        self,
        principal: Principal,
        request: OfferBatchActionRequest,
    ) -> OfferBatchActionResponse:
        self._require_active_merchant(principal)
        operation_kind = "OFFER_ACTION"
        command_hash = self._marketplace_batch_command_hash(operation_kind, request)
        try:
            prior = self.store.get_marketplace_batch_response(
                principal.uid,
                request.client_request_id,
                operation_kind,
                command_hash,
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        if prior is not None:
            return OfferBatchActionResponse.model_validate(prior)
        operation_id = f"offer-batch:{uuid.uuid4()}"
        offer_ids = tuple(request.offer_ids)
        audit = {
            "operation_id": operation_id,
            "suite_id": LAB_SUITE_ID,
            "key_ref_token": self._issuer_key_ref(),
            "event_type": {
                "DELETE": "OFFER_BATCH_REVOKED",
                "INCREASE_DISCOUNT": "OFFER_BATCH_DISCOUNT_INCREASED",
                "EXTEND_VALIDITY": "OFFER_BATCH_VALIDITY_EXTENDED",
            }[request.action],
            "result": request.action,
            "reason_codes": (),
            "evidence_refs": (),
            "details": {
                "merchant_ref": self._actor_ref(principal.uid),
                "offer_ids": list(offer_ids),
                "action": request.action,
                "updated_count": len(offer_ids),
                **(
                    {
                        "discount_type": request.discount_type,
                        "discount_delta": request.discount_delta,
                    }
                    if request.action == "INCREASE_DISCOUNT"
                    else {
                        "extension_minutes": request.extension_minutes,
                    }
                    if request.action == "EXTEND_VALIDITY"
                    else {}
                ),
            },
        }
        if request.action == "DELETE":
            def delete_response_factory(
                offers: list[OfferRecord],
            ) -> dict[str, Any]:
                return OfferBatchActionResponse(
                    operation_id=operation_id,
                    action=request.action,
                    updated_count=len(offers),
                    items=[
                        OfferBatchActionItemResponse(
                            offer=self._offer_preview(offer), qr_payload=None
                        )
                        for offer in offers
                    ],
                ).model_dump(mode="json")

            try:
                response = self.store.revoke_offers_batch(
                    principal.uid,
                    offer_ids,
                    client_request_id=request.client_request_id,
                    operation_kind=operation_kind,
                    command_hash=command_hash,
                    batch_operation_id=operation_id,
                    response_factory=delete_response_factory,
                    **audit,
                )
            except StoreNotFound as exc:
                raise ServiceError(str(exc), 404) from exc
            except StoreConflict as exc:
                raise ServiceError(str(exc), 409) from exc
            except Exception as exc:
                raise ServiceError("OFFER_BATCH_ACTION_FAILED", 503) from exc
            return OfferBatchActionResponse.model_validate(response)

        assert request.device_key_id is not None
        self._activate_due_devices(principal)
        if self.store.get_device(principal.uid, request.device_key_id) is None:
            raise ServiceError("DEVICE_NOT_ENROLLED", 403)
        if not self.settings.lab_suite_enabled:
            pq = self.pqc_provider.status()
            if not pq.ready:
                raise ServiceError("PQC_PROVIDER_NOT_READY", 503)
            raise ServiceError("PQC_ENVELOPE_ADAPTER_PENDING_APPROVAL", 503)
        try:
            current_offers = self.store.get_offers_for_batch(
                principal.uid, offer_ids
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc

        now = int(time.time())
        mutations: list[OfferBatchMutationRecord] = []
        qr_by_offer: dict[str, CompactQrPayload] = {}
        for offer in current_offers:
            if request.action == "INCREASE_DISCOUNT":
                assert request.discount_type is not None
                assert request.discount_delta is not None
                if offer.discount_type != request.discount_type:
                    raise ServiceError("OFFER_BATCH_DISCOUNT_TYPE_MISMATCH", 409)
                new_discount_value = offer.discount_value + request.discount_delta
                if (
                    offer.discount_type == "PERCENT"
                    and new_discount_value > 90
                ):
                    raise ServiceError("OFFER_BATCH_DISCOUNT_LIMIT_EXCEEDED", 400)
                if (
                    offer.discount_type == "FIXED_AMOUNT"
                    and new_discount_value >= offer.original_amount_minor
                ):
                    raise ServiceError("OFFER_BATCH_DISCOUNT_LIMIT_EXCEEDED", 400)
                new_expires_at = offer.expires_at
            else:
                assert request.extension_minutes is not None
                new_discount_value = offer.discount_value
                new_expires_at = (
                    offer.expires_at + request.extension_minutes * 60
                )
            mutation, qr_payload = self._offer_rotation_mutation(
                principal,
                offer,
                new_discount_value=new_discount_value,
                new_expires_at=new_expires_at,
                now=now,
            )
            mutations.append(mutation)
            qr_by_offer[offer.offer_id] = qr_payload

        def rotation_response_factory(
            offers: list[OfferRecord],
        ) -> dict[str, Any]:
            return OfferBatchActionResponse(
                operation_id=operation_id,
                action=request.action,
                updated_count=len(offers),
                items=[
                    OfferBatchActionItemResponse(
                        offer=self._offer_preview(offer),
                        qr_payload=qr_by_offer[offer.offer_id],
                    )
                    for offer in offers
                ],
            ).model_dump(mode="json")

        try:
            response = self.store.rotate_offers_batch(
                principal.uid,
                tuple(mutations),
                client_request_id=request.client_request_id,
                operation_kind=operation_kind,
                command_hash=command_hash,
                batch_operation_id=operation_id,
                response_factory=rotation_response_factory,
                **audit,
            )
        except StoreNotFound as exc:
            raise ServiceError(str(exc), 404) from exc
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        except Exception as exc:
            raise ServiceError("OFFER_BATCH_ACTION_FAILED", 503) from exc
        return OfferBatchActionResponse.model_validate(response)

    def issue_coupon(self, principal: Principal, request: IssueCouponRequest) -> IssueCouponResponse:
        merchant = self._require_active_merchant(principal)
        self._activate_due_devices(principal)
        if self.store.get_device(principal.uid, request.device_key_id) is None:
            raise ServiceError("DEVICE_NOT_ENROLLED", 403)
        product = self.store.get_product_for_offer(principal.uid, request.product_id)
        if product is None:
            raise ServiceError("PRODUCT_NOT_ACTIVE_OR_NOT_OWNED", 404)
        if not self.settings.lab_suite_enabled:
            pq = self.pqc_provider.status()
            if not pq.ready:
                raise ServiceError("PQC_PROVIDER_NOT_READY", 503)
            raise ServiceError("PQC_ENVELOPE_ADAPTER_PENDING_APPROVAL", 503)

        now = int(time.time())
        expires_at = int(request.valid_until.timestamp())
        ttl_seconds = expires_at - now
        if ttl_seconds < 30:
            raise ServiceError("OFFER_VALIDITY_TOO_SHORT", 400)
        if ttl_seconds > self.settings.live_offer_max_ttl_seconds:
            raise ServiceError("OFFER_VALIDITY_TOO_LONG", 400)
        if request.maximum_redemptions > product.stock_quantity:
            raise ServiceError("OFFER_LIMIT_EXCEEDS_STOCK", 409)

        if request.discount_type == "PERCENT":
            discount_amount = product.price_minor * request.discount_value // 100
        else:
            discount_amount = request.discount_value
        if discount_amount <= 0 or discount_amount >= product.price_minor:
            raise ServiceError("DISCOUNT_INVALID_FOR_AUTHORITATIVE_PRICE", 400)
        final_amount = product.price_minor - discount_amount
        offer_id = f"OFFER-{secrets.token_hex(8).upper()}"
        intent = Intent(
            txn_id=f"offer:{uuid.uuid4()}",
            merchant_id=principal.uid,
            amount_minor=final_amount,
            currency=product.currency,
            resource_ref=f"offer/{offer_id}",
            purpose=request.purpose,
        )
        envelope = self.envelopes.issue(
            intent,
            suite_id=LAB_SUITE_ID,
            key_id=self.settings.issuer_key_id,
            policy_version=self.settings.policy_version,
            issuer=self.settings.issuer,
            audience=self.settings.audience,
            ttl_seconds=ttl_seconds,
        )
        token_ref = secrets.token_urlsafe(24)
        issuer_ref = self._actor_ref(principal.uid)
        record = TokenRecord(
            token_ref=token_ref,
            issuer_uid=principal.uid,
            issuer_ref=issuer_ref,
            coupon_id=None,
            offer_id=offer_id,
            intent=intent.to_dict(),
            envelope=envelope.to_dict(),
            expires_at=envelope.exp,
            status="ISSUED",
            redeemed_operation_id=None,
        )
        offer = OfferRecord(
            offer_id=offer_id,
            token_ref=token_ref,
            merchant_uid=principal.uid,
            merchant_name=merchant.display_name,
            establishment_name=merchant.establishment_name,
            product_id=product.product_id,
            product_title=product.title,
            original_amount_minor=product.price_minor,
            discount_amount_minor=discount_amount,
            final_amount_minor=final_amount,
            currency=product.currency,
            maximum_redemptions=request.maximum_redemptions,
            redeemed_count=0,
            stock_quantity=product.stock_quantity,
            merchant_status=merchant.status,
            product_status=product.status,
            expires_at=envelope.exp,
            purpose=request.purpose,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
            discount_type=request.discount_type,
            discount_value=request.discount_value,
        )
        try:
            self.store.create_live_offer(
                offer,
                record,
                discount_type=request.discount_type,
                discount_value=request.discount_value,
                operation_id=f"issue:{uuid.uuid4()}",
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="COUPON_ISSUED",
                result="ISSUED",
                reason_codes=(),
                evidence_refs=(),
                details={
                    "actor_ref": issuer_ref,
                    "offer_id": offer_id,
                    "product_id": product.product_id,
                    "original_amount_minor": product.price_minor,
                    "discount_amount_minor": discount_amount,
                    "final_amount_minor": final_amount,
                    "maximum_redemptions": request.maximum_redemptions,
                    "expires_at": envelope.exp,
                },
            )
        except StoreConflict as exc:
            raise ServiceError(str(exc), 409) from exc
        qr = CompactQrPayload(
            token_ref=token_ref,
            issuer_ref=issuer_ref,
            expires_at=envelope.exp,
        )
        return IssueCouponResponse(
            offer_id=offer_id,
            qr_payload=qr,
            expires_at=envelope.exp,
            offer=self._offer_preview(offer),
        )

    def _load_valid_token(self, payload: CompactQrPayload) -> TokenRecord:
        self._verify_qr_quantity_binding(payload)
        token = self.store.get_token(payload.token_ref)
        if token is None:
            raise ServiceError("TOKEN_REFERENCE_UNKNOWN", 404)
        if token.issuer_ref != payload.issuer_ref or token.expires_at != payload.expires_at:
            raise ServiceError("QR_BINDING_MISMATCH", 400)
        if token.status == "EXPIRED" and token.offer_id:
            raise ServiceError("OFFER_EXPIRED", 410)
        if token.status != "ISSUED":
            raise ServiceError("TOKEN_NOT_REDEEMABLE", 409)
        if int(time.time()) > token.expires_at:
            if token.offer_id:
                self._persist_offer_expiration(token.token_ref, token.offer_id)
                raise ServiceError("OFFER_EXPIRED", 410)
            raise ServiceError("TOKEN_EXPIRED", 410)
        intent = Intent.from_dict(token.intent)
        envelope = CryptoEnvelope.from_dict(token.envelope)
        ok, reasons = self.envelopes.verify_preconditions(
            envelope,
            intent,
            expected_issuer=self.settings.issuer,
            expected_audience=self.settings.audience,
            expected_policy_version=self.settings.policy_version,
        )
        if not ok:
            raise ServiceError("TOKEN_CRYPTO_INVALID", 400, f"TOKEN_CRYPTO_INVALID:{','.join(reasons)}")
        if token.offer_id:
            offer = self.store.get_offer_by_token(token.token_ref)
            if offer is None:
                raise ServiceError("OFFER_NOT_FOUND", 404)
            if offer.merchant_status != "ACTIVE":
                raise ServiceError("MERCHANT_ACCOUNT_INACTIVE", 409)
            if offer.product_status != "ACTIVE" or offer.stock_quantity <= 0:
                raise ServiceError("PRODUCT_NOT_ACTIVE_OR_OUT_OF_STOCK", 409)
            preview = self._offer_preview(offer)
            if preview.status == "EXPIRED":
                self._persist_offer_expiration(token.token_ref, offer.offer_id)
                raise ServiceError("OFFER_EXPIRED", 410)
            if preview.status != "ACTIVE":
                raise ServiceError("OFFER_NOT_ACTIVE", 409)
            if preview.remaining_redemptions <= 0:
                raise ServiceError("OFFER_REDEMPTION_LIMIT_REACHED", 409)
            if payload.quantity > preview.remaining_redemptions:
                raise ServiceError("OFFER_QR_QUANTITY_EXCEEDS_AVAILABLE", 409)
        return token

    def preview_coupon(self, principal: Principal, request: PreviewCouponRequest) -> OfferPreviewResponse:
        del principal  # O token Firebase é exigido na fronteira; o preview não expõe UID nem segredo.
        token = self._load_valid_token(request.qr_payload)
        if not token.offer_id:
            raise ServiceError("OFFER_NOT_FOUND", 404)
        offer = self.store.get_offer_by_token(token.token_ref)
        if offer is None:
            raise ServiceError("OFFER_NOT_FOUND", 404)
        return self._offer_preview(offer).model_copy(
            update={"purchase_quantity": request.qr_payload.quantity}
        )

    def begin_redemption(self, principal: Principal, request: BeginRedemptionRequest) -> BeginRedemptionResponse:
        if not principal.is_visitor:
            raise ServiceError("VISITOR_CLAIM_REQUIRED", 403)
        self._require_permission(principal, "coupons.redeem")
        token = self._load_valid_token(request.qr_payload)
        if token.issuer_uid == principal.uid:
            raise ServiceError("SELF_REDEMPTION_FORBIDDEN", 403)
        self._activate_due_devices(principal)
        device = self.store.get_device(principal.uid, request.device_key_id)
        if device is None:
            raise ServiceError("DEVICE_NOT_ENROLLED", 403)
        operation_id = f"op:{uuid.uuid4()}"
        session_id = f"session:{uuid.uuid4()}"
        replay_jti = secrets.token_hex(16)
        try:
            challenge = self.distributed.issue_challenge(operation_id, self.settings.challenge_ttl_seconds)
        except Exception as exc:
            raise ServiceError("CHALLENGE_STORE_UNAVAILABLE", 503) from exc
        operation = OperationRecord(
            operation_id=operation_id,
            firebase_uid=principal.uid,
            session_id=session_id,
            token_ref=token.token_ref,
            device_key_id=device.device_key_id,
            challenge_id=str(challenge["challenge_id"]),
            replay_jti=replay_jti,
            expires_at=min(int(challenge["expires_at"]), int(time.time()) + self.settings.operation_ttl_seconds),
            status="PENDING",
            result={"purchase_quantity": request.qr_payload.quantity},
        )
        try:
            self.store.create_operation(
                operation,
                operation_id=operation_id,
                suite_id=LAB_SUITE_ID,
                key_ref_token=self._issuer_key_ref(),
                event_type="REDEMPTION_BEGUN",
                result="PENDING",
                reason_codes=(),
                evidence_refs=(),
                details={
                    "actor_ref": self._actor_ref(principal.uid),
                    "device_ref": self._device_ref(device.device_key_id),
                    "coupon_id": token.coupon_id,
                    "offer_id": token.offer_id,
                    "quantity": request.qr_payload.quantity,
                },
            )
        except StoreConflict as exc:
            try:
                self.distributed.consume_challenge(str(challenge["challenge_id"]), operation_id)
            except Exception:
                pass
            raise ServiceError(str(exc), 409) from exc
        except Exception:
            try:
                self.distributed.consume_challenge(str(challenge["challenge_id"]), operation_id)
            except Exception:
                pass
            raise
        envelope = CryptoEnvelope.from_dict(token.envelope)
        proof_message = device_proof_message(
            envelope,
            challenge,
            session_id,
            device.device_key_id,
            replay_jti,
        )
        offer = self.store.get_offer_by_token(token.token_ref)
        if offer is None:
            raise ServiceError("OFFER_NOT_FOUND", 404)
        return BeginRedemptionResponse(
            operation_id=operation_id,
            session_id=session_id,
            challenge=ChallengeResponse(
                challenge_id=str(challenge["challenge_id"]),
                expires_at=int(challenge["expires_at"]),
            ),
            proof_message_b64u=base64.urlsafe_b64encode(proof_message).rstrip(b"=").decode("ascii"),
            offer=self._offer_preview(offer).model_copy(
                update={"purchase_quantity": request.qr_payload.quantity}
            ),
        )

    def _deny(
        self,
        operation_id: str,
        code: str,
        *,
        crypto_ok: bool = False,
        coupon_id: str | None = None,
        offer_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuthorizationResponse:
        event_ref = None
        try:
            event = self._append_event(
                operation_id=operation_id,
                event_type="REDEMPTION_AUTHORIZATION",
                result="DENY",
                reason_codes=(code,),
                details=details or {},
            )
            event_ref = event.event_id
        except LedgerError:
            pass
        return AuthorizationResponse(
            decision="DENY",
            operation_id=operation_id,
            crypto_ok=crypto_ok,
            reason_codes=[code],
            coupon_id=coupon_id,
            offer_id=offer_id,
            event_ref=event_ref,
        )

    def _abort_replay_best_effort(self, envelope: CryptoEnvelope, operation: OperationRecord) -> None:
        try:
            self.distributed.abort_replay(envelope.iss, operation.replay_jti, operation.operation_id)
        except Exception:
            pass

    def _finalize_consumed_denial(
        self,
        operation: OperationRecord,
        token: TokenRecord,
        envelope: CryptoEnvelope,
        code: str,
        actor_ref: str,
        device_ref: str,
    ) -> AuthorizationResponse:
        current = self.store.get_operation(operation.operation_id)
        if current is not None and current.status != "PENDING" and current.result:
            prior = AuthorizationResponse.model_validate(current.result)
            return prior.model_copy(update={"idempotent": True})
        denied = AuthorizationResponse(
            decision="DENY",
            operation_id=operation.operation_id,
            crypto_ok=True,
            reason_codes=[code],
            coupon_id=token.coupon_id or token.offer_id,
            offer_id=token.offer_id,
        )
        try:
            _, denied_result = self.store.finalize_authorization(
                operation.operation_id,
                token.token_ref,
                "DENY",
                denied.model_dump(mode="json"),
                suite_id=envelope.suite_id,
                key_ref_token=self._issuer_key_ref(),
                event_type="REDEMPTION_AUTHORIZATION",
                reason_codes=(code,),
                evidence_refs=(),
                details={
                    "actor_ref": actor_ref,
                    "device_ref": device_ref,
                    "coupon_id": token.coupon_id,
                    "offer_id": token.offer_id,
                },
            )
        except (StoreConflict, StoreNotFound, LedgerError) as exc:
            self._abort_replay_best_effort(envelope, operation)
            raise ServiceError("AUTHORIZATION_DENIAL_COMMIT_FAILED", 503) from exc
        denied = AuthorizationResponse.model_validate(denied_result)
        try:
            committed = self.distributed.commit_replay(
                envelope.iss,
                operation.replay_jti,
                operation.operation_id,
                denied.model_dump(mode="json"),
                self.settings.replay_ttl_seconds,
            )
        except Exception:
            committed = False
        if not committed:
            denied = denied.model_copy(
                update={"reason_codes": [*denied.reason_codes, "REPLAY_CACHE_COMMIT_DEGRADED"]}
            )
        return denied

    def authorize_redemption(
        self,
        principal: Principal,
        request: AuthorizeRedemptionRequest,
    ) -> AuthorizationResponse:
        if not principal.is_visitor:
            raise ServiceError("VISITOR_CLAIM_REQUIRED", 403)
        self._require_permission(principal, "coupons.redeem")
        operation = self.store.get_operation(request.operation_id)
        if operation is None:
            raise ServiceError("OPERATION_UNKNOWN", 404)
        if operation.status != "PENDING" and operation.result:
            prior = AuthorizationResponse.model_validate(operation.result)
            return prior.model_copy(update={"idempotent": True})
        if int(time.time()) > operation.expires_at:
            return self._deny(request.operation_id, "OPERATION_EXPIRED")
        if (
            operation.firebase_uid != principal.uid
            or operation.session_id != request.session_id
            or operation.device_key_id != request.device_key_id
            or operation.challenge_id != request.challenge_id
        ):
            return self._deny(request.operation_id, "OPERATION_BINDING_MISMATCH")

        token = self.store.get_token(operation.token_ref)
        self._activate_due_devices(principal)
        device = self.store.get_device(principal.uid, request.device_key_id)
        if token is None or device is None:
            return self._deny(request.operation_id, "TOKEN_OR_DEVICE_UNAVAILABLE")
        envelope = CryptoEnvelope.from_dict(token.envelope)
        intent = Intent.from_dict(token.intent)
        crypto_ok, crypto_reasons = self.envelopes.verify_preconditions(
            envelope,
            intent,
            expected_issuer=self.settings.issuer,
            expected_audience=self.settings.audience,
            expected_policy_version=self.settings.policy_version,
        )
        if not crypto_ok:
            return self._deny(request.operation_id, crypto_reasons[0] if crypto_reasons else "CRYPTO_INVALID")

        try:
            replay = self.distributed.reserve_replay(
                envelope.iss,
                operation.replay_jti,
                request.operation_id,
                self.settings.replay_ttl_seconds,
            )
        except Exception as exc:
            raise ServiceError("REPLAY_STORE_UNAVAILABLE", 503) from exc
        if replay is ReplayStatus.REPLAY:
            return self._deny(request.operation_id, "REPLAY", coupon_id=token.coupon_id or token.offer_id)
        if replay is ReplayStatus.SAME_OP:
            try:
                cached = self.distributed.get_replay_result(
                    envelope.iss,
                    operation.replay_jti,
                    request.operation_id,
                )
            except Exception:
                cached = None
            if cached:
                prior = AuthorizationResponse.model_validate(cached)
                return prior.model_copy(update={"idempotent": True})
            current = self.store.get_operation(request.operation_id)
            if current is not None and current.status != "PENDING" and current.result:
                prior = AuthorizationResponse.model_validate(current.result)
                return prior.model_copy(update={"idempotent": True})
            # Outra requisição da mesma operação ainda está em andamento.
            # Não gravamos uma negativa falsa nem consumimos evidência extra.
            raise ServiceError("OPERATION_IN_PROGRESS", 409)

        try:
            challenge = self.distributed.get_challenge(request.challenge_id, request.operation_id)
        except Exception as exc:
            self._abort_replay_best_effort(envelope, operation)
            raise ServiceError("CHALLENGE_STORE_UNAVAILABLE", 503) from exc
        if challenge is None:
            self._abort_replay_best_effort(envelope, operation)
            return self._deny(request.operation_id, "FRESHNESS_CHALLENGE_INVALID")
        proof_message = device_proof_message(
            envelope,
            challenge,
            request.session_id,
            request.device_key_id,
            operation.replay_jti,
        )
        if not verify_device_signature(device.public_key_b64u, proof_message, request.device_proof_b64u):
            self._abort_replay_best_effort(envelope, operation)
            return self._deny(request.operation_id, "DEVICE_PROOF_INVALID")
        try:
            consumed = self.distributed.consume_challenge(request.challenge_id, request.operation_id)
        except Exception as exc:
            self._abort_replay_best_effort(envelope, operation)
            raise ServiceError("CHALLENGE_STORE_UNAVAILABLE", 503) from exc
        if not consumed:
            self._abort_replay_best_effort(envelope, operation)
            return self._deny(request.operation_id, "FRESHNESS_CONSUME_FAILED")

        now = int(time.time())
        actor_ref = self._actor_ref(principal.uid)
        device_ref = self._device_ref(request.device_key_id)
        try:
            rate_high = self.distributed.rate_is_high(
                actor_ref,
                self.settings.rate_window_seconds,
                self.settings.rate_high_threshold,
            )
        except Exception:
            return self._finalize_consumed_denial(
                operation,
                token,
                envelope,
                "RATE_STORE_UNAVAILABLE",
                actor_ref,
                device_ref,
            )
        observations = [
            Observation("device_key_known", "true", "firebase-backend", now, now + 30, 10_000, 10_000, f"evidence:{device_ref}"),
            Observation("session_context_changed", "false", "firebase-backend", now, now + 30, 9_000, 10_000, f"evidence:session:{request.operation_id}"),
            Observation("rate_increase", str(rate_high).lower(), "firebase-backend", now, now + 30, 9_000, 10_000, f"evidence:rate:{request.operation_id}"),
            Observation("collector_health_ok", "true", "firebase-backend", now, now + 30, 10_000, 10_000, f"evidence:health:{request.operation_id}"),
        ]
        risk_result = self.risk.evaluate(observations)
        decision = Decision.DENY if rate_high else self.policy.decide(True, risk_result)
        reason_codes = list(risk_result.reason_codes)
        if rate_high and "RATE_LIMIT_EXCEEDED" not in reason_codes:
            reason_codes.append("RATE_LIMIT_EXCEEDED")
        response = AuthorizationResponse(
            decision=decision.value,
            operation_id=request.operation_id,
            crypto_ok=True,
            reason_codes=reason_codes,
            coupon_id=(token.coupon_id or token.offer_id) if decision is Decision.ALLOW else None,
            offer_id=token.offer_id if decision is Decision.ALLOW else None,
        )
        try:
            event, committed_result = self.store.finalize_authorization(
                request.operation_id,
                token.token_ref,
                decision.value,
                response.model_dump(mode="json"),
                suite_id=envelope.suite_id,
                key_ref_token=self._issuer_key_ref(),
                event_type="REDEMPTION_AUTHORIZATION",
                reason_codes=tuple(reason_codes),
                evidence_refs=risk_result.evidence_refs,
                details={
                    "actor_ref": actor_ref,
                    "device_ref": device_ref,
                    "coupon_id": token.coupon_id,
                    "risk_bps": risk_result.risk_bps,
                    "coverage_bps": risk_result.coverage_bps,
                    "detector_version": risk_result.detector_version,
                },
            )
        except StoreConflict as exc:
            # A prova e o desafio já foram consumidos. Persistimos a negativa
            # na mesma máquina de idempotência para não deixar a operação
            # indefinidamente PENDING quando estoque/limite muda na corrida.
            code = str(exc)
            if code == "OFFER_EXPIRED" and token.offer_id:
                self._persist_offer_expiration(token.token_ref, token.offer_id)
            return self._finalize_consumed_denial(
                operation,
                token,
                envelope,
                code,
                actor_ref,
                device_ref,
            )
        response = AuthorizationResponse.model_validate(committed_result)
        try:
            committed = self.distributed.commit_replay(
                envelope.iss,
                operation.replay_jti,
                request.operation_id,
                response.model_dump(mode="json"),
                self.settings.replay_ttl_seconds,
            )
        except Exception:
            committed = False
        if not committed:
            response = response.model_copy(
                update={"reason_codes": [*response.reason_codes, "REPLAY_CACHE_COMMIT_DEGRADED"]}
            )
        return response

    def checkpoint(self, principal: Principal) -> dict[str, Any]:
        if not principal.is_admin:
            raise ServiceError("ADMIN_CLAIM_REQUIRED", 403)
        self._require_permission(principal, "ledger.checkpoint.create")
        try:
            return self.store.create_checkpoint(self.settings.checkpoint_key_id, self.settings.policy_version)
        except LedgerError as exc:
            raise ServiceError(str(exc), 409) from exc
