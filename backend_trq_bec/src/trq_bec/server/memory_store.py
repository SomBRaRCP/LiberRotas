"""Thread-safe durable-store test double used by API regression tests."""

from __future__ import annotations

import base64
import copy
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..canonical import domain_message, sha3_hex
from ..contracts import CryptoEnvelope
from ..errors import LedgerError
from .access_control import default_permissions
from .catalog_state import offer_public_state, product_public_state
from .institution_badges import allocate_by_badges
from .models import (
    InstitutionBadgePolicy,
    InstitutionBadgeDistribution,
    AccessAccountRecord,
    AccessAccountSummaryRecord,
    AccessAuditEventRecord,
    AdminOperationsSummaryRecord,
    AuditRecord,
    CatalogMerchantRecord,
    CatalogOfferRecord,
    CatalogProductRecord,
    CommunityCommentRecord,
    CouponRecord,
    DeviceRecord,
    EmailVerificationQueueRecord,
    InstitutionApplicationRecord,
    InstitutionGroupRecord,
    InstitutionFundedEventProductAllocationRecord,
    InstitutionFundedEventProductReportRecord,
    InstitutionFundedEventRecord,
    InstitutionFundedEventReportRecord,
    InstitutionFundedEventSellerAllocationRecord,
    InstitutionFundedEventSellerReportRecord,
    InstitutionMembershipRecord,
    InstitutionProfileRecord,
    InstitutionReportSummaryRecord,
    InstitutionSalesCurrencyTotalRecord,
    InstitutionSalesReportRecord,
    InstitutionSellerSalesRecord,
    MediaAssetRecord,
    MediaVariantRecord,
    MerchantRecord,
    OfferRecord,
    OfferBatchMutationRecord,
    OperationRecord,
    ProductRecord,
    PrivilegedAccountValidationRecord,
    PublicProfileRecord,
    GlobalSearchItemRecord,
    ConversationRecord,
    PrivateMessageRecord,
    MessageBlockRecord,
    SecurityMonitoringSummaryRecord,
    TrqBecSecurityStatusRecord,
    TokenRecord,
)
from .store import StoreConflict, StoreNotFound
from .directory import normalize_display_name


class MemoryDurableStore:
    def __init__(self, signing_provider) -> None:
        self.signing_provider = signing_provider
        self.devices: dict[str, DeviceRecord] = {}
        self.device_approval_hashes: dict[str, str] = {}
        self.coupons = {
            f"FEITUR-{number:03d}": CouponRecord(f"FEITUR-{number:03d}", None, True, None)
            for number in range(1, 5)
        }
        self.tokens: dict[str, TokenRecord] = {}
        self.operations: dict[str, OperationRecord] = {}
        self.access_accounts: dict[str, AccessAccountRecord] = {}
        self.access_account_times: dict[str, tuple[datetime, datetime]] = {}
        self.privileged_account_validations: dict[
            str, PrivilegedAccountValidationRecord
        ] = {}
        self.email_verification_queue: dict[uuid.UUID, EmailVerificationQueueRecord] = {}
        self.institution_profiles: dict[str, InstitutionProfileRecord] = {}
        self.institution_applications: dict[uuid.UUID, InstitutionApplicationRecord] = {}
        self.institution_groups: dict[str, InstitutionGroupRecord] = {}
        self.institution_memberships: dict[str, InstitutionMembershipRecord] = {}
        self.institution_funded_events: dict[
            str, InstitutionFundedEventRecord
        ] = {}
        self.institution_membership_events: list[dict[str, Any]] = []
        self.access_audit_events: list[AccessAuditEventRecord] = []
        self.merchants: dict[str, MerchantRecord] = {}
        self.products: dict[str, ProductRecord] = {}
        self.offers: dict[str, OfferRecord] = {}
        self.public_profiles: dict[str, PublicProfileRecord] = {}
        self.community_post_search: dict[str, tuple[str, str, datetime, bool]] = {}
        self.community_comments: dict[str, CommunityCommentRecord] = {}
        self.community_comment_idempotency: dict[tuple[str, str], str] = {}
        self.community_comment_likes: set[tuple[str, str]] = set()
        self.conversations: dict[str, ConversationRecord] = {}
        self.private_messages: dict[str, list[PrivateMessageRecord]] = {}
        self.message_idempotency: dict[tuple[str, str], PrivateMessageRecord] = {}
        self.marketplace_batch_idempotency: dict[
            tuple[str, str], tuple[str, str, dict[str, Any]]
        ] = {}
        self.conversation_reads: dict[tuple[str, str], datetime] = {}
        self.message_blocks: dict[tuple[str, str], MessageBlockRecord] = {}
        self.media_assets: dict[str, MediaAssetRecord] = {}
        self.media_variants: dict[tuple[str, str], MediaVariantRecord] = {}
        self.media_client_requests: dict[tuple[str, str], str] = {}
        self.redemptions: dict[tuple[str, str], dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def ping(self) -> bool:
        return True

    def _owned_media_asset(
        self,
        media_id: str,
        owner_uid: str | None = None,
    ) -> MediaAssetRecord:
        asset = self.media_assets.get(media_id)
        if asset is None or (
            owner_uid is not None and asset.owner_user_id != owner_uid
        ):
            raise StoreNotFound("MEDIA_ASSET_NOT_FOUND")
        return asset

    def create_media_asset(self, asset: MediaAssetRecord) -> MediaAssetRecord:
        with self._lock:
            request_key = (asset.owner_user_id, asset.client_request_id)
            if asset.status != "pending" or asset.version != 1:
                raise StoreConflict("MEDIA_ASSET_INITIAL_STATE_INVALID")
            if (
                asset.media_id in self.media_assets
                or request_key in self.media_client_requests
                or any(
                    existing.bucket_name == asset.bucket_name
                    and existing.object_key == asset.object_key
                    for existing in self.media_assets.values()
                )
            ):
                raise StoreConflict("MEDIA_ASSET_ALREADY_EXISTS")
            if (
                asset.owner_user_id not in self.access_accounts
                or asset.created_by not in self.access_accounts
            ):
                raise StoreConflict("MEDIA_ASSET_ACCOUNT_NOT_FOUND")
            self.media_assets[asset.media_id] = asset
            self.media_client_requests[request_key] = asset.media_id
            return asset

    def get_media_asset(self, media_id: str) -> MediaAssetRecord | None:
        with self._lock:
            return self.media_assets.get(media_id)

    def get_media_asset_with_variant(
        self,
        media_id: str,
        variant: str,
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]:
        with self._lock:
            return (
                self.media_assets.get(media_id),
                self.media_variants.get((media_id, variant)),
            )

    def get_latest_ready_media_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        media_role: str,
        variant: str,
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]:
        with self._lock:
            candidates = [
                asset
                for asset in self.media_assets.values()
                if asset.entity_type == entity_type
                and asset.entity_id == entity_id
                and asset.media_role == media_role
                and asset.status == "ready"
            ]
            if not candidates:
                return None, None
            asset = max(
                candidates,
                key=lambda item: (item.created_at, item.media_id),
            )
            return asset, self.media_variants.get((asset.media_id, variant))

    def replace_media_variants(
        self,
        media_id: str,
        variants: list[MediaVariantRecord],
    ) -> list[MediaVariantRecord]:
        if {variant.variant for variant in variants} != {"thumbnail", "display"}:
            raise StoreConflict("MEDIA_VARIANTS_INCOMPLETE")
        with self._lock:
            asset = self._owned_media_asset(media_id)
            if asset.status not in {"processing", "ready"}:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            for variant in variants:
                if variant.media_id != media_id:
                    raise StoreConflict("MEDIA_VARIANT_ASSET_MISMATCH")
                self.media_variants[(media_id, variant.variant)] = variant
            return self.list_media_variants(media_id)

    def list_media_variants(self, media_id: str) -> list[MediaVariantRecord]:
        with self._lock:
            return [
                variant
                for name in ("thumbnail", "display")
                if (variant := self.media_variants.get((media_id, name))) is not None
            ]

    def get_media_asset_by_client_request(
        self,
        owner_uid: str,
        client_request_id: str,
    ) -> MediaAssetRecord | None:
        with self._lock:
            media_id = self.media_client_requests.get(
                (owner_uid, client_request_id)
            )
            return None if media_id is None else self.media_assets.get(media_id)

    def count_pending_media(self, owner_uid: str) -> int:
        now = datetime.now(timezone.utc)
        with self._lock:
            return sum(
                1
                for asset in self.media_assets.values()
                if asset.owner_user_id == owner_uid
                and asset.status in {"pending", "uploaded", "processing"}
                and asset.upload_expires_at > now
            )

    def count_ready_media(
        self,
        entity_type: str,
        entity_id: str,
        media_role: str,
    ) -> int:
        with self._lock:
            return sum(
                1
                for asset in self.media_assets.values()
                if asset.entity_type == entity_type
                and asset.entity_id == entity_id
                and asset.media_role == media_role
                and asset.status == "ready"
            )

    def mark_media_processing(
        self,
        media_id: str,
        owner_uid: str,
        uploaded_at: datetime,
        size_bytes: int,
        detected_content_type: str,
        crc32c: str | None,
        object_generation: int | None,
    ) -> MediaAssetRecord:
        with self._lock:
            current = self._owned_media_asset(media_id, owner_uid)
            metadata_matches = (
                current.size_bytes == size_bytes
                and current.detected_content_type == detected_content_type
                and current.crc32c == crc32c
                and current.object_generation == object_generation
            )
            if current.status in {"processing", "ready"} and metadata_matches:
                return current
            if (
                current.status != "pending"
                or current.upload_expires_at <= uploaded_at
            ):
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            updated = replace(
                current,
                status="processing",
                uploaded_at=uploaded_at,
                size_bytes=size_bytes,
                detected_content_type=detected_content_type,
                crc32c=crc32c,
                object_generation=object_generation,
                version=current.version + 1,
            )
            if self.media_assets.get(media_id) is not current:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            self.media_assets[media_id] = updated
            return updated

    def mark_media_ready(
        self,
        media_id: str,
        owner_uid: str,
        detected_content_type: str,
        size_bytes: int,
        checksum_sha256: str,
        crc32c: str | None,
        object_generation: int | None,
        width: int,
        height: int,
        confirmed_at: datetime,
    ) -> MediaAssetRecord:
        with self._lock:
            current = self._owned_media_asset(media_id, owner_uid)
            final_matches = (
                current.detected_content_type == detected_content_type
                and current.size_bytes == size_bytes
                and current.checksum_sha256 == checksum_sha256
                and current.crc32c == crc32c
                and current.object_generation == object_generation
                and current.width == width
                and current.height == height
            )
            if current.status == "ready" and final_matches:
                return current
            if current.status != "processing":
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            updated = replace(
                current,
                status="ready",
                detected_content_type=detected_content_type,
                size_bytes=size_bytes,
                checksum_sha256=checksum_sha256,
                crc32c=crc32c,
                object_generation=object_generation,
                width=width,
                height=height,
                moderation_status="approved",
                confirmed_at=confirmed_at,
                version=current.version + 1,
            )
            if self.media_assets.get(media_id) is not current:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            self.media_assets[media_id] = updated
            return updated

    def mark_media_status(
        self,
        media_id: str,
        owner_uid: str,
        status: str,
        reason: str,
        changed_at: datetime,
    ) -> MediaAssetRecord:
        allowed_sources = {
            "rejected": {"pending", "uploaded", "processing", "ready"},
            "quarantined": {"pending", "uploaded", "processing", "ready"},
            "orphaned": {"pending", "uploaded", "processing", "ready"},
        }
        if status not in allowed_sources or not 3 <= len(reason) <= 80:
            raise StoreConflict("MEDIA_ASSET_STATUS_INVALID")
        with self._lock:
            current = self._owned_media_asset(media_id, owner_uid)
            if current.status == status and current.rejection_reason == reason:
                return current
            if current.status not in allowed_sources[status]:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            updated = replace(
                current,
                status=status,
                moderation_status={
                    "rejected": "rejected",
                    "quarantined": "flagged",
                    "orphaned": current.moderation_status,
                }[status],
                rejection_reason=reason,
                confirmed_at=(
                    current.confirmed_at
                    if status == "orphaned"
                    else current.confirmed_at or changed_at
                ),
                version=current.version + 1,
            )
            if self.media_assets.get(media_id) is not current:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            self.media_assets[media_id] = updated
            return updated

    def associate_media(
        self,
        media_id: str,
        owner_uid: str,
        entity_type: str,
        entity_id: str,
    ) -> MediaAssetRecord:
        with self._lock:
            current = self._owned_media_asset(media_id, owner_uid)
            if (
                current.entity_type == entity_type
                and current.entity_id == entity_id
            ):
                return current
            if (
                current.status != "ready"
                or current.entity_id
                not in {current.media_id, f"pending:{current.media_id}"}
            ):
                raise StoreConflict("MEDIA_ASSET_ALREADY_ASSOCIATED")
            updated = replace(
                current,
                entity_type=entity_type,
                entity_id=entity_id,
                version=current.version + 1,
            )
            if self.media_assets.get(media_id) is not current:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            self.media_assets[media_id] = updated
            return updated

    def mark_media_deleted(
        self,
        media_id: str,
        actor_uid: str,
        deleted_at: datetime,
    ) -> MediaAssetRecord:
        with self._lock:
            current = self._owned_media_asset(media_id)
            if current.status == "deleted":
                return current
            if actor_uid not in self.access_accounts:
                raise StoreConflict("MEDIA_ASSET_ACCOUNT_NOT_FOUND")
            updated = replace(
                current,
                status="deleted",
                deleted_at=deleted_at,
                deleted_by=actor_uid,
                version=current.version + 1,
            )
            if self.media_assets.get(media_id) is not current:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            self.media_assets[media_id] = updated
            for key in [key for key in self.media_variants if key[0] == media_id]:
                del self.media_variants[key]
            return updated

    def list_media_assets(
        self,
        entity_type: str,
        entity_id: str,
        limit: int,
        offset: int,
    ) -> list[MediaAssetRecord]:
        with self._lock:
            assets = [
                asset
                for asset in self.media_assets.values()
                if asset.entity_type == entity_type
                and asset.entity_id == entity_id
                and asset.status == "ready"
            ]
            assets.sort(
                key=lambda asset: (asset.created_at, asset.media_id),
                reverse=True,
            )
            return assets[offset : offset + limit]

    def list_expired_pending_media(
        self,
        now: datetime,
        limit: int,
    ) -> list[MediaAssetRecord]:
        with self._lock:
            assets = [
                asset
                for asset in self.media_assets.values()
                if asset.status in {"pending", "uploaded", "processing"}
                and asset.upload_expires_at <= now
            ]
            assets.sort(
                key=lambda asset: (asset.upload_expires_at, asset.media_id)
            )
            return assets[:limit]

    def list_orphaned_media(
        self,
        created_before: datetime,
        limit: int,
    ) -> list[MediaAssetRecord]:
        with self._lock:
            assets = [
                asset
                for asset in self.media_assets.values()
                if asset.status == "orphaned"
                and asset.created_at <= created_before
            ]
            assets.sort(key=lambda asset: (asset.created_at, asset.media_id))
            return assets[:limit]

    def get_access_account(self, uid: str):
        with self._lock:
            return self.access_accounts.get(uid)

    def set_access_account(self, account: AccessAccountRecord):
        with self._lock:
            normalized = replace(account, permissions=tuple(sorted(set(account.permissions))))
            self.access_accounts[account.firebase_uid] = normalized
            now = datetime.now(timezone.utc)
            created_at = self.access_account_times.get(account.firebase_uid, (now, now))[0]
            self.access_account_times[account.firebase_uid] = (created_at, now)
            return normalized

    def get_privileged_account_validation(
        self,
        uid: str,
    ) -> PrivilegedAccountValidationRecord | None:
        with self._lock:
            return self.privileged_account_validations.get(uid)

    def set_privileged_account_validation(
        self,
        validation: PrivilegedAccountValidationRecord,
    ) -> PrivilegedAccountValidationRecord:
        """Helper explícito para seeds e testes do armazenamento em memória."""

        with self._lock:
            self.privileged_account_validations[validation.firebase_uid] = validation
            return validation

    def create_staff_account(
        self,
        account: AccessAccountRecord,
        validation: PrivilegedAccountValidationRecord,
        *,
        actor_uid: str,
        event_id: str,
        queue_id: uuid.UUID,
    ) -> AccessAccountSummaryRecord:
        with self._lock:
            actor = self.access_accounts.get(actor_uid)
            actor_validation = self.privileged_account_validations.get(actor_uid)
            if (
                actor is None
                or actor.role != "admin"
                or actor.status != "ACTIVE"
                or "admin.staff_accounts.manage" not in actor.permissions
                or actor_validation is None
                or actor_validation.validation_state != "APPROVED"
            ):
                raise StoreConflict("ADMIN_STAFF_ACCESS_REQUIRED")
            if account.firebase_uid in self.access_accounts:
                raise StoreConflict("STAFF_ACCOUNT_EXISTS")
            if (
                account.role not in {"admin", "support", "security"}
                or account.status != "PENDING"
                or validation.firebase_uid != account.firebase_uid
                or validation.requested_role != account.role
                or validation.validation_state != "PENDING"
                or validation.protection_level != "PRIVILEGED"
                or validation.account_origin != "ADMIN_INVITATION"
            ):
                raise StoreConflict("STAFF_ACCOUNT_STATE_INVALID")

            normalized = replace(
                account,
                permissions=tuple(sorted(set(account.permissions))),
            )
            self.access_accounts[account.firebase_uid] = normalized
            self.access_account_times[account.firebase_uid] = (
                validation.created_at,
                validation.updated_at,
            )
            self.privileged_account_validations[account.firebase_uid] = validation
            self.email_verification_queue[queue_id] = EmailVerificationQueueRecord(
                queue_id=queue_id,
                firebase_uid=account.firebase_uid,
                email=account.email or "",
                status="PENDING",
                attempt_count=0,
                next_attempt_at=validation.created_at,
                created_at=validation.created_at,
                updated_at=validation.created_at,
            )
            self.access_audit_events.append(
                AccessAuditEventRecord(
                    event_id=event_id,
                    actor_uid=actor_uid,
                    target_uid=account.firebase_uid,
                    event_type="STAFF_ACCOUNT_CREATED",
                    previous_status=None,
                    new_status="PENDING",
                    reason=(
                        "Conta de equipe criada sem acesso e aguardando "
                        "validação administrativa."
                    ),
                    created_at=validation.created_at,
                )
            )
            return self._access_summary(normalized)

    def approve_staff_account(
        self,
        actor_uid: str,
        target_uid: str,
        reason: str,
        *,
        event_id: str,
        approved_at: datetime,
    ) -> AccessAccountSummaryRecord:
        with self._lock:
            actor = self.access_accounts.get(actor_uid)
            actor_validation = self.privileged_account_validations.get(actor_uid)
            if (
                actor is None
                or actor.role != "admin"
                or actor.status != "ACTIVE"
                or "admin.staff_accounts.manage" not in actor.permissions
                or actor_validation is None
                or actor_validation.validation_state != "APPROVED"
            ):
                raise StoreConflict("ADMIN_STAFF_ACCESS_REQUIRED")
            account = self.access_accounts.get(target_uid)
            validation = self.privileged_account_validations.get(target_uid)
            if account is None or validation is None:
                raise StoreNotFound("STAFF_ACCOUNT_NOT_FOUND")
            if actor_uid == target_uid:
                raise StoreConflict("STAFF_SELF_VALIDATION_FORBIDDEN")
            if (
                account.status != "PENDING"
                or validation.validation_state != "PENDING"
                or validation.requested_role != account.role
            ):
                raise StoreConflict("STAFF_VALIDATION_STATE_INVALID")

            updated_account = replace(account, status="ACTIVE")
            updated_validation = replace(
                validation,
                validation_state="APPROVED",
                validated_by_uid=actor_uid,
                validation_reason=reason,
                validated_at=approved_at,
                updated_at=approved_at,
            )
            self.access_accounts[target_uid] = updated_account
            self.privileged_account_validations[target_uid] = updated_validation
            created_at = self.access_account_times[target_uid][0]
            self.access_account_times[target_uid] = (created_at, approved_at)
            self.access_audit_events.append(
                AccessAuditEventRecord(
                    event_id=event_id,
                    actor_uid=actor_uid,
                    target_uid=target_uid,
                    event_type="STAFF_ACCOUNT_VALIDATED",
                    previous_status="PENDING",
                    new_status="ACTIVE",
                    reason=reason,
                    created_at=approved_at,
                )
            )
            return self._access_summary(updated_account)

    def enqueue_email_verification(
        self,
        uid: str,
        email: str,
        now: datetime,
    ) -> EmailVerificationQueueRecord:
        with self._lock:
            existing = next(
                (
                    item
                    for item in self.email_verification_queue.values()
                    if item.firebase_uid == uid
                    and item.status in {"PENDING", "PROCESSING"}
                ),
                None,
            )
            if existing is not None:
                queued = replace(
                    existing,
                    email=email,
                    status="PENDING",
                    next_attempt_at=min(existing.next_attempt_at, now),
                    updated_at=now,
                )
            else:
                queued = EmailVerificationQueueRecord(
                    queue_id=uuid.uuid4(),
                    firebase_uid=uid,
                    email=email,
                    status="PENDING",
                    attempt_count=0,
                    next_attempt_at=now,
                    created_at=now,
                    updated_at=now,
                )
            self.email_verification_queue[queued.queue_id] = queued
            return queued

    def claim_due_email_verifications(
        self,
        now: datetime,
        limit: int,
        processing_timeout: timedelta,
    ) -> list[EmailVerificationQueueRecord]:
        with self._lock:
            stale_before = now - processing_timeout
            due = [
                item
                for item in self.email_verification_queue.values()
                if (
                    item.status == "PENDING"
                    and item.next_attempt_at <= now
                )
                or (
                    item.status == "PROCESSING"
                    and item.updated_at <= stale_before
                )
            ]
            due.sort(key=lambda item: (item.next_attempt_at, item.created_at))
            claimed = [
                replace(
                    item,
                    status="PROCESSING",
                    attempt_count=item.attempt_count + 1,
                    updated_at=now,
                )
                for item in due[:limit]
            ]
            for item in claimed:
                self.email_verification_queue[item.queue_id] = item
            return claimed

    def finish_email_verification(
        self,
        queue_id: uuid.UUID,
        status: str,
        result_code: str,
        now: datetime,
        next_attempt_at: datetime,
    ) -> None:
        del result_code
        with self._lock:
            queued = self.email_verification_queue.get(queue_id)
            if queued is None or queued.status != "PROCESSING":
                raise StoreConflict("EMAIL_VERIFICATION_QUEUE_STATE_CONFLICT")
            self.email_verification_queue[queue_id] = replace(
                queued,
                status=status,
                next_attempt_at=next_attempt_at,
                updated_at=now,
            )

    def upsert_public_profile(self, profile: PublicProfileRecord) -> PublicProfileRecord:
        with self._lock:
            account = self.access_accounts.get(profile.firebase_uid)
            if (
                account is None
                or account.status != "ACTIVE"
                or account.role != profile.role
                or account.role not in {"visitor", "entrepreneur", "institution"}
            ):
                raise StoreConflict("PUBLIC_PROFILE_ACCOUNT_NOT_ELIGIBLE")
            for uid, existing in self.public_profiles.items():
                if uid != profile.firebase_uid and existing.normalized_name == profile.normalized_name:
                    raise StoreConflict("DISPLAY_NAME_ALREADY_IN_USE")
            previous = self.public_profiles.get(profile.firebase_uid)
            stored = replace(
                profile,
                created_at=previous.created_at if previous else profile.created_at,
            )
            self.public_profiles[profile.firebase_uid] = stored
            return stored

    def get_public_profile(self, uid: str) -> PublicProfileRecord | None:
        with self._lock:
            profile = self.public_profiles.get(uid)
            account = self.access_accounts.get(uid)
            if (
                profile is None
                or account is None
                or account.status != "ACTIVE"
                or account.role != profile.role
                or profile.role not in {"visitor", "entrepreneur", "institution"}
            ):
                return None
            return profile

    def search_directory(
        self, query: str, types: tuple[str, ...], limit: int
    ) -> list[GlobalSearchItemRecord]:
        with self._lock:
            items: list[GlobalSearchItemRecord] = []
            if "PROFILE" in types:
                for profile in self.public_profiles.values():
                    account = self.access_accounts.get(profile.firebase_uid)
                    haystack = normalize_display_name(
                        f"{profile.display_name} {profile.city} {profile.category}"
                    )
                    if account and account.status == "ACTIVE" and account.role == profile.role and query in haystack:
                        items.append(
                            GlobalSearchItemRecord(
                                type="PROFILE", item_id=profile.firebase_uid,
                                title=profile.display_name,
                                subtitle=" · ".join(filter(None, (profile.category, profile.city))),
                                owner_uid=profile.firebase_uid,
                                route=f"/profile/{profile.firebase_uid}", status=profile.role,
                                created_at=profile.updated_at,
                            )
                        )
            if "PRODUCT" in types:
                for product in self.products.values():
                    merchant = self.merchants.get(product.merchant_uid)
                    account = self.access_accounts.get(product.merchant_uid)
                    haystack = normalize_display_name(
                        f"{product.title} {product.description} {merchant.display_name if merchant else ''}"
                    )
                    if (
                        merchant and account and merchant.status == "ACTIVE"
                        and account.status == "ACTIVE" and product.status == "ACTIVE"
                        and product.stock_quantity > 0 and query in haystack
                    ):
                        items.append(
                            GlobalSearchItemRecord(
                                type="PRODUCT", item_id=product.product_id,
                                title=product.title, subtitle=merchant.display_name,
                                owner_uid=product.merchant_uid,
                                route=f"/profile/{product.merchant_uid}?product={product.product_id}",
                                status=product.status,
                                created_at=datetime.fromtimestamp(product.created_at or 0, timezone.utc),
                            )
                        )
            if "OFFER" in types:
                now = int(time.time())
                for offer in self.offers.values():
                    token = self.tokens.get(offer.token_ref)
                    haystack = normalize_display_name(
                        f"{offer.product_title} {offer.merchant_name} {offer.establishment_name}"
                    )
                    if (
                        offer.status == "ACTIVE" and offer.expires_at > now
                        and token is not None and token.status == "ISSUED"
                        and token.expires_at > now
                        and offer.redeemed_count < offer.maximum_redemptions
                        and offer.stock_quantity > 0 and query in haystack
                    ):
                        items.append(
                            GlobalSearchItemRecord(
                                type="OFFER", item_id=offer.offer_id,
                                title=offer.product_title, subtitle=offer.merchant_name,
                                owner_uid=offer.merchant_uid,
                                route=f"/profile/{offer.merchant_uid}?offer={offer.offer_id}",
                                status=offer.status,
                                created_at=datetime.fromtimestamp(offer.created_at or 0, timezone.utc),
                            )
                        )
            if "POST" in types:
                for post_id, (author_uid, body, created_at, active) in self.community_post_search.items():
                    profile = self.get_public_profile(author_uid)
                    if profile and active and query in normalize_display_name(f"{body} {profile.display_name}"):
                        items.append(
                            GlobalSearchItemRecord(
                                type="POST", item_id=post_id, title=body,
                                subtitle=profile.display_name, owner_uid=author_uid,
                                route=f"/feed?post={post_id}", status="ACTIVE",
                                created_at=created_at,
                            )
                        )
            items.sort(
                key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            return items[: max(1, min(int(limit), 50))]

    def index_community_post(
        self, post_id: str, author_uid: str, body: str, created_at: datetime
    ) -> None:
        with self._lock:
            self.community_post_search[post_id] = (author_uid, body, created_at, True)

    def update_community_post(
        self, post_id: str, author_uid: str, body: str
    ) -> None:
        with self._lock:
            post = self.community_post_search.get(post_id)
            if post is None or not post[3]:
                raise StoreNotFound("COMMUNITY_POST_NOT_FOUND")
            if post[0] != author_uid:
                raise StoreConflict("COMMUNITY_POST_FORBIDDEN")
            self.community_post_search[post_id] = (
                author_uid,
                body,
                post[2],
                True,
            )

    def delete_community_post(self, post_id: str, author_uid: str) -> None:
        with self._lock:
            post = self.community_post_search.get(post_id)
            if post is None:
                raise StoreNotFound("COMMUNITY_POST_NOT_FOUND")
            if post[0] != author_uid:
                raise StoreConflict("COMMUNITY_POST_FORBIDDEN")
            del self.community_post_search[post_id]
            comment_ids = {
                comment.comment_id
                for comment in self.community_comments.values()
                if comment.post_id == post_id
            }
            for comment_id in comment_ids:
                comment = self.community_comments.pop(comment_id)
                self.community_comment_idempotency.pop(
                    (comment.author_uid, comment.client_comment_id),
                    None,
                )
            self.community_comment_likes = {
                like
                for like in self.community_comment_likes
                if like[0] not in comment_ids
            }

    def create_community_comment(
        self, comment: CommunityCommentRecord
    ) -> CommunityCommentRecord:
        with self._lock:
            post = self.community_post_search.get(comment.post_id)
            account = self.access_accounts.get(comment.author_uid)
            if post is None or not post[3]:
                raise StoreNotFound("COMMUNITY_POST_NOT_FOUND")
            if (
                account is None
                or account.status != "ACTIVE"
                or account.role not in {"visitor", "entrepreneur"}
            ):
                raise StoreNotFound("COMMUNITY_COMMENT_AUTHOR_NOT_AVAILABLE")
            if comment.parent_comment_id is not None:
                parent = self.community_comments.get(comment.parent_comment_id)
                if parent is None or parent.post_id != comment.post_id:
                    raise StoreConflict("COMMUNITY_COMMENT_PARENT_INVALID")
                if parent.parent_comment_id is not None:
                    raise StoreConflict("COMMUNITY_COMMENT_REPLY_DEPTH_EXCEEDED")
            request_key = (comment.author_uid, comment.client_comment_id)
            previous_id = self.community_comment_idempotency.get(request_key)
            if previous_id:
                previous = self.community_comments[previous_id]
                if (
                    previous.post_id != comment.post_id
                    or previous.parent_comment_id != comment.parent_comment_id
                    or previous.body != comment.body
                ):
                    raise StoreConflict("CLIENT_COMMENT_ID_CONFLICT")
                return previous
            self.community_comments[comment.comment_id] = comment
            self.community_comment_idempotency[request_key] = comment.comment_id
            return comment

    def list_community_comments(
        self, post_id: str, viewer_uid: str, limit: int
    ) -> list[CommunityCommentRecord]:
        with self._lock:
            post = self.community_post_search.get(post_id)
            if post is None or not post[3]:
                raise StoreNotFound("COMMUNITY_POST_NOT_FOUND")
            comments = [
                replace(
                    comment,
                    like_count=sum(
                        1
                        for comment_id, _ in self.community_comment_likes
                        if comment_id == comment.comment_id
                    ),
                    liked_by_viewer=(
                        comment.comment_id, viewer_uid
                    ) in self.community_comment_likes,
                )
                for comment in self.community_comments.values()
                if comment.post_id == post_id
            ]
            comments.sort(key=lambda item: (item.created_at, item.comment_id))
            return comments[: max(1, min(int(limit), 200))]

    def update_community_comment(
        self,
        comment_id: str,
        author_uid: str,
        body: str,
        updated_at: datetime,
    ) -> CommunityCommentRecord:
        with self._lock:
            comment = self.community_comments.get(comment_id)
            if comment is None:
                raise StoreNotFound("COMMUNITY_COMMENT_NOT_FOUND")
            if comment.author_uid != author_uid:
                raise StoreConflict("COMMUNITY_COMMENT_FORBIDDEN")
            updated = replace(comment, body=body, updated_at=updated_at)
            self.community_comments[comment_id] = updated
            return replace(
                updated,
                like_count=sum(
                    1
                    for liked_comment_id, _ in self.community_comment_likes
                    if liked_comment_id == comment_id
                ),
                liked_by_viewer=(comment_id, author_uid)
                in self.community_comment_likes,
            )

    def delete_community_comment(self, comment_id: str, author_uid: str) -> None:
        with self._lock:
            comment = self.community_comments.get(comment_id)
            if comment is None:
                raise StoreNotFound("COMMUNITY_COMMENT_NOT_FOUND")
            if comment.author_uid != author_uid:
                raise StoreConflict("COMMUNITY_COMMENT_FORBIDDEN")
            comment_ids = {comment_id}
            comment_ids.update(
                item.comment_id
                for item in self.community_comments.values()
                if item.parent_comment_id == comment_id
            )
            for current_id in comment_ids:
                current = self.community_comments.pop(current_id, None)
                if current is not None:
                    self.community_comment_idempotency.pop(
                        (current.author_uid, current.client_comment_id),
                        None,
                    )
            self.community_comment_likes = {
                like
                for like in self.community_comment_likes
                if like[0] not in comment_ids
            }

    def set_community_comment_like(
        self,
        comment_id: str,
        viewer_uid: str,
        liked: bool,
        changed_at: datetime,
    ) -> tuple[bool, int]:
        del changed_at
        with self._lock:
            if comment_id not in self.community_comments:
                raise StoreNotFound("COMMUNITY_COMMENT_NOT_FOUND")
            key = (comment_id, viewer_uid)
            if liked:
                self.community_comment_likes.add(key)
            else:
                self.community_comment_likes.discard(key)
            count = sum(
                1
                for current_comment_id, _ in self.community_comment_likes
                if current_comment_id == comment_id
            )
            return liked, count

    def _conversation_view(
        self,
        conversation: ConversationRecord,
        uid: str,
        *,
        support_inbox: bool = False,
    ) -> ConversationRecord:
        messages = self.private_messages.get(conversation.conversation_id, [])
        last = messages[-1] if messages else None
        read_at = self.conversation_reads.get(
            (conversation.conversation_id, uid),
            datetime.min.replace(tzinfo=timezone.utc),
        )
        unread = sum(
            1
            for item in messages
            if item.created_at > read_at
            and (
                item.sender_uid == conversation.requester_uid
                if support_inbox
                else item.sender_uid != uid
            )
        )
        return replace(
            conversation,
            last_message=last.body if last else None,
            last_message_at=last.created_at if last else None,
            unread_count=unread,
        )

    def create_direct_conversation(
        self, conversation_id: str, sender_uid: str, recipient_uid: str
    ) -> ConversationRecord:
        with self._lock:
            if sender_uid == recipient_uid:
                raise StoreConflict("MESSAGE_RECIPIENT_NOT_AVAILABLE")
            if self.get_public_profile(sender_uid) is None or self.get_public_profile(recipient_uid) is None:
                raise StoreConflict("MESSAGE_RECIPIENT_NOT_AVAILABLE")
            if (sender_uid, recipient_uid) in self.message_blocks or (recipient_uid, sender_uid) in self.message_blocks:
                raise StoreConflict("MESSAGE_RECIPIENT_NOT_AVAILABLE")
            participants = tuple(sorted((sender_uid, recipient_uid)))
            for existing in self.conversations.values():
                if existing.kind == "DIRECT" and existing.participant_uids == participants:
                    return self._conversation_view(existing, sender_uid)
            now = datetime.now(timezone.utc)
            conversation = ConversationRecord(
                conversation_id=conversation_id, kind="DIRECT", status="OPEN",
                subject=None, created_by_uid=sender_uid, requester_uid=None,
                assigned_support_uid=None, participant_uids=participants,
                last_message=None, last_message_at=None, unread_count=0,
                created_at=now, updated_at=now,
            )
            self.conversations[conversation_id] = conversation
            self.private_messages[conversation_id] = []
            return conversation

    def create_support_conversation(
        self, conversation_id: str, requester_uid: str, subject: str
    ) -> ConversationRecord:
        with self._lock:
            account = self.access_accounts.get(requester_uid)
            if not account or account.status != "ACTIVE" or account.role not in {"visitor", "entrepreneur", "institution"}:
                raise StoreConflict("SUPPORT_REQUESTER_NOT_ELIGIBLE")
            now = datetime.now(timezone.utc)
            conversation = ConversationRecord(
                conversation_id=conversation_id, kind="SUPPORT", status="OPEN",
                subject=subject, created_by_uid=requester_uid,
                requester_uid=requester_uid, assigned_support_uid=None,
                participant_uids=(requester_uid,), last_message=None,
                last_message_at=None, unread_count=0, created_at=now, updated_at=now,
            )
            self.conversations[conversation_id] = conversation
            self.private_messages[conversation_id] = []
            return conversation

    def list_conversations(
        self, uid: str, *, support_inbox: bool, limit: int
    ) -> list[ConversationRecord]:
        with self._lock:
            values = [
                self._conversation_view(item, uid, support_inbox=support_inbox)
                for item in self.conversations.values()
                if (item.kind == "SUPPORT" if support_inbox else uid in item.participant_uids)
            ]
            values.sort(key=lambda item: item.last_message_at or item.created_at, reverse=True)
            return values[: max(1, min(int(limit), 100))]

    def get_conversation(
        self, uid: str, conversation_id: str, *, support_inbox: bool
    ) -> ConversationRecord | None:
        with self._lock:
            item = self.conversations.get(conversation_id)
            if item is None:
                return None
            if support_inbox:
                return (
                    self._conversation_view(item, uid, support_inbox=True)
                    if item.kind == "SUPPORT"
                    else None
                )
            return self._conversation_view(item, uid) if uid in item.participant_uids else None

    def send_private_message(
        self, message: PrivateMessageRecord, *, support_actor: bool
    ) -> PrivateMessageRecord:
        with self._lock:
            conversation = self.conversations.get(message.conversation_id)
            account = self.access_accounts.get(message.sender_uid)
            if not conversation or not account or account.status != "ACTIVE":
                raise StoreNotFound("CONVERSATION_NOT_FOUND")
            allowed = (
                conversation.kind == "SUPPORT" and account.role == "support"
                if support_actor
                else message.sender_uid in conversation.participant_uids
                and account.role in {"visitor", "entrepreneur", "institution"}
            )
            if not allowed:
                raise StoreNotFound("CONVERSATION_NOT_FOUND")
            if conversation.status == "CLOSED" or (
                conversation.kind == "SUPPORT" and conversation.status == "RESOLVED"
            ):
                raise StoreConflict("CONVERSATION_CLOSED")
            if conversation.kind == "DIRECT":
                other_uid = next(uid for uid in conversation.participant_uids if uid != message.sender_uid)
                if self.get_public_profile(other_uid) is None:
                    raise StoreNotFound("CONVERSATION_NOT_FOUND")
                if (message.sender_uid, other_uid) in self.message_blocks or (other_uid, message.sender_uid) in self.message_blocks:
                    raise StoreConflict("MESSAGE_DELIVERY_BLOCKED")
            elif conversation.kind == "SUPPORT" and support_actor:
                requester = self.access_accounts.get(conversation.requester_uid or "")
                if (
                    requester is None
                    or requester.status != "ACTIVE"
                    or requester.role not in {"visitor", "entrepreneur", "institution"}
                ):
                    raise StoreNotFound("CONVERSATION_NOT_FOUND")
            idempotency_key = (message.sender_uid, message.client_message_id)
            previous = self.message_idempotency.get(idempotency_key)
            if previous:
                if (
                    previous.conversation_id != message.conversation_id
                    or previous.body != message.body
                    or previous.media_id != message.media_id
                ):
                    raise StoreConflict("CLIENT_MESSAGE_ID_CONFLICT")
                return previous
            self.private_messages.setdefault(message.conversation_id, []).append(message)
            self.message_idempotency[idempotency_key] = message
            next_status = conversation.status
            assigned_uid = conversation.assigned_support_uid
            if conversation.kind == "SUPPORT":
                if support_actor:
                    assigned_uid = assigned_uid or message.sender_uid
                    if next_status == "OPEN":
                        next_status = "IN_PROGRESS"
            self.conversations[conversation.conversation_id] = replace(
                conversation, status=next_status, assigned_support_uid=assigned_uid,
                updated_at=message.created_at, last_message=message.body,
                last_message_at=message.created_at,
            )
            return message

    def list_private_messages(
        self, uid: str, conversation_id: str, *, support_inbox: bool, limit: int
    ) -> list[PrivateMessageRecord]:
        with self._lock:
            if self.get_conversation(uid, conversation_id, support_inbox=support_inbox) is None:
                raise StoreNotFound("CONVERSATION_NOT_FOUND")
            return list(self.private_messages.get(conversation_id, []))[: max(1, min(int(limit), 200))]

    def mark_conversation_read(
        self, uid: str, conversation_id: str, *, support_inbox: bool, read_at: datetime
    ) -> None:
        with self._lock:
            if self.get_conversation(uid, conversation_id, support_inbox=support_inbox) is None:
                raise StoreNotFound("CONVERSATION_NOT_FOUND")
            self.conversation_reads[(conversation_id, uid)] = max(
                read_at,
                self.conversation_reads.get(
                    (conversation_id, uid), datetime.min.replace(tzinfo=timezone.utc)
                ),
            )

    def resolve_support_conversation(
        self, support_uid: str, conversation_id: str, resolved_at: datetime
    ) -> ConversationRecord:
        with self._lock:
            account = self.access_accounts.get(support_uid)
            conversation = self.conversations.get(conversation_id)
            if (
                not account or account.status != "ACTIVE" or account.role != "support"
                or not conversation or conversation.kind != "SUPPORT"
                or conversation.status in {"RESOLVED", "CLOSED"}
            ):
                raise StoreConflict("SUPPORT_REQUEST_NOT_RESOLVABLE")
            updated = replace(
                conversation, status="RESOLVED", updated_at=resolved_at,
                assigned_support_uid=conversation.assigned_support_uid or support_uid,
            )
            self.conversations[conversation_id] = updated
            return self._conversation_view(updated, support_uid, support_inbox=True)

    def set_message_block(
        self, blocker_uid: str, blocked_uid: str, blocked_at: datetime
    ) -> MessageBlockRecord:
        with self._lock:
            if blocker_uid == blocked_uid or self.get_public_profile(blocked_uid) is None:
                raise StoreConflict("MESSAGE_BLOCK_TARGET_INVALID")
            key = (blocker_uid, blocked_uid)
            record = self.message_blocks.get(key) or MessageBlockRecord(
                blocker_uid=blocker_uid, blocked_uid=blocked_uid, created_at=blocked_at
            )
            self.message_blocks[key] = record
            return record

    def delete_message_block(self, blocker_uid: str, blocked_uid: str) -> bool:
        with self._lock:
            return self.message_blocks.pop((blocker_uid, blocked_uid), None) is not None

    def list_message_blocks(self, blocker_uid: str, limit: int) -> list[MessageBlockRecord]:
        with self._lock:
            records = [
                record for (owner_uid, _), record in self.message_blocks.items()
                if owner_uid == blocker_uid and self.get_public_profile(record.blocked_uid) is not None
            ]
            records.sort(key=lambda item: item.created_at, reverse=True)
            return records[: max(1, min(int(limit), 200))]

    def get_message_block_state(
        self, viewer_uid: str, other_uid: str
    ) -> tuple[bool, bool]:
        with self._lock:
            return (
                (viewer_uid, other_uid) in self.message_blocks,
                (other_uid, viewer_uid) in self.message_blocks,
            )

    def _access_summary(self, account: AccessAccountRecord) -> AccessAccountSummaryRecord:
        created_at, updated_at = self.access_account_times.get(
            account.firebase_uid,
            (None, None),
        )
        validation = self.privileged_account_validations.get(
            account.firebase_uid
        )
        return AccessAccountSummaryRecord(
            firebase_uid=account.firebase_uid,
            email=account.email,
            role=account.role,
            status=account.status,
            permissions=account.permissions,
            created_at=created_at,
            updated_at=updated_at,
            authority_validation_state=(
                validation.validation_state if validation else None
            ),
            protection_level=validation.protection_level if validation else None,
            account_origin=validation.account_origin if validation else None,
            authority_validated_at=validation.validated_at if validation else None,
            authority_validated_by_uid=(
                validation.validated_by_uid if validation else None
            ),
            created_by_uid=validation.created_by_uid if validation else None,
        )

    def create_institution_application(
        self, application: InstitutionApplicationRecord
    ) -> InstitutionApplicationRecord:
        with self._lock:
            if application.application_id in self.institution_applications:
                raise StoreConflict("INSTITUTION_APPLICATION_EXISTS")
            self.institution_applications[application.application_id] = application
            return application

    def list_institution_applications(
        self, status: str | None, limit: int
    ) -> list[InstitutionApplicationRecord]:
        with self._lock:
            applications = [
                item
                for item in self.institution_applications.values()
                if status is None or item.status == status
            ]
            return sorted(
                applications,
                key=lambda item: (item.created_at, str(item.application_id)),
                reverse=True,
            )[: max(1, min(int(limit), 200))]

    def get_institution_application(
        self, application_id: uuid.UUID
    ) -> InstitutionApplicationRecord | None:
        with self._lock:
            return self.institution_applications.get(application_id)

    def update_institution_application_status(
        self,
        application_id: uuid.UUID,
        status: str,
        support_notes: str | None,
        reviewer_uid: str,
        reviewed_at: datetime,
    ) -> InstitutionApplicationRecord:
        with self._lock:
            reviewer = self.access_accounts.get(reviewer_uid)
            current = self.institution_applications.get(application_id)
            if (
                reviewer is None
                or reviewer.role != "support"
                or reviewer.status != "ACTIVE"
                or "support.requests.manage" not in reviewer.permissions
                or current is None
            ):
                raise StoreNotFound("INSTITUTION_APPLICATION_NOT_FOUND")
            updated = replace(
                current,
                status=status,
                support_notes=support_notes,
                reviewed_by_uid=reviewer_uid,
                reviewed_at=reviewed_at,
                updated_at=reviewed_at,
            )
            self.institution_applications[application_id] = updated
            return updated

    def create_institution(
        self,
        profile: InstitutionProfileRecord,
        *,
        actor_uid: str,
        event_id: str,
        application_id: uuid.UUID | None = None,
        application_support_notes: str | None = None,
    ) -> InstitutionProfileRecord:
        with self._lock:
            actor = self.access_accounts.get(actor_uid)
            if (
                actor is None
                or actor.status != "ACTIVE"
                or not (
                    (
                        actor.role == "admin"
                        and "admin.institutions.manage" in actor.permissions
                    )
                    or (
                        actor.role == "support"
                        and "support.institutions.create" in actor.permissions
                    )
                )
            ):
                raise StoreConflict("INSTITUTION_CREATOR_ACCESS_REQUIRED")
            if profile.status != "ACTIVE":
                raise StoreConflict("INSTITUTION_STATUS_INVALID")
            normalized_email = profile.email.casefold()
            if profile.firebase_uid in self.access_accounts or any(
                (account.email or "").casefold() == normalized_email
                for account in self.access_accounts.values()
            ):
                raise StoreConflict("INSTITUTION_ACCOUNT_EXISTS")
            application = (
                self.institution_applications.get(application_id)
                if application_id is not None
                else None
            )
            if application_id is not None and (
                application is None or application.status == "APPROVED"
            ):
                raise StoreConflict("INSTITUTION_APPLICATION_NOT_APPROVABLE")
            self.set_access_account(
                AccessAccountRecord(
                    firebase_uid=profile.firebase_uid,
                    email=profile.email,
                    role="institution",
                    status="ACTIVE",
                    allow_entrepreneur_fallback=False,
                    permissions=default_permissions("institution"),
                )
            )
            self.institution_profiles[profile.firebase_uid] = profile
            if application is not None:
                self.institution_applications[application.application_id] = replace(
                    application,
                    status="APPROVED",
                    support_notes=application_support_notes,
                    reviewed_by_uid=actor_uid,
                    provisioned_uid=profile.firebase_uid,
                    reviewed_at=profile.created_at,
                    updated_at=profile.created_at,
                )
            self.access_audit_events.append(
                AccessAuditEventRecord(
                    event_id=event_id,
                    actor_uid=actor_uid,
                    target_uid=profile.firebase_uid,
                    event_type="INSTITUTION_PROVISIONED",
                    previous_status=None,
                    new_status="ACTIVE",
                    reason="Conta institucional provisionada por operador autorizado.",
                    created_at=profile.created_at,
                )
            )
            return profile

    def list_institutions(self, limit: int) -> list[InstitutionProfileRecord]:
        with self._lock:
            profiles = [
                replace(profile, status=self.access_accounts[uid].status)
                for uid, profile in self.institution_profiles.items()
                if uid in self.access_accounts and self.access_accounts[uid].role == "institution"
            ]
            return sorted(
                profiles,
                key=lambda item: (item.created_at, item.firebase_uid),
                reverse=True,
            )[:limit]

    def get_institution_profile(self, owner_uid: str) -> InstitutionProfileRecord | None:
        with self._lock:
            profile = self.institution_profiles.get(owner_uid)
            account = self.access_accounts.get(owner_uid)
            if profile is None or account is None or account.role != "institution":
                return None
            return replace(profile, status=account.status)

    def update_institution_profile(
        self,
        owner_uid: str,
        updates: dict[str, str | None],
        updated_at: datetime,
    ) -> InstitutionProfileRecord:
        allowed_fields = {"name", "description", "city"}
        if not updates or not set(updates).issubset(allowed_fields):
            raise StoreConflict("INSTITUTION_PROFILE_FIELDS_INVALID")
        with self._lock:
            account = self.access_accounts.get(owner_uid)
            profile = self.institution_profiles.get(owner_uid)
            if (
                account is None
                or account.role != "institution"
                or account.status != "ACTIVE"
                or "institution.profile.manage" not in account.permissions
            ):
                raise StoreConflict("INSTITUTION_PROFILE_ACCESS_REQUIRED")
            if profile is None:
                raise StoreNotFound("INSTITUTION_PROFILE_NOT_FOUND")
            updated = replace(profile, **updates, updated_at=updated_at, status=account.status)
            self.institution_profiles[owner_uid] = updated
            return updated

    def _require_active_institution_group_access(self, owner_uid: str) -> None:
        account = self.access_accounts.get(owner_uid)
        profile = self.institution_profiles.get(owner_uid)
        if (
            account is None
            or account.role != "institution"
            or account.status != "ACTIVE"
            or "institution.groups.manage" not in account.permissions
            or profile is None
        ):
            raise StoreConflict("INSTITUTION_GROUP_ACCESS_REQUIRED")

    def _require_active_institution_event_access(self, owner_uid: str) -> None:
        account = self.access_accounts.get(owner_uid)
        profile = self.institution_profiles.get(owner_uid)
        if (
            account is None
            or account.role != "institution"
            or account.status != "ACTIVE"
            or "institution.events.manage" not in account.permissions
            or profile is None
        ):
            raise StoreConflict("INSTITUTION_EVENT_ACCESS_REQUIRED")

    def set_institution_badge_policy(
        self, owner_uid: str, group_id: str, policy: InstitutionBadgePolicy, updated_at: datetime,
    ) -> InstitutionGroupRecord:
        with self._lock:
            self._require_active_institution_group_access(owner_uid)
            group = self.institution_groups.get(group_id)
            if group is None or group.owner_uid != owner_uid:
                raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            if group.status != "ACTIVE":
                raise StoreConflict("INSTITUTION_GROUP_CLOSED")
            updated = replace(group, badge_policy=policy, updated_at=updated_at)
            self.institution_groups[group_id] = updated
            return updated

    def set_institution_member_badge(
        self, owner_uid: str, group_id: str, membership_id: str, badge: str, updated_at: datetime,
    ) -> InstitutionMembershipRecord:
        with self._lock:
            self._require_active_institution_group_access(owner_uid)
            group = self.institution_groups.get(group_id)
            if group is None or group.owner_uid != owner_uid:
                raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            if group.status != "ACTIVE":
                raise StoreConflict("INSTITUTION_GROUP_CLOSED")
            member = self.institution_memberships.get(membership_id)
            if member is None or member.group_id != group_id:
                raise StoreNotFound("INSTITUTION_MEMBERSHIP_NOT_FOUND")
            if member.status != "ACTIVE":
                raise StoreConflict("INSTITUTION_BADGE_ACTIVE_MEMBER_REQUIRED")
            updated = replace(member, support_badge=badge, updated_at=updated_at)
            self.institution_memberships[membership_id] = updated
            return updated

    def create_institution_group(
        self,
        group: InstitutionGroupRecord,
    ) -> InstitutionGroupRecord:
        with self._lock:
            self._require_active_institution_group_access(group.owner_uid)
            if group.group_id in self.institution_groups:
                raise StoreConflict("INSTITUTION_GROUP_EXISTS")
            normalized = replace(group, status="ACTIVE", closed_at=None)
            self.institution_groups[group.group_id] = normalized
            return normalized

    def list_institution_groups(
        self,
        owner_uid: str,
        limit: int,
    ) -> list[InstitutionGroupRecord]:
        with self._lock:
            groups = [
                group
                for group in self.institution_groups.values()
                if group.owner_uid == owner_uid
            ]
            return sorted(
                groups,
                key=lambda item: (item.created_at, item.group_id),
                reverse=True,
            )[:limit]

    def close_institution_group(
        self,
        owner_uid: str,
        group_id: str,
        closed_at: datetime,
    ) -> InstitutionGroupRecord:
        with self._lock:
            self._require_active_institution_group_access(owner_uid)
            current = self.institution_groups.get(group_id)
            if current is None or current.owner_uid != owner_uid:
                raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            if current.status == "CLOSED":
                return current
            for membership_id, membership in tuple(self.institution_memberships.items()):
                if membership.group_id != group_id or membership.status not in {"PENDING", "ACTIVE"}:
                    continue
                updated_membership = replace(
                    membership,
                    status="REMOVED",
                    responded_at=membership.responded_at or closed_at,
                    ended_at=closed_at,
                    updated_at=closed_at,
                )
                self.institution_memberships[membership_id] = updated_membership
                self.institution_membership_events.append(
                    {
                        "event_id": f"membership-close:{uuid.uuid4()}",
                        "membership_id": membership_id,
                        "actor_uid": owner_uid,
                        "event_type": "GROUP_CLOSED",
                        "previous_status": membership.status,
                        "new_status": "REMOVED",
                        "created_at": closed_at,
                    }
                )
            updated = replace(
                current,
                status="CLOSED",
                updated_at=closed_at,
                closed_at=closed_at,
            )
            self.institution_groups[group_id] = updated
            return updated

    def get_institution_report_summary(
        self,
        owner_uid: str,
    ) -> InstitutionReportSummaryRecord:
        with self._lock:
            groups = [
                group
                for group in self.institution_groups.values()
                if group.owner_uid == owner_uid
            ]
            return InstitutionReportSummaryRecord(
                total_groups=len(groups),
                active_groups=sum(group.status == "ACTIVE" for group in groups),
                closed_groups=sum(group.status == "CLOSED" for group in groups),
                last_group_created_at=max(
                    (group.created_at for group in groups),
                    default=None,
                ),
            )

    def invite_institution_seller(
        self,
        owner_uid: str,
        group_id: str,
        normalized_seller_name: str,
        membership_id: str,
        invited_at: datetime,
        event_id: str,
    ) -> InstitutionMembershipRecord:
        with self._lock:
            self._require_active_institution_group_access(owner_uid)
            group = self.institution_groups.get(group_id)
            if group is None or group.owner_uid != owner_uid or group.status != "ACTIVE":
                raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            profile = next(
                (
                    item
                    for item in self.public_profiles.values()
                    if item.normalized_name == normalized_seller_name
                ),
                None,
            )
            account = self.access_accounts.get(profile.firebase_uid) if profile else None
            merchant = self.merchants.get(profile.firebase_uid) if profile else None
            if (
                profile is None
                or profile.role != "entrepreneur"
                or account is None
                or account.role != "entrepreneur"
                or account.status != "ACTIVE"
                or merchant is None
                or merchant.status != "ACTIVE"
            ):
                raise StoreNotFound("ELIGIBLE_SELLER_NOT_FOUND")
            existing = next(
                (
                    membership
                    for membership in self.institution_memberships.values()
                    if membership.group_id == group_id
                    and membership.seller_uid == profile.firebase_uid
                    and membership.status in {"PENDING", "ACTIVE"}
                ),
                None,
            )
            if existing is not None:
                return existing
            institution = self.institution_profiles[owner_uid]
            membership = InstitutionMembershipRecord(
                membership_id=membership_id,
                group_id=group_id,
                group_name=group.name,
                institution_name=institution.name,
                seller_uid=profile.firebase_uid,
                seller_name=profile.display_name,
                status="PENDING",
                invited_at=invited_at,
                responded_at=None,
                active_from=None,
                ended_at=None,
                updated_at=invited_at,
            )
            self.institution_memberships[membership_id] = membership
            self.institution_membership_events.append(
                {
                    "event_id": event_id,
                    "membership_id": membership_id,
                    "actor_uid": owner_uid,
                    "event_type": "INVITED",
                    "previous_status": None,
                    "new_status": "PENDING",
                    "created_at": invited_at,
                }
            )
            return membership

    def list_institution_group_memberships(
        self,
        owner_uid: str,
        group_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[InstitutionMembershipRecord], bool]:
        with self._lock:
            group = self.institution_groups.get(group_id)
            if group is None or group.owner_uid != owner_uid:
                raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            items = [
                membership
                for membership in self.institution_memberships.values()
                if membership.group_id == group_id
                and (status is None or membership.status == status)
            ]
            items.sort(key=lambda item: (item.invited_at, item.membership_id), reverse=True)
            page = items[offset : offset + limit + 1]
            return page[:limit], len(page) > limit

    def list_entrepreneur_institution_memberships(
        self,
        seller_uid: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[InstitutionMembershipRecord], bool]:
        with self._lock:
            items = [
                membership
                for membership in self.institution_memberships.values()
                if membership.seller_uid == seller_uid
                and (status is None or membership.status == status)
            ]
            items.sort(key=lambda item: (item.invited_at, item.membership_id), reverse=True)
            page = items[offset : offset + limit + 1]
            return page[:limit], len(page) > limit

    def respond_institution_invitation(
        self,
        seller_uid: str,
        membership_id: str,
        decision: str,
        changed_at: datetime,
        event_id: str,
    ) -> InstitutionMembershipRecord:
        with self._lock:
            account = self.access_accounts.get(seller_uid)
            merchant = self.merchants.get(seller_uid)
            if (
                account is None
                or account.role != "entrepreneur"
                or account.status != "ACTIVE"
                or "institution.memberships.respond" not in account.permissions
                or merchant is None
                or merchant.status != "ACTIVE"
            ):
                raise StoreConflict("INSTITUTION_MEMBERSHIP_ACCESS_REQUIRED")
            current = self.institution_memberships.get(membership_id)
            if current is None or current.seller_uid != seller_uid:
                raise StoreNotFound("INSTITUTION_INVITATION_NOT_FOUND")
            target_status = "ACTIVE" if decision == "ACCEPT" else "DECLINED"
            if current.status == target_status:
                return current
            if current.status != "PENDING":
                raise StoreConflict("INSTITUTION_INVITATION_NOT_PENDING")
            if decision == "ACCEPT":
                group = self.institution_groups.get(current.group_id)
                institution_access = (
                    self.access_accounts.get(group.owner_uid) if group is not None else None
                )
                if (
                    group is None
                    or group.status != "ACTIVE"
                    or institution_access is None
                    or institution_access.role != "institution"
                    or institution_access.status != "ACTIVE"
                ):
                    raise StoreConflict("INSTITUTION_GROUP_NOT_ACTIVE")
                if any(
                    item.seller_uid == seller_uid and item.status == "ACTIVE"
                    for item in self.institution_memberships.values()
                ):
                    raise StoreConflict("SELLER_ALREADY_HAS_ACTIVE_MEMBERSHIP")
                updated = replace(
                    current,
                    status="ACTIVE",
                    responded_at=changed_at,
                    active_from=changed_at,
                    updated_at=changed_at,
                )
                event_type = "ACCEPTED"
            else:
                updated = replace(
                    current,
                    status="DECLINED",
                    responded_at=changed_at,
                    ended_at=changed_at,
                    updated_at=changed_at,
                )
                event_type = "DECLINED"
            self.institution_memberships[membership_id] = updated
            self.institution_membership_events.append(
                {
                    "event_id": event_id,
                    "membership_id": membership_id,
                    "actor_uid": seller_uid,
                    "event_type": event_type,
                    "previous_status": "PENDING",
                    "new_status": updated.status,
                    "created_at": changed_at,
                }
            )
            return updated

    def leave_institution_membership(
        self,
        seller_uid: str,
        membership_id: str,
        changed_at: datetime,
        event_id: str,
    ) -> InstitutionMembershipRecord:
        with self._lock:
            current = self.institution_memberships.get(membership_id)
            if current is None or current.seller_uid != seller_uid:
                raise StoreNotFound("INSTITUTION_MEMBERSHIP_NOT_FOUND")
            if current.status == "LEFT":
                return current
            if current.status != "ACTIVE":
                raise StoreConflict("INSTITUTION_MEMBERSHIP_NOT_ACTIVE")
            updated = replace(current, status="LEFT", ended_at=changed_at, updated_at=changed_at)
            self.institution_memberships[membership_id] = updated
            self.institution_membership_events.append(
                {
                    "event_id": event_id,
                    "membership_id": membership_id,
                    "actor_uid": seller_uid,
                    "event_type": "LEFT",
                    "previous_status": "ACTIVE",
                    "new_status": "LEFT",
                    "created_at": changed_at,
                }
            )
            return updated

    def remove_institution_group_member(
        self,
        owner_uid: str,
        group_id: str,
        membership_id: str,
        changed_at: datetime,
        event_id: str,
    ) -> InstitutionMembershipRecord:
        with self._lock:
            self._require_active_institution_group_access(owner_uid)
            group = self.institution_groups.get(group_id)
            current = self.institution_memberships.get(membership_id)
            if (
                group is None
                or group.owner_uid != owner_uid
                or current is None
                or current.group_id != group_id
            ):
                raise StoreNotFound("INSTITUTION_MEMBERSHIP_NOT_FOUND_OR_NOT_OWNED")
            if current.status == "REMOVED":
                return current
            if current.status not in {"PENDING", "ACTIVE"}:
                raise StoreConflict("INSTITUTION_MEMBERSHIP_NOT_ACTIVE")
            updated = replace(
                current,
                status="REMOVED",
                responded_at=current.responded_at or changed_at,
                ended_at=changed_at,
                updated_at=changed_at,
            )
            self.institution_memberships[membership_id] = updated
            self.institution_membership_events.append(
                {
                    "event_id": event_id,
                    "membership_id": membership_id,
                    "actor_uid": owner_uid,
                    "event_type": "REMOVED",
                    "previous_status": current.status,
                    "new_status": "REMOVED",
                    "created_at": changed_at,
                }
            )
            return updated

    @staticmethod
    def _memory_redemption_time(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return None

    @staticmethod
    def _memory_currency_totals(
        redemptions: list[dict[str, Any]],
    ) -> tuple[InstitutionSalesCurrencyTotalRecord, ...]:
        totals: dict[str, list[int]] = {}
        for redemption in redemptions:
            original = redemption.get("original_amount_minor")
            final = redemption.get("final_amount_minor")
            if original is None or final is None:
                continue
            currency = str(redemption.get("currency") or "BRL")
            bucket = totals.setdefault(currency, [0, 0, 0])
            bucket[0] += int(original)
            bucket[1] += int(final)
            bucket[2] += int(original) - int(final)
        return tuple(
            InstitutionSalesCurrencyTotalRecord(
                currency=currency,
                gross_original_amount_minor=values[0],
                gross_final_amount_minor=values[1],
                total_discount_amount_minor=values[2],
            )
            for currency, values in sorted(totals.items())
        )

    def get_institution_sales_report(
        self,
        owner_uid: str,
        group_id: str | None,
        period_from: datetime,
        period_to: datetime,
        limit: int,
        offset: int,
    ) -> InstitutionSalesReportRecord:
        with self._lock:
            if group_id is not None:
                group = self.institution_groups.get(group_id)
                if group is None or group.owner_uid != owner_uid:
                    raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            memberships = [
                item
                for item in self.institution_memberships.values()
                if self.institution_groups.get(item.group_id) is not None
                and self.institution_groups[item.group_id].owner_uid == owner_uid
                and (group_id is None or item.group_id == group_id)
                and item.active_from is not None
                and item.active_from < period_to
                and (item.ended_at is None or item.ended_at > period_from)
            ]
            memberships.sort(key=lambda item: (item.group_name, item.seller_name, item.membership_id))

            def attributed(membership: InstitutionMembershipRecord) -> list[dict[str, Any]]:
                selected: list[dict[str, Any]] = []
                for redemption in self.redemptions.values():
                    committed_at = self._memory_redemption_time(redemption.get("committed_at"))
                    if (
                        redemption.get("status", "REDEEMED") == "REDEEMED"
                        and redemption.get("merchant_uid") == membership.seller_uid
                        and committed_at is not None
                        and period_from <= committed_at < period_to
                        and membership.active_from <= committed_at
                        and (membership.ended_at is None or committed_at < membership.ended_at)
                    ):
                        selected.append(redemption)
                return selected

            seller_rows: list[InstitutionSellerSalesRecord] = []
            for membership in memberships[offset : offset + limit]:
                rows = attributed(membership)
                seller_rows.append(
                    InstitutionSellerSalesRecord(
                        membership_id=membership.membership_id,
                        group_id=membership.group_id,
                        group_name=membership.group_name,
                        seller_uid=membership.seller_uid,
                        seller_name=membership.seller_name,
                        membership_status=membership.status,
                        active_from=membership.active_from,
                        ended_at=membership.ended_at,
                        confirmed_redemptions=len(rows),
                        units_sold=sum(int(row.get("quantity", 1)) for row in rows),
                        amounts_unavailable_count=sum(
                            row.get("original_amount_minor") is None
                            or row.get("final_amount_minor") is None
                            for row in rows
                        ),
                        totals_by_currency=self._memory_currency_totals(rows),
                    )
                )
            unique: dict[str, dict[str, Any]] = {}
            for membership in memberships:
                for redemption in attributed(membership):
                    key = str(
                        redemption.get("redemption_id")
                        or redemption.get("operation_id")
                        or id(redemption)
                    )
                    unique[key] = redemption
            aggregate = list(unique.values())
            return InstitutionSalesReportRecord(
                confirmed_redemptions=len(aggregate),
                units_sold=sum(int(row.get("quantity", 1)) for row in aggregate),
                amounts_unavailable_count=sum(
                    row.get("original_amount_minor") is None
                    or row.get("final_amount_minor") is None
                    for row in aggregate
                ),
                totals_by_currency=self._memory_currency_totals(aggregate),
                sellers=tuple(seller_rows),
                has_more=offset + limit < len(memberships),
            )

    @staticmethod
    def _equal_minor_allocations(
        total_amount_minor: int,
        identifiers: list[str],
    ) -> dict[str, int]:
        ordered = sorted(identifiers)
        if not ordered:
            return {}
        base_amount, remainder = divmod(total_amount_minor, len(ordered))
        return {
            identifier: base_amount + (1 if index < remainder else 0)
            for index, identifier in enumerate(ordered)
        }

    def _event_redemptions(
        self,
        event: InstitutionFundedEventRecord,
    ) -> list[dict[str, Any]]:
        eligible = {
            (seller.seller_uid, product.product_id)
            for seller in event.seller_allocations
            for product in seller.product_allocations
        }
        effective_start = max(
            event.starts_at,
            event.activated_at or event.starts_at,
        )
        effective_end = event.ended_at or (
            event.ends_at if event.end_mode == "TIME" else None
        )
        rows: list[tuple[datetime, str, dict[str, Any]]] = []
        for redemption in self.redemptions.values():
            committed_at = self._memory_redemption_time(
                redemption.get("committed_at")
            )
            if (
                redemption.get("status", "REDEEMED") != "REDEEMED"
                or committed_at is None
                or committed_at < effective_start
                or (effective_end is not None and committed_at > effective_end)
                or str(redemption.get("currency") or "BRL")
                != event.currency
                or (
                    redemption.get("merchant_uid"),
                    redemption.get("product_id"),
                )
                not in eligible
            ):
                continue
            redemption_id = str(
                redemption.get("redemption_id")
                or redemption.get("operation_id")
                or id(redemption)
            )
            rows.append((committed_at, redemption_id, redemption))
        rows.sort(key=lambda item: (item[0], item[1]))
        return [row[2] for row in rows]

    def _settle_funded_event(
        self,
        event: InstitutionFundedEventRecord,
        checked_at: datetime,
    ) -> InstitutionFundedEventRecord:
        rows = self._event_redemptions(event)
        current_count = len(rows)
        if event.end_mode == "COUPONS":
            current_count = min(current_count, int(event.coupon_limit or 0))
        updated = (
            replace(event, current_coupon_redemptions=current_count)
            if event.current_coupon_redemptions != current_count
            else event
        )
        if event.status != "ACTIVE":
            if updated is not event:
                self.institution_funded_events[event.event_id] = updated
            return updated
        if event.end_mode == "TIME" and event.ends_at <= checked_at:
            updated = replace(
                updated,
                status="ENDED",
                end_reason="TIME",
                ended_at=event.ends_at,
                updated_at=checked_at,
            )
        elif event.end_mode == "COUPONS":
            if len(rows) >= int(event.coupon_limit or 0):
                last = rows[int(event.coupon_limit or 0) - 1]
                updated = replace(
                    updated,
                    status="ENDED",
                    end_reason="COUPONS",
                    ended_at=self._memory_redemption_time(
                        last.get("committed_at")
                    ),
                    updated_at=checked_at,
                )
        if updated is not event:
            self.institution_funded_events[event.event_id] = updated
        return updated

    def create_institution_funded_event(
        self,
        event: InstitutionFundedEventRecord,
    ) -> InstitutionFundedEventRecord:
        with self._lock:
            self._require_active_institution_event_access(event.owner_uid)
            group = self.institution_groups.get(event.group_id)
            if (
                group is None
                or group.owner_uid != event.owner_uid
                or group.status != "ACTIVE"
            ):
                raise StoreNotFound(
                    "INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED"
                )
            if event.event_id in self.institution_funded_events:
                raise StoreConflict("INSTITUTION_FUNDED_EVENT_CONFLICT")
            memberships = sorted(
                (
                    membership
                    for membership in self.institution_memberships.values()
                    if membership.group_id == event.group_id
                    and membership.status == "ACTIVE"
                ),
                key=lambda item: (item.seller_uid, item.membership_id),
            )
            if not memberships:
                raise StoreConflict(
                    "INSTITUTION_EVENT_REQUIRES_ACTIVE_AFFILIATES"
                )
            equal = self._equal_minor_allocations(
                event.budget_amount_minor,
                [membership.seller_uid for membership in memberships],
            )
            profile = self.institution_profiles[event.owner_uid]
            created = replace(
                event,
                institution_name=profile.name,
                group_name=group.name,
                seller_allocations=tuple(
                    InstitutionFundedEventSellerAllocationRecord(
                        membership_id=membership.membership_id,
                        seller_uid=membership.seller_uid,
                        seller_name=membership.seller_name,
                        allocated_amount_minor=equal[
                            membership.seller_uid
                        ],
                        allocation_mode="EQUAL",
                        product_allocations=(),
                    )
                    for membership in memberships
                ),
            )
            self.institution_funded_events[event.event_id] = created
            return created

    def list_institution_funded_events(
        self,
        owner_uid: str,
        limit: int,
    ) -> list[InstitutionFundedEventRecord]:
        with self._lock:
            now = datetime.now(timezone.utc)
            events = [
                self._settle_funded_event(event, now)
                for event in self.institution_funded_events.values()
                if event.owner_uid == owner_uid
            ]
            return sorted(
                events,
                key=lambda item: (item.created_at, item.event_id),
                reverse=True,
            )[:limit]

    def set_institution_event_seller_allocations(
        self,
        owner_uid: str,
        event_id: str,
        allocations: tuple[tuple[str, int], ...],
        updated_at: datetime,
        *, by_badges: bool = False,
    ) -> InstitutionFundedEventRecord:
        with self._lock:
            self._require_active_institution_event_access(owner_uid)
            event = self.institution_funded_events.get(event_id)
            if event is None or event.owner_uid != owner_uid:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            if event.status != "DRAFT":
                raise StoreConflict("INSTITUTION_EVENT_ALLOCATION_LOCKED")
            distribution = None
            if by_badges:
                group = self.institution_groups[event.group_id]
                if group.status != "ACTIVE":
                    raise StoreConflict("INSTITUTION_GROUP_CLOSED")
                members = [self.institution_memberships[seller.membership_id] for seller in event.seller_allocations]
                if any(member.status != "ACTIVE" for member in members):
                    raise StoreConflict("INSTITUTION_BADGE_ACTIVE_MEMBER_REQUIRED")
                badges = {member.seller_uid: member.support_badge for member in members}
                try:
                    allocations = allocate_by_badges(event.budget_amount_minor, group.badge_policy, badges)
                except ValueError as exc:
                    raise StoreConflict(str(exc)) from exc
                distribution = InstitutionBadgeDistribution(policy=group.badge_policy, seller_badges=badges)
            supplied = dict(allocations)
            if len(supplied) != len(allocations):
                raise StoreConflict("INSTITUTION_EVENT_DUPLICATE_SELLER")
            current = {seller.seller_uid for seller in event.seller_allocations}
            if set(supplied) != current:
                raise StoreConflict("INSTITUTION_EVENT_SELLER_SET_MISMATCH")
            if sum(supplied.values()) != event.budget_amount_minor:
                raise StoreConflict("INSTITUTION_EVENT_BUDGET_TOTAL_MISMATCH")
            updated = replace(
                event,
                seller_allocations=tuple(
                    replace(
                        seller,
                        allocated_amount_minor=supplied[seller.seller_uid],
                        allocation_mode="CUSTOM",
                        product_allocations=(),
                    )
                    for seller in event.seller_allocations
                ),
                updated_at=updated_at,
                badge_distribution=distribution,
            )
            self.institution_funded_events[event_id] = updated
            return updated

    def set_institution_event_product_allocations(
        self,
        seller_uid: str,
        event_id: str,
        allocations: tuple[tuple[str, int], ...],
        updated_at: datetime,
    ) -> InstitutionFundedEventRecord:
        with self._lock:
            event = self.institution_funded_events.get(event_id)
            if event is None:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            if event.status != "DRAFT":
                raise StoreConflict("INSTITUTION_EVENT_ALLOCATION_LOCKED")
            seller = next(
                (
                    allocation
                    for allocation in event.seller_allocations
                    if allocation.seller_uid == seller_uid
                ),
                None,
            )
            if seller is None:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            supplied = dict(allocations)
            if len(supplied) != len(allocations):
                raise StoreConflict("INSTITUTION_EVENT_DUPLICATE_PRODUCT")
            if sum(supplied.values()) != seller.allocated_amount_minor:
                raise StoreConflict(
                    "INSTITUTION_EVENT_PRODUCT_TOTAL_MISMATCH"
                )
            products = {
                product.product_id: product
                for product in self.products.values()
                if product.product_id in supplied
                and product.merchant_uid == seller_uid
                and product.currency == event.currency
                and product.status == "ACTIVE"
            }
            if set(products) != set(supplied):
                raise StoreConflict("INSTITUTION_EVENT_PRODUCT_NOT_ELIGIBLE")
            product_allocations = tuple(
                InstitutionFundedEventProductAllocationRecord(
                    product_id=product_id,
                    product_title=products[product_id].title,
                    allocated_amount_minor=amount,
                    allocation_mode="CUSTOM",
                )
                for product_id, amount in allocations
            )
            updated = replace(
                event,
                seller_allocations=tuple(
                    replace(
                        allocation,
                        product_allocations=product_allocations,
                    )
                    if allocation.seller_uid == seller_uid
                    else allocation
                    for allocation in event.seller_allocations
                ),
                updated_at=updated_at,
            )
            self.institution_funded_events[event_id] = updated
            return updated

    def activate_institution_funded_event(
        self,
        owner_uid: str,
        event_id: str,
        activated_at: datetime,
    ) -> InstitutionFundedEventRecord:
        with self._lock:
            self._require_active_institution_event_access(owner_uid)
            event = self.institution_funded_events.get(event_id)
            if event is None or event.owner_uid != owner_uid:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            if event.status != "DRAFT":
                raise StoreConflict("INSTITUTION_EVENT_NOT_DRAFT")
            if event.end_mode == "TIME" and event.ends_at <= activated_at:
                raise StoreConflict(
                    "INSTITUTION_EVENT_END_TIME_ALREADY_PASSED"
                )
            if any(
                other.event_id != event_id
                and other.group_id == event.group_id
                and other.status == "ACTIVE"
                for other in self.institution_funded_events.values()
            ):
                raise StoreConflict(
                    "INSTITUTION_GROUP_ALREADY_HAS_ACTIVE_FUNDED_EVENT"
                )
            seller_allocations: list[
                InstitutionFundedEventSellerAllocationRecord
            ] = []
            for seller in event.seller_allocations:
                products = seller.product_allocations
                if products:
                    if (
                        sum(
                            product.allocated_amount_minor
                            for product in products
                        )
                        != seller.allocated_amount_minor
                    ):
                        raise StoreConflict(
                            "INSTITUTION_EVENT_PRODUCT_TOTAL_MISMATCH"
                        )
                else:
                    eligible = sorted(
                        (
                            product
                            for product in self.products.values()
                            if product.merchant_uid == seller.seller_uid
                            and product.currency == event.currency
                            and product.status == "ACTIVE"
                        ),
                        key=lambda item: item.product_id,
                    )
                    if not eligible and seller.allocated_amount_minor > 0:
                        raise StoreConflict(
                            "INSTITUTION_EVENT_SELLER_HAS_NO_ACTIVE_PRODUCTS"
                        )
                    equal = self._equal_minor_allocations(
                        seller.allocated_amount_minor,
                        [product.product_id for product in eligible],
                    )
                    products = tuple(
                        InstitutionFundedEventProductAllocationRecord(
                            product_id=product.product_id,
                            product_title=product.title,
                            allocated_amount_minor=equal[product.product_id],
                            allocation_mode="EQUAL",
                        )
                        for product in eligible
                    )
                seller_allocations.append(
                    replace(seller, product_allocations=products)
                )
            updated = replace(
                event,
                status="ACTIVE",
                activated_at=activated_at,
                updated_at=activated_at,
                seller_allocations=tuple(seller_allocations),
            )
            self.institution_funded_events[event_id] = updated
            return self._settle_funded_event(updated, activated_at)

    def end_institution_funded_event(
        self,
        owner_uid: str,
        event_id: str,
        ended_at: datetime,
    ) -> InstitutionFundedEventRecord:
        with self._lock:
            self._require_active_institution_event_access(owner_uid)
            event = self.institution_funded_events.get(event_id)
            if event is None or event.owner_uid != owner_uid:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            if event.status != "ACTIVE":
                raise StoreConflict("INSTITUTION_EVENT_NOT_ACTIVE")
            updated = replace(
                event,
                status="ENDED",
                end_reason="MANUAL",
                ended_at=ended_at,
                updated_at=ended_at,
            )
            self.institution_funded_events[event_id] = updated
            return updated

    def list_entrepreneur_funded_events(
        self,
        seller_uid: str,
        limit: int,
    ) -> list[InstitutionFundedEventRecord]:
        with self._lock:
            now = datetime.now(timezone.utc)
            events = [
                self._settle_funded_event(event, now)
                for event in self.institution_funded_events.values()
                if any(
                    seller.seller_uid == seller_uid
                    for seller in event.seller_allocations
                )
            ]
            return sorted(
                events,
                key=lambda item: (item.created_at, item.event_id),
                reverse=True,
            )[:limit]

    def get_institution_funded_event_report(
        self,
        owner_uid: str,
        event_id: str,
        generated_at: datetime,
    ) -> InstitutionFundedEventReportRecord:
        with self._lock:
            event = self.institution_funded_events.get(event_id)
            if event is None or event.owner_uid != owner_uid:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            event = self._settle_funded_event(event, generated_at)
            rows = self._event_redemptions(event)
            if event.end_mode == "COUPONS":
                rows = rows[: event.coupon_limit]
            totals_by_product: dict[str, dict[str, int]] = {}
            for redemption in rows:
                totals = totals_by_product.setdefault(
                    str(redemption.get("product_id")),
                    {
                        "confirmed_redemptions": 0,
                        "units_sold": 0,
                        "gross_original_amount_minor": 0,
                        "gross_final_amount_minor": 0,
                        "discount_used_minor": 0,
                    },
                )
                original = int(redemption.get("original_amount_minor") or 0)
                final = int(redemption.get("final_amount_minor") or 0)
                totals["confirmed_redemptions"] += 1
                totals["units_sold"] += int(redemption.get("quantity") or 1)
                totals["gross_original_amount_minor"] += original
                totals["gross_final_amount_minor"] += final
                totals["discount_used_minor"] += max(original - final, 0)
            seller_reports: list[
                InstitutionFundedEventSellerReportRecord
            ] = []
            for seller in event.seller_allocations:
                products: list[
                    InstitutionFundedEventProductReportRecord
                ] = []
                for product in seller.product_allocations:
                    totals = totals_by_product.get(product.product_id, {})
                    discount = int(totals.get("discount_used_minor", 0))
                    due = min(discount, product.allocated_amount_minor)
                    products.append(
                        InstitutionFundedEventProductReportRecord(
                            product_id=product.product_id,
                            product_title=product.product_title,
                            allocated_amount_minor=product.allocated_amount_minor,
                            confirmed_redemptions=int(
                                totals.get("confirmed_redemptions", 0)
                            ),
                            units_sold=int(totals.get("units_sold", 0)),
                            gross_original_amount_minor=int(
                                totals.get("gross_original_amount_minor", 0)
                            ),
                            gross_final_amount_minor=int(
                                totals.get("gross_final_amount_minor", 0)
                            ),
                            discount_used_minor=discount,
                            amount_due_minor=due,
                            unfunded_discount_minor=max(
                                discount - product.allocated_amount_minor,
                                0,
                            ),
                            remaining_budget_minor=max(
                                product.allocated_amount_minor - due,
                                0,
                            ),
                        )
                    )
                seller_reports.append(
                    InstitutionFundedEventSellerReportRecord(
                        seller_uid=seller.seller_uid,
                        seller_name=seller.seller_name,
                        allocated_amount_minor=seller.allocated_amount_minor,
                        confirmed_redemptions=sum(
                            product.confirmed_redemptions
                            for product in products
                        ),
                        units_sold=sum(
                            product.units_sold for product in products
                        ),
                        gross_original_amount_minor=sum(
                            product.gross_original_amount_minor
                            for product in products
                        ),
                        gross_final_amount_minor=sum(
                            product.gross_final_amount_minor
                            for product in products
                        ),
                        discount_used_minor=sum(
                            product.discount_used_minor for product in products
                        ),
                        amount_due_minor=sum(
                            product.amount_due_minor for product in products
                        ),
                        unfunded_discount_minor=sum(
                            product.unfunded_discount_minor
                            for product in products
                        ),
                        remaining_budget_minor=sum(
                            product.remaining_budget_minor
                            for product in products
                        ),
                        products=tuple(products),
                    )
                )
            return InstitutionFundedEventReportRecord(
                event=event,
                confirmed_redemptions=sum(
                    seller.confirmed_redemptions for seller in seller_reports
                ),
                units_sold=sum(seller.units_sold for seller in seller_reports),
                gross_original_amount_minor=sum(
                    seller.gross_original_amount_minor for seller in seller_reports
                ),
                gross_final_amount_minor=sum(
                    seller.gross_final_amount_minor for seller in seller_reports
                ),
                discount_used_minor=sum(
                    seller.discount_used_minor for seller in seller_reports
                ),
                amount_due_minor=sum(
                    seller.amount_due_minor for seller in seller_reports
                ),
                unfunded_discount_minor=sum(
                    seller.unfunded_discount_minor for seller in seller_reports
                ),
                remaining_budget_minor=sum(
                    seller.remaining_budget_minor for seller in seller_reports
                ),
                sellers=tuple(seller_reports),
            )

    def list_access_accounts(self, limit: int) -> list[AccessAccountSummaryRecord]:
        with self._lock:
            accounts = [self._access_summary(account) for account in self.access_accounts.values()]
            return sorted(
                accounts,
                key=lambda item: (item.updated_at or datetime.min.replace(tzinfo=timezone.utc), item.firebase_uid),
                reverse=True,
            )[:limit]

    def list_staff_accounts(self, limit: int) -> list[AccessAccountSummaryRecord]:
        with self._lock:
            accounts = [
                self._access_summary(account)
                for account in self.access_accounts.values()
                if account.role in {"admin", "support", "security"}
            ]
            return sorted(
                accounts,
                key=lambda item: (
                    item.updated_at
                    or datetime.min.replace(tzinfo=timezone.utc),
                    item.firebase_uid,
                ),
                reverse=True,
            )[:limit]

    def get_admin_operations_summary(self) -> AdminOperationsSummaryRecord:
        with self._lock:
            accounts_by_role: dict[str, int] = {}
            accounts_by_status: dict[str, int] = {}
            for account in self.access_accounts.values():
                accounts_by_role[account.role] = accounts_by_role.get(account.role, 0) + 1
                accounts_by_status[account.status] = accounts_by_status.get(account.status, 0) + 1
            return AdminOperationsSummaryRecord(
                accounts_total=len(self.access_accounts),
                accounts_by_role=accounts_by_role,
                accounts_by_status=accounts_by_status,
                institutions_total=len(self.institution_profiles),
                groups_total=len(self.institution_groups),
                groups_active=sum(
                    group.status == "ACTIVE" for group in self.institution_groups.values()
                ),
                merchants_active=sum(
                    merchant.status == "ACTIVE" for merchant in self.merchants.values()
                ),
                merchants_suspended=sum(
                    merchant.status == "SUSPENDED" for merchant in self.merchants.values()
                ),
                products_active=sum(
                    product.status == "ACTIVE" for product in self.products.values()
                ),
                offers_active=sum(offer.status == "ACTIVE" for offer in self.offers.values()),
            )

    def get_security_monitoring_summary(self) -> SecurityMonitoringSummaryRecord:
        with self._lock:
            by_status: dict[str, int] = {}
            for account in self.access_accounts.values():
                by_status[account.status] = by_status.get(account.status, 0) + 1
            return SecurityMonitoringSummaryRecord(
                accounts_total=len(self.access_accounts),
                active_accounts=by_status.get("ACTIVE", 0),
                suspended_accounts=by_status.get("SUSPENDED", 0),
                pending_accounts=by_status.get("PENDING", 0),
                disabled_accounts=by_status.get("DISABLED", 0),
                recent_events_total=len(self.access_audit_events),
                last_event_at=max(
                    (event.created_at for event in self.access_audit_events),
                    default=None,
                ),
            )

    def get_trq_bec_security_status(self) -> TrqBecSecurityStatusRecord:
        with self._lock:
            now = datetime.now(timezone.utc)
            return TrqBecSecurityStatusRecord(
                privileged_accounts_total=len(
                    self.privileged_account_validations
                ),
                official_accounts_total=sum(
                    validation.protection_level == "SYSTEM"
                    and validation.validation_state == "APPROVED"
                    for validation in self.privileged_account_validations.values()
                ),
                privileged_accounts_pending_validation=sum(
                    validation.validation_state == "PENDING"
                    for validation in self.privileged_account_validations.values()
                ),
                access_events_total=len(self.access_audit_events),
                access_events_last_24h=sum(
                    event.created_at >= now - timedelta(hours=24)
                    for event in self.access_audit_events
                ),
                audit_events_total=len(self.events),
                audit_checkpoints_total=0,
                devices_active=sum(
                    device.status == "ACTIVE" for device in self.devices.values()
                ),
                devices_pending=sum(
                    device.status == "PENDING_APPROVAL"
                    for device in self.devices.values()
                ),
                devices_revoked=sum(
                    device.status == "REVOKED" for device in self.devices.values()
                ),
                device_notifications_failed=sum(
                    device.notification_status in {"FAILED", "NOT_CONFIGURED"}
                    for device in self.devices.values()
                ),
                email_verifications_pending=sum(
                    item.status in {"PENDING", "PROCESSING"}
                    for item in self.email_verification_queue.values()
                ),
                email_verifications_failed=sum(
                    item.status == "FAILED"
                    for item in self.email_verification_queue.values()
                ),
                latest_schema_migration="memory-test-store",
            )

    def update_access_account_status(
        self,
        actor_uid: str,
        target_uid: str,
        status: str,
        reason: str,
        *,
        event_id: str,
    ) -> AccessAccountSummaryRecord:
        with self._lock:
            actor = self.access_accounts.get(actor_uid)
            if (
                actor is None
                or actor.role != "security"
                or actor.status != "ACTIVE"
                or "security.incidents.manage" not in actor.permissions
            ):
                raise StoreConflict("SECURITY_ACCESS_REQUIRED")
            current = self.access_accounts.get(target_uid)
            if current is None:
                raise StoreNotFound("ACCESS_ACCOUNT_NOT_FOUND")
            if actor_uid == target_uid:
                raise StoreConflict("SELF_STATUS_CHANGE_FORBIDDEN")
            validation = self.privileged_account_validations.get(target_uid)
            if (
                current.role in {"admin", "security"}
                or (
                    validation is not None
                    and validation.protection_level == "SYSTEM"
                )
            ):
                raise StoreConflict("PROTECTED_ACCOUNT_STATUS_CHANGE")
            if current.status not in {"ACTIVE", "SUSPENDED"}:
                raise StoreConflict("ACCOUNT_STATUS_TRANSITION_FORBIDDEN")
            if current.status == status:
                return self._access_summary(current)

            now = datetime.now(timezone.utc)
            updated = replace(current, status=status)
            self.access_accounts[target_uid] = updated
            created_at = self.access_account_times.get(target_uid, (now, now))[0]
            self.access_account_times[target_uid] = (created_at, now)
            self.access_audit_events.append(
                AccessAuditEventRecord(
                    event_id=event_id,
                    actor_uid=actor_uid,
                    target_uid=target_uid,
                    event_type="ACCOUNT_STATUS_CHANGED",
                    previous_status=current.status,
                    new_status=status,
                    reason=reason,
                    created_at=now,
                )
            )
            return self._access_summary(updated)

    def list_access_audit_events(self, limit: int) -> list[AccessAuditEventRecord]:
        with self._lock:
            return sorted(
                self.access_audit_events,
                key=lambda item: (item.created_at, item.event_id),
                reverse=True,
            )[:limit]

    def enroll_device(
        self,
        uid: str,
        key_id: str,
        public_key_b64u: str,
        algorithm: str,
        storage_profile: str,
        auth_is_recent: bool,
        *,
        device_name: str | None,
        platform: str,
        model_name: str | None,
        app_version: str | None,
        approval_token_hash: str,
        approval_expires_at: datetime,
        max_pending_devices: int,
        requires_approval: bool,
        first_device_requires_approval: bool,
        **audit: Any,
    ):
        with self._lock:
            now = datetime.now(timezone.utc)
            current = self.devices.get(key_id)
            if current:
                if (
                    current.firebase_uid != uid
                    or current.public_key_b64u != public_key_b64u
                    or current.algorithm != algorithm
                    or current.storage_profile != storage_profile
                ):
                    raise StoreConflict("DEVICE_KEY_BINDING_CONFLICT")
                if current.status == "REVOKED":
                    raise StoreConflict("DEVICE_KEY_REVOKED")
                bypassed_approval = (
                    not requires_approval
                    and current.status == "PENDING_APPROVAL"
                )
                current = replace(
                    current,
                    device_name=device_name or current.device_name,
                    platform=current.platform if platform == "unknown" else platform,
                    model_name=model_name or current.model_name,
                    app_version=app_version or current.app_version,
                    last_seen_at=datetime.now(timezone.utc),
                    status="ACTIVE" if bypassed_approval else current.status,
                    notification_status=(
                        "NOT_REQUIRED"
                        if bypassed_approval
                        else current.notification_status
                    ),
                    approval_expires_at=(
                        None
                        if bypassed_approval
                        else current.approval_expires_at
                    ),
                    approved_at=(
                        current.approved_at or now
                        if bypassed_approval
                        else current.approved_at
                    ),
                )
                self.devices[key_id] = current
                if bypassed_approval:
                    self.device_approval_hashes.pop(key_id, None)
                self.append_audit(
                    result=(
                        "VISITOR_DEVICE_ACTIVATED"
                        if bypassed_approval
                        else "ALREADY_ENROLLED"
                    ),
                    **audit,
                )
                return current, False, bypassed_approval or current.status == "PENDING_APPROVAL"
            if not auth_is_recent:
                raise StoreConflict("RECENT_AUTHENTICATION_REQUIRED")
            history = [
                item
                for item in self.devices.values()
                if item.firebase_uid == uid
            ]
            pending_count = sum(item.status == "PENDING_APPROVAL" for item in history)
            is_additional = bool(history)
            approval_required_for_device = requires_approval and (
                is_additional or first_device_requires_approval
            )
            if (
                approval_required_for_device
                and pending_count >= max_pending_devices
            ):
                raise StoreConflict("PENDING_DEVICE_LIMIT_REACHED")
            if any(item.firebase_uid == uid and item.public_key_b64u == public_key_b64u for item in self.devices.values()):
                raise StoreConflict("DEVICE_PUBLIC_KEY_ALREADY_BOUND")
            status = (
                "PENDING_APPROVAL"
                if approval_required_for_device
                else "ACTIVE"
            )
            record = DeviceRecord(
                firebase_uid=uid,
                device_key_id=key_id,
                public_key_b64u=public_key_b64u,
                algorithm=algorithm,
                storage_profile=storage_profile,
                status=status,
                device_name=device_name,
                platform=platform,
                model_name=model_name,
                app_version=app_version,
                notification_status=(
                    "PENDING" if status == "PENDING_APPROVAL" else "NOT_REQUIRED"
                ),
                created_at=now,
                last_seen_at=now,
                approval_expires_at=(
                    approval_expires_at if status == "PENDING_APPROVAL" else None
                ),
                approval_last_sent_at=(
                    now if status == "PENDING_APPROVAL" else None
                ),
                approved_at=None if status == "PENDING_APPROVAL" else now,
            )
            self.devices[key_id] = record
            if status == "PENDING_APPROVAL":
                self.device_approval_hashes[key_id] = approval_token_hash
            try:
                self.append_audit(
                    result=(
                        "ENROLLED_PENDING_APPROVAL"
                        if status == "PENDING_APPROVAL"
                        else "ENROLLED"
                    ),
                    **audit,
                )
            except Exception:
                del self.devices[key_id]
                self.device_approval_hashes.pop(key_id, None)
                raise
            return record, True, is_additional

    def list_devices(self, uid: str, limit: int) -> list[DeviceRecord]:
        with self._lock:
            order = {"PENDING_APPROVAL": 0, "ACTIVE": 1, "REVOKED": 2}
            devices = [item for item in self.devices.values() if item.firebase_uid == uid]
            return sorted(
                devices,
                key=lambda item: (
                    order.get(item.status, 3),
                    -(item.last_seen_at or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
                    item.device_key_id,
                ),
            )[:limit]

    def activate_due_devices(
        self, uid: str, activated_at: datetime, **audit: Any
    ) -> int:
        with self._lock:
            previous_devices = dict(self.devices)
            previous_hashes = dict(self.device_approval_hashes)
            activated = 0
            for key_id, item in list(self.devices.items()):
                if (
                    item.firebase_uid != uid
                    or item.status != "PENDING_APPROVAL"
                    or item.approval_expires_at is None
                    or item.approval_expires_at > activated_at
                ):
                    continue
                self.devices[key_id] = replace(
                    item,
                    status="ACTIVE",
                    approval_expires_at=None,
                    approved_at=item.approved_at or activated_at,
                )
                self.device_approval_hashes.pop(key_id, None)
                activated += 1
            if not activated:
                return 0
            try:
                details = dict(audit.get("details") or {})
                details["activated_device_count"] = activated
                self.append_audit(
                    **{
                        **audit,
                        "details": details,
                        "result": "AUTO_ACTIVATED",
                    }
                )
            except Exception:
                self.devices = previous_devices
                self.device_approval_hashes = previous_hashes
                raise
            return activated

    def set_device_notification_status(
        self, uid: str, key_id: str, notification_status: str
    ) -> DeviceRecord:
        with self._lock:
            item = self.devices.get(key_id)
            if item is None or item.firebase_uid != uid:
                raise StoreNotFound("DEVICE_NOT_FOUND")
            updated = replace(item, notification_status=notification_status)
            self.devices[key_id] = updated
            return updated

    def approve_device(
        self, uid: str, approval_token_hash: str, approved_at: datetime, **audit: Any
    ) -> DeviceRecord:
        with self._lock:
            match = next(
                (
                    item
                    for key_id, item in self.devices.items()
                    if item.firebase_uid == uid
                    and self.device_approval_hashes.get(key_id) == approval_token_hash
                ),
                None,
            )
            if (
                match is None
                or match.status != "PENDING_APPROVAL"
                or match.approval_expires_at is None
                or match.approval_expires_at <= approved_at
            ):
                raise StoreConflict("DEVICE_APPROVAL_INVALID_OR_EXPIRED")
            previous = match
            updated = replace(
                match,
                status="ACTIVE",
                approval_expires_at=None,
                approved_at=approved_at,
                last_seen_at=approved_at,
            )
            self.devices[match.device_key_id] = updated
            self.device_approval_hashes.pop(match.device_key_id, None)
            try:
                self.append_audit(result="APPROVED", **audit)
            except Exception:
                self.devices[match.device_key_id] = previous
                self.device_approval_hashes[match.device_key_id] = approval_token_hash
                raise
            return updated

    def rotate_device_approval(
        self,
        uid: str,
        key_id: str,
        approval_token_hash: str,
        approval_expires_at: datetime,
        cooldown_seconds: int,
        **audit: Any,
    ) -> DeviceRecord:
        with self._lock:
            item = self.devices.get(key_id)
            if item is None or item.firebase_uid != uid:
                raise StoreNotFound("DEVICE_NOT_FOUND")
            if item.status != "PENDING_APPROVAL":
                raise StoreConflict("DEVICE_APPROVAL_NOT_PENDING")
            now = datetime.now(timezone.utc)
            if (
                item.approval_last_sent_at is not None
                and (now - item.approval_last_sent_at).total_seconds() < cooldown_seconds
            ):
                raise StoreConflict("APPROVAL_RESEND_COOLDOWN")
            previous_hash = self.device_approval_hashes.get(key_id)
            updated = replace(
                item,
                approval_last_sent_at=now,
                notification_status="PENDING",
            )
            self.devices[key_id] = updated
            self.device_approval_hashes[key_id] = approval_token_hash
            try:
                self.append_audit(result="APPROVAL_REISSUED", **audit)
            except Exception:
                self.devices[key_id] = item
                if previous_hash is None:
                    self.device_approval_hashes.pop(key_id, None)
                else:
                    self.device_approval_hashes[key_id] = previous_hash
                raise
            return updated

    def revoke_all_devices(self, uid: str, **audit: Any) -> int:
        with self._lock:
            previous_devices = dict(self.devices)
            previous_hashes = dict(self.device_approval_hashes)
            revoked = 0
            now = datetime.now(timezone.utc)
            for key_id, item in list(self.devices.items()):
                if item.firebase_uid != uid or item.status not in {"ACTIVE", "PENDING_APPROVAL"}:
                    continue
                self.devices[key_id] = replace(
                    item,
                    status="REVOKED",
                    revoked_at=item.revoked_at or now,
                    approval_expires_at=None,
                    notification_status="NOT_REQUIRED",
                )
                self.device_approval_hashes.pop(key_id, None)
                revoked += 1
            try:
                self.append_audit(result="ALL_DEVICES_REVOKED", **audit)
            except Exception:
                self.devices = previous_devices
                self.device_approval_hashes = previous_hashes
                raise
            return revoked

    def get_device(self, uid: str, key_id: str):
        with self._lock:
            item = self.devices.get(key_id)
            return item if item and item.firebase_uid == uid and item.status == "ACTIVE" else None

    def set_merchant_status(self, merchant: MerchantRecord, **audit: Any):
        with self._lock:
            previous = self.merchants.get(merchant.firebase_uid)
            previous_access = self.access_accounts.get(merchant.firebase_uid)
            if previous_access and previous_access.role != "entrepreneur" and merchant.status == "ACTIVE":
                raise StoreConflict("ACCESS_ROLE_CONFLICT")
            if previous_access and previous_access.status == "DISABLED" and merchant.status == "ACTIVE":
                raise StoreConflict("ACCOUNT_DISABLED")
            self.merchants[merchant.firebase_uid] = merchant
            if previous_access is None:
                self.access_accounts[merchant.firebase_uid] = AccessAccountRecord(
                    firebase_uid=merchant.firebase_uid,
                    email=None,
                    role="entrepreneur",
                    status=merchant.status,
                    allow_entrepreneur_fallback=False,
                    permissions=default_permissions("entrepreneur"),
                )
            elif previous_access.role == "entrepreneur" and previous_access.status != "DISABLED":
                self.access_accounts[merchant.firebase_uid] = replace(
                    previous_access,
                    status=merchant.status,
                )
            try:
                self.append_audit(**audit)
            except Exception:
                if previous is None:
                    del self.merchants[merchant.firebase_uid]
                else:
                    self.merchants[merchant.firebase_uid] = previous
                if previous_access is None:
                    self.access_accounts.pop(merchant.firebase_uid, None)
                else:
                    self.access_accounts[merchant.firebase_uid] = previous_access
                raise
            return merchant

    def get_active_merchant(self, uid: str):
        with self._lock:
            item = self.merchants.get(uid)
            return item if item and item.status == "ACTIVE" else None

    def close_account(self, uid: str, **audit: Any) -> None:
        with self._lock:
            previous = (
                dict(self.merchants),
                dict(self.products),
                dict(self.offers),
                dict(self.tokens),
                dict(self.devices),
                dict(self.device_approval_hashes),
                dict(self.coupons),
                dict(self.access_accounts),
            )
            changed = False
            now = int(time.time())

            merchant = self.merchants.get(uid)
            if merchant is not None and merchant.status == "ACTIVE":
                self.merchants[uid] = replace(merchant, status="SUSPENDED")
                changed = True
            access_account = self.access_accounts.get(uid)
            if access_account is not None and access_account.status != "DISABLED":
                self.access_accounts[uid] = replace(access_account, status="DISABLED")
                changed = True
            for product_id, product in list(self.products.items()):
                if product.merchant_uid == uid and product.status != "ARCHIVED":
                    self.products[product_id] = replace(product, status="ARCHIVED", updated_at=now)
                    changed = True
            for offer_id, offer in list(self.offers.items()):
                if offer.merchant_uid == uid and offer.status in {"ACTIVE", "PAUSED"}:
                    self.offers[offer_id] = replace(offer, status="CANCELLED", updated_at=now)
                    changed = True
            for token_ref, token in list(self.tokens.items()):
                if token.issuer_uid == uid and token.status == "ISSUED":
                    self.tokens[token_ref] = replace(token, status="REVOKED")
                    changed = True
            for device_key_id, device in list(self.devices.items()):
                if device.firebase_uid == uid and device.status in {"ACTIVE", "PENDING_APPROVAL"}:
                    self.devices[device_key_id] = replace(
                        device,
                        status="REVOKED",
                        revoked_at=datetime.now(timezone.utc),
                        approval_expires_at=None,
                        notification_status="NOT_REQUIRED",
                    )
                    self.device_approval_hashes.pop(device_key_id, None)
                    changed = True
            for coupon_id, coupon in list(self.coupons.items()):
                if coupon.owner_uid == uid and coupon.active:
                    self.coupons[coupon_id] = replace(coupon, active=False)
                    changed = True

            if not changed:
                return
            try:
                self.append_audit(**audit)
            except Exception:
                (
                    self.merchants,
                    self.products,
                    self.offers,
                    self.tokens,
                    self.devices,
                    self.device_approval_hashes,
                    self.coupons,
                    self.access_accounts,
                ) = previous
                raise

    def create_product(self, product: ProductRecord, **audit: Any):
        with self._lock:
            merchant = self.merchants.get(product.merchant_uid)
            if merchant is None or merchant.status != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            if product.product_id in self.products:
                raise StoreConflict("PRODUCT_ID_EXISTS")
            self.products[product.product_id] = product
            try:
                self.append_audit(**audit)
            except Exception:
                del self.products[product.product_id]
                raise
            return product

    def update_product_stock(
        self,
        uid: str,
        product_id: str,
        stock_quantity: int,
        **audit: Any,
    ):
        with self._lock:
            merchant = self.merchants.get(uid)
            if merchant is None or merchant.status != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            product = self.products.get(product_id)
            if product is None or product.merchant_uid != uid or product.status == "ARCHIVED":
                raise StoreNotFound("PRODUCT_NOT_FOUND_OR_NOT_OWNED")
            updated = replace(
                product,
                stock_quantity=stock_quantity,
                updated_at=int(time.time()),
            )
            self.products[product_id] = updated
            try:
                self.append_audit(**audit)
            except Exception:
                self.products[product_id] = product
                raise
            return updated

    def list_products(self, uid: str):
        with self._lock:
            return [product for product in self.products.values() if product.merchant_uid == uid]

    def get_marketplace_batch_response(
        self,
        uid: str,
        client_request_id: str,
        operation_kind: str,
        command_hash: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            prior = self.marketplace_batch_idempotency.get(
                (uid, client_request_id)
            )
            if prior is None:
                return None
            prior_kind, prior_hash, response = prior
            if prior_kind != operation_kind or prior_hash != command_hash:
                raise StoreConflict("BATCH_CLIENT_REQUEST_ID_REUSED")
            return copy.deepcopy(response)

    def _prior_marketplace_batch_response_locked(
        self,
        uid: str,
        client_request_id: str,
        operation_kind: str,
        command_hash: str,
    ) -> dict[str, Any] | None:
        prior = self.marketplace_batch_idempotency.get((uid, client_request_id))
        if prior is None:
            return None
        prior_kind, prior_hash, response = prior
        if prior_kind != operation_kind or prior_hash != command_hash:
            raise StoreConflict("BATCH_CLIENT_REQUEST_ID_REUSED")
        return copy.deepcopy(response)

    def archive_products_batch(
        self,
        uid: str,
        product_ids: tuple[str, ...],
        *,
        client_request_id: str,
        operation_kind: str,
        command_hash: str,
        batch_operation_id: str,
        response_factory: Callable[[list[ProductRecord]], dict[str, Any]],
        **audit: Any,
    ) -> dict[str, Any]:
        with self._lock:
            if not product_ids or len(set(product_ids)) != len(product_ids):
                raise StoreConflict("PRODUCT_BATCH_IDS_INVALID")
            prior = self._prior_marketplace_batch_response_locked(
                uid, client_request_id, operation_kind, command_hash
            )
            if prior is not None:
                return prior
            merchant = self.merchants.get(uid)
            if merchant is None or merchant.status != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            selected = [self.products.get(product_id) for product_id in product_ids]
            if any(
                product is None
                or product.merchant_uid != uid
                for product in selected
            ):
                raise StoreNotFound("PRODUCT_BATCH_NOT_FOUND_OR_FINAL")
            previous_products = dict(self.products)
            previous_offers = dict(self.offers)
            previous_tokens = dict(self.tokens)
            previous_events = list(self.events)
            previous_idempotency = copy.deepcopy(
                self.marketplace_batch_idempotency
            )
            now = int(time.time())
            try:
                for product in selected:
                    assert product is not None
                    self.products[product.product_id] = replace(
                        product, status="ARCHIVED", updated_at=now
                    )
                selected_ids = set(product_ids)
                for offer_id, offer in list(self.offers.items()):
                    if (
                        offer.merchant_uid == uid
                        and offer.product_id in selected_ids
                        and offer.status in {"ACTIVE", "PAUSED"}
                    ):
                        self.offers[offer_id] = replace(
                            offer, status="REVOKED", updated_at=now
                        )
                        token = self.tokens.get(offer.token_ref)
                        if token and token.status == "ISSUED":
                            self.tokens[offer.token_ref] = replace(
                                token, status="REVOKED"
                            )
                self.append_audit(**audit)
                products = [self.products[product_id] for product_id in product_ids]
                response = response_factory(products)
                self.marketplace_batch_idempotency[(uid, client_request_id)] = (
                    operation_kind,
                    command_hash,
                    copy.deepcopy(response),
                )
            except Exception:
                self.products = previous_products
                self.offers = previous_offers
                self.tokens = previous_tokens
                self.events = previous_events
                self.marketplace_batch_idempotency = previous_idempotency
                raise
            return copy.deepcopy(response)

    def activate_products_batch(
        self,
        uid: str,
        product_stocks: tuple[tuple[str, int], ...],
        *,
        client_request_id: str,
        operation_kind: str,
        command_hash: str,
        batch_operation_id: str,
        response_factory: Callable[[list[ProductRecord]], dict[str, Any]],
        **audit: Any,
    ) -> dict[str, Any]:
        del batch_operation_id
        product_ids = tuple(product_id for product_id, _ in product_stocks)
        if (
            not product_stocks
            or len(set(product_ids)) != len(product_ids)
            or any(stock_quantity <= 0 for _, stock_quantity in product_stocks)
        ):
            raise StoreConflict("PRODUCT_BATCH_ACTIVATE_ITEMS_INVALID")
        with self._lock:
            prior = self._prior_marketplace_batch_response_locked(
                uid, client_request_id, operation_kind, command_hash
            )
            if prior is not None:
                return prior
            merchant = self.merchants.get(uid)
            if merchant is None or merchant.status != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            selected = [self.products.get(product_id) for product_id in product_ids]
            if any(
                product is None
                or product.merchant_uid != uid
                or product.status == "ARCHIVED"
                for product in selected
            ):
                raise StoreNotFound("PRODUCT_BATCH_NOT_FOUND_OR_NOT_OWNED")

            previous_products = dict(self.products)
            previous_events = list(self.events)
            previous_idempotency = copy.deepcopy(
                self.marketplace_batch_idempotency
            )
            now = int(time.time())
            try:
                stocks_by_id = dict(product_stocks)
                for product in selected:
                    assert product is not None
                    self.products[product.product_id] = replace(
                        product,
                        status="ACTIVE",
                        stock_quantity=stocks_by_id[product.product_id],
                        updated_at=now,
                    )
                self.append_audit(**audit)
                products = [self.products[product_id] for product_id in product_ids]
                response = response_factory(products)
                self.marketplace_batch_idempotency[(uid, client_request_id)] = (
                    operation_kind,
                    command_hash,
                    copy.deepcopy(response),
                )
            except Exception:
                self.products = previous_products
                self.events = previous_events
                self.marketplace_batch_idempotency = previous_idempotency
                raise
            return copy.deepcopy(response)

    @staticmethod
    def _catalog_merchant(merchant: MerchantRecord) -> CatalogMerchantRecord:
        return CatalogMerchantRecord(
            firebase_uid=merchant.firebase_uid,
            display_name=merchant.display_name,
            establishment_name=merchant.establishment_name,
        )

    def _catalog_offers_for_product(
        self,
        product: ProductRecord,
        *,
        now: int,
        product_state: tuple[str, str | None, int | None],
    ) -> tuple[CatalogOfferRecord, ...]:
        public_offers: list[CatalogOfferRecord] = []
        for offer in reversed(list(self.offers.values())):
            if offer.product_id != product.product_id or offer.merchant_uid != product.merchant_uid:
                continue
            token = self.tokens.get(offer.token_ref)
            remaining = max(
                0,
                min(
                    offer.maximum_redemptions - offer.redeemed_count,
                    product.stock_quantity,
                ),
            )
            updated_at = offer.updated_at or offer.created_at or now
            public_state = offer_public_state(
                offer_status=offer.status,
                expires_at=offer.expires_at,
                updated_at=updated_at,
                remaining_redemptions=remaining,
                token_redeemable=(
                    token is not None
                    and token.offer_id == offer.offer_id
                    and token.status == "ISSUED"
                    and token.expires_at > now
                ),
                product_status=product_state[0],
                product_status_reason=product_state[1],
                product_ended_at=product_state[2],
                now=now,
            )
            if public_state is None:
                continue
            public_offers.append(
                CatalogOfferRecord(
                    offer_id=offer.offer_id,
                    original_amount_minor=offer.original_amount_minor,
                    discount_amount_minor=offer.discount_amount_minor,
                    final_amount_minor=offer.final_amount_minor,
                    currency=offer.currency,
                    remaining_redemptions=remaining,
                    expires_at=offer.expires_at,
                    created_at=offer.created_at or updated_at,
                    updated_at=updated_at,
                    status=public_state[0],
                    status_reason=public_state[1],
                    ended_at=public_state[2],
                )
            )
            if len(public_offers) == 50:
                break
        return tuple(public_offers)

    def _list_public_catalog_locked(
        self,
        *,
        merchant_uid: str | None,
        limit: int,
    ) -> list[CatalogProductRecord]:
        now = int(time.time())
        bounded_limit = max(0, min(int(limit), 50))
        if bounded_limit == 0:
            return []
        public_products: list[CatalogProductRecord] = []
        for product in reversed(list(self.products.values())):
            merchant = self.merchants.get(product.merchant_uid)
            if (
                merchant is None
                or merchant.status != "ACTIVE"
                or (merchant_uid is not None and product.merchant_uid != merchant_uid)
            ):
                continue
            updated_at = product.updated_at or product.created_at or now
            public_state = product_public_state(
                product_status=product.status,
                stock_quantity=product.stock_quantity,
                updated_at=updated_at,
            )
            if public_state is None:
                continue
            public_products.append(
                CatalogProductRecord(
                    product_id=product.product_id,
                    title=product.title,
                    description=product.description,
                    price_minor=product.price_minor,
                    currency=product.currency,
                    stock_quantity=product.stock_quantity,
                    created_at=product.created_at or updated_at,
                    updated_at=updated_at,
                    status=public_state[0],
                    status_reason=public_state[1],
                    ended_at=public_state[2],
                    merchant=self._catalog_merchant(merchant),
                    offers=self._catalog_offers_for_product(
                        product,
                        now=now,
                        product_state=public_state,
                    ),
                )
            )
            if len(public_products) == bounded_limit:
                break
        return public_products

    def list_public_catalog(self, limit: int) -> list[CatalogProductRecord]:
        with self._lock:
            return self._list_public_catalog_locked(merchant_uid=None, limit=limit)

    def get_public_merchant_catalog(
        self,
        firebase_uid: str,
        limit: int,
    ) -> tuple[CatalogMerchantRecord, list[CatalogProductRecord]] | None:
        with self._lock:
            merchant = self.merchants.get(firebase_uid)
            if merchant is None or merchant.status != "ACTIVE":
                return None
            products = self._list_public_catalog_locked(
                merchant_uid=firebase_uid,
                limit=limit,
            )
            return self._catalog_merchant(merchant), products

    def get_product_for_offer(self, uid: str, product_id: str):
        with self._lock:
            product = self.products.get(product_id)
            merchant = self.merchants.get(uid)
            if (
                product is None
                or product.merchant_uid != uid
                or product.status != "ACTIVE"
                or product.stock_quantity <= 0
                or merchant is None
                or merchant.status != "ACTIVE"
            ):
                return None
            return product

    def create_live_offer(
        self,
        offer: OfferRecord,
        token: TokenRecord,
        *,
        discount_type: str,
        discount_value: int,
        **audit: Any,
    ):
        with self._lock:
            merchant = self.merchants.get(offer.merchant_uid)
            product = self.products.get(offer.product_id)
            if merchant is None or merchant.status != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            if (
                product is None
                or product.merchant_uid != offer.merchant_uid
                or product.status != "ACTIVE"
            ):
                raise StoreConflict("PRODUCT_NOT_ACTIVE_OR_NOT_OWNED")
            if product.price_minor != offer.original_amount_minor or product.currency != offer.currency:
                raise StoreConflict("AUTHORITATIVE_PRODUCT_CHANGED")
            if product.stock_quantity < offer.maximum_redemptions:
                raise StoreConflict("OFFER_LIMIT_EXCEEDS_STOCK")
            if offer.offer_id in self.offers or token.token_ref in self.tokens:
                raise StoreConflict("LIVE_OFFER_CREATE_FAILED")
            self.offers[offer.offer_id] = offer
            self.tokens[token.token_ref] = token
            try:
                return self.append_audit(**audit)
            except Exception:
                del self.offers[offer.offer_id]
                del self.tokens[token.token_ref]
                raise

    def _offer_with_current_stock(self, offer: OfferRecord) -> OfferRecord:
        product = self.products.get(offer.product_id)
        merchant = self.merchants.get(offer.merchant_uid)
        return replace(
            offer,
            stock_quantity=product.stock_quantity if product else 0,
            product_status=product.status if product else "ARCHIVED",
            merchant_status=merchant.status if merchant else "SUSPENDED",
        )

    def get_offer_by_token(self, token_ref: str):
        with self._lock:
            token = self.tokens.get(token_ref)
            offer = self.offers.get(token.offer_id) if token and token.offer_id else None
            return self._offer_with_current_stock(offer) if offer else None

    def expire_offer(self, token_ref: str, **audit: Any) -> None:
        with self._lock:
            token = self.tokens.get(token_ref)
            offer = self.offers.get(token.offer_id) if token and token.offer_id else None
            if offer is None:
                raise StoreNotFound("OFFER_NOT_FOUND")
            if offer.status == "EXPIRED":
                return
            if offer.status not in {"ACTIVE", "PAUSED"} or offer.expires_at > int(time.time()):
                return
            updated_offer = replace(
                offer,
                status="EXPIRED",
                updated_at=int(time.time()),
            )
            updated_token = replace(token, status="EXPIRED") if token.status == "ISSUED" else token
            self.offers[offer.offer_id] = updated_offer
            self.tokens[token_ref] = updated_token
            try:
                self.append_audit(**audit)
            except Exception:
                self.offers[offer.offer_id] = offer
                self.tokens[token_ref] = token
                raise

    def list_offers(self, uid: str):
        with self._lock:
            return [
                self._offer_with_current_stock(offer)
                for offer in self.offers.values()
                if offer.merchant_uid == uid
            ]

    def revoke_offer(self, uid: str, offer_id: str, **audit: Any) -> OfferRecord:
        with self._lock:
            merchant = self.merchants.get(uid)
            if merchant is None or merchant.status != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            offer = self.offers.get(offer_id)
            if offer is None or offer.merchant_uid != uid or offer.status == "REVOKED":
                raise StoreNotFound("OFFER_NOT_FOUND")
            token = self.tokens.get(offer.token_ref)
            previous_events = list(self.events)
            updated = replace(
                offer,
                status="REVOKED",
                updated_at=int(time.time()),
            )
            self.offers[offer_id] = updated
            if token is not None and token.status == "ISSUED":
                self.tokens[offer.token_ref] = replace(token, status="REVOKED")
            try:
                self.append_audit(**audit)
            except Exception:
                self.offers[offer_id] = offer
                if token is not None:
                    self.tokens[offer.token_ref] = token
                self.events = previous_events
                raise
            return self._offer_with_current_stock(updated)

    def get_offers_for_batch(
        self, uid: str, offer_ids: tuple[str, ...]
    ) -> list[OfferRecord]:
        with self._lock:
            if not offer_ids or len(set(offer_ids)) != len(offer_ids):
                raise StoreConflict("OFFER_BATCH_IDS_INVALID")
            merchant = self.merchants.get(uid)
            if merchant is None or merchant.status != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            now = int(time.time())
            selected: list[OfferRecord] = []
            for offer_id in offer_ids:
                offer = self.offers.get(offer_id)
                product = self.products.get(offer.product_id) if offer else None
                token = self.tokens.get(offer.token_ref) if offer else None
                if (
                    offer is None
                    or offer.merchant_uid != uid
                    or offer.status not in {"ACTIVE", "PAUSED"}
                    or offer.expires_at <= now
                    or offer.redeemed_count >= offer.maximum_redemptions
                    or product is None
                    or product.status != "ACTIVE"
                    or product.stock_quantity <= 0
                    or product.price_minor != offer.original_amount_minor
                    or product.currency != offer.currency
                    or token is None
                    or token.offer_id != offer.offer_id
                    or token.status != "ISSUED"
                    or token.expires_at <= now
                ):
                    raise StoreNotFound("OFFER_BATCH_NOT_FOUND_OR_FINAL")
                selected.append(self._offer_with_current_stock(offer))
            return selected

    def revoke_offers_batch(
        self,
        uid: str,
        offer_ids: tuple[str, ...],
        *,
        client_request_id: str,
        operation_kind: str,
        command_hash: str,
        batch_operation_id: str,
        response_factory: Callable[[list[OfferRecord]], dict[str, Any]],
        **audit: Any,
    ) -> dict[str, Any]:
        with self._lock:
            prior = self._prior_marketplace_batch_response_locked(
                uid, client_request_id, operation_kind, command_hash
            )
            if prior is not None:
                return prior
            self.get_offers_for_batch(uid, offer_ids)
            previous_offers = dict(self.offers)
            previous_tokens = dict(self.tokens)
            previous_events = list(self.events)
            previous_idempotency = copy.deepcopy(
                self.marketplace_batch_idempotency
            )
            now = int(time.time())
            try:
                for offer_id in offer_ids:
                    offer = self.offers[offer_id]
                    token = self.tokens[offer.token_ref]
                    if token.status != "ISSUED":
                        raise StoreConflict("OFFER_BATCH_TOKEN_CHANGED")
                    self.tokens[offer.token_ref] = replace(token, status="REVOKED")
                    self.offers[offer_id] = replace(
                        offer, status="REVOKED", updated_at=now
                    )
                self.append_audit(**audit)
                offers = [
                    self._offer_with_current_stock(self.offers[offer_id])
                    for offer_id in offer_ids
                ]
                response = response_factory(offers)
                self.marketplace_batch_idempotency[(uid, client_request_id)] = (
                    operation_kind,
                    command_hash,
                    copy.deepcopy(response),
                )
            except Exception:
                self.offers = previous_offers
                self.tokens = previous_tokens
                self.events = previous_events
                self.marketplace_batch_idempotency = previous_idempotency
                raise
            return copy.deepcopy(response)

    def rotate_offers_batch(
        self,
        uid: str,
        mutations: tuple[OfferBatchMutationRecord, ...],
        *,
        client_request_id: str,
        operation_kind: str,
        command_hash: str,
        batch_operation_id: str,
        response_factory: Callable[[list[OfferRecord]], dict[str, Any]],
        **audit: Any,
    ) -> dict[str, Any]:
        with self._lock:
            offer_ids = tuple(mutation.offer_id for mutation in mutations)
            prior = self._prior_marketplace_batch_response_locked(
                uid, client_request_id, operation_kind, command_hash
            )
            if prior is not None:
                return prior
            current = self.get_offers_for_batch(uid, offer_ids)
            current_by_id = {offer.offer_id: offer for offer in current}
            now = int(time.time())
            for mutation in mutations:
                offer = current_by_id[mutation.offer_id]
                product = self.products[offer.product_id]
                if (
                    offer.token_ref != mutation.expected_token_ref
                    or offer.discount_type != mutation.expected_discount_type
                    or offer.discount_value != mutation.expected_discount_value
                    or offer.expires_at != mutation.expected_expires_at
                    or mutation.new_discount_type != offer.discount_type
                ):
                    raise StoreConflict("OFFER_BATCH_CHANGED_RETRY")
                if mutation.new_discount_type == "PERCENT":
                    valid_discount = 1 <= mutation.new_discount_value <= 90
                    expected_amount = (
                        product.price_minor * mutation.new_discount_value // 100
                    )
                elif mutation.new_discount_type == "FIXED_AMOUNT":
                    valid_discount = mutation.new_discount_value > 0
                    expected_amount = mutation.new_discount_value
                else:
                    valid_discount = False
                    expected_amount = 0
                token = mutation.new_token
                envelope = CryptoEnvelope.from_dict(token.envelope)
                if (
                    not valid_discount
                    or expected_amount <= 0
                    or expected_amount >= product.price_minor
                    or mutation.new_discount_amount_minor != expected_amount
                    or mutation.new_final_amount_minor
                    != product.price_minor - expected_amount
                    or mutation.new_expires_at <= now
                    or token.offer_id != mutation.offer_id
                    or token.issuer_uid != uid
                    or token.status != "ISSUED"
                    or token.expires_at != mutation.new_expires_at
                    or envelope.exp != mutation.new_expires_at
                    or token.intent.get("resource_ref")
                    != f"offer/{mutation.offer_id}"
                    or int(token.intent.get("amount_minor", -1))
                    != mutation.new_final_amount_minor
                ):
                    raise StoreConflict("OFFER_BATCH_TOKEN_INVALID")
            previous_offers = dict(self.offers)
            previous_tokens = dict(self.tokens)
            previous_events = list(self.events)
            previous_idempotency = copy.deepcopy(
                self.marketplace_batch_idempotency
            )
            try:
                for mutation in mutations:
                    offer = self.offers[mutation.offer_id]
                    old_token = self.tokens.get(mutation.expected_token_ref)
                    if old_token is None or old_token.status != "ISSUED":
                        raise StoreConflict("OFFER_BATCH_TOKEN_CHANGED")
                    if mutation.new_token.token_ref in self.tokens:
                        raise StoreConflict("TOKEN_REFERENCE_EXISTS")
                    self.tokens[old_token.token_ref] = replace(
                        old_token, status="REVOKED"
                    )
                    self.tokens[mutation.new_token.token_ref] = mutation.new_token
                    self.offers[offer.offer_id] = replace(
                        offer,
                        token_ref=mutation.new_token.token_ref,
                        discount_type=mutation.new_discount_type,
                        discount_value=mutation.new_discount_value,
                        discount_amount_minor=mutation.new_discount_amount_minor,
                        final_amount_minor=mutation.new_final_amount_minor,
                        expires_at=mutation.new_expires_at,
                        updated_at=now,
                    )
                self.append_audit(**audit)
                offers = [
                    self._offer_with_current_stock(self.offers[offer_id])
                    for offer_id in offer_ids
                ]
                response = response_factory(offers)
                self.marketplace_batch_idempotency[(uid, client_request_id)] = (
                    operation_kind,
                    command_hash,
                    copy.deepcopy(response),
                )
            except Exception:
                self.offers = previous_offers
                self.tokens = previous_tokens
                self.events = previous_events
                self.marketplace_batch_idempotency = previous_idempotency
                raise
            return copy.deepcopy(response)

    def update_offer_status(self, uid: str, offer_id: str, status: str, **audit: Any):
        expired = False
        with self._lock:
            merchant = self.merchants.get(uid)
            if merchant is None or merchant.status != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            offer = self.offers.get(offer_id)
            if offer is None or offer.merchant_uid != uid or offer.status in {"EXHAUSTED", "EXPIRED", "REVOKED", "CANCELLED"}:
                raise StoreNotFound("OFFER_NOT_FOUND_OR_FINAL")
            effective_status = "EXPIRED" if offer.expires_at <= int(time.time()) else status
            updated = replace(
                offer,
                status=effective_status,
                updated_at=int(time.time()),
            )
            self.offers[offer_id] = updated
            token = self.tokens.get(offer.token_ref)
            previous_token = token
            if token and token.status == "ISSUED" and effective_status in {"CANCELLED", "EXPIRED"}:
                token_status = "REVOKED" if effective_status == "CANCELLED" else "EXPIRED"
                self.tokens[offer.token_ref] = replace(token, status=token_status)
            selected_audit = audit
            if effective_status == "EXPIRED":
                selected_audit = {
                    **audit,
                    "event_type": "OFFER_EXPIRED",
                    "result": "EXPIRED",
                    "reason_codes": ("OFFER_EXPIRED",),
                }
                expired = True
            try:
                self.append_audit(**selected_audit)
            except Exception:
                self.offers[offer_id] = offer
                if previous_token is not None:
                    self.tokens[offer.token_ref] = previous_token
                raise
            result = self._offer_with_current_stock(updated)
        if expired:
            raise StoreConflict("OFFER_EXPIRED")
        return result

    def get_coupon_for_issue(self, coupon_id: str, owner_uid: str):
        item = self.coupons.get(coupon_id)
        return item if item and item.active and (item.owner_uid is None or item.owner_uid == owner_uid) else None

    def store_token(self, token: TokenRecord) -> None:
        with self._lock:
            if token.token_ref in self.tokens:
                raise StoreConflict("TOKEN_REFERENCE_EXISTS")
            self.tokens[token.token_ref] = token

    def get_token(self, token_ref: str):
        with self._lock:
            return self.tokens.get(token_ref)

    def create_operation(self, operation: OperationRecord, **audit: Any) -> None:
        with self._lock:
            if operation.operation_id in self.operations:
                raise StoreConflict("OPERATION_EXISTS")
            token = self.tokens.get(operation.token_ref)
            if token is None or token.status != "ISSUED" or token.expires_at <= int(time.time()):
                raise StoreConflict("TOKEN_NOT_REDEEMABLE")
            if token.offer_id:
                offer = self.offers.get(token.offer_id)
                product = self.products.get(offer.product_id) if offer else None
                merchant = self.merchants.get(offer.merchant_uid) if offer else None
                if merchant is None or merchant.status != "ACTIVE":
                    raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
                if product is None or product.status != "ACTIVE" or product.stock_quantity <= 0:
                    raise StoreConflict("PRODUCT_NOT_ACTIVE_OR_OUT_OF_STOCK")
                if (
                    offer is None
                    or offer.status != "ACTIVE"
                    or offer.expires_at <= int(time.time())
                    or offer.redeemed_count >= offer.maximum_redemptions
                ):
                    raise StoreConflict("OFFER_NOT_ACTIVE")
            self.operations[operation.operation_id] = operation
            try:
                self.append_audit(**audit)
            except Exception:
                del self.operations[operation.operation_id]
                raise

    def get_operation(self, operation_id: str):
        with self._lock:
            return self.operations.get(operation_id)

    def append_audit(self, **kwargs: Any) -> AuditRecord:
        with self._lock:
            seq = len(self.events) + 1
            previous = self.events[-1]["event_hash"] if self.events else "0" * 64
            event_id = str(uuid.uuid4())
            body = {
                "event_id": event_id,
                "seq": seq,
                "operation_id": kwargs["operation_id"],
                "suite_id": kwargs["suite_id"],
                "key_ref_token": kwargs["key_ref_token"],
                "event_type": kwargs["event_type"],
                "result": kwargs["result"],
                "reason_codes": list(kwargs.get("reason_codes", ())),
                "evidence_refs": list(kwargs.get("evidence_refs", ())),
                "details": kwargs.get("details", {}),
                "prev_hash": previous,
            }
            event_hash = sha3_hex(body, "TRQ-BEC/audit/v1")
            self.events.append({**body, "event_hash": event_hash})
            return AuditRecord(f"event:{event_id}", seq, event_hash)

    def finalize_authorization(self, operation_id: str, token_ref: str, decision: str, result: dict[str, Any], **audit: Any):
        with self._lock:
            operation = self.operations.get(operation_id)
            token = self.tokens.get(token_ref)
            if operation is None or token is None:
                raise StoreConflict("OPERATION_OR_TOKEN_MISSING")
            if operation.status != "PENDING":
                raise StoreConflict("OPERATION_ALREADY_COMPLETED")
            result_with_commit = dict(result)
            pending_context = operation.result or {}
            if not isinstance(pending_context, dict):
                raise StoreConflict("OFFER_QR_QUANTITY_INVALID")
            try:
                purchase_quantity = int(pending_context.get("purchase_quantity", 1))
            except (TypeError, ValueError) as exc:
                raise StoreConflict("OFFER_QR_QUANTITY_INVALID") from exc
            if purchase_quantity < 1 or purchase_quantity > 1_000:
                raise StoreConflict("OFFER_QR_QUANTITY_INVALID")
            if decision == "ALLOW" and token.offer_id:
                offer = self.offers.get(token.offer_id)
                product = self.products.get(offer.product_id) if offer else None
                merchant = self.merchants.get(offer.merchant_uid) if offer else None
                if offer is None or product is None:
                    raise StoreConflict("OFFER_NOT_FOUND")
                if merchant is None or merchant.status != "ACTIVE":
                    raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
                if offer.status != "ACTIVE":
                    raise StoreConflict("OFFER_NOT_ACTIVE")
                if offer.expires_at <= int(time.time()):
                    raise StoreConflict("OFFER_EXPIRED")
                if offer.redeemed_count >= offer.maximum_redemptions:
                    raise StoreConflict("OFFER_REDEMPTION_LIMIT_REACHED")
                if product.status != "ACTIVE" or product.stock_quantity <= 0:
                    raise StoreConflict("PRODUCT_OUT_OF_STOCK")
                available = min(
                    offer.maximum_redemptions - offer.redeemed_count,
                    product.stock_quantity,
                )
                if purchase_quantity > available:
                    raise StoreConflict("OFFER_QR_QUANTITY_EXCEEDS_AVAILABLE")
                redemption_key = (offer.offer_id, operation.firebase_uid)
                if redemption_key in self.redemptions:
                    raise StoreConflict("OFFER_ALREADY_REDEEMED_BY_USER")
                new_count = offer.redeemed_count + purchase_quantity
                new_stock = product.stock_quantity - purchase_quantity
                exhausted = new_count >= offer.maximum_redemptions or new_stock == 0
                remaining = max(0, min(offer.maximum_redemptions - new_count, new_stock))
                committed_at_precise = datetime.now(timezone.utc)
                committed_at = int(committed_at_precise.timestamp())
                self.products[product.product_id] = replace(
                    product,
                    stock_quantity=new_stock,
                    updated_at=committed_at,
                )
                self.offers[offer.offer_id] = replace(
                    offer,
                    redeemed_count=new_count,
                    status="EXHAUSTED" if exhausted else "ACTIVE",
                    updated_at=committed_at,
                )
                if exhausted:
                    self.tokens[token_ref] = replace(token, status="REDEEMED", redeemed_operation_id=operation_id)
                result_with_commit.update(
                    {
                        "coupon_id": offer.offer_id,
                        "offer_id": offer.offer_id,
                        "product_id": offer.product_id,
                        "amount_saved_minor": offer.discount_amount_minor * purchase_quantity,
                        "final_amount_minor": offer.final_amount_minor * purchase_quantity,
                        "remaining_redemptions": remaining,
                        "quantity": purchase_quantity,
                    }
                )
                audit["details"] = {
                    **dict(audit.get("details") or {}),
                    "offer_id": offer.offer_id,
                    "product_id": offer.product_id,
                    "amount_saved_minor": offer.discount_amount_minor * purchase_quantity,
                    "remaining_redemptions": remaining,
                    "quantity": purchase_quantity,
                }
                self.redemptions[redemption_key] = {
                    "redemption_id": str(uuid.uuid4()),
                    "operation_id": operation_id,
                    "offer_id": offer.offer_id,
                    "merchant_uid": offer.merchant_uid,
                    "product_id": offer.product_id,
                    "status": "REDEEMED",
                    "amount_saved_minor": offer.discount_amount_minor * purchase_quantity,
                    "original_amount_minor": offer.original_amount_minor * purchase_quantity,
                    "final_amount_minor": offer.final_amount_minor * purchase_quantity,
                    "currency": offer.currency,
                    "quantity": purchase_quantity,
                    "snapshot_quality": "CURRENT",
                    "committed_at": committed_at_precise,
                }
            elif decision == "ALLOW":
                if token.status != "ISSUED":
                    raise StoreConflict("TOKEN_ALREADY_USED_OR_EXPIRED")
                self.tokens[token_ref] = replace(token, status="REDEEMED", redeemed_operation_id=operation_id)
            elif decision == "HOLD_OR_REVIEW" and token.coupon_id:
                self.tokens[token_ref] = replace(token, status="HELD", redeemed_operation_id=operation_id)
            event = self.append_audit(operation_id=operation_id, result=decision, **audit)
            result_with_event = {**result_with_commit, "event_ref": event.event_id}
            status = {
                "ALLOW": "COMPLETED",
                "STEP_UP": "STEP_UP_REQUIRED",
                "HOLD_OR_REVIEW": "HELD",
                "DENY": "DENIED",
            }[decision]
            self.operations[operation_id] = replace(
                operation,
                status=status,
                result=result_with_event,
            )
            if token.offer_id:
                redemption_key = (token.offer_id, operation.firebase_uid)
                if redemption_key in self.redemptions:
                    self.redemptions[redemption_key]["ledger_event_id"] = event.event_id
            return event, result_with_event

    def create_checkpoint(self, checkpoint_key_id: str, policy_version: str):
        with self._lock:
            if not self.events:
                raise LedgerError("LEDGER_EMPTY")
            body = {
                "first_seq": 1,
                "last_seq": len(self.events),
                "root_hash": self.events[-1]["event_hash"],
                "policy_version": policy_version,
            }
            signature = self.signing_provider.sign(
                checkpoint_key_id,
                domain_message("TRQ-BEC/checkpoint/v1", body),
                "checkpoint-signing",
            )
            return {
                **body,
                "checkpoint_id": str(uuid.uuid4()),
                "signature_b64u": base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
            }
