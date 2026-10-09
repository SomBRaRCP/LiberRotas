"""PostgreSQL durable state and append-only evidence ledger."""

from __future__ import annotations

import base64
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ..canonical import domain_message, sha3_hex
from ..contracts import CryptoEnvelope, Intent
from ..errors import LedgerError
from ..ledger.ledger import _validate_sanitized
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


AUDIT_LOCK_ID = 0x545251424543
ZERO_HASH = "0" * 64


class StoreConflict(RuntimeError):
    pass


class StoreNotFound(RuntimeError):
    pass


class DurableStore(Protocol):
    def ping(self) -> bool: ...
    def create_media_asset(self, asset: MediaAssetRecord) -> MediaAssetRecord: ...
    def get_media_asset(self, media_id: str) -> MediaAssetRecord | None: ...
    def get_media_asset_with_variant(
        self, media_id: str, variant: str
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]: ...
    def get_latest_ready_media_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        media_role: str,
        variant: str,
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]: ...
    def replace_media_variants(
        self, media_id: str, variants: list[MediaVariantRecord]
    ) -> list[MediaVariantRecord]: ...
    def list_media_variants(self, media_id: str) -> list[MediaVariantRecord]: ...
    def get_media_asset_by_client_request(
        self, owner_uid: str, client_request_id: str
    ) -> MediaAssetRecord | None: ...
    def count_pending_media(self, owner_uid: str) -> int: ...
    def count_ready_media(
        self, entity_type: str, entity_id: str, media_role: str
    ) -> int: ...
    def mark_media_processing(
        self,
        media_id: str,
        owner_uid: str,
        uploaded_at: datetime,
        size_bytes: int,
        detected_content_type: str,
        crc32c: str | None,
        object_generation: int | None,
    ) -> MediaAssetRecord: ...
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
    ) -> MediaAssetRecord: ...
    def mark_media_status(
        self,
        media_id: str,
        owner_uid: str,
        status: str,
        reason: str,
        changed_at: datetime,
    ) -> MediaAssetRecord: ...
    def associate_media(
        self,
        media_id: str,
        owner_uid: str,
        entity_type: str,
        entity_id: str,
    ) -> MediaAssetRecord: ...
    def mark_media_deleted(
        self, media_id: str, actor_uid: str, deleted_at: datetime
    ) -> MediaAssetRecord: ...
    def list_media_assets(
        self, entity_type: str, entity_id: str, limit: int, offset: int
    ) -> list[MediaAssetRecord]: ...
    def list_expired_pending_media(
        self, now: datetime, limit: int
    ) -> list[MediaAssetRecord]: ...
    def list_orphaned_media(
        self, created_before: datetime, limit: int
    ) -> list[MediaAssetRecord]: ...
    def get_access_account(self, uid: str) -> AccessAccountRecord | None: ...
    def set_access_account(self, account: AccessAccountRecord) -> AccessAccountRecord: ...
    def get_privileged_account_validation(
        self, uid: str
    ) -> PrivilegedAccountValidationRecord | None: ...
    def create_staff_account(
        self,
        account: AccessAccountRecord,
        validation: PrivilegedAccountValidationRecord,
        *,
        actor_uid: str,
        event_id: str,
        queue_id: uuid.UUID,
    ) -> AccessAccountSummaryRecord: ...
    def approve_staff_account(
        self,
        actor_uid: str,
        target_uid: str,
        reason: str,
        *,
        event_id: str,
        approved_at: datetime,
    ) -> AccessAccountSummaryRecord: ...
    def enqueue_email_verification(
        self, uid: str, email: str, now: datetime
    ) -> EmailVerificationQueueRecord: ...
    def claim_due_email_verifications(
        self, now: datetime, limit: int, processing_timeout: timedelta
    ) -> list[EmailVerificationQueueRecord]: ...
    def finish_email_verification(
        self,
        queue_id: uuid.UUID,
        status: str,
        result_code: str,
        now: datetime,
        next_attempt_at: datetime,
    ) -> None: ...
    def upsert_public_profile(self, profile: PublicProfileRecord) -> PublicProfileRecord: ...
    def get_public_profile(self, uid: str) -> PublicProfileRecord | None: ...
    def search_directory(self, query: str, types: tuple[str, ...], limit: int) -> list[GlobalSearchItemRecord]: ...
    def index_community_post(self, post_id: str, author_uid: str, body: str, created_at: datetime) -> None: ...
    def update_community_post(self, post_id: str, author_uid: str, body: str) -> None: ...
    def delete_community_post(self, post_id: str, author_uid: str) -> None: ...
    def create_community_comment(self, comment: CommunityCommentRecord) -> CommunityCommentRecord: ...
    def list_community_comments(self, post_id: str, viewer_uid: str, limit: int) -> list[CommunityCommentRecord]: ...
    def update_community_comment(self, comment_id: str, author_uid: str, body: str, updated_at: datetime) -> CommunityCommentRecord: ...
    def delete_community_comment(self, comment_id: str, author_uid: str) -> None: ...
    def set_community_comment_like(self, comment_id: str, viewer_uid: str, liked: bool, changed_at: datetime) -> tuple[bool, int]: ...
    def create_direct_conversation(self, conversation_id: str, sender_uid: str, recipient_uid: str) -> ConversationRecord: ...
    def create_support_conversation(self, conversation_id: str, requester_uid: str, subject: str) -> ConversationRecord: ...
    def list_conversations(self, uid: str, *, support_inbox: bool, limit: int) -> list[ConversationRecord]: ...
    def get_conversation(self, uid: str, conversation_id: str, *, support_inbox: bool) -> ConversationRecord | None: ...
    def send_private_message(self, message: PrivateMessageRecord, *, support_actor: bool) -> PrivateMessageRecord: ...
    def list_private_messages(self, uid: str, conversation_id: str, *, support_inbox: bool, limit: int) -> list[PrivateMessageRecord]: ...
    def mark_conversation_read(self, uid: str, conversation_id: str, *, support_inbox: bool, read_at: datetime) -> None: ...
    def resolve_support_conversation(self, support_uid: str, conversation_id: str, resolved_at: datetime) -> ConversationRecord: ...
    def set_message_block(self, blocker_uid: str, blocked_uid: str, blocked_at: datetime) -> MessageBlockRecord: ...
    def delete_message_block(self, blocker_uid: str, blocked_uid: str) -> bool: ...
    def list_message_blocks(self, blocker_uid: str, limit: int) -> list[MessageBlockRecord]: ...
    def get_message_block_state(self, viewer_uid: str, other_uid: str) -> tuple[bool, bool]: ...
    def create_institution_application(
        self, application: InstitutionApplicationRecord
    ) -> InstitutionApplicationRecord: ...
    def list_institution_applications(
        self, status: str | None, limit: int
    ) -> list[InstitutionApplicationRecord]: ...
    def get_institution_application(
        self, application_id: uuid.UUID
    ) -> InstitutionApplicationRecord | None: ...
    def update_institution_application_status(
        self,
        application_id: uuid.UUID,
        status: str,
        support_notes: str | None,
        reviewer_uid: str,
        reviewed_at: datetime,
    ) -> InstitutionApplicationRecord: ...
    def create_institution(
        self,
        profile: InstitutionProfileRecord,
        *,
        actor_uid: str,
        event_id: str,
        application_id: uuid.UUID | None = None,
        application_support_notes: str | None = None,
    ) -> InstitutionProfileRecord: ...
    def list_institutions(self, limit: int) -> list[InstitutionProfileRecord]: ...
    def get_institution_profile(self, owner_uid: str) -> InstitutionProfileRecord | None: ...
    def update_institution_profile(
        self,
        owner_uid: str,
        updates: dict[str, str | None],
        updated_at: datetime,
    ) -> InstitutionProfileRecord: ...
    def set_institution_badge_policy(
        self, owner_uid: str, group_id: str, policy: InstitutionBadgePolicy, updated_at: datetime,
    ) -> InstitutionGroupRecord: ...
    def set_institution_member_badge(
        self, owner_uid: str, group_id: str, membership_id: str, badge: str, updated_at: datetime,
    ) -> InstitutionMembershipRecord: ...
    def create_institution_group(
        self, group: InstitutionGroupRecord
    ) -> InstitutionGroupRecord: ...
    def list_institution_groups(
        self, owner_uid: str, limit: int
    ) -> list[InstitutionGroupRecord]: ...
    def close_institution_group(
        self, owner_uid: str, group_id: str, closed_at
    ) -> InstitutionGroupRecord: ...
    def get_institution_report_summary(
        self, owner_uid: str
    ) -> InstitutionReportSummaryRecord: ...
    def invite_institution_seller(
        self,
        owner_uid: str,
        group_id: str,
        normalized_seller_name: str,
        membership_id: str,
        invited_at: datetime,
        event_id: str,
    ) -> InstitutionMembershipRecord: ...
    def list_institution_group_memberships(
        self, owner_uid: str, group_id: str, status: str | None, limit: int, offset: int
    ) -> tuple[list[InstitutionMembershipRecord], bool]: ...
    def list_entrepreneur_institution_memberships(
        self, seller_uid: str, status: str | None, limit: int, offset: int
    ) -> tuple[list[InstitutionMembershipRecord], bool]: ...
    def respond_institution_invitation(
        self, seller_uid: str, membership_id: str, decision: str, changed_at: datetime, event_id: str
    ) -> InstitutionMembershipRecord: ...
    def leave_institution_membership(
        self, seller_uid: str, membership_id: str, changed_at: datetime, event_id: str
    ) -> InstitutionMembershipRecord: ...
    def remove_institution_group_member(
        self, owner_uid: str, group_id: str, membership_id: str, changed_at: datetime, event_id: str
    ) -> InstitutionMembershipRecord: ...
    def get_institution_sales_report(
        self,
        owner_uid: str,
        group_id: str | None,
        period_from: datetime,
        period_to: datetime,
        limit: int,
        offset: int,
    ) -> InstitutionSalesReportRecord: ...
    def create_institution_funded_event(
        self, event: InstitutionFundedEventRecord
    ) -> InstitutionFundedEventRecord: ...
    def list_institution_funded_events(
        self, owner_uid: str, limit: int
    ) -> list[InstitutionFundedEventRecord]: ...
    def set_institution_event_seller_allocations(
        self,
        owner_uid: str,
        event_id: str,
        allocations: tuple[tuple[str, int], ...],
        updated_at: datetime,
        *, by_badges: bool = False,
    ) -> InstitutionFundedEventRecord: ...
    def activate_institution_funded_event(
        self, owner_uid: str, event_id: str, activated_at: datetime
    ) -> InstitutionFundedEventRecord: ...
    def end_institution_funded_event(
        self, owner_uid: str, event_id: str, ended_at: datetime
    ) -> InstitutionFundedEventRecord: ...
    def list_entrepreneur_funded_events(
        self, seller_uid: str, limit: int
    ) -> list[InstitutionFundedEventRecord]: ...
    def set_institution_event_product_allocations(
        self,
        seller_uid: str,
        event_id: str,
        allocations: tuple[tuple[str, int], ...],
        updated_at: datetime,
    ) -> InstitutionFundedEventRecord: ...
    def get_institution_funded_event_report(
        self, owner_uid: str, event_id: str, generated_at: datetime
    ) -> InstitutionFundedEventReportRecord: ...
    def list_access_accounts(self, limit: int) -> list[AccessAccountSummaryRecord]: ...
    def list_staff_accounts(self, limit: int) -> list[AccessAccountSummaryRecord]: ...
    def get_admin_operations_summary(self) -> AdminOperationsSummaryRecord: ...
    def get_security_monitoring_summary(self) -> SecurityMonitoringSummaryRecord: ...
    def get_trq_bec_security_status(self) -> TrqBecSecurityStatusRecord: ...
    def update_access_account_status(
        self,
        actor_uid: str,
        target_uid: str,
        status: str,
        reason: str,
        *,
        event_id: str,
    ) -> AccessAccountSummaryRecord: ...
    def list_access_audit_events(self, limit: int) -> list[AccessAuditEventRecord]: ...
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
    ) -> tuple[DeviceRecord, bool, bool]: ...
    def list_devices(self, uid: str, limit: int) -> list[DeviceRecord]: ...
    def activate_due_devices(
        self, uid: str, activated_at: datetime, **audit: Any
    ) -> int: ...
    def set_device_notification_status(
        self, uid: str, key_id: str, notification_status: str
    ) -> DeviceRecord: ...
    def approve_device(
        self, uid: str, approval_token_hash: str, approved_at: datetime, **audit: Any
    ) -> DeviceRecord: ...
    def rotate_device_approval(
        self,
        uid: str,
        key_id: str,
        approval_token_hash: str,
        approval_expires_at: datetime,
        cooldown_seconds: int,
        **audit: Any,
    ) -> DeviceRecord: ...
    def revoke_all_devices(self, uid: str, **audit: Any) -> int: ...
    def get_device(self, uid: str, key_id: str) -> DeviceRecord | None: ...
    def set_merchant_status(self, merchant: MerchantRecord, **audit: Any) -> MerchantRecord: ...
    def get_active_merchant(self, uid: str) -> MerchantRecord | None: ...
    def close_account(self, uid: str, **audit: Any) -> None: ...
    def create_product(self, product: ProductRecord, **audit: Any) -> ProductRecord: ...
    def update_product_stock(
        self, uid: str, product_id: str, stock_quantity: int, **audit: Any
    ) -> ProductRecord: ...
    def list_products(self, uid: str) -> list[ProductRecord]: ...
    def get_marketplace_batch_response(
        self,
        uid: str,
        client_request_id: str,
        operation_kind: str,
        command_hash: str,
    ) -> dict[str, Any] | None: ...
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
    ) -> dict[str, Any]: ...
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
    ) -> dict[str, Any]: ...
    def list_public_catalog(self, limit: int) -> list[CatalogProductRecord]: ...
    def get_public_merchant_catalog(
        self, firebase_uid: str, limit: int
    ) -> tuple[CatalogMerchantRecord, list[CatalogProductRecord]] | None: ...
    def get_product_for_offer(self, uid: str, product_id: str) -> ProductRecord | None: ...
    def create_live_offer(
        self,
        offer: OfferRecord,
        token: TokenRecord,
        *,
        discount_type: str,
        discount_value: int,
        **audit: Any,
    ) -> AuditRecord: ...
    def get_offer_by_token(self, token_ref: str) -> OfferRecord | None: ...
    def expire_offer(self, token_ref: str, **audit: Any) -> None: ...
    def list_offers(self, uid: str) -> list[OfferRecord]: ...
    def get_visitor_purchases(self, uid: str, limit: int, offset: int) -> dict[str, Any]: ...
    def revoke_offer(self, uid: str, offer_id: str, **audit: Any) -> OfferRecord: ...
    def get_offers_for_batch(
        self, uid: str, offer_ids: tuple[str, ...]
    ) -> list[OfferRecord]: ...
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
    ) -> dict[str, Any]: ...
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
    ) -> dict[str, Any]: ...
    def update_offer_status(
        self, uid: str, offer_id: str, status: str, **audit: Any
    ) -> OfferRecord: ...
    def get_coupon_for_issue(self, coupon_id: str, owner_uid: str) -> CouponRecord | None: ...
    def store_token(self, token: TokenRecord) -> None: ...
    def get_token(self, token_ref: str) -> TokenRecord | None: ...
    def create_operation(self, operation: OperationRecord, **audit: Any) -> None: ...
    def get_operation(self, operation_id: str) -> OperationRecord | None: ...
    def append_audit(self, **kwargs: Any) -> AuditRecord: ...
    def finalize_authorization(self, operation_id: str, token_ref: str, decision: str, result: dict[str, Any], **audit: Any) -> tuple[AuditRecord, dict[str, Any]]: ...
    def create_checkpoint(self, checkpoint_key_id: str, policy_version: str) -> dict[str, Any]: ...


class PostgresStore:
    def __init__(self, pool: ConnectionPool, signing_provider) -> None:
        self.pool = pool
        self.signing_provider = signing_provider

    def ping(self) -> bool:
        with self.pool.connection() as conn:
            return conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1

    @staticmethod
    def _media_asset(row: dict[str, Any]) -> MediaAssetRecord:
        values = dict(row)
        values["media_id"] = str(values["media_id"])
        for field in (
            "declared_size_bytes",
            "size_bytes",
            "object_generation",
            "width",
            "height",
            "version",
        ):
            if values[field] is not None:
                values[field] = int(values[field])
        return MediaAssetRecord(**values)

    @staticmethod
    def _media_variant(row: dict[str, Any]) -> MediaVariantRecord:
        values = dict(row)
        values["media_id"] = str(values["media_id"])
        for field in ("size_bytes", "object_generation", "width", "height"):
            if values[field] is not None:
                values[field] = int(values[field])
        return MediaVariantRecord(**values)

    def _locked_media_asset(
        self,
        conn,
        media_id: str,
        owner_uid: str | None = None,
    ) -> MediaAssetRecord:
        row = conn.execute(
            "SELECT * FROM media_assets WHERE media_id = %s FOR UPDATE",
            (media_id,),
        ).fetchone()
        if row is None or (
            owner_uid is not None and row["owner_user_id"] != owner_uid
        ):
            raise StoreNotFound("MEDIA_ASSET_NOT_FOUND")
        return self._media_asset(row)

    def create_media_asset(self, asset: MediaAssetRecord) -> MediaAssetRecord:
        if asset.status != "pending" or asset.version != 1:
            raise StoreConflict("MEDIA_ASSET_INITIAL_STATE_INVALID")
        try:
            with self.pool.connection() as conn, conn.transaction():
                row = conn.execute(
                    """
                    INSERT INTO media_assets
                      (media_id, owner_user_id, entity_type, entity_id, media_role,
                       bucket_name, object_key, original_filename,
                       declared_content_type, detected_content_type,
                       declared_size_bytes, size_bytes, checksum_sha256, crc32c,
                       object_generation, width, height, status, visibility,
                       moderation_status, rejection_reason, client_request_id,
                       upload_expires_at, created_at, uploaded_at, confirmed_at,
                       deleted_at, created_by, deleted_by, version)
                    VALUES
                      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        asset.media_id,
                        asset.owner_user_id,
                        asset.entity_type,
                        asset.entity_id,
                        asset.media_role,
                        asset.bucket_name,
                        asset.object_key,
                        asset.original_filename,
                        asset.declared_content_type,
                        asset.detected_content_type,
                        asset.declared_size_bytes,
                        asset.size_bytes,
                        asset.checksum_sha256,
                        asset.crc32c,
                        asset.object_generation,
                        asset.width,
                        asset.height,
                        asset.status,
                        asset.visibility,
                        asset.moderation_status,
                        asset.rejection_reason,
                        asset.client_request_id,
                        asset.upload_expires_at,
                        asset.created_at,
                        asset.uploaded_at,
                        asset.confirmed_at,
                        asset.deleted_at,
                        asset.created_by,
                        asset.deleted_by,
                        asset.version,
                    ),
                ).fetchone()
        except UniqueViolation as exc:
            raise StoreConflict("MEDIA_ASSET_ALREADY_EXISTS") from exc
        return self._media_asset(row)

    def get_media_asset(self, media_id: str) -> MediaAssetRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM media_assets WHERE media_id = %s",
                (media_id,),
            ).fetchone()
        return None if row is None else self._media_asset(row)

    def get_media_asset_with_variant(
        self,
        media_id: str,
        variant: str,
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT asset.*,
                       derived.variant AS derived_variant,
                       derived.bucket_name AS derived_bucket_name,
                       derived.object_key AS derived_object_key,
                       derived.content_type AS derived_content_type,
                       derived.size_bytes AS derived_size_bytes,
                       derived.checksum_sha256 AS derived_checksum_sha256,
                       derived.crc32c AS derived_crc32c,
                       derived.object_generation AS derived_object_generation,
                       derived.width AS derived_width,
                       derived.height AS derived_height,
                       derived.created_at AS derived_created_at
                  FROM media_assets AS asset
                  LEFT JOIN media_variants AS derived
                    ON derived.media_id = asset.media_id
                   AND derived.variant = %s
                 WHERE asset.media_id = %s
                """,
                (variant, media_id),
            ).fetchone()
        if row is None:
            return None, None
        asset_values = {
            field: row[field]
            for field in MediaAssetRecord.__dataclass_fields__
        }
        derived = None
        if row["derived_variant"] is not None:
            derived = self._media_variant(
                {
                    "media_id": row["media_id"],
                    "variant": row["derived_variant"],
                    "bucket_name": row["derived_bucket_name"],
                    "object_key": row["derived_object_key"],
                    "content_type": row["derived_content_type"],
                    "size_bytes": row["derived_size_bytes"],
                    "checksum_sha256": row["derived_checksum_sha256"],
                    "crc32c": row["derived_crc32c"],
                    "object_generation": row["derived_object_generation"],
                    "width": row["derived_width"],
                    "height": row["derived_height"],
                    "created_at": row["derived_created_at"],
                }
            )
        return (
            self._media_asset(asset_values),
            derived,
        )

    def get_latest_ready_media_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        media_role: str,
        variant: str,
    ) -> tuple[MediaAssetRecord | None, MediaVariantRecord | None]:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT asset.*,
                       derived.variant AS derived_variant,
                       derived.bucket_name AS derived_bucket_name,
                       derived.object_key AS derived_object_key,
                       derived.content_type AS derived_content_type,
                       derived.size_bytes AS derived_size_bytes,
                       derived.checksum_sha256 AS derived_checksum_sha256,
                       derived.crc32c AS derived_crc32c,
                       derived.object_generation AS derived_object_generation,
                       derived.width AS derived_width,
                       derived.height AS derived_height,
                       derived.created_at AS derived_created_at
                  FROM media_assets AS asset
                  LEFT JOIN media_variants AS derived
                    ON derived.media_id = asset.media_id
                   AND derived.variant = %s
                 WHERE asset.entity_type = %s
                   AND asset.entity_id = %s
                   AND asset.media_role = %s
                   AND asset.status = 'ready'
                 ORDER BY asset.created_at DESC, asset.media_id DESC
                 LIMIT 1
                """,
                (variant, entity_type, entity_id, media_role),
            ).fetchone()
        if row is None:
            return None, None
        asset_values = {
            field: row[field]
            for field in MediaAssetRecord.__dataclass_fields__
        }
        derived = None
        if row["derived_variant"] is not None:
            derived = self._media_variant(
                {
                    "media_id": row["media_id"],
                    "variant": row["derived_variant"],
                    "bucket_name": row["derived_bucket_name"],
                    "object_key": row["derived_object_key"],
                    "content_type": row["derived_content_type"],
                    "size_bytes": row["derived_size_bytes"],
                    "checksum_sha256": row["derived_checksum_sha256"],
                    "crc32c": row["derived_crc32c"],
                    "object_generation": row["derived_object_generation"],
                    "width": row["derived_width"],
                    "height": row["derived_height"],
                    "created_at": row["derived_created_at"],
                }
            )
        return self._media_asset(asset_values), derived

    def replace_media_variants(
        self,
        media_id: str,
        variants: list[MediaVariantRecord],
    ) -> list[MediaVariantRecord]:
        if {variant.variant for variant in variants} != {"thumbnail", "display"}:
            raise StoreConflict("MEDIA_VARIANTS_INCOMPLETE")
        with self.pool.connection() as conn, conn.transaction():
            asset = self._locked_media_asset(conn, media_id)
            if asset.status not in {"processing", "ready"}:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            rows = []
            for variant in variants:
                if variant.media_id != media_id:
                    raise StoreConflict("MEDIA_VARIANT_ASSET_MISMATCH")
                row = conn.execute(
                    """
                    INSERT INTO media_variants
                      (media_id, variant, bucket_name, object_key, content_type,
                       size_bytes, checksum_sha256, crc32c, object_generation,
                       width, height, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (media_id, variant) DO UPDATE
                      SET bucket_name = EXCLUDED.bucket_name,
                          object_key = EXCLUDED.object_key,
                          content_type = EXCLUDED.content_type,
                          size_bytes = EXCLUDED.size_bytes,
                          checksum_sha256 = EXCLUDED.checksum_sha256,
                          crc32c = EXCLUDED.crc32c,
                          object_generation = EXCLUDED.object_generation,
                          width = EXCLUDED.width,
                          height = EXCLUDED.height
                    RETURNING *
                    """,
                    (
                        variant.media_id,
                        variant.variant,
                        variant.bucket_name,
                        variant.object_key,
                        variant.content_type,
                        variant.size_bytes,
                        variant.checksum_sha256,
                        variant.crc32c,
                        variant.object_generation,
                        variant.width,
                        variant.height,
                        variant.created_at,
                    ),
                ).fetchone()
                rows.append(row)
        return [self._media_variant(row) for row in rows]

    def list_media_variants(self, media_id: str) -> list[MediaVariantRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                  FROM media_variants
                 WHERE media_id = %s
                 ORDER BY CASE variant WHEN 'thumbnail' THEN 1 ELSE 2 END
                """,
                (media_id,),
            ).fetchall()
        return [self._media_variant(row) for row in rows]

    def get_media_asset_by_client_request(
        self,
        owner_uid: str,
        client_request_id: str,
    ) -> MediaAssetRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT *
                  FROM media_assets
                 WHERE owner_user_id = %s AND client_request_id = %s
                """,
                (owner_uid, client_request_id),
            ).fetchone()
        return None if row is None else self._media_asset(row)

    def count_pending_media(self, owner_uid: str) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT count(*) AS total
                  FROM media_assets
                 WHERE owner_user_id = %s
                   AND status IN ('pending', 'uploaded', 'processing')
                   AND upload_expires_at > now()
                """,
                (owner_uid,),
            ).fetchone()
        return int(row["total"])

    def count_ready_media(
        self,
        entity_type: str,
        entity_id: str,
        media_role: str,
    ) -> int:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT count(*) AS total
                  FROM media_assets
                 WHERE entity_type = %s
                   AND entity_id = %s
                   AND media_role = %s
                   AND status = 'ready'
                """,
                (entity_type, entity_id, media_role),
            ).fetchone()
        return int(row["total"])

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
        with self.pool.connection() as conn, conn.transaction():
            current = self._locked_media_asset(conn, media_id, owner_uid)
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
            row = conn.execute(
                """
                UPDATE media_assets
                   SET status = 'processing',
                       uploaded_at = %s,
                       size_bytes = %s,
                       detected_content_type = %s,
                       crc32c = %s,
                       object_generation = %s,
                       version = version + 1
                 WHERE media_id = %s
                   AND owner_user_id = %s
                   AND status = 'pending'
                   AND version = %s
                RETURNING *
                """,
                (
                    uploaded_at,
                    size_bytes,
                    detected_content_type,
                    crc32c,
                    object_generation,
                    media_id,
                    owner_uid,
                    current.version,
                ),
            ).fetchone()
            if row is None:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
        return self._media_asset(row)

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
        with self.pool.connection() as conn, conn.transaction():
            current = self._locked_media_asset(conn, media_id, owner_uid)
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
            row = conn.execute(
                """
                UPDATE media_assets
                   SET status = 'ready',
                       detected_content_type = %s,
                       size_bytes = %s,
                       checksum_sha256 = %s,
                       crc32c = %s,
                       object_generation = %s,
                       width = %s,
                       height = %s,
                       moderation_status = 'approved',
                       confirmed_at = %s,
                       version = version + 1
                 WHERE media_id = %s
                   AND owner_user_id = %s
                   AND status = 'processing'
                   AND version = %s
                RETURNING *
                """,
                (
                    detected_content_type,
                    size_bytes,
                    checksum_sha256,
                    crc32c,
                    object_generation,
                    width,
                    height,
                    confirmed_at,
                    media_id,
                    owner_uid,
                    current.version,
                ),
            ).fetchone()
            if row is None:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
        return self._media_asset(row)

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
        with self.pool.connection() as conn, conn.transaction():
            current = self._locked_media_asset(conn, media_id, owner_uid)
            if current.status == status and current.rejection_reason == reason:
                return current
            if current.status not in allowed_sources[status]:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            moderation_status = {
                "rejected": "rejected",
                "quarantined": "flagged",
                "orphaned": current.moderation_status,
            }[status]
            confirmed_at = (
                current.confirmed_at
                if status == "orphaned"
                else current.confirmed_at or changed_at
            )
            row = conn.execute(
                """
                UPDATE media_assets
                   SET status = %s,
                       moderation_status = %s,
                       rejection_reason = %s,
                       confirmed_at = %s,
                       version = version + 1
                 WHERE media_id = %s
                   AND owner_user_id = %s
                   AND status = %s
                   AND version = %s
                RETURNING *
                """,
                (
                    status,
                    moderation_status,
                    reason,
                    confirmed_at,
                    media_id,
                    owner_uid,
                    current.status,
                    current.version,
                ),
            ).fetchone()
            if row is None:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
        return self._media_asset(row)

    def associate_media(
        self,
        media_id: str,
        owner_uid: str,
        entity_type: str,
        entity_id: str,
    ) -> MediaAssetRecord:
        with self.pool.connection() as conn, conn.transaction():
            current = self._locked_media_asset(conn, media_id, owner_uid)
            if (
                current.entity_type == entity_type
                and current.entity_id == entity_id
            ):
                return current
            provisional_ids = {current.media_id, f"pending:{current.media_id}"}
            if (
                current.status != "ready"
                or current.entity_id not in provisional_ids
            ):
                raise StoreConflict("MEDIA_ASSET_ALREADY_ASSOCIATED")
            row = conn.execute(
                """
                UPDATE media_assets
                   SET entity_type = %s,
                       entity_id = %s,
                       version = version + 1
                 WHERE media_id = %s
                   AND owner_user_id = %s
                   AND status = 'ready'
                   AND version = %s
                RETURNING *
                """,
                (
                    entity_type,
                    entity_id,
                    media_id,
                    owner_uid,
                    current.version,
                ),
            ).fetchone()
            if row is None:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
        return self._media_asset(row)

    def mark_media_deleted(
        self,
        media_id: str,
        actor_uid: str,
        deleted_at: datetime,
    ) -> MediaAssetRecord:
        with self.pool.connection() as conn, conn.transaction():
            current = self._locked_media_asset(conn, media_id)
            if current.status == "deleted":
                return current
            row = conn.execute(
                """
                UPDATE media_assets
                   SET status = 'deleted',
                       deleted_at = %s,
                       deleted_by = %s,
                       version = version + 1
                 WHERE media_id = %s
                   AND status = %s
                   AND version = %s
                RETURNING *
                """,
                (
                    deleted_at,
                    actor_uid,
                    media_id,
                    current.status,
                    current.version,
                ),
            ).fetchone()
            if row is None:
                raise StoreConflict("MEDIA_ASSET_STATE_CONFLICT")
            conn.execute(
                "DELETE FROM media_variants WHERE media_id = %s",
                (media_id,),
            )
        return self._media_asset(row)

    def list_media_assets(
        self,
        entity_type: str,
        entity_id: str,
        limit: int,
        offset: int,
    ) -> list[MediaAssetRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                  FROM media_assets
                 WHERE entity_type = %s
                   AND entity_id = %s
                   AND status = 'ready'
                 ORDER BY created_at DESC, media_id
                 LIMIT %s OFFSET %s
                """,
                (entity_type, entity_id, limit, offset),
            ).fetchall()
        return [self._media_asset(row) for row in rows]

    def list_expired_pending_media(
        self,
        now: datetime,
        limit: int,
    ) -> list[MediaAssetRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                  FROM media_assets
                 WHERE status IN ('pending', 'uploaded', 'processing')
                   AND upload_expires_at <= %s
                 ORDER BY upload_expires_at, media_id
                 LIMIT %s
                """,
                (now, limit),
            ).fetchall()
        return [self._media_asset(row) for row in rows]

    def list_orphaned_media(
        self,
        created_before: datetime,
        limit: int,
    ) -> list[MediaAssetRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                  FROM media_assets
                 WHERE status = 'orphaned'
                   AND created_at <= %s
                 ORDER BY created_at, media_id
                 LIMIT %s
                """,
                (created_before, limit),
            ).fetchall()
        return [self._media_asset(row) for row in rows]

    def get_marketplace_batch_response(
        self,
        uid: str,
        client_request_id: str,
        operation_kind: str,
        command_hash: str,
    ) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT operation_kind, command_hash, response_json
                  FROM marketplace_batch_idempotency
                 WHERE merchant_uid = %s AND client_request_id = %s
                """,
                (uid, client_request_id),
            ).fetchone()
        if row is None:
            return None
        if (
            row["operation_kind"] != operation_kind
            or row["command_hash"] != command_hash
        ):
            raise StoreConflict("BATCH_CLIENT_REQUEST_ID_REUSED")
        response = row["response_json"]
        return dict(response) if response is not None else None

    @staticmethod
    def _claim_marketplace_batch_conn(
        conn,
        *,
        uid: str,
        client_request_id: str,
        operation_kind: str,
        command_hash: str,
        operation_id: str,
    ) -> dict[str, Any] | None:
        conn.execute(
            """
            INSERT INTO marketplace_batch_idempotency
              (merchant_uid, client_request_id, operation_kind, command_hash,
               operation_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (merchant_uid, client_request_id) DO NOTHING
            """,
            (
                uid,
                client_request_id,
                operation_kind,
                command_hash,
                operation_id,
            ),
        )
        row = conn.execute(
            """
            SELECT operation_kind, command_hash, response_json
              FROM marketplace_batch_idempotency
             WHERE merchant_uid = %s AND client_request_id = %s
             FOR UPDATE
            """,
            (uid, client_request_id),
        ).fetchone()
        if row is None:
            raise StoreConflict("BATCH_IDEMPOTENCY_CLAIM_FAILED")
        if (
            row["operation_kind"] != operation_kind
            or row["command_hash"] != command_hash
        ):
            raise StoreConflict("BATCH_CLIENT_REQUEST_ID_REUSED")
        response = row["response_json"]
        return dict(response) if response is not None else None

    @staticmethod
    def _complete_marketplace_batch_conn(
        conn,
        *,
        uid: str,
        client_request_id: str,
        response: dict[str, Any],
    ) -> None:
        completed = conn.execute(
            """
            UPDATE marketplace_batch_idempotency
               SET response_json = %s, completed_at = now()
             WHERE merchant_uid = %s AND client_request_id = %s
               AND response_json IS NULL
            RETURNING client_request_id
            """,
            (Jsonb(response), uid, client_request_id),
        ).fetchone()
        if completed is None:
            raise StoreConflict("BATCH_IDEMPOTENCY_COMMIT_FAILED")

    def get_access_account(self, uid: str) -> AccessAccountRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT a.firebase_uid, a.email, a.role, a.status,
                       a.allow_entrepreneur_fallback,
                       COALESCE(
                         array_agg(p.permission ORDER BY p.permission)
                           FILTER (WHERE p.permission IS NOT NULL),
                         ARRAY[]::TEXT[]
                       ) AS permissions
                  FROM access_accounts AS a
                  LEFT JOIN account_permissions AS p USING (firebase_uid)
                 WHERE a.firebase_uid = %s
                 GROUP BY a.firebase_uid, a.email, a.role, a.status,
                          a.allow_entrepreneur_fallback
                """,
                (uid,),
            ).fetchone()
            if row is None:
                return None
        return AccessAccountRecord(
            firebase_uid=row["firebase_uid"],
            email=row["email"],
            role=row["role"],
            status=row["status"],
            allow_entrepreneur_fallback=bool(row["allow_entrepreneur_fallback"]),
            permissions=tuple(row["permissions"]),
        )

    def set_access_account(self, account: AccessAccountRecord) -> AccessAccountRecord:
        permissions = tuple(sorted(set(account.permissions)))
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO access_accounts
                  (firebase_uid, email, role, status, allow_entrepreneur_fallback)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (firebase_uid) DO UPDATE SET
                  email = EXCLUDED.email,
                  role = EXCLUDED.role,
                  status = EXCLUDED.status,
                  allow_entrepreneur_fallback = EXCLUDED.allow_entrepreneur_fallback,
                  updated_at = now()
                """,
                (
                    account.firebase_uid,
                    account.email,
                    account.role,
                    account.status,
                    account.allow_entrepreneur_fallback,
                ),
            )
            conn.execute(
                "DELETE FROM account_permissions WHERE firebase_uid = %s",
                (account.firebase_uid,),
            )
            if permissions:
                with conn.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO account_permissions (firebase_uid, permission) VALUES (%s, %s)",
                        [(account.firebase_uid, permission) for permission in permissions],
                    )
        return AccessAccountRecord(
            firebase_uid=account.firebase_uid,
            email=account.email,
            role=account.role,
            status=account.status,
            allow_entrepreneur_fallback=account.allow_entrepreneur_fallback,
            permissions=permissions,
        )

    def get_privileged_account_validation(
        self,
        uid: str,
    ) -> PrivilegedAccountValidationRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT *
                  FROM privileged_account_validations
                 WHERE firebase_uid = %s
                """,
                (uid,),
            ).fetchone()
        return self._privileged_validation(row) if row is not None else None

    def create_staff_account(
        self,
        account: AccessAccountRecord,
        validation: PrivilegedAccountValidationRecord,
        *,
        actor_uid: str,
        event_id: str,
        queue_id: uuid.UUID,
    ) -> AccessAccountSummaryRecord:
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
        permissions = tuple(sorted(set(account.permissions)))
        try:
            with self.pool.connection() as conn, conn.transaction():
                actor = conn.execute(
                    """
                    SELECT account.firebase_uid
                      FROM access_accounts AS account
                      JOIN account_permissions AS permission USING (firebase_uid)
                      JOIN privileged_account_validations AS validation USING (firebase_uid)
                     WHERE account.firebase_uid = %s
                       AND account.role = 'admin'
                       AND account.status = 'ACTIVE'
                       AND permission.permission = 'admin.staff_accounts.manage'
                       AND validation.validation_state = 'APPROVED'
                     FOR UPDATE OF account, validation
                    """,
                    (actor_uid,),
                ).fetchone()
                if actor is None:
                    raise StoreConflict("ADMIN_STAFF_ACCESS_REQUIRED")

                conn.execute(
                    """
                    INSERT INTO access_accounts
                      (firebase_uid, email, role, status, allow_entrepreneur_fallback)
                    VALUES (%s, %s, %s, 'PENDING', FALSE)
                    """,
                    (account.firebase_uid, account.email, account.role),
                )
                if permissions:
                    with conn.cursor() as cursor:
                        cursor.executemany(
                            """
                            INSERT INTO account_permissions (firebase_uid, permission)
                            VALUES (%s, %s)
                            """,
                            [
                                (account.firebase_uid, permission)
                                for permission in permissions
                            ],
                        )
                conn.execute(
                    """
                    INSERT INTO privileged_account_validations (
                      firebase_uid, requested_role, validation_state,
                      protection_level, account_origin, created_by_uid,
                      validated_by_uid, validation_reason, validated_at,
                      created_at, updated_at
                    )
                    VALUES (%s, %s, 'PENDING', 'PRIVILEGED', 'ADMIN_INVITATION',
                            %s, NULL, NULL, NULL, %s, %s)
                    """,
                    (
                        validation.firebase_uid,
                        validation.requested_role,
                        actor_uid,
                        validation.created_at,
                        validation.updated_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO email_verification_queue
                      (queue_id, firebase_uid, email, status, next_attempt_at,
                       created_at, updated_at)
                    VALUES (%s, %s, %s, 'PENDING', %s, %s, %s)
                    """,
                    (
                        queue_id,
                        account.firebase_uid,
                        account.email,
                        validation.created_at,
                        validation.created_at,
                        validation.created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO access_audit_events
                      (event_id, actor_uid, target_uid, event_type,
                       previous_status, new_status, reason)
                    VALUES (%s, %s, %s, 'STAFF_ACCOUNT_CREATED',
                            NULL, 'PENDING', %s)
                    """,
                    (
                        event_id,
                        actor_uid,
                        account.firebase_uid,
                        "Conta de equipe criada sem acesso e aguardando validação administrativa.",
                    ),
                )
                created = conn.execute(
                    """
                    SELECT account.firebase_uid, account.email, account.role,
                           account.status, account.created_at, account.updated_at,
                           validation.validation_state AS authority_validation_state,
                           validation.protection_level,
                           validation.account_origin,
                           validation.validated_at AS authority_validated_at,
                           validation.validated_by_uid AS authority_validated_by_uid,
                           validation.created_by_uid,
                           %s::TEXT[] AS permissions
                      FROM access_accounts AS account
                      JOIN privileged_account_validations AS validation
                        USING (firebase_uid)
                     WHERE account.firebase_uid = %s
                    """,
                    (list(permissions), account.firebase_uid),
                ).fetchone()
        except UniqueViolation as exc:
            raise StoreConflict("STAFF_ACCOUNT_EXISTS") from exc
        return self._access_summary(created)

    def approve_staff_account(
        self,
        actor_uid: str,
        target_uid: str,
        reason: str,
        *,
        event_id: str,
        approved_at: datetime,
    ) -> AccessAccountSummaryRecord:
        with self.pool.connection() as conn, conn.transaction():
            actor = conn.execute(
                """
                SELECT account.firebase_uid
                  FROM access_accounts AS account
                  JOIN account_permissions AS permission USING (firebase_uid)
                  JOIN privileged_account_validations AS validation USING (firebase_uid)
                 WHERE account.firebase_uid = %s
                   AND account.role = 'admin'
                   AND account.status = 'ACTIVE'
                   AND permission.permission = 'admin.staff_accounts.manage'
                   AND validation.validation_state = 'APPROVED'
                 FOR UPDATE OF account, validation
                """,
                (actor_uid,),
            ).fetchone()
            if actor is None:
                raise StoreConflict("ADMIN_STAFF_ACCESS_REQUIRED")

            current = conn.execute(
                """
                SELECT account.*, validation.requested_role,
                       validation.validation_state,
                       validation.protection_level,
                       validation.account_origin
                  FROM access_accounts AS account
                  JOIN privileged_account_validations AS validation
                    USING (firebase_uid)
                 WHERE account.firebase_uid = %s
                 FOR UPDATE OF account, validation
                """,
                (target_uid,),
            ).fetchone()
            if current is None:
                raise StoreNotFound("STAFF_ACCOUNT_NOT_FOUND")
            if target_uid == actor_uid:
                raise StoreConflict("STAFF_SELF_VALIDATION_FORBIDDEN")
            if (
                current["status"] != "PENDING"
                or current["validation_state"] != "PENDING"
                or current["role"] not in {"admin", "support", "security"}
                or current["requested_role"] != current["role"]
            ):
                raise StoreConflict("STAFF_VALIDATION_STATE_INVALID")

            updated = conn.execute(
                """
                UPDATE access_accounts
                   SET status = 'ACTIVE', updated_at = %s
                 WHERE firebase_uid = %s
                RETURNING *
                """,
                (approved_at, target_uid),
            ).fetchone()
            validation = conn.execute(
                """
                UPDATE privileged_account_validations
                   SET validation_state = 'APPROVED',
                       validated_by_uid = %s,
                       validation_reason = %s,
                       validated_at = %s,
                       updated_at = %s
                 WHERE firebase_uid = %s
                RETURNING *
                """,
                (actor_uid, reason, approved_at, approved_at, target_uid),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO access_audit_events
                  (event_id, actor_uid, target_uid, event_type,
                   previous_status, new_status, reason)
                VALUES (%s, %s, %s, 'STAFF_ACCOUNT_VALIDATED',
                        'PENDING', 'ACTIVE', %s)
                """,
                (event_id, actor_uid, target_uid, reason),
            )
            permission_rows = conn.execute(
                """
                SELECT permission
                  FROM account_permissions
                 WHERE firebase_uid = %s
                 ORDER BY permission
                """,
                (target_uid,),
            ).fetchall()
        return self._access_summary(
            {
                **updated,
                "permissions": [row["permission"] for row in permission_rows],
                "authority_validation_state": validation["validation_state"],
                "protection_level": validation["protection_level"],
                "account_origin": validation["account_origin"],
                "authority_validated_at": validation["validated_at"],
                "authority_validated_by_uid": validation["validated_by_uid"],
                "created_by_uid": validation["created_by_uid"],
            }
        )

    @staticmethod
    def _email_verification_queue(row: dict[str, Any]) -> EmailVerificationQueueRecord:
        return EmailVerificationQueueRecord(
            queue_id=row["queue_id"],
            firebase_uid=row["firebase_uid"],
            email=row["email"],
            status=row["status"],
            attempt_count=row["attempt_count"],
            next_attempt_at=row["next_attempt_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def enqueue_email_verification(
        self,
        uid: str,
        email: str,
        now: datetime,
    ) -> EmailVerificationQueueRecord:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO email_verification_queue
                  (queue_id, firebase_uid, email, status, next_attempt_at, created_at, updated_at)
                VALUES (%s, %s, %s, 'PENDING', %s, %s, %s)
                ON CONFLICT (firebase_uid)
                  WHERE status IN ('PENDING', 'PROCESSING')
                DO UPDATE SET
                  email = EXCLUDED.email,
                  status = 'PENDING',
                  next_attempt_at = LEAST(
                    email_verification_queue.next_attempt_at,
                    EXCLUDED.next_attempt_at
                  ),
                  updated_at = EXCLUDED.updated_at
                RETURNING *
                """,
                (uuid.uuid4(), uid, email, now, now, now),
            ).fetchone()
        return self._email_verification_queue(row)

    def claim_due_email_verifications(
        self,
        now: datetime,
        limit: int,
        processing_timeout: timedelta,
    ) -> list[EmailVerificationQueueRecord]:
        stale_before = now - processing_timeout
        with self.pool.connection() as conn, conn.transaction():
            rows = conn.execute(
                """
                WITH due AS (
                  SELECT queue_id
                    FROM email_verification_queue
                   WHERE (
                     status = 'PENDING' AND next_attempt_at <= %s
                   ) OR (
                     status = 'PROCESSING' AND updated_at <= %s
                   )
                   ORDER BY next_attempt_at, created_at
                   FOR UPDATE SKIP LOCKED
                   LIMIT %s
                )
                UPDATE email_verification_queue AS queue
                   SET status = 'PROCESSING',
                       attempt_count = queue.attempt_count + 1,
                       updated_at = %s
                  FROM due
                 WHERE queue.queue_id = due.queue_id
                RETURNING queue.*
                """,
                (now, stale_before, limit, now),
            ).fetchall()
        return [self._email_verification_queue(row) for row in rows]

    def finish_email_verification(
        self,
        queue_id: uuid.UUID,
        status: str,
        result_code: str,
        now: datetime,
        next_attempt_at: datetime,
    ) -> None:
        if status not in {"PENDING", "SENT", "FAILED"}:
            raise ValueError("invalid email verification queue status")
        with self.pool.connection() as conn:
            updated = conn.execute(
                """
                UPDATE email_verification_queue
                   SET status = %s,
                       result_code = %s,
                       sent_at = CASE WHEN %s = 'SENT' THEN %s ELSE sent_at END,
                       next_attempt_at = %s,
                       updated_at = %s
                 WHERE queue_id = %s
                   AND status = 'PROCESSING'
                RETURNING queue_id
                """,
                (
                    status,
                    result_code,
                    status,
                    now,
                    next_attempt_at,
                    now,
                    queue_id,
                ),
            ).fetchone()
        if updated is None:
            raise StoreConflict("EMAIL_VERIFICATION_QUEUE_STATE_CONFLICT")

    @staticmethod
    def _institution_profile(row: dict[str, Any]) -> InstitutionProfileRecord:
        return InstitutionProfileRecord(
            firebase_uid=row["firebase_uid"],
            email=row["email"],
            name=row["name"],
            description=row["description"],
            city=row["city"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _institution_group(row: dict[str, Any]) -> InstitutionGroupRecord:
        return InstitutionGroupRecord(
            group_id=row["group_id"],
            owner_uid=row["owner_uid"],
            name=row["name"],
            description=row["description"],
            city=row["city"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
            badge_policy=InstitutionBadgePolicy(
                green_percent=row["badge_green_percent"],
                yellow_percent=row["badge_yellow_percent"],
                red_percent=row["badge_red_percent"],
            ) if row.get("badge_green_percent") is not None else None,
        )

    @staticmethod
    def _institution_membership(row: dict[str, Any]) -> InstitutionMembershipRecord:
        return InstitutionMembershipRecord(
            membership_id=row["membership_id"],
            group_id=row["group_id"],
            group_name=row["group_name"],
            institution_name=row["institution_name"],
            seller_uid=row["merchant_uid"],
            support_badge=row.get("support_badge"),
            seller_name=row["seller_name"],
            status=row["status"],
            invited_at=row["invited_at"],
            responded_at=row["responded_at"],
            active_from=row["active_from"],
            ended_at=row["ended_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _access_summary(row: dict[str, Any]) -> AccessAccountSummaryRecord:
        return AccessAccountSummaryRecord(
            firebase_uid=row["firebase_uid"],
            email=row["email"],
            role=row["role"],
            status=row["status"],
            permissions=tuple(row["permissions"]),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            authority_validation_state=row.get("authority_validation_state"),
            protection_level=row.get("protection_level"),
            account_origin=row.get("account_origin"),
            authority_validated_at=row.get("authority_validated_at"),
            authority_validated_by_uid=row.get("authority_validated_by_uid"),
            created_by_uid=row.get("created_by_uid"),
        )

    @staticmethod
    def _privileged_validation(
        row: dict[str, Any],
    ) -> PrivilegedAccountValidationRecord:
        return PrivilegedAccountValidationRecord(
            firebase_uid=row["firebase_uid"],
            requested_role=row["requested_role"],
            validation_state=row["validation_state"],
            protection_level=row["protection_level"],
            account_origin=row["account_origin"],
            created_by_uid=row["created_by_uid"],
            validated_by_uid=row["validated_by_uid"],
            validation_reason=row["validation_reason"],
            validated_at=row["validated_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _access_audit_event(row: dict[str, Any]) -> AccessAuditEventRecord:
        return AccessAuditEventRecord(
            event_id=row["event_id"],
            actor_uid=row["actor_uid"],
            target_uid=row["target_uid"],
            event_type=row["event_type"],
            previous_status=row["previous_status"],
            new_status=row["new_status"],
            reason=row["reason"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _institution_application(row: dict[str, Any]) -> InstitutionApplicationRecord:
        values = dict(row)
        values["application_id"] = uuid.UUID(str(values["application_id"]))
        return InstitutionApplicationRecord(**values)

    def create_institution_application(
        self, application: InstitutionApplicationRecord
    ) -> InstitutionApplicationRecord:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                INSERT INTO public_institution_applications
                  (application_id, organization_type, organization_name,
                   contact_name, email, phone, registration_number, city, state,
                   website_or_social, description, status, support_notes,
                   reviewed_by_uid, reviewed_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'NEW', NULL, NULL, NULL, %s, %s)
                RETURNING *
                """,
                (
                    application.application_id,
                    application.organization_type,
                    application.organization_name,
                    application.contact_name,
                    application.email,
                    application.phone,
                    application.registration_number,
                    application.city,
                    application.state,
                    application.website_or_social,
                    application.description,
                    application.created_at,
                    application.updated_at,
                ),
            ).fetchone()
        return self._institution_application(row)

    def list_institution_applications(
        self, status: str | None, limit: int
    ) -> list[InstitutionApplicationRecord]:
        where_clause = "WHERE status = %s" if status else ""
        parameters: tuple[Any, ...] = (status, limit) if status else (limit,)
        with self.pool.connection() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM public_institution_applications
                {where_clause}
                ORDER BY created_at DESC, application_id
                LIMIT %s
                """,
                parameters,
            ).fetchall()
        return [self._institution_application(row) for row in rows]

    def get_institution_application(
        self, application_id: uuid.UUID
    ) -> InstitutionApplicationRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM public_institution_applications WHERE application_id = %s",
                (application_id,),
            ).fetchone()
        return None if row is None else self._institution_application(row)

    def update_institution_application_status(
        self,
        application_id: uuid.UUID,
        status: str,
        support_notes: str | None,
        reviewer_uid: str,
        reviewed_at: datetime,
    ) -> InstitutionApplicationRecord:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                UPDATE public_institution_applications AS application
                   SET status = %s,
                       support_notes = %s,
                       reviewed_by_uid = %s,
                       reviewed_at = %s,
                       updated_at = %s
                 WHERE application.application_id = %s
                   AND EXISTS (
                     SELECT 1 FROM access_accounts AS account
                     JOIN account_permissions AS permission USING (firebase_uid)
                     WHERE account.firebase_uid = %s
                       AND account.role = 'support'
                       AND account.status = 'ACTIVE'
                       AND permission.permission = 'support.requests.manage'
                   )
                RETURNING application.*
                """,
                (
                    status,
                    support_notes,
                    reviewer_uid,
                    reviewed_at,
                    reviewed_at,
                    application_id,
                    reviewer_uid,
                ),
            ).fetchone()
        if row is None:
            raise StoreNotFound("INSTITUTION_APPLICATION_NOT_FOUND")
        return self._institution_application(row)

    def create_institution(
        self,
        profile: InstitutionProfileRecord,
        *,
        actor_uid: str,
        event_id: str,
        application_id: uuid.UUID | None = None,
        application_support_notes: str | None = None,
    ) -> InstitutionProfileRecord:
        if profile.status != "ACTIVE":
            raise StoreConflict("INSTITUTION_STATUS_INVALID")
        try:
            with self.pool.connection() as conn, conn.transaction():
                actor = conn.execute(
                    """
                    SELECT a.firebase_uid
                     FROM access_accounts AS a
                      JOIN account_permissions AS p USING (firebase_uid)
                     WHERE a.firebase_uid = %s
                       AND a.status = 'ACTIVE'
                       AND (
                         (a.role = 'admin' AND p.permission = 'admin.institutions.manage')
                         OR
                         (a.role = 'support' AND p.permission = 'support.institutions.create')
                       )
                     FOR UPDATE OF a
                    """,
                    (actor_uid,),
                ).fetchone()
                if actor is None:
                    raise StoreConflict("INSTITUTION_CREATOR_ACCESS_REQUIRED")
                conn.execute(
                    """
                    INSERT INTO access_accounts
                      (firebase_uid, email, role, status, allow_entrepreneur_fallback)
                    VALUES (%s, %s, 'institution', 'ACTIVE', FALSE)
                    """,
                    (profile.firebase_uid, profile.email),
                )
                with conn.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO account_permissions (firebase_uid, permission) VALUES (%s, %s)",
                        [
                            (profile.firebase_uid, permission)
                            for permission in default_permissions("institution")
                        ],
                    )
                conn.execute(
                    """
                    INSERT INTO institutional_profiles
                      (firebase_uid, email, name, description, city, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        profile.firebase_uid,
                        profile.email,
                        profile.name,
                        profile.description,
                        profile.city,
                        profile.created_at,
                        profile.updated_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO access_audit_events
                      (event_id, actor_uid, target_uid, event_type, previous_status, new_status, reason)
                    VALUES (%s, %s, %s, 'INSTITUTION_PROVISIONED', NULL, 'ACTIVE', %s)
                    """,
                    (
                        event_id,
                        actor_uid,
                        profile.firebase_uid,
                        "Conta institucional provisionada por operador autorizado.",
                    ),
                )
                if application_id is not None:
                    reviewed = conn.execute(
                        """
                        UPDATE public_institution_applications
                           SET status = 'APPROVED',
                               support_notes = %s,
                               reviewed_by_uid = %s,
                               provisioned_uid = %s,
                               reviewed_at = %s,
                               updated_at = %s
                         WHERE application_id = %s
                           AND status <> 'APPROVED'
                        RETURNING application_id
                        """,
                        (
                            application_support_notes,
                            actor_uid,
                            profile.firebase_uid,
                            profile.created_at,
                            profile.created_at,
                            application_id,
                        ),
                    ).fetchone()
                    if reviewed is None:
                        raise StoreConflict("INSTITUTION_APPLICATION_NOT_APPROVABLE")
        except UniqueViolation as exc:
            raise StoreConflict("INSTITUTION_ACCOUNT_EXISTS") from exc
        return profile

    def list_institutions(self, limit: int) -> list[InstitutionProfileRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT p.firebase_uid, p.email, p.name, p.description, p.city,
                       a.status, p.created_at, p.updated_at
                  FROM institutional_profiles AS p
                  JOIN access_accounts AS a USING (firebase_uid)
                 WHERE a.role = 'institution'
                 ORDER BY p.created_at DESC, p.firebase_uid
                 LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [self._institution_profile(row) for row in rows]

    def get_institution_profile(self, owner_uid: str) -> InstitutionProfileRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT p.firebase_uid, p.email, p.name, p.description, p.city,
                       a.status, p.created_at, p.updated_at
                  FROM institutional_profiles AS p
                  JOIN access_accounts AS a USING (firebase_uid)
                 WHERE p.firebase_uid = %s
                   AND a.role = 'institution'
                """,
                (owner_uid,),
            ).fetchone()
        return None if row is None else self._institution_profile(row)

    def update_institution_profile(
        self,
        owner_uid: str,
        updates: dict[str, str | None],
        updated_at: datetime,
    ) -> InstitutionProfileRecord:
        allowed_columns = {"name", "description", "city"}
        if not updates or not set(updates).issubset(allowed_columns):
            raise StoreConflict("INSTITUTION_PROFILE_FIELDS_INVALID")

        assignments = [f"{field} = %s" for field in sorted(updates)]
        values = [updates[field] for field in sorted(updates)]
        assignments.append("updated_at = %s")
        values.extend((updated_at, owner_uid))

        with self.pool.connection() as conn, conn.transaction():
            access = conn.execute(
                """
                SELECT a.firebase_uid
                  FROM access_accounts AS a
                  JOIN account_permissions AS permission USING (firebase_uid)
                 WHERE a.firebase_uid = %s
                   AND a.role = 'institution'
                   AND a.status = 'ACTIVE'
                   AND permission.permission = 'institution.profile.manage'
                 FOR UPDATE OF a
                """,
                (owner_uid,),
            ).fetchone()
            if access is None:
                raise StoreConflict("INSTITUTION_PROFILE_ACCESS_REQUIRED")
            row = conn.execute(
                f"""
                UPDATE institutional_profiles
                   SET {', '.join(assignments)}
                 WHERE firebase_uid = %s
                RETURNING firebase_uid, email, name, description, city,
                          'ACTIVE' AS status, created_at, updated_at
                """,
                tuple(values),
            ).fetchone()
            if row is None:
                raise StoreNotFound("INSTITUTION_PROFILE_NOT_FOUND")
        return self._institution_profile(row)

    @staticmethod
    def _lock_active_institution(
        conn,
        owner_uid: str,
        permission: str = "institution.groups.manage",
    ) -> None:
        access = conn.execute(
            """
            SELECT a.firebase_uid
              FROM access_accounts AS a
              JOIN institutional_profiles AS i USING (firebase_uid)
              JOIN account_permissions AS p USING (firebase_uid)
             WHERE a.firebase_uid = %s
               AND a.role = 'institution'
               AND a.status = 'ACTIVE'
               AND p.permission = %s
             FOR UPDATE OF a
            """,
            (owner_uid, permission),
        ).fetchone()
        if access is None:
            code = (
                "INSTITUTION_EVENT_ACCESS_REQUIRED"
                if permission == "institution.events.manage"
                else "INSTITUTION_GROUP_ACCESS_REQUIRED"
            )
            raise StoreConflict(code)

    def set_institution_badge_policy(
        self, owner_uid: str, group_id: str, policy: InstitutionBadgePolicy, updated_at: datetime,
    ) -> InstitutionGroupRecord:
        with self.pool.connection() as conn, conn.transaction():
            self._lock_active_institution(conn, owner_uid)
            group = conn.execute("SELECT * FROM institution_groups WHERE group_id = %s AND owner_uid = %s FOR UPDATE", (group_id, owner_uid)).fetchone()
            if group is None:
                raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            if group["status"] != "ACTIVE":
                raise StoreConflict("INSTITUTION_GROUP_CLOSED")
            row = conn.execute(
                """UPDATE institution_groups SET badge_green_percent = %s, badge_yellow_percent = %s,
                       badge_red_percent = %s, updated_at = %s WHERE group_id = %s RETURNING *""",
                (policy.green_percent, policy.yellow_percent, policy.red_percent, updated_at, group_id),
            ).fetchone()
            return self._institution_group(row)

    def set_institution_member_badge(
        self, owner_uid: str, group_id: str, membership_id: str, badge: str, updated_at: datetime,
    ) -> InstitutionMembershipRecord:
        with self.pool.connection() as conn, conn.transaction():
            self._lock_active_institution(conn, owner_uid)
            group = conn.execute("SELECT status FROM institution_groups WHERE group_id = %s AND owner_uid = %s FOR UPDATE", (group_id, owner_uid)).fetchone()
            if group is None:
                raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            if group["status"] != "ACTIVE":
                raise StoreConflict("INSTITUTION_GROUP_CLOSED")
            member = conn.execute("SELECT status FROM institution_group_memberships WHERE group_id = %s AND membership_id = %s FOR UPDATE", (group_id, membership_id)).fetchone()
            if member is None:
                raise StoreNotFound("INSTITUTION_MEMBERSHIP_NOT_FOUND")
            if member["status"] != "ACTIVE":
                raise StoreConflict("INSTITUTION_BADGE_ACTIVE_MEMBER_REQUIRED")
            conn.execute("UPDATE institution_group_memberships SET support_badge = %s, updated_at = %s WHERE membership_id = %s", (badge, updated_at, membership_id))
            row = conn.execute(self._membership_select_sql() + " WHERE membership.membership_id = %s", (membership_id,)).fetchone()
            return self._institution_membership(row)

    def create_institution_group(
        self,
        group: InstitutionGroupRecord,
    ) -> InstitutionGroupRecord:
        try:
            with self.pool.connection() as conn, conn.transaction():
                self._lock_active_institution(conn, group.owner_uid)
                row = conn.execute(
                    """
                    INSERT INTO institution_groups
                      (group_id, owner_uid, name, description, city, status,
                       created_at, updated_at, closed_at)
                    VALUES (%s, %s, %s, %s, %s, 'ACTIVE', %s, %s, NULL)
                    RETURNING *
                    """,
                    (
                        group.group_id,
                        group.owner_uid,
                        group.name,
                        group.description,
                        group.city,
                        group.created_at,
                        group.updated_at,
                    ),
                ).fetchone()
        except UniqueViolation as exc:
            raise StoreConflict("INSTITUTION_GROUP_EXISTS") from exc
        return self._institution_group(row)

    def get_institution_report_summary(
        self,
        owner_uid: str,
    ) -> InstitutionReportSummaryRecord:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)::INTEGER AS total_groups,
                       COUNT(*) FILTER (WHERE status = 'ACTIVE')::INTEGER AS active_groups,
                       COUNT(*) FILTER (WHERE status = 'CLOSED')::INTEGER AS closed_groups,
                       MAX(created_at) AS last_group_created_at
                  FROM institution_groups
                 WHERE owner_uid = %s
                """,
                (owner_uid,),
            ).fetchone()
        return InstitutionReportSummaryRecord(
            total_groups=int(row["total_groups"]),
            active_groups=int(row["active_groups"]),
            closed_groups=int(row["closed_groups"]),
            last_group_created_at=row["last_group_created_at"],
        )

    @staticmethod
    def _membership_select_sql() -> str:
        return """
            SELECT membership.*, group_row.name AS group_name,
                   institution.name AS institution_name,
                   COALESCE(profile.display_name, merchant.display_name) AS seller_name
              FROM institution_group_memberships AS membership
              JOIN institution_groups AS group_row USING (group_id)
              JOIN institutional_profiles AS institution
                ON institution.firebase_uid = group_row.owner_uid
              JOIN merchant_accounts AS merchant
                ON merchant.firebase_uid = membership.merchant_uid
              LEFT JOIN public_profile_directory AS profile
                ON profile.firebase_uid = membership.merchant_uid
        """

    def invite_institution_seller(
        self,
        owner_uid: str,
        group_id: str,
        normalized_seller_name: str,
        membership_id: str,
        invited_at: datetime,
        event_id: str,
    ) -> InstitutionMembershipRecord:
        try:
            with self.pool.connection() as conn, conn.transaction():
                self._lock_active_institution(conn, owner_uid)
                group = conn.execute(
                    """
                    SELECT group_id
                      FROM institution_groups
                     WHERE group_id = %s AND owner_uid = %s AND status = 'ACTIVE'
                     FOR UPDATE
                    """,
                    (group_id, owner_uid),
                ).fetchone()
                if group is None:
                    raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
                seller = conn.execute(
                    """
                    SELECT profile.firebase_uid
                      FROM public_profile_directory AS profile
                      JOIN access_accounts AS access USING (firebase_uid)
                      JOIN merchant_accounts AS merchant USING (firebase_uid)
                     WHERE profile.normalized_name = %s
                       AND profile.role = 'entrepreneur'
                       AND access.role = 'entrepreneur'
                       AND access.status = 'ACTIVE'
                       AND merchant.status = 'ACTIVE'
                     FOR UPDATE OF merchant
                    """,
                    (normalized_seller_name,),
                ).fetchone()
                if seller is None:
                    raise StoreNotFound("ELIGIBLE_SELLER_NOT_FOUND")
                existing = conn.execute(
                    self._membership_select_sql()
                    + """
                       WHERE membership.group_id = %s
                         AND membership.merchant_uid = %s
                         AND membership.status IN ('PENDING', 'ACTIVE')
                       FOR UPDATE OF membership
                    """,
                    (group_id, seller["firebase_uid"]),
                ).fetchone()
                if existing is not None:
                    return self._institution_membership(existing)
                conn.execute(
                    """
                    INSERT INTO institution_group_memberships
                      (membership_id, group_id, merchant_uid, invited_by_uid,
                       status, invited_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'PENDING', %s, %s)
                    """,
                    (
                        membership_id,
                        group_id,
                        seller["firebase_uid"],
                        owner_uid,
                        invited_at,
                        invited_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO institution_membership_events
                      (event_id, membership_id, actor_uid, event_type,
                       previous_status, new_status, created_at)
                    VALUES (%s, %s, %s, 'INVITED', NULL, 'PENDING', %s)
                    """,
                    (event_id, membership_id, owner_uid, invited_at),
                )
                row = conn.execute(
                    self._membership_select_sql()
                    + " WHERE membership.membership_id = %s",
                    (membership_id,),
                ).fetchone()
        except UniqueViolation as exc:
            raise StoreConflict("INSTITUTION_INVITATION_CONFLICT") from exc
        return self._institution_membership(row)

    def list_institution_group_memberships(
        self,
        owner_uid: str,
        group_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[InstitutionMembershipRecord], bool]:
        with self.pool.connection() as conn:
            owned = conn.execute(
                "SELECT 1 FROM institution_groups WHERE group_id = %s AND owner_uid = %s",
                (group_id, owner_uid),
            ).fetchone()
            if owned is None:
                raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            conditions = ["membership.group_id = %s"]
            params: list[Any] = [group_id]
            if status is not None:
                conditions.append("membership.status = %s")
                params.append(status)
            params.extend((limit + 1, offset))
            rows = conn.execute(
                self._membership_select_sql()
                + f"""
                   WHERE {' AND '.join(conditions)}
                   ORDER BY membership.invited_at DESC, membership.membership_id
                   LIMIT %s OFFSET %s
                """,
                tuple(params),
            ).fetchall()
        return (
            [self._institution_membership(row) for row in rows[:limit]],
            len(rows) > limit,
        )

    def list_entrepreneur_institution_memberships(
        self,
        seller_uid: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[InstitutionMembershipRecord], bool]:
        conditions = ["membership.merchant_uid = %s"]
        params: list[Any] = [seller_uid]
        if status is not None:
            conditions.append("membership.status = %s")
            params.append(status)
        params.extend((limit + 1, offset))
        with self.pool.connection() as conn:
            rows = conn.execute(
                self._membership_select_sql()
                + f"""
                   WHERE {' AND '.join(conditions)}
                   ORDER BY membership.invited_at DESC, membership.membership_id
                   LIMIT %s OFFSET %s
                """,
                tuple(params),
            ).fetchall()
        return (
            [self._institution_membership(row) for row in rows[:limit]],
            len(rows) > limit,
        )

    def respond_institution_invitation(
        self,
        seller_uid: str,
        membership_id: str,
        decision: str,
        changed_at: datetime,
        event_id: str,
    ) -> InstitutionMembershipRecord:
        target_status = "ACTIVE" if decision == "ACCEPT" else "DECLINED"
        event_type = "ACCEPTED" if decision == "ACCEPT" else "DECLINED"
        with self.pool.connection() as conn, conn.transaction():
            access = conn.execute(
                """
                SELECT access.firebase_uid
                  FROM access_accounts AS access
                  JOIN account_permissions AS permission USING (firebase_uid)
                  JOIN merchant_accounts AS merchant USING (firebase_uid)
                 WHERE access.firebase_uid = %s
                   AND access.role = 'entrepreneur'
                   AND access.status = 'ACTIVE'
                   AND permission.permission = 'institution.memberships.respond'
                   AND merchant.status = 'ACTIVE'
                 FOR UPDATE OF access, merchant
                """,
                (seller_uid,),
            ).fetchone()
            if access is None:
                raise StoreConflict("INSTITUTION_MEMBERSHIP_ACCESS_REQUIRED")
            current = conn.execute(
                """
                SELECT membership.*, group_row.status AS group_status,
                       institution_access.status AS institution_status,
                       institution_access.role AS institution_role
                  FROM institution_group_memberships AS membership
                  JOIN institution_groups AS group_row USING (group_id)
                  JOIN access_accounts AS institution_access
                    ON institution_access.firebase_uid = group_row.owner_uid
                 WHERE membership.membership_id = %s
                   AND membership.merchant_uid = %s
                 FOR UPDATE OF membership, group_row
                """,
                (membership_id, seller_uid),
            ).fetchone()
            if current is None:
                raise StoreNotFound("INSTITUTION_INVITATION_NOT_FOUND")
            if current["status"] == target_status:
                row = conn.execute(
                    self._membership_select_sql()
                    + " WHERE membership.membership_id = %s",
                    (membership_id,),
                ).fetchone()
                return self._institution_membership(row)
            if current["status"] != "PENDING":
                raise StoreConflict("INSTITUTION_INVITATION_NOT_PENDING")
            if decision == "ACCEPT":
                if (
                    current["group_status"] != "ACTIVE"
                    or current["institution_status"] != "ACTIVE"
                    or current["institution_role"] != "institution"
                ):
                    raise StoreConflict("INSTITUTION_GROUP_NOT_ACTIVE")
                active = conn.execute(
                    """
                    SELECT membership_id
                      FROM institution_group_memberships
                     WHERE merchant_uid = %s AND status = 'ACTIVE'
                     FOR UPDATE
                    """,
                    (seller_uid,),
                ).fetchone()
                if active is not None:
                    raise StoreConflict("SELLER_ALREADY_HAS_ACTIVE_MEMBERSHIP")
                conn.execute(
                    """
                    UPDATE institution_group_memberships
                       SET status = 'ACTIVE', responded_at = %s, active_from = %s,
                           ended_at = NULL, updated_at = %s
                     WHERE membership_id = %s
                    """,
                    (changed_at, changed_at, changed_at, membership_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE institution_group_memberships
                       SET status = 'DECLINED', responded_at = %s,
                           ended_at = %s, updated_at = %s
                     WHERE membership_id = %s
                    """,
                    (changed_at, changed_at, changed_at, membership_id),
                )
            conn.execute(
                """
                INSERT INTO institution_membership_events
                  (event_id, membership_id, actor_uid, event_type,
                   previous_status, new_status, created_at)
                VALUES (%s, %s, %s, %s, 'PENDING', %s, %s)
                """,
                (event_id, membership_id, seller_uid, event_type, target_status, changed_at),
            )
            row = conn.execute(
                self._membership_select_sql()
                + " WHERE membership.membership_id = %s",
                (membership_id,),
            ).fetchone()
        return self._institution_membership(row)

    def leave_institution_membership(
        self,
        seller_uid: str,
        membership_id: str,
        changed_at: datetime,
        event_id: str,
    ) -> InstitutionMembershipRecord:
        with self.pool.connection() as conn, conn.transaction():
            current = conn.execute(
                """
                SELECT * FROM institution_group_memberships
                 WHERE membership_id = %s AND merchant_uid = %s
                 FOR UPDATE
                """,
                (membership_id, seller_uid),
            ).fetchone()
            if current is None:
                raise StoreNotFound("INSTITUTION_MEMBERSHIP_NOT_FOUND")
            if current["status"] == "LEFT":
                row = conn.execute(
                    self._membership_select_sql()
                    + " WHERE membership.membership_id = %s",
                    (membership_id,),
                ).fetchone()
                return self._institution_membership(row)
            if current["status"] != "ACTIVE":
                raise StoreConflict("INSTITUTION_MEMBERSHIP_NOT_ACTIVE")
            conn.execute(
                """
                UPDATE institution_group_memberships
                   SET status = 'LEFT', ended_at = %s, updated_at = %s
                 WHERE membership_id = %s
                """,
                (changed_at, changed_at, membership_id),
            )
            conn.execute(
                """
                INSERT INTO institution_membership_events
                  (event_id, membership_id, actor_uid, event_type,
                   previous_status, new_status, created_at)
                VALUES (%s, %s, %s, 'LEFT', 'ACTIVE', 'LEFT', %s)
                """,
                (event_id, membership_id, seller_uid, changed_at),
            )
            row = conn.execute(
                self._membership_select_sql()
                + " WHERE membership.membership_id = %s",
                (membership_id,),
            ).fetchone()
        return self._institution_membership(row)

    def remove_institution_group_member(
        self,
        owner_uid: str,
        group_id: str,
        membership_id: str,
        changed_at: datetime,
        event_id: str,
    ) -> InstitutionMembershipRecord:
        with self.pool.connection() as conn, conn.transaction():
            self._lock_active_institution(conn, owner_uid)
            current = conn.execute(
                """
                SELECT membership.*
                  FROM institution_group_memberships AS membership
                  JOIN institution_groups AS group_row USING (group_id)
                 WHERE membership.membership_id = %s
                   AND membership.group_id = %s
                   AND group_row.owner_uid = %s
                 FOR UPDATE OF membership
                """,
                (membership_id, group_id, owner_uid),
            ).fetchone()
            if current is None:
                raise StoreNotFound("INSTITUTION_MEMBERSHIP_NOT_FOUND_OR_NOT_OWNED")
            if current["status"] == "REMOVED":
                row = conn.execute(
                    self._membership_select_sql()
                    + " WHERE membership.membership_id = %s",
                    (membership_id,),
                ).fetchone()
                return self._institution_membership(row)
            if current["status"] not in {"PENDING", "ACTIVE"}:
                raise StoreConflict("INSTITUTION_MEMBERSHIP_NOT_ACTIVE")
            conn.execute(
                """
                UPDATE institution_group_memberships
                   SET status = 'REMOVED', responded_at = COALESCE(responded_at, %s),
                       ended_at = %s, updated_at = %s
                 WHERE membership_id = %s
                """,
                (changed_at, changed_at, changed_at, membership_id),
            )
            conn.execute(
                """
                INSERT INTO institution_membership_events
                  (event_id, membership_id, actor_uid, event_type,
                   previous_status, new_status, created_at)
                VALUES (%s, %s, %s, 'REMOVED', %s, 'REMOVED', %s)
                """,
                (event_id, membership_id, owner_uid, current["status"], changed_at),
            )
            row = conn.execute(
                self._membership_select_sql()
                + " WHERE membership.membership_id = %s",
                (membership_id,),
            ).fetchone()
        return self._institution_membership(row)

    @staticmethod
    def _currency_totals(rows: list[dict[str, Any]]) -> tuple[InstitutionSalesCurrencyTotalRecord, ...]:
        return tuple(
            InstitutionSalesCurrencyTotalRecord(
                currency=row["currency"],
                gross_original_amount_minor=int(row["gross_original_amount_minor"] or 0),
                gross_final_amount_minor=int(row["gross_final_amount_minor"] or 0),
                total_discount_amount_minor=int(row["total_discount_amount_minor"] or 0),
            )
            for row in rows
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
        # O relatório usa várias consultas (filiações, linhas por vendedor e
        # agregado). Uma única fotografia REPEATABLE READ evita que um resgate
        # concorrente apareça no total, mas ainda não na respectiva linha.
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if group_id is not None:
                owned = conn.execute(
                    "SELECT 1 FROM institution_groups WHERE group_id = %s AND owner_uid = %s",
                    (group_id, owner_uid),
                ).fetchone()
                if owned is None:
                    raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            group_condition = "AND group_row.group_id = %s" if group_id is not None else ""
            membership_params: list[Any] = [owner_uid, period_to, period_from]
            if group_id is not None:
                membership_params.append(group_id)
            membership_params.extend((limit + 1, offset))
            memberships = conn.execute(
                self._membership_select_sql()
                + f"""
                   WHERE group_row.owner_uid = %s
                     AND membership.active_from IS NOT NULL
                     AND membership.active_from < %s
                     AND (membership.ended_at IS NULL OR membership.ended_at > %s)
                     {group_condition}
                   ORDER BY group_row.name, seller_name, membership.membership_id
                   LIMIT %s OFFSET %s
                """,
                tuple(membership_params),
            ).fetchall()

            sellers: list[InstitutionSellerSalesRecord] = []
            for membership in memberships[:limit]:
                totals_rows = conn.execute(
                    """
                    SELECT currency,
                           COUNT(*)::INTEGER AS confirmed_redemptions,
                           COALESCE(SUM(quantity), 0)::INTEGER AS units_sold,
                           COUNT(*) FILTER (
                             WHERE original_amount_minor IS NULL OR final_amount_minor IS NULL
                           )::INTEGER AS amounts_unavailable_count,
                           COALESCE(SUM(original_amount_minor), 0)::BIGINT AS gross_original_amount_minor,
                           COALESCE(SUM(final_amount_minor), 0)::BIGINT AS gross_final_amount_minor,
                           COALESCE(SUM(original_amount_minor - final_amount_minor), 0)::BIGINT
                             AS total_discount_amount_minor
                      FROM coupon_redemptions
                     WHERE merchant_uid = %s
                       AND status = 'REDEEMED'
                       AND committed_at >= %s AND committed_at < %s
                       AND committed_at >= %s
                       AND (%s::timestamptz IS NULL OR committed_at < %s::timestamptz)
                     GROUP BY currency
                     ORDER BY currency
                    """,
                    (
                        membership["merchant_uid"],
                        period_from,
                        period_to,
                        membership["active_from"],
                        membership["ended_at"],
                        membership["ended_at"],
                    ),
                ).fetchall()
                sellers.append(
                    InstitutionSellerSalesRecord(
                        membership_id=membership["membership_id"],
                        group_id=membership["group_id"],
                        group_name=membership["group_name"],
                        seller_uid=membership["merchant_uid"],
                        seller_name=membership["seller_name"],
                        membership_status=membership["status"],
                        active_from=membership["active_from"],
                        ended_at=membership["ended_at"],
                        confirmed_redemptions=sum(int(row["confirmed_redemptions"]) for row in totals_rows),
                        units_sold=sum(int(row["units_sold"]) for row in totals_rows),
                        amounts_unavailable_count=sum(
                            int(row["amounts_unavailable_count"]) for row in totals_rows
                        ),
                        totals_by_currency=self._currency_totals(totals_rows),
                    )
                )

            aggregate_group_condition = "AND group_row.group_id = %s" if group_id is not None else ""
            aggregate_rows = conn.execute(
                f"""
                WITH attributed AS (
                  SELECT DISTINCT redemption.redemption_id, redemption.currency,
                         redemption.quantity, redemption.original_amount_minor,
                         redemption.final_amount_minor
                    FROM coupon_redemptions AS redemption
                   WHERE redemption.status = 'REDEEMED'
                     AND redemption.committed_at >= %s
                     AND redemption.committed_at < %s
                     AND EXISTS (
                       SELECT 1
                         FROM institution_group_memberships AS membership
                         JOIN institution_groups AS group_row USING (group_id)
                        WHERE group_row.owner_uid = %s
                          {aggregate_group_condition}
                          AND membership.merchant_uid = redemption.merchant_uid
                          AND membership.active_from IS NOT NULL
                          AND membership.active_from <= redemption.committed_at
                          AND (membership.ended_at IS NULL OR membership.ended_at > redemption.committed_at)
                     )
                )
                SELECT currency,
                       COUNT(*)::INTEGER AS confirmed_redemptions,
                       COALESCE(SUM(quantity), 0)::INTEGER AS units_sold,
                       COUNT(*) FILTER (
                         WHERE original_amount_minor IS NULL OR final_amount_minor IS NULL
                       )::INTEGER AS amounts_unavailable_count,
                       COALESCE(SUM(original_amount_minor), 0)::BIGINT AS gross_original_amount_minor,
                       COALESCE(SUM(final_amount_minor), 0)::BIGINT AS gross_final_amount_minor,
                       COALESCE(SUM(original_amount_minor - final_amount_minor), 0)::BIGINT
                         AS total_discount_amount_minor
                  FROM attributed
                 GROUP BY currency
                 ORDER BY currency
                """,
                tuple([period_from, period_to, owner_uid] + ([group_id] if group_id is not None else [])),
            ).fetchall()
        return InstitutionSalesReportRecord(
            confirmed_redemptions=sum(int(row["confirmed_redemptions"]) for row in aggregate_rows),
            units_sold=sum(int(row["units_sold"]) for row in aggregate_rows),
            amounts_unavailable_count=sum(
                int(row["amounts_unavailable_count"]) for row in aggregate_rows
            ),
            totals_by_currency=self._currency_totals(aggregate_rows),
            sellers=tuple(sellers),
            has_more=len(memberships) > limit,
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

    @staticmethod
    def _funded_event_redemptions_sql() -> str:
        return """
            SELECT redemption.redemption_id, redemption.committed_at,
                   allocation.seller_uid, allocation.product_id,
                   redemption.quantity,
                   redemption.original_amount_minor,
                   redemption.final_amount_minor
              FROM coupon_redemptions AS redemption
              JOIN institution_event_product_allocations AS allocation
                ON allocation.event_id = %s
               AND allocation.product_id = redemption.product_id
               AND allocation.seller_uid = redemption.merchant_uid
              JOIN institution_funded_events AS event
                ON event.event_id = allocation.event_id
             WHERE redemption.status = 'REDEEMED'
               AND redemption.currency = event.currency
               AND redemption.committed_at >= GREATEST(
                 event.starts_at,
                 COALESCE(event.activated_at, event.starts_at)
               )
               AND (
                 event.ended_at IS NULL
                 OR redemption.committed_at <= event.ended_at
               )
               AND redemption.committed_at <= now()
             ORDER BY redemption.committed_at, redemption.redemption_id
        """

    def _settle_institution_funded_event(
        self,
        conn,
        event_id: str,
        checked_at: datetime,
    ) -> None:
        row = conn.execute(
            """
            SELECT event_id, end_mode, ends_at, coupon_limit, status
              FROM institution_funded_events
             WHERE event_id = %s
             FOR UPDATE
            """,
            (event_id,),
        ).fetchone()
        if row is None or row["status"] != "ACTIVE":
            return
        if row["end_mode"] == "TIME":
            if row["ends_at"] <= checked_at:
                conn.execute(
                    """
                    UPDATE institution_funded_events
                       SET status = 'ENDED', end_reason = 'TIME',
                           ended_at = ends_at, updated_at = %s
                     WHERE event_id = %s
                    """,
                    (checked_at, event_id),
                )
            return
        redemptions = conn.execute(
            self._funded_event_redemptions_sql()
            + """
               LIMIT %s
            """,
            (event_id, int(row["coupon_limit"])),
        ).fetchall()
        if len(redemptions) >= int(row["coupon_limit"]):
            conn.execute(
                """
                UPDATE institution_funded_events
                   SET status = 'ENDED', end_reason = 'COUPONS',
                       ended_at = %s, updated_at = %s
                 WHERE event_id = %s
                """,
                (
                    redemptions[-1]["committed_at"],
                    checked_at,
                    event_id,
                ),
            )

    def _load_institution_funded_event(
        self,
        conn,
        event_id: str,
        *,
        owner_uid: str | None = None,
        seller_uid: str | None = None,
        checked_at: datetime | None = None,
    ) -> InstitutionFundedEventRecord:
        if checked_at is not None:
            self._settle_institution_funded_event(conn, event_id, checked_at)
        conditions = ["event.event_id = %s"]
        params: list[Any] = [event_id]
        if owner_uid is not None:
            conditions.append("event.owner_uid = %s")
            params.append(owner_uid)
        if seller_uid is not None:
            conditions.append(
                """
                EXISTS (
                  SELECT 1
                    FROM institution_event_seller_allocations AS permitted
                   WHERE permitted.event_id = event.event_id
                     AND permitted.seller_uid = %s
                )
                """
            )
            params.append(seller_uid)
        row = conn.execute(
            f"""
            SELECT event.*, institution.name AS institution_name,
                   group_row.name AS group_name
              FROM institution_funded_events AS event
              JOIN institutional_profiles AS institution
                ON institution.firebase_uid = event.owner_uid
              JOIN institution_groups AS group_row USING (group_id)
             WHERE {' AND '.join(conditions)}
            """,
            tuple(params),
        ).fetchone()
        if row is None:
            raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
        seller_rows = conn.execute(
            """
            SELECT allocation.*,
                   COALESCE(profile.display_name, merchant.display_name) AS seller_name
              FROM institution_event_seller_allocations AS allocation
              JOIN merchant_accounts AS merchant
                ON merchant.firebase_uid = allocation.seller_uid
              LEFT JOIN public_profile_directory AS profile
                ON profile.firebase_uid = allocation.seller_uid
             WHERE allocation.event_id = %s
             ORDER BY seller_name, allocation.seller_uid
            """,
            (event_id,),
        ).fetchall()
        product_rows = conn.execute(
            """
            SELECT allocation.*, product.title AS product_title
              FROM institution_event_product_allocations AS allocation
              JOIN products AS product USING (product_id)
             WHERE allocation.event_id = %s
             ORDER BY allocation.seller_uid, product.title, allocation.product_id
            """,
            (event_id,),
        ).fetchall()
        products_by_seller: dict[
            str, list[InstitutionFundedEventProductAllocationRecord]
        ] = {}
        for product in product_rows:
            products_by_seller.setdefault(product["seller_uid"], []).append(
                InstitutionFundedEventProductAllocationRecord(
                    product_id=product["product_id"],
                    product_title=product["product_title"],
                    allocated_amount_minor=int(product["allocated_amount_minor"]),
                    allocation_mode=product["allocation_mode"],
                )
            )
        redemptions = conn.execute(
            self._funded_event_redemptions_sql(),
            (event_id,),
        ).fetchall()
        current_coupon_redemptions = len(redemptions)
        if row["end_mode"] == "COUPONS":
            current_coupon_redemptions = min(
                current_coupon_redemptions,
                int(row["coupon_limit"]),
            )
        return InstitutionFundedEventRecord(
            event_id=row["event_id"],
            owner_uid=row["owner_uid"],
            institution_name=row["institution_name"],
            group_id=row["group_id"],
            group_name=row["group_name"],
            badge_distribution=InstitutionBadgeDistribution.model_validate(row["badge_distribution"]) if row.get("badge_distribution") else None,
            name=row["name"],
            description=row["description"],
            funding_source=row["funding_source"],
            budget_amount_minor=int(row["budget_amount_minor"]),
            currency=row["currency"],
            end_mode=row["end_mode"],
            starts_at=row["starts_at"],
            ends_at=row["ends_at"],
            coupon_limit=(
                int(row["coupon_limit"]) if row["coupon_limit"] is not None else None
            ),
            current_coupon_redemptions=current_coupon_redemptions,
            status=row["status"],
            end_reason=row["end_reason"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            activated_at=row["activated_at"],
            ended_at=row["ended_at"],
            seller_allocations=tuple(
                InstitutionFundedEventSellerAllocationRecord(
                    membership_id=seller["membership_id"],
                    seller_uid=seller["seller_uid"],
                    seller_name=seller["seller_name"],
                    allocated_amount_minor=int(seller["allocated_amount_minor"]),
                    allocation_mode=seller["allocation_mode"],
                    product_allocations=tuple(
                        products_by_seller.get(seller["seller_uid"], [])
                    ),
                )
                for seller in seller_rows
            ),
        )

    def create_institution_funded_event(
        self,
        event: InstitutionFundedEventRecord,
    ) -> InstitutionFundedEventRecord:
        try:
            with self.pool.connection() as conn, conn.transaction():
                self._lock_active_institution(
                    conn,
                    event.owner_uid,
                    "institution.events.manage",
                )
                group = conn.execute(
                    """
                    SELECT group_id
                      FROM institution_groups
                     WHERE group_id = %s AND owner_uid = %s AND status = 'ACTIVE'
                     FOR UPDATE
                    """,
                    (event.group_id, event.owner_uid),
                ).fetchone()
                if group is None:
                    raise StoreNotFound(
                        "INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED"
                    )
                memberships = conn.execute(
                    """
                    SELECT membership_id, merchant_uid
                      FROM institution_group_memberships
                     WHERE group_id = %s AND status = 'ACTIVE'
                     ORDER BY merchant_uid, membership_id
                     FOR UPDATE
                    """,
                    (event.group_id,),
                ).fetchall()
                if not memberships:
                    raise StoreConflict(
                        "INSTITUTION_EVENT_REQUIRES_ACTIVE_AFFILIATES"
                    )
                conn.execute(
                    """
                    INSERT INTO institution_funded_events
                      (event_id, owner_uid, group_id, name, description,
                       funding_source, budget_amount_minor, currency, end_mode,
                       starts_at, ends_at, coupon_limit, status, created_at,
                       updated_at)
                    VALUES
                      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       'DRAFT', %s, %s)
                    """,
                    (
                        event.event_id,
                        event.owner_uid,
                        event.group_id,
                        event.name,
                        event.description,
                        event.funding_source,
                        event.budget_amount_minor,
                        event.currency,
                        event.end_mode,
                        event.starts_at,
                        event.ends_at,
                        event.coupon_limit,
                        event.created_at,
                        event.updated_at,
                    ),
                )
                equal_allocations = self._equal_minor_allocations(
                    event.budget_amount_minor,
                    [membership["merchant_uid"] for membership in memberships],
                )
                with conn.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO institution_event_seller_allocations
                          (event_id, membership_id, seller_uid,
                           allocated_amount_minor, allocation_mode,
                           created_at, updated_at)
                        VALUES (%s, %s, %s, %s, 'EQUAL', %s, %s)
                        """,
                        [
                            (
                                event.event_id,
                                membership["membership_id"],
                                membership["merchant_uid"],
                                equal_allocations[membership["merchant_uid"]],
                                event.created_at,
                                event.updated_at,
                            )
                            for membership in memberships
                        ],
                    )
                return self._load_institution_funded_event(
                    conn,
                    event.event_id,
                    owner_uid=event.owner_uid,
                )
        except UniqueViolation as exc:
            raise StoreConflict("INSTITUTION_FUNDED_EVENT_CONFLICT") from exc

    def list_institution_funded_events(
        self,
        owner_uid: str,
        limit: int,
    ) -> list[InstitutionFundedEventRecord]:
        checked_at = datetime.now(timezone.utc)
        with self.pool.connection() as conn, conn.transaction():
            event_rows = conn.execute(
                """
                SELECT event_id
                  FROM institution_funded_events
                 WHERE owner_uid = %s
                 ORDER BY created_at DESC, event_id
                 LIMIT %s
                """,
                (owner_uid, limit),
            ).fetchall()
            return [
                self._load_institution_funded_event(
                    conn,
                    row["event_id"],
                    owner_uid=owner_uid,
                    checked_at=checked_at,
                )
                for row in event_rows
            ]

    def set_institution_event_seller_allocations(
        self,
        owner_uid: str,
        event_id: str,
        allocations: tuple[tuple[str, int], ...],
        updated_at: datetime,
        *, by_badges: bool = False,
    ) -> InstitutionFundedEventRecord:
        with self.pool.connection() as conn, conn.transaction():
            self._lock_active_institution(
                conn,
                owner_uid,
                "institution.events.manage",
            )
            event = conn.execute(
                """
                SELECT budget_amount_minor, status, group_id
                  FROM institution_funded_events
                 WHERE event_id = %s AND owner_uid = %s
                 FOR UPDATE
                """,
                (event_id, owner_uid),
            ).fetchone()
            if event is None:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            if event["status"] != "DRAFT":
                raise StoreConflict("INSTITUTION_EVENT_ALLOCATION_LOCKED")
            distribution = None
            if by_badges:
                group_row = conn.execute("SELECT * FROM institution_groups WHERE group_id = %s FOR UPDATE", (event["group_id"],)).fetchone()
                group = self._institution_group(group_row)
                if group.status != "ACTIVE":
                    raise StoreConflict("INSTITUTION_GROUP_CLOSED")
                rows = conn.execute(
                    """SELECT membership.merchant_uid, membership.support_badge, membership.status
                         FROM institution_group_memberships AS membership
                         JOIN institution_event_seller_allocations AS allocation USING (membership_id)
                        WHERE allocation.event_id = %s FOR UPDATE OF membership""", (event_id,),
                ).fetchall()
                if any(row["status"] != "ACTIVE" for row in rows):
                    raise StoreConflict("INSTITUTION_BADGE_ACTIVE_MEMBER_REQUIRED")
                badges = {row["merchant_uid"]: row["support_badge"] for row in rows}
                try:
                    allocations = allocate_by_badges(int(event["budget_amount_minor"]), group.badge_policy, badges)
                except ValueError as exc:
                    raise StoreConflict(str(exc)) from exc
                distribution = InstitutionBadgeDistribution(policy=group.badge_policy, seller_badges=badges)
            supplied = dict(allocations)
            if len(supplied) != len(allocations):
                raise StoreConflict("INSTITUTION_EVENT_DUPLICATE_SELLER")
            current_rows = conn.execute(
                """
                SELECT seller_uid
                  FROM institution_event_seller_allocations
                 WHERE event_id = %s
                 FOR UPDATE
                """,
                (event_id,),
            ).fetchall()
            current_sellers = {row["seller_uid"] for row in current_rows}
            if set(supplied) != current_sellers:
                raise StoreConflict("INSTITUTION_EVENT_SELLER_SET_MISMATCH")
            if sum(supplied.values()) != int(event["budget_amount_minor"]):
                raise StoreConflict("INSTITUTION_EVENT_BUDGET_TOTAL_MISMATCH")
            for seller_uid, amount in allocations:
                conn.execute(
                    """
                    UPDATE institution_event_seller_allocations
                       SET allocated_amount_minor = %s,
                           allocation_mode = 'CUSTOM', updated_at = %s
                     WHERE event_id = %s AND seller_uid = %s
                    """,
                    (amount, updated_at, event_id, seller_uid),
                )
            conn.execute(
                "DELETE FROM institution_event_product_allocations WHERE event_id = %s",
                (event_id,),
            )
            conn.execute(
                """
                UPDATE institution_funded_events
                   SET updated_at = %s, badge_distribution = %s
                 WHERE event_id = %s
                """,
                (updated_at, Jsonb(distribution.model_dump()) if distribution else None, event_id),
            )
            return self._load_institution_funded_event(
                conn,
                event_id,
                owner_uid=owner_uid,
            )

    def set_institution_event_product_allocations(
        self,
        seller_uid: str,
        event_id: str,
        allocations: tuple[tuple[str, int], ...],
        updated_at: datetime,
    ) -> InstitutionFundedEventRecord:
        with self.pool.connection() as conn, conn.transaction():
            event = conn.execute(
                """
                SELECT event.status, event.currency,
                       seller.allocated_amount_minor
                  FROM institution_funded_events AS event
                  JOIN institution_event_seller_allocations AS seller
                    ON seller.event_id = event.event_id
                   AND seller.seller_uid = %s
                 WHERE event.event_id = %s
                 FOR UPDATE OF event, seller
                """,
                (seller_uid, event_id),
            ).fetchone()
            if event is None:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            if event["status"] != "DRAFT":
                raise StoreConflict("INSTITUTION_EVENT_ALLOCATION_LOCKED")
            supplied = dict(allocations)
            if len(supplied) != len(allocations):
                raise StoreConflict("INSTITUTION_EVENT_DUPLICATE_PRODUCT")
            if sum(supplied.values()) != int(event["allocated_amount_minor"]):
                raise StoreConflict("INSTITUTION_EVENT_PRODUCT_TOTAL_MISMATCH")
            products = conn.execute(
                """
                SELECT product_id
                  FROM products
                 WHERE merchant_uid = %s
                   AND product_id = ANY(%s)
                   AND currency = %s
                   AND status = 'ACTIVE'
                 FOR UPDATE
                """,
                (seller_uid, list(supplied), event["currency"]),
            ).fetchall()
            if {row["product_id"] for row in products} != set(supplied):
                raise StoreConflict("INSTITUTION_EVENT_PRODUCT_NOT_ELIGIBLE")
            conn.execute(
                """
                DELETE FROM institution_event_product_allocations
                 WHERE event_id = %s AND seller_uid = %s
                """,
                (event_id, seller_uid),
            )
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO institution_event_product_allocations
                      (event_id, seller_uid, product_id,
                       allocated_amount_minor, allocation_mode,
                       created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'CUSTOM', %s, %s)
                    """,
                    [
                        (
                            event_id,
                            seller_uid,
                            product_id,
                            amount,
                            updated_at,
                            updated_at,
                        )
                        for product_id, amount in allocations
                    ],
                )
            conn.execute(
                """
                UPDATE institution_funded_events
                   SET updated_at = %s
                 WHERE event_id = %s
                """,
                (updated_at, event_id),
            )
            return self._load_institution_funded_event(
                conn,
                event_id,
                seller_uid=seller_uid,
            )

    def activate_institution_funded_event(
        self,
        owner_uid: str,
        event_id: str,
        activated_at: datetime,
    ) -> InstitutionFundedEventRecord:
        with self.pool.connection() as conn, conn.transaction():
            self._lock_active_institution(
                conn,
                owner_uid,
                "institution.events.manage",
            )
            event = conn.execute(
                """
                SELECT *
                  FROM institution_funded_events
                 WHERE event_id = %s AND owner_uid = %s
                 FOR UPDATE
                """,
                (event_id, owner_uid),
            ).fetchone()
            if event is None:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            if event["status"] != "DRAFT":
                raise StoreConflict("INSTITUTION_EVENT_NOT_DRAFT")
            if event["end_mode"] == "TIME" and event["ends_at"] <= activated_at:
                raise StoreConflict("INSTITUTION_EVENT_END_TIME_ALREADY_PASSED")
            active = conn.execute(
                """
                SELECT event_id
                  FROM institution_funded_events
                 WHERE group_id = %s AND status = 'ACTIVE' AND event_id <> %s
                 FOR UPDATE
                """,
                (event["group_id"], event_id),
            ).fetchone()
            if active is not None:
                raise StoreConflict(
                    "INSTITUTION_GROUP_ALREADY_HAS_ACTIVE_FUNDED_EVENT"
                )
            sellers = conn.execute(
                """
                SELECT seller_uid, allocated_amount_minor
                  FROM institution_event_seller_allocations
                 WHERE event_id = %s
                 ORDER BY seller_uid
                 FOR UPDATE
                """,
                (event_id,),
            ).fetchall()
            for seller in sellers:
                existing = conn.execute(
                    """
                    SELECT product_id, allocated_amount_minor
                      FROM institution_event_product_allocations
                     WHERE event_id = %s AND seller_uid = %s
                     FOR UPDATE
                    """,
                    (event_id, seller["seller_uid"]),
                ).fetchall()
                if existing:
                    if sum(
                        int(row["allocated_amount_minor"]) for row in existing
                    ) != int(seller["allocated_amount_minor"]):
                        raise StoreConflict(
                            "INSTITUTION_EVENT_PRODUCT_TOTAL_MISMATCH"
                        )
                    continue
                products = conn.execute(
                    """
                    SELECT product_id
                      FROM products
                     WHERE merchant_uid = %s
                       AND currency = %s
                       AND status = 'ACTIVE'
                     ORDER BY product_id
                     FOR UPDATE
                    """,
                    (seller["seller_uid"], event["currency"]),
                ).fetchall()
                if not products:
                    if int(seller["allocated_amount_minor"]) == 0:
                        continue
                    raise StoreConflict(
                        "INSTITUTION_EVENT_SELLER_HAS_NO_ACTIVE_PRODUCTS"
                    )
                equal = self._equal_minor_allocations(
                    int(seller["allocated_amount_minor"]),
                    [product["product_id"] for product in products],
                )
                with conn.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO institution_event_product_allocations
                          (event_id, seller_uid, product_id,
                           allocated_amount_minor, allocation_mode,
                           created_at, updated_at)
                        VALUES (%s, %s, %s, %s, 'EQUAL', %s, %s)
                        """,
                        [
                            (
                                event_id,
                                seller["seller_uid"],
                                product["product_id"],
                                equal[product["product_id"]],
                                activated_at,
                                activated_at,
                            )
                            for product in products
                        ],
                    )
            conn.execute(
                """
                UPDATE institution_funded_events
                   SET status = 'ACTIVE', activated_at = %s, updated_at = %s
                 WHERE event_id = %s
                """,
                (activated_at, activated_at, event_id),
            )
            return self._load_institution_funded_event(
                conn,
                event_id,
                owner_uid=owner_uid,
                checked_at=activated_at,
            )

    def end_institution_funded_event(
        self,
        owner_uid: str,
        event_id: str,
        ended_at: datetime,
    ) -> InstitutionFundedEventRecord:
        with self.pool.connection() as conn, conn.transaction():
            self._lock_active_institution(
                conn,
                owner_uid,
                "institution.events.manage",
            )
            event = conn.execute(
                """
                SELECT status
                  FROM institution_funded_events
                 WHERE event_id = %s AND owner_uid = %s
                 FOR UPDATE
                """,
                (event_id, owner_uid),
            ).fetchone()
            if event is None:
                raise StoreNotFound("INSTITUTION_FUNDED_EVENT_NOT_FOUND")
            if event["status"] != "ACTIVE":
                raise StoreConflict("INSTITUTION_EVENT_NOT_ACTIVE")
            conn.execute(
                """
                UPDATE institution_funded_events
                   SET status = 'ENDED', end_reason = 'MANUAL',
                       ended_at = %s, updated_at = %s
                 WHERE event_id = %s
                """,
                (ended_at, ended_at, event_id),
            )
            return self._load_institution_funded_event(
                conn,
                event_id,
                owner_uid=owner_uid,
            )

    def list_entrepreneur_funded_events(
        self,
        seller_uid: str,
        limit: int,
    ) -> list[InstitutionFundedEventRecord]:
        checked_at = datetime.now(timezone.utc)
        with self.pool.connection() as conn, conn.transaction():
            event_rows = conn.execute(
                """
                SELECT event.event_id
                  FROM institution_funded_events AS event
                  JOIN institution_event_seller_allocations AS allocation
                    ON allocation.event_id = event.event_id
                 WHERE allocation.seller_uid = %s
                 ORDER BY event.created_at DESC, event.event_id
                 LIMIT %s
                """,
                (seller_uid, limit),
            ).fetchall()
            return [
                self._load_institution_funded_event(
                    conn,
                    row["event_id"],
                    seller_uid=seller_uid,
                    checked_at=checked_at,
                )
                for row in event_rows
            ]

    def get_institution_funded_event_report(
        self,
        owner_uid: str,
        event_id: str,
        generated_at: datetime,
    ) -> InstitutionFundedEventReportRecord:
        with self.pool.connection() as conn, conn.transaction():
            event = self._load_institution_funded_event(
                conn,
                event_id,
                owner_uid=owner_uid,
                checked_at=generated_at,
            )
            redemptions = conn.execute(
                self._funded_event_redemptions_sql(),
                (event_id,),
            ).fetchall()
            if event.end_mode == "COUPONS":
                redemptions = redemptions[: event.coupon_limit]
            totals_by_product: dict[str, dict[str, int]] = {}
            for redemption in redemptions:
                current = totals_by_product.setdefault(
                    redemption["product_id"],
                    {
                        "confirmed_redemptions": 0,
                        "units_sold": 0,
                        "gross_original_amount_minor": 0,
                        "gross_final_amount_minor": 0,
                        "discount_used_minor": 0,
                    },
                )
                original = int(redemption["original_amount_minor"] or 0)
                final = int(redemption["final_amount_minor"] or 0)
                current["confirmed_redemptions"] += 1
                current["units_sold"] += int(redemption["quantity"] or 1)
                current["gross_original_amount_minor"] += original
                current["gross_final_amount_minor"] += final
                current["discount_used_minor"] += max(original - final, 0)
            seller_reports: list[InstitutionFundedEventSellerReportRecord] = []
            for seller in event.seller_allocations:
                product_reports: list[
                    InstitutionFundedEventProductReportRecord
                ] = []
                for product in seller.product_allocations:
                    totals = totals_by_product.get(product.product_id, {})
                    discount_used = int(totals.get("discount_used_minor", 0))
                    amount_due = min(
                        discount_used,
                        product.allocated_amount_minor,
                    )
                    product_reports.append(
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
                            discount_used_minor=discount_used,
                            amount_due_minor=amount_due,
                            unfunded_discount_minor=max(
                                discount_used
                                - product.allocated_amount_minor,
                                0,
                            ),
                            remaining_budget_minor=max(
                                product.allocated_amount_minor - amount_due,
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
                            for product in product_reports
                        ),
                        units_sold=sum(
                            product.units_sold for product in product_reports
                        ),
                        gross_original_amount_minor=sum(
                            product.gross_original_amount_minor
                            for product in product_reports
                        ),
                        gross_final_amount_minor=sum(
                            product.gross_final_amount_minor
                            for product in product_reports
                        ),
                        discount_used_minor=sum(
                            product.discount_used_minor
                            for product in product_reports
                        ),
                        amount_due_minor=sum(
                            product.amount_due_minor for product in product_reports
                        ),
                        unfunded_discount_minor=sum(
                            product.unfunded_discount_minor
                            for product in product_reports
                        ),
                        remaining_budget_minor=sum(
                            product.remaining_budget_minor
                            for product in product_reports
                        ),
                        products=tuple(product_reports),
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

    def list_institution_groups(
        self,
        owner_uid: str,
        limit: int,
    ) -> list[InstitutionGroupRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                  FROM institution_groups
                 WHERE owner_uid = %s
                 ORDER BY created_at DESC, group_id
                 LIMIT %s
                """,
                (owner_uid, limit),
            ).fetchall()
        return [self._institution_group(row) for row in rows]

    def close_institution_group(
        self,
        owner_uid: str,
        group_id: str,
        closed_at: datetime,
    ) -> InstitutionGroupRecord:
        with self.pool.connection() as conn, conn.transaction():
            self._lock_active_institution(conn, owner_uid)
            current = conn.execute(
                """
                SELECT *
                  FROM institution_groups
                 WHERE group_id = %s AND owner_uid = %s
                 FOR UPDATE
                """,
                (group_id, owner_uid),
            ).fetchone()
            if current is None:
                raise StoreNotFound("INSTITUTION_GROUP_NOT_FOUND_OR_NOT_OWNED")
            if current["status"] == "CLOSED":
                return self._institution_group(current)
            memberships = conn.execute(
                """
                SELECT membership_id, status
                  FROM institution_group_memberships
                 WHERE group_id = %s AND status IN ('PENDING', 'ACTIVE')
                 FOR UPDATE
                """,
                (group_id,),
            ).fetchall()
            for membership in memberships:
                conn.execute(
                    """
                    UPDATE institution_group_memberships
                       SET status = 'REMOVED', responded_at = COALESCE(responded_at, %s),
                           ended_at = %s, updated_at = %s
                     WHERE membership_id = %s
                    """,
                    (closed_at, closed_at, closed_at, membership["membership_id"]),
                )
                conn.execute(
                    """
                    INSERT INTO institution_membership_events
                      (event_id, membership_id, actor_uid, event_type,
                       previous_status, new_status, created_at)
                    VALUES (%s, %s, %s, 'GROUP_CLOSED', %s, 'REMOVED', %s)
                    """,
                    (
                        f"membership-close:{uuid.uuid4()}",
                        membership["membership_id"],
                        owner_uid,
                        membership["status"],
                        closed_at,
                    ),
                )
            row = conn.execute(
                """
                UPDATE institution_groups
                   SET status = 'CLOSED', closed_at = %s, updated_at = %s
                 WHERE group_id = %s AND owner_uid = %s
                RETURNING *
                """,
                (closed_at, closed_at, group_id, owner_uid),
            ).fetchone()
        return self._institution_group(row)

    def list_access_accounts(self, limit: int) -> list[AccessAccountSummaryRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT a.firebase_uid, a.email, a.role, a.status,
                       a.created_at, a.updated_at,
                       validation.validation_state AS authority_validation_state,
                       validation.protection_level,
                       validation.account_origin,
                       validation.validated_at AS authority_validated_at,
                       validation.validated_by_uid AS authority_validated_by_uid,
                       validation.created_by_uid,
                       COALESCE(
                         array_agg(p.permission ORDER BY p.permission)
                           FILTER (WHERE p.permission IS NOT NULL),
                         ARRAY[]::TEXT[]
                       ) AS permissions
                  FROM access_accounts AS a
                  LEFT JOIN account_permissions AS p USING (firebase_uid)
                  LEFT JOIN privileged_account_validations AS validation
                    USING (firebase_uid)
                 GROUP BY a.firebase_uid, a.email, a.role, a.status,
                          a.created_at, a.updated_at,
                          validation.validation_state,
                          validation.protection_level,
                          validation.account_origin,
                          validation.validated_at,
                          validation.validated_by_uid,
                          validation.created_by_uid
                 ORDER BY a.updated_at DESC, a.firebase_uid
                 LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [self._access_summary(row) for row in rows]

    def list_staff_accounts(self, limit: int) -> list[AccessAccountSummaryRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT account.firebase_uid, account.email, account.role,
                       account.status, account.created_at, account.updated_at,
                       validation.validation_state AS authority_validation_state,
                       validation.protection_level,
                       validation.account_origin,
                       validation.validated_at AS authority_validated_at,
                       validation.validated_by_uid AS authority_validated_by_uid,
                       validation.created_by_uid,
                       COALESCE(
                         array_agg(permission.permission ORDER BY permission.permission)
                           FILTER (WHERE permission.permission IS NOT NULL),
                         ARRAY[]::TEXT[]
                       ) AS permissions
                  FROM access_accounts AS account
                  LEFT JOIN account_permissions AS permission USING (firebase_uid)
                  LEFT JOIN privileged_account_validations AS validation
                    USING (firebase_uid)
                 WHERE account.role IN ('admin', 'support', 'security')
                 GROUP BY account.firebase_uid, account.email, account.role,
                          account.status, account.created_at, account.updated_at,
                          validation.validation_state,
                          validation.protection_level,
                          validation.account_origin,
                          validation.validated_at,
                          validation.validated_by_uid,
                          validation.created_by_uid
                 ORDER BY account.updated_at DESC, account.firebase_uid
                 LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [self._access_summary(row) for row in rows]

    def get_admin_operations_summary(self) -> AdminOperationsSummaryRecord:
        with self.pool.connection() as conn:
            account_rows = conn.execute(
                """
                SELECT role, status, COUNT(*)::INTEGER AS total
                  FROM access_accounts
                 GROUP BY role, status
                """
            ).fetchall()
            counts = conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM institutional_profiles)::INTEGER AS institutions_total,
                  (SELECT COUNT(*) FROM institution_groups)::INTEGER AS groups_total,
                  (SELECT COUNT(*) FROM institution_groups WHERE status = 'ACTIVE')::INTEGER AS groups_active,
                  (SELECT COUNT(*) FROM merchant_accounts WHERE status = 'ACTIVE')::INTEGER AS merchants_active,
                  (SELECT COUNT(*) FROM merchant_accounts WHERE status = 'SUSPENDED')::INTEGER AS merchants_suspended,
                  (SELECT COUNT(*) FROM products WHERE status = 'ACTIVE')::INTEGER AS products_active,
                  (SELECT COUNT(*) FROM live_offers WHERE status = 'ACTIVE')::INTEGER AS offers_active
                """
            ).fetchone()

        accounts_by_role: dict[str, int] = {}
        accounts_by_status: dict[str, int] = {}
        for row in account_rows:
            total = int(row["total"])
            accounts_by_role[row["role"]] = accounts_by_role.get(row["role"], 0) + total
            accounts_by_status[row["status"]] = accounts_by_status.get(row["status"], 0) + total
        return AdminOperationsSummaryRecord(
            accounts_total=sum(accounts_by_role.values()),
            accounts_by_role=accounts_by_role,
            accounts_by_status=accounts_by_status,
            institutions_total=int(counts["institutions_total"]),
            groups_total=int(counts["groups_total"]),
            groups_active=int(counts["groups_active"]),
            merchants_active=int(counts["merchants_active"]),
            merchants_suspended=int(counts["merchants_suspended"]),
            products_active=int(counts["products_active"]),
            offers_active=int(counts["offers_active"]),
        )

    def get_security_monitoring_summary(self) -> SecurityMonitoringSummaryRecord:
        with self.pool.connection() as conn:
            status_rows = conn.execute(
                """
                SELECT status, COUNT(*)::INTEGER AS total
                  FROM access_accounts
                 GROUP BY status
                """
            ).fetchall()
            event_row = conn.execute(
                """
                SELECT COUNT(*)::INTEGER AS recent_events_total,
                       MAX(created_at) AS last_event_at
                  FROM access_audit_events
                """
            ).fetchone()

        by_status = {row["status"]: int(row["total"]) for row in status_rows}
        return SecurityMonitoringSummaryRecord(
            accounts_total=sum(by_status.values()),
            active_accounts=by_status.get("ACTIVE", 0),
            suspended_accounts=by_status.get("SUSPENDED", 0),
            pending_accounts=by_status.get("PENDING", 0),
            disabled_accounts=by_status.get("DISABLED", 0),
            recent_events_total=int(event_row["recent_events_total"]),
            last_event_at=event_row["last_event_at"],
        )

    def get_trq_bec_security_status(self) -> TrqBecSecurityStatusRecord:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM privileged_account_validations
                  ) AS privileged_accounts_total,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM privileged_account_validations
                     WHERE protection_level = 'SYSTEM'
                       AND validation_state = 'APPROVED'
                  ) AS official_accounts_total,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM privileged_account_validations
                     WHERE validation_state = 'PENDING'
                  ) AS privileged_accounts_pending_validation,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM access_audit_events
                  ) AS access_events_total,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM access_audit_events
                     WHERE created_at >= now() - INTERVAL '24 hours'
                  ) AS access_events_last_24h,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM audit_events
                  ) AS audit_events_total,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM audit_checkpoints
                  ) AS audit_checkpoints_total,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM device_keys
                     WHERE status = 'ACTIVE'
                  ) AS devices_active,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM device_keys
                     WHERE status = 'PENDING_APPROVAL'
                  ) AS devices_pending,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM device_keys
                     WHERE status = 'REVOKED'
                  ) AS devices_revoked,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM device_keys
                     WHERE notification_status IN ('FAILED', 'NOT_CONFIGURED')
                  ) AS device_notifications_failed,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM email_verification_queue
                     WHERE status IN ('PENDING', 'PROCESSING')
                  ) AS email_verifications_pending,
                  (
                    SELECT COUNT(*)::INTEGER
                      FROM email_verification_queue
                     WHERE status = 'FAILED'
                  ) AS email_verifications_failed,
                  (
                    SELECT version
                      FROM schema_migrations
                     ORDER BY version DESC
                     LIMIT 1
                  ) AS latest_schema_migration
                """
            ).fetchone()
        return TrqBecSecurityStatusRecord(
            privileged_accounts_total=int(row["privileged_accounts_total"]),
            official_accounts_total=int(row["official_accounts_total"]),
            privileged_accounts_pending_validation=int(
                row["privileged_accounts_pending_validation"]
            ),
            access_events_total=int(row["access_events_total"]),
            access_events_last_24h=int(row["access_events_last_24h"]),
            audit_events_total=int(row["audit_events_total"]),
            audit_checkpoints_total=int(row["audit_checkpoints_total"]),
            devices_active=int(row["devices_active"]),
            devices_pending=int(row["devices_pending"]),
            devices_revoked=int(row["devices_revoked"]),
            device_notifications_failed=int(row["device_notifications_failed"]),
            email_verifications_pending=int(row["email_verifications_pending"]),
            email_verifications_failed=int(row["email_verifications_failed"]),
            latest_schema_migration=row["latest_schema_migration"],
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
        with self.pool.connection() as conn, conn.transaction():
            actor = conn.execute(
                """
                SELECT a.firebase_uid
                  FROM access_accounts AS a
                  JOIN account_permissions AS p USING (firebase_uid)
                 WHERE a.firebase_uid = %s
                   AND a.role = 'security'
                   AND a.status = 'ACTIVE'
                   AND p.permission = 'security.incidents.manage'
                 FOR UPDATE OF a
                """,
                (actor_uid,),
            ).fetchone()
            if actor is None:
                raise StoreConflict("SECURITY_ACCESS_REQUIRED")
            current = conn.execute(
                """
                SELECT account.*, validation.protection_level
                  FROM access_accounts AS account
                  LEFT JOIN privileged_account_validations AS validation
                    USING (firebase_uid)
                 WHERE account.firebase_uid = %s
                 FOR UPDATE OF account
                """,
                (target_uid,),
            ).fetchone()
            if current is None:
                raise StoreNotFound("ACCESS_ACCOUNT_NOT_FOUND")
            if actor_uid == target_uid:
                raise StoreConflict("SELF_STATUS_CHANGE_FORBIDDEN")
            if (
                current["role"] in {"admin", "security"}
                or current["protection_level"] == "SYSTEM"
            ):
                raise StoreConflict("PROTECTED_ACCOUNT_STATUS_CHANGE")
            if current["status"] not in {"ACTIVE", "SUSPENDED"}:
                raise StoreConflict("ACCOUNT_STATUS_TRANSITION_FORBIDDEN")

            if current["status"] != status:
                updated = conn.execute(
                    """
                    UPDATE access_accounts
                       SET status = %s, updated_at = now()
                     WHERE firebase_uid = %s
                    RETURNING *
                    """,
                    (status, target_uid),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO access_audit_events
                      (event_id, actor_uid, target_uid, event_type,
                       previous_status, new_status, reason)
                    VALUES (%s, %s, %s, 'ACCOUNT_STATUS_CHANGED', %s, %s, %s)
                    """,
                    (event_id, actor_uid, target_uid, current["status"], status, reason),
                )
            else:
                updated = current

            permissions = conn.execute(
                """
                SELECT permission
                  FROM account_permissions
                 WHERE firebase_uid = %s
                 ORDER BY permission
                """,
                (target_uid,),
            ).fetchall()
        return self._access_summary(
            {
                **updated,
                "permissions": [row["permission"] for row in permissions],
            }
        )

    def list_access_audit_events(self, limit: int) -> list[AccessAuditEventRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                  FROM access_audit_events
                 ORDER BY created_at DESC, event_id
                 LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [self._access_audit_event(row) for row in rows]

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
    ) -> tuple[DeviceRecord, bool, bool]:
        with self.pool.connection() as conn, conn.transaction():
            # Serializa o bootstrap por UID mesmo quando ainda não existe linha.
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (uid,))
            existing = conn.execute(
                "SELECT * FROM device_keys WHERE device_key_id = %s FOR UPDATE",
                (key_id,),
            ).fetchone()
            if existing:
                if (
                    existing["firebase_uid"] != uid
                    or existing["public_key_b64u"] != public_key_b64u
                    or existing["algorithm"] != algorithm
                    or existing["storage_profile"] != storage_profile
                ):
                    raise StoreConflict("DEVICE_KEY_BINDING_CONFLICT")
                if existing["status"] == "REVOKED":
                    raise StoreConflict("DEVICE_KEY_REVOKED")
                bypassed_approval = (
                    not requires_approval
                    and existing["status"] == "PENDING_APPROVAL"
                )
                row = conn.execute(
                    """
                    UPDATE device_keys
                       SET last_seen_at = now(),
                           device_name = COALESCE(%s, device_name),
                           platform = CASE WHEN %s = 'unknown' THEN platform ELSE %s END,
                           model_name = COALESCE(%s, model_name),
                           app_version = COALESCE(%s, app_version),
                           status = CASE WHEN %s THEN 'ACTIVE' ELSE status END,
                           approval_token_hash = CASE WHEN %s THEN NULL ELSE approval_token_hash END,
                           approval_expires_at = CASE WHEN %s THEN NULL ELSE approval_expires_at END,
                           approved_at = CASE WHEN %s THEN COALESCE(approved_at, now()) ELSE approved_at END,
                           notification_status = CASE WHEN %s THEN 'NOT_REQUIRED' ELSE notification_status END
                     WHERE device_key_id = %s
                    RETURNING *
                    """,
                    (
                        device_name,
                        platform,
                        platform,
                        model_name,
                        app_version,
                        bypassed_approval,
                        bypassed_approval,
                        bypassed_approval,
                        bypassed_approval,
                        bypassed_approval,
                        key_id,
                    ),
                ).fetchone()
                self._append_audit_conn(
                    conn,
                    result=(
                        "VISITOR_DEVICE_ACTIVATED"
                        if bypassed_approval
                        else "ALREADY_ENROLLED"
                    ),
                    **audit,
                )
                return self._device(row), False, existing["status"] == "PENDING_APPROVAL"
            if not auth_is_recent:
                raise StoreConflict("RECENT_AUTHENTICATION_REQUIRED")
            counts = conn.execute(
                """
                SELECT
                  count(*) AS history_count,
                  count(*) FILTER (WHERE status = 'PENDING_APPROVAL') AS pending_count
                  FROM device_keys
                 WHERE firebase_uid = %s
                """,
                (uid,),
            ).fetchone()
            is_additional = int(counts["history_count"] or 0) > 0
            approval_required_for_device = requires_approval and (
                is_additional or first_device_requires_approval
            )
            if (
                approval_required_for_device
                and int(counts["pending_count"] or 0) >= max_pending_devices
            ):
                raise StoreConflict("PENDING_DEVICE_LIMIT_REACHED")
            status = (
                "PENDING_APPROVAL"
                if approval_required_for_device
                else "ACTIVE"
            )
            notification_status = (
                "PENDING" if status == "PENDING_APPROVAL" else "NOT_REQUIRED"
            )
            try:
                row = conn.execute(
                    """
                    INSERT INTO device_keys
                      (device_key_id, firebase_uid, public_key_b64u, algorithm, storage_profile,
                       status, device_name, platform, model_name, app_version,
                       approval_token_hash, approval_expires_at, approval_last_sent_at,
                       approved_at, notification_status)
                    VALUES
                      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       CASE WHEN %s = 'PENDING_APPROVAL' THEN %s ELSE NULL END,
                       CASE WHEN %s = 'PENDING_APPROVAL' THEN %s ELSE NULL END,
                       CASE WHEN %s = 'PENDING_APPROVAL' THEN now() ELSE NULL END,
                       CASE WHEN %s = 'ACTIVE' THEN now() ELSE NULL END,
                       %s)
                    RETURNING *
                    """,
                    (
                        key_id,
                        uid,
                        public_key_b64u,
                        algorithm,
                        storage_profile,
                        status,
                        device_name,
                        platform,
                        model_name,
                        app_version,
                        status,
                        approval_token_hash,
                        status,
                        approval_expires_at,
                        status,
                        status,
                        notification_status,
                    ),
                ).fetchone()
            except UniqueViolation as exc:
                raise StoreConflict("DEVICE_ENROLLMENT_CONFLICT") from exc
            self._append_audit_conn(
                conn,
                result=(
                    "ENROLLED_PENDING_APPROVAL"
                    if status == "PENDING_APPROVAL"
                    else "ENROLLED"
                ),
                **audit,
            )
            return self._device(row), True, is_additional

    @staticmethod
    def _device(row: dict[str, Any]) -> DeviceRecord:
        return DeviceRecord(
            firebase_uid=row["firebase_uid"],
            device_key_id=row["device_key_id"],
            public_key_b64u=row["public_key_b64u"],
            algorithm=row["algorithm"],
            storage_profile=row["storage_profile"],
            status=row["status"],
            device_name=row.get("device_name"),
            platform=row.get("platform") or "unknown",
            model_name=row.get("model_name"),
            app_version=row.get("app_version"),
            notification_status=row.get("notification_status") or "NOT_REQUIRED",
            created_at=row.get("created_at"),
            last_seen_at=row.get("last_seen_at"),
            revoked_at=row.get("revoked_at"),
            approval_expires_at=row.get("approval_expires_at"),
            approval_last_sent_at=row.get("approval_last_sent_at"),
            approved_at=row.get("approved_at"),
        )

    def list_devices(self, uid: str, limit: int) -> list[DeviceRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                  FROM device_keys
                 WHERE firebase_uid = %s
                 ORDER BY
                   CASE status WHEN 'PENDING_APPROVAL' THEN 0 WHEN 'ACTIVE' THEN 1 ELSE 2 END,
                   last_seen_at DESC,
                   device_key_id
                 LIMIT %s
                """,
                (uid, limit),
            ).fetchall()
        return [self._device(row) for row in rows]

    def activate_due_devices(
        self, uid: str, activated_at: datetime, **audit: Any
    ) -> int:
        with self.pool.connection() as conn, conn.transaction():
            rows = conn.execute(
                """
                UPDATE device_keys
                   SET status = 'ACTIVE',
                       approval_token_hash = NULL,
                       approval_expires_at = NULL,
                       approved_at = COALESCE(approved_at, %s)
                 WHERE firebase_uid = %s
                   AND status = 'PENDING_APPROVAL'
                   AND approval_expires_at <= %s
                RETURNING device_key_id
                """,
                (activated_at, uid, activated_at),
            ).fetchall()
            if rows:
                details = dict(audit.get("details") or {})
                details["activated_device_count"] = len(rows)
                self._append_audit_conn(
                    conn,
                    **{
                        **audit,
                        "details": details,
                        "result": "AUTO_ACTIVATED",
                    },
                )
        return len(rows)

    def set_device_notification_status(
        self, uid: str, key_id: str, notification_status: str
    ) -> DeviceRecord:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                UPDATE device_keys
                   SET notification_status = %s
                 WHERE firebase_uid = %s AND device_key_id = %s
                RETURNING *
                """,
                (notification_status, uid, key_id),
            ).fetchone()
            if row is None:
                raise StoreNotFound("DEVICE_NOT_FOUND")
        return self._device(row)

    def approve_device(
        self, uid: str, approval_token_hash: str, approved_at: datetime, **audit: Any
    ) -> DeviceRecord:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                SELECT *
                  FROM device_keys
                 WHERE firebase_uid = %s AND approval_token_hash = %s
                 FOR UPDATE
                """,
                (uid, approval_token_hash),
            ).fetchone()
            if row is None or row["status"] != "PENDING_APPROVAL":
                raise StoreConflict("DEVICE_APPROVAL_INVALID_OR_EXPIRED")
            if row["approval_expires_at"] <= approved_at:
                raise StoreConflict("DEVICE_APPROVAL_INVALID_OR_EXPIRED")
            approved = conn.execute(
                """
                UPDATE device_keys
                   SET status = 'ACTIVE',
                       approval_token_hash = NULL,
                       approval_expires_at = NULL,
                       approved_at = %s,
                       last_seen_at = now()
                 WHERE device_key_id = %s
                RETURNING *
                """,
                (approved_at, row["device_key_id"]),
            ).fetchone()
            self._append_audit_conn(conn, result="APPROVED", **audit)
        return self._device(approved)

    def rotate_device_approval(
        self,
        uid: str,
        key_id: str,
        approval_token_hash: str,
        approval_expires_at: datetime,
        cooldown_seconds: int,
        **audit: Any,
    ) -> DeviceRecord:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                SELECT *
                  FROM device_keys
                 WHERE firebase_uid = %s AND device_key_id = %s
                 FOR UPDATE
                """,
                (uid, key_id),
            ).fetchone()
            if row is None:
                raise StoreNotFound("DEVICE_NOT_FOUND")
            if row["status"] != "PENDING_APPROVAL":
                raise StoreConflict("DEVICE_APPROVAL_NOT_PENDING")
            if row["approval_last_sent_at"] is not None:
                seconds_since_send = (
                    datetime.now(timezone.utc) - row["approval_last_sent_at"]
                ).total_seconds()
                if seconds_since_send < cooldown_seconds:
                    raise StoreConflict("APPROVAL_RESEND_COOLDOWN")
            updated = conn.execute(
                """
                UPDATE device_keys
                   SET approval_token_hash = %s,
                       approval_last_sent_at = now(),
                       notification_status = 'PENDING'
                 WHERE device_key_id = %s
                RETURNING *
                """,
                (approval_token_hash, key_id),
            ).fetchone()
            self._append_audit_conn(conn, result="APPROVAL_REISSUED", **audit)
        return self._device(updated)

    def revoke_all_devices(self, uid: str, **audit: Any) -> int:
        with self.pool.connection() as conn, conn.transaction():
            revoked_count = conn.execute(
                """
                UPDATE device_keys
                   SET status = 'REVOKED',
                       revoked_at = COALESCE(revoked_at, now()),
                       approval_token_hash = NULL,
                       approval_expires_at = NULL,
                       notification_status = 'NOT_REQUIRED'
                 WHERE firebase_uid = %s
                   AND status IN ('ACTIVE', 'PENDING_APPROVAL')
                """,
                (uid,),
            ).rowcount
            self._append_audit_conn(conn, result="ALL_DEVICES_REVOKED", **audit)
        return revoked_count

    def get_device(self, uid: str, key_id: str) -> DeviceRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM device_keys WHERE firebase_uid = %s AND device_key_id = %s AND status = 'ACTIVE'",
                (uid, key_id),
            ).fetchone()
        return self._device(row) if row else None

    @staticmethod
    def _merchant(row: dict[str, Any]) -> MerchantRecord:
        return MerchantRecord(
            firebase_uid=row["firebase_uid"],
            display_name=row["display_name"],
            establishment_id=row["establishment_id"],
            establishment_name=row["establishment_name"],
            status=row["status"],
        )

    def set_merchant_status(self, merchant: MerchantRecord, **audit: Any) -> MerchantRecord:
        with self.pool.connection() as conn, conn.transaction():
            access = conn.execute(
                """
                SELECT role, status
                  FROM access_accounts
                 WHERE firebase_uid = %s
                 FOR UPDATE
                """,
                (merchant.firebase_uid,),
            ).fetchone()
            if access and access["role"] != "entrepreneur" and merchant.status == "ACTIVE":
                raise StoreConflict("ACCESS_ROLE_CONFLICT")
            if access and access["status"] == "DISABLED" and merchant.status == "ACTIVE":
                raise StoreConflict("ACCOUNT_DISABLED")

            row = conn.execute(
                """
                INSERT INTO merchant_accounts
                  (firebase_uid, display_name, establishment_id, establishment_name, status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (firebase_uid) DO UPDATE SET
                  display_name = EXCLUDED.display_name,
                  establishment_id = EXCLUDED.establishment_id,
                  establishment_name = EXCLUDED.establishment_name,
                  status = EXCLUDED.status,
                  updated_at = now()
                RETURNING *
                """,
                (
                    merchant.firebase_uid,
                    merchant.display_name,
                    merchant.establishment_id,
                    merchant.establishment_name,
                    merchant.status,
                ),
            ).fetchone()
            if access is None:
                conn.execute(
                    """
                    INSERT INTO access_accounts (firebase_uid, role, status)
                    VALUES (%s, 'entrepreneur', %s)
                    """,
                    (merchant.firebase_uid, merchant.status),
                )
                with conn.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO account_permissions (firebase_uid, permission) VALUES (%s, %s)",
                        [
                            (merchant.firebase_uid, permission)
                            for permission in default_permissions("entrepreneur")
                        ],
                    )
            elif access["role"] == "entrepreneur" and access["status"] != "DISABLED":
                conn.execute(
                    """
                    UPDATE access_accounts
                       SET status = %s, updated_at = now()
                     WHERE firebase_uid = %s
                    """,
                    (merchant.status, merchant.firebase_uid),
                )
            self._append_audit_conn(conn, **audit)
        return self._merchant(row)

    def get_active_merchant(self, uid: str) -> MerchantRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM merchant_accounts WHERE firebase_uid = %s AND status = 'ACTIVE'",
                (uid,),
            ).fetchone()
        return self._merchant(row) if row else None

    def close_account(self, uid: str, **audit: Any) -> None:
        """Desativa dados comerciais sem alterar o histórico técnico assinado."""

        with self.pool.connection() as conn, conn.transaction():
            changed = 0
            changed += conn.execute(
                """
                UPDATE live_offers
                   SET status = 'CANCELLED', updated_at = now()
                 WHERE merchant_uid = %s AND status IN ('ACTIVE', 'PAUSED')
                """,
                (uid,),
            ).rowcount
            changed += conn.execute(
                """
                UPDATE coupon_tokens
                   SET status = 'REVOKED'
                 WHERE issuer_uid = %s AND status = 'ISSUED'
                """,
                (uid,),
            ).rowcount
            changed += conn.execute(
                """
                UPDATE products
                   SET status = 'ARCHIVED', updated_at = now()
                 WHERE merchant_uid = %s AND status <> 'ARCHIVED'
                """,
                (uid,),
            ).rowcount
            changed += conn.execute(
                """
                UPDATE device_keys
                   SET status = 'REVOKED',
                       revoked_at = COALESCE(revoked_at, now()),
                       approval_token_hash = NULL,
                       approval_expires_at = NULL,
                       notification_status = 'NOT_REQUIRED'
                 WHERE firebase_uid = %s
                   AND status IN ('ACTIVE', 'PENDING_APPROVAL')
                """,
                (uid,),
            ).rowcount
            changed += conn.execute(
                """
                UPDATE coupon_definitions
                   SET active = FALSE, updated_at = now()
                 WHERE owner_uid = %s AND active = TRUE
                """,
                (uid,),
            ).rowcount
            changed += conn.execute(
                """
                UPDATE merchant_accounts
                   SET status = 'SUSPENDED', updated_at = now()
                 WHERE firebase_uid = %s AND status = 'ACTIVE'
                """,
                (uid,),
            ).rowcount
            changed += conn.execute(
                """
                UPDATE access_accounts
                   SET status = 'DISABLED', updated_at = now()
                 WHERE firebase_uid = %s AND status <> 'DISABLED'
                """,
                (uid,),
            ).rowcount

            if changed:
                self._append_audit_conn(conn, **audit)

    @staticmethod
    def _product(row: dict[str, Any]) -> ProductRecord:
        return ProductRecord(
            product_id=row["product_id"],
            merchant_uid=row["merchant_uid"],
            title=row["title"],
            description=row["description"],
            price_minor=int(row["price_minor"]),
            currency=row["currency"],
            stock_quantity=int(row["stock_quantity"]),
            status=row["status"],
            created_at=int(row["created_at"].timestamp()) if row.get("created_at") else None,
            updated_at=int(row["updated_at"].timestamp()) if row.get("updated_at") else None,
        )

    def create_product(self, product: ProductRecord, **audit: Any) -> ProductRecord:
        with self.pool.connection() as conn, conn.transaction():
            merchant = conn.execute(
                "SELECT status FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                (product.merchant_uid,),
            ).fetchone()
            if not merchant or merchant["status"] != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            row = conn.execute(
                """
                INSERT INTO products
                  (product_id, merchant_uid, title, description, price_minor, currency, stock_quantity, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    product.product_id,
                    product.merchant_uid,
                    product.title,
                    product.description,
                    product.price_minor,
                    product.currency,
                    product.stock_quantity,
                    product.status,
                ),
            ).fetchone()
            self._append_audit_conn(conn, **audit)
        return self._product(row)

    def update_product_stock(
        self,
        uid: str,
        product_id: str,
        stock_quantity: int,
        **audit: Any,
    ) -> ProductRecord:
        with self.pool.connection() as conn, conn.transaction():
            merchant = conn.execute(
                "SELECT status FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                (uid,),
            ).fetchone()
            if not merchant or merchant["status"] != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            row = conn.execute(
                """
                UPDATE products SET stock_quantity = %s, updated_at = now()
                WHERE product_id = %s AND merchant_uid = %s AND status != 'ARCHIVED'
                RETURNING *
                """,
                (stock_quantity, product_id, uid),
            ).fetchone()
            if not row:
                raise StoreNotFound("PRODUCT_NOT_FOUND_OR_NOT_OWNED")
            self._append_audit_conn(conn, **audit)
        return self._product(row)

    def list_products(self, uid: str) -> list[ProductRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM products WHERE merchant_uid = %s ORDER BY created_at DESC",
                (uid,),
            ).fetchall()
        return [self._product(row) for row in rows]

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
        if not product_ids or len(set(product_ids)) != len(product_ids):
            raise StoreConflict("PRODUCT_BATCH_IDS_INVALID")
        with self.pool.connection() as conn, conn.transaction():
            prior = self._claim_marketplace_batch_conn(
                conn,
                uid=uid,
                client_request_id=client_request_id,
                operation_kind=operation_kind,
                command_hash=command_hash,
                operation_id=batch_operation_id,
            )
            if prior is not None:
                return prior
            merchant = conn.execute(
                "SELECT status FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                (uid,),
            ).fetchone()
            if not merchant or merchant["status"] != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            rows = conn.execute(
                """
                SELECT * FROM products
                 WHERE product_id = ANY(%s) AND merchant_uid = %s
                 ORDER BY product_id FOR UPDATE
                """,
                (list(product_ids), uid),
            ).fetchall()
            if len(rows) != len(product_ids):
                raise StoreNotFound("PRODUCT_BATCH_NOT_FOUND_OR_FINAL")
            offer_rows = conn.execute(
                """
                SELECT offer_id FROM live_offers
                 WHERE product_id = ANY(%s) AND merchant_uid = %s
                 ORDER BY offer_id FOR UPDATE
                """,
                (list(product_ids), uid),
            ).fetchall()
            offer_ids = [row["offer_id"] for row in offer_rows]
            if offer_ids:
                conn.execute(
                    """
                    UPDATE coupon_tokens SET status = 'REVOKED'
                     WHERE offer_id = ANY(%s) AND status = 'ISSUED'
                    """,
                    (offer_ids,),
                )
                conn.execute(
                    """
                    UPDATE live_offers SET status = 'REVOKED', updated_at = now()
                     WHERE offer_id = ANY(%s) AND status IN ('ACTIVE', 'PAUSED')
                    """,
                    (offer_ids,),
                )
            updated_rows = conn.execute(
                """
                UPDATE products SET status = 'ARCHIVED', updated_at = now()
                 WHERE product_id = ANY(%s) AND merchant_uid = %s
                RETURNING *
                """,
                (list(product_ids), uid),
            ).fetchall()
            self._append_audit_conn(conn, **audit)
            by_id = {row["product_id"]: self._product(row) for row in updated_rows}
            products = [by_id[product_id] for product_id in product_ids]
            response = response_factory(products)
            self._complete_marketplace_batch_conn(
                conn,
                uid=uid,
                client_request_id=client_request_id,
                response=response,
            )
            return response

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
        product_ids = tuple(product_id for product_id, _ in product_stocks)
        if (
            not product_stocks
            or len(set(product_ids)) != len(product_ids)
            or any(stock_quantity <= 0 for _, stock_quantity in product_stocks)
        ):
            raise StoreConflict("PRODUCT_BATCH_ACTIVATE_ITEMS_INVALID")
        with self.pool.connection() as conn, conn.transaction():
            prior = self._claim_marketplace_batch_conn(
                conn,
                uid=uid,
                client_request_id=client_request_id,
                operation_kind=operation_kind,
                command_hash=command_hash,
                operation_id=batch_operation_id,
            )
            if prior is not None:
                return prior
            merchant = conn.execute(
                "SELECT status FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                (uid,),
            ).fetchone()
            if not merchant or merchant["status"] != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            rows = conn.execute(
                """
                SELECT product_id, status FROM products
                 WHERE product_id = ANY(%s) AND merchant_uid = %s
                 ORDER BY product_id FOR UPDATE
                """,
                (list(product_ids), uid),
            ).fetchall()
            if len(rows) != len(product_ids) or any(
                row["status"] == "ARCHIVED" for row in rows
            ):
                raise StoreNotFound("PRODUCT_BATCH_NOT_FOUND_OR_NOT_OWNED")

            products: list[ProductRecord] = []
            for product_id, stock_quantity in product_stocks:
                row = conn.execute(
                    """
                    UPDATE products
                       SET status = 'ACTIVE', stock_quantity = %s, updated_at = now()
                     WHERE product_id = %s AND merchant_uid = %s
                    RETURNING *
                    """,
                    (stock_quantity, product_id, uid),
                ).fetchone()
                if not row:
                    raise StoreNotFound("PRODUCT_BATCH_NOT_FOUND_OR_NOT_OWNED")
                products.append(self._product(row))

            self._append_audit_conn(conn, **audit)
            response = response_factory(products)
            self._complete_marketplace_batch_conn(
                conn,
                uid=uid,
                client_request_id=client_request_id,
                response=response,
            )
            return response

    @staticmethod
    def _catalog_merchant(row: dict[str, Any]) -> CatalogMerchantRecord:
        return CatalogMerchantRecord(
            firebase_uid=row["merchant_uid"],
            display_name=row["merchant_display_name"],
            establishment_name=row["merchant_establishment_name"],
        )

    def _list_public_catalog_conn(
        self,
        conn,
        *,
        merchant_uid: str | None,
        limit: int,
    ) -> list[CatalogProductRecord]:
        bounded_limit = max(0, min(int(limit), 50))
        if bounded_limit == 0:
            return []
        now = int(time.time())
        rows = conn.execute(
            """
            WITH catalog_products AS (
                SELECT p.product_id, p.merchant_uid, p.title, p.description,
                       p.price_minor, p.currency, p.stock_quantity,
                       p.status AS product_internal_status,
                       EXTRACT(EPOCH FROM p.created_at)::bigint AS product_created_at,
                       EXTRACT(EPOCH FROM p.updated_at)::bigint AS product_updated_at,
                       m.display_name AS merchant_display_name,
                       m.establishment_name AS merchant_establishment_name
                FROM products p
                JOIN merchant_accounts m ON m.firebase_uid = p.merchant_uid
                WHERE m.status = 'ACTIVE'
                  AND p.status != 'ARCHIVED'
                  AND (%s::text IS NULL OR p.merchant_uid = %s::text)
                ORDER BY p.created_at DESC, p.product_id DESC
                LIMIT %s
            )
            SELECT cp.product_id, cp.merchant_uid, cp.title, cp.description,
                   cp.price_minor, cp.currency, cp.stock_quantity,
                   cp.product_internal_status, cp.product_created_at,
                   cp.product_updated_at,
                   cp.merchant_display_name, cp.merchant_establishment_name,
                   public_offer.offer_id, public_offer.original_amount_minor,
                   public_offer.discount_amount_minor, public_offer.final_amount_minor,
                   public_offer.offer_currency, public_offer.remaining_redemptions,
                   public_offer.expires_at, public_offer.offer_created_at,
                   public_offer.offer_updated_at, public_offer.offer_status,
                   public_offer.token_redeemable
            FROM catalog_products cp
            LEFT JOIN LATERAL (
                SELECT o.offer_id, o.original_amount_minor, o.discount_amount_minor,
                       o.final_amount_minor, o.currency AS offer_currency,
                       GREATEST(0, LEAST(
                           o.maximum_redemptions - o.redeemed_count,
                           cp.stock_quantity
                       ))::integer AS remaining_redemptions,
                       EXTRACT(EPOCH FROM o.expires_at)::bigint AS expires_at,
                       EXTRACT(EPOCH FROM o.created_at)::bigint AS offer_created_at,
                       EXTRACT(EPOCH FROM o.updated_at)::bigint AS offer_updated_at,
                       o.status AS offer_status,
                       COALESCE(
                           o.starts_at <= now()
                           AND t.status = 'ISSUED'
                           AND t.expires_at > now(),
                           FALSE
                       ) AS token_redeemable
                FROM live_offers o
                LEFT JOIN coupon_tokens t
                  ON t.offer_id = o.offer_id AND t.token_ref = o.token_ref
                WHERE o.product_id = cp.product_id
                  AND o.status != 'REVOKED'
                ORDER BY o.created_at DESC, o.offer_id DESC
                LIMIT 50
            ) AS public_offer ON TRUE
            ORDER BY cp.product_created_at DESC, cp.product_id DESC,
                     public_offer.offer_created_at DESC NULLS LAST,
                     public_offer.offer_id DESC NULLS LAST
            """,
            (merchant_uid, merchant_uid, bounded_limit),
        ).fetchall()

        products: dict[str, CatalogProductRecord] = {}
        offers: dict[str, list[CatalogOfferRecord]] = {}
        product_order: list[str] = []
        for row in rows:
            product_id = row["product_id"]
            if product_id not in products:
                product_state = product_public_state(
                    product_status=row["product_internal_status"],
                    stock_quantity=int(row["stock_quantity"]),
                    updated_at=int(row["product_updated_at"]),
                )
                if product_state is None:
                    continue
                products[product_id] = CatalogProductRecord(
                    product_id=product_id,
                    title=row["title"],
                    description=row["description"],
                    price_minor=int(row["price_minor"]),
                    currency=row["currency"],
                    stock_quantity=int(row["stock_quantity"]),
                    created_at=int(row["product_created_at"]),
                    updated_at=int(row["product_updated_at"]),
                    status=product_state[0],
                    status_reason=product_state[1],
                    ended_at=product_state[2],
                    merchant=self._catalog_merchant(row),
                    offers=(),
                )
                offers[product_id] = []
                product_order.append(product_id)
            if row["offer_id"] is not None:
                product = products[product_id]
                offer_state = offer_public_state(
                    offer_status=row["offer_status"],
                    expires_at=int(row["expires_at"]),
                    updated_at=int(row["offer_updated_at"]),
                    remaining_redemptions=int(row["remaining_redemptions"]),
                    token_redeemable=bool(row["token_redeemable"]),
                    product_status=product.status,
                    product_status_reason=product.status_reason,
                    product_ended_at=product.ended_at,
                    now=now,
                )
                if offer_state is None:
                    continue
                offers[product_id].append(
                    CatalogOfferRecord(
                        offer_id=row["offer_id"],
                        original_amount_minor=int(row["original_amount_minor"]),
                        discount_amount_minor=int(row["discount_amount_minor"]),
                        final_amount_minor=int(row["final_amount_minor"]),
                        currency=row["offer_currency"],
                        remaining_redemptions=int(row["remaining_redemptions"]),
                        expires_at=int(row["expires_at"]),
                        created_at=int(row["offer_created_at"]),
                        updated_at=int(row["offer_updated_at"]),
                        status=offer_state[0],
                        status_reason=offer_state[1],
                        ended_at=offer_state[2],
                    )
                )
        return [
            replace(products[product_id], offers=tuple(offers[product_id]))
            for product_id in product_order
        ]

    def list_public_catalog(self, limit: int) -> list[CatalogProductRecord]:
        with self.pool.connection() as conn:
            return self._list_public_catalog_conn(conn, merchant_uid=None, limit=limit)

    def get_public_merchant_catalog(
        self,
        firebase_uid: str,
        limit: int,
    ) -> tuple[CatalogMerchantRecord, list[CatalogProductRecord]] | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT firebase_uid AS merchant_uid,
                       display_name AS merchant_display_name,
                       establishment_name AS merchant_establishment_name
                FROM merchant_accounts
                WHERE firebase_uid = %s AND status = 'ACTIVE'
                """,
                (firebase_uid,),
            ).fetchone()
            if row is None:
                return None
            merchant = self._catalog_merchant(row)
            products = self._list_public_catalog_conn(
                conn,
                merchant_uid=firebase_uid,
                limit=limit,
            )
        return merchant, products

    def get_product_for_offer(self, uid: str, product_id: str) -> ProductRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT p.* FROM products p
                JOIN merchant_accounts m ON m.firebase_uid = p.merchant_uid
                WHERE p.product_id = %s AND p.merchant_uid = %s
                  AND p.status = 'ACTIVE' AND p.stock_quantity > 0 AND m.status = 'ACTIVE'
                """,
                (product_id, uid),
            ).fetchone()
        return self._product(row) if row else None

    def get_coupon_for_issue(self, coupon_id: str, owner_uid: str) -> CouponRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT coupon_id, owner_uid, active,
                       CASE WHEN valid_until IS NULL THEN NULL ELSE EXTRACT(EPOCH FROM valid_until)::BIGINT END AS valid_until
                FROM coupon_definitions
                WHERE coupon_id = %s AND active = TRUE
                  AND (owner_uid IS NULL OR owner_uid = %s)
                  AND (valid_until IS NULL OR valid_until > now())
                """,
                (coupon_id, owner_uid),
            ).fetchone()
        return CouponRecord(**row) if row else None

    @staticmethod
    def _offer(row: dict[str, Any]) -> OfferRecord:
        return OfferRecord(
            offer_id=row["offer_id"],
            token_ref=row["token_ref"],
            merchant_uid=row["merchant_uid"],
            merchant_name=row["merchant_name"],
            establishment_name=row["establishment_name"],
            product_id=row["product_id"],
            product_title=row["product_title"],
            original_amount_minor=int(row["original_amount_minor"]),
            discount_amount_minor=int(row["discount_amount_minor"]),
            final_amount_minor=int(row["final_amount_minor"]),
            currency=row["currency"],
            maximum_redemptions=int(row["maximum_redemptions"]),
            redeemed_count=int(row["redeemed_count"]),
            stock_quantity=int(row["stock_quantity"]),
            merchant_status=row["merchant_status"],
            product_status=row["product_status"],
            expires_at=int(row["expires_at"]),
            purpose=row["purpose"],
            status=row["status"],
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            discount_type=row["discount_type"],
            discount_value=int(row["discount_value"]),
        )

    @staticmethod
    def _offer_select() -> str:
        return """
            SELECT o.offer_id, o.token_ref, o.merchant_uid,
                   m.display_name AS merchant_name, m.establishment_name,
                   o.product_id, p.title AS product_title,
                   o.original_amount_minor, o.discount_type, o.discount_value,
                   o.discount_amount_minor, o.final_amount_minor,
                    o.currency, o.maximum_redemptions, o.redeemed_count,
                    p.stock_quantity, m.status AS merchant_status,
                    p.status AS product_status,
                   EXTRACT(EPOCH FROM o.expires_at)::BIGINT AS expires_at,
                   EXTRACT(EPOCH FROM o.created_at)::BIGINT AS created_at,
                   EXTRACT(EPOCH FROM o.updated_at)::BIGINT AS updated_at,
                   o.purpose, o.status
            FROM live_offers o
            JOIN merchant_accounts m ON m.firebase_uid = o.merchant_uid
            JOIN products p ON p.product_id = o.product_id
        """

    def create_live_offer(
        self,
        offer: OfferRecord,
        token: TokenRecord,
        *,
        discount_type: str,
        discount_value: int,
        **audit: Any,
    ) -> AuditRecord:
        envelope = CryptoEnvelope.from_dict(token.envelope)
        try:
            with self.pool.connection() as conn, conn.transaction():
                merchant = conn.execute(
                    "SELECT status FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                    (offer.merchant_uid,),
                ).fetchone()
                if not merchant or merchant["status"] != "ACTIVE":
                    raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
                product = conn.execute(
                    """
                    SELECT merchant_uid, price_minor, currency, stock_quantity, status
                    FROM products WHERE product_id = %s FOR UPDATE
                    """,
                    (offer.product_id,),
                ).fetchone()
                if (
                    not product
                    or product["merchant_uid"] != offer.merchant_uid
                    or product["status"] != "ACTIVE"
                ):
                    raise StoreConflict("PRODUCT_NOT_ACTIVE_OR_NOT_OWNED")
                if (
                    int(product["price_minor"]) != offer.original_amount_minor
                    or product["currency"] != offer.currency
                ):
                    raise StoreConflict("AUTHORITATIVE_PRODUCT_CHANGED")
                if int(product["stock_quantity"]) < offer.maximum_redemptions:
                    raise StoreConflict("OFFER_LIMIT_EXCEEDS_STOCK")
                conn.execute(
                    """
                    INSERT INTO live_offers
                      (offer_id, token_ref, merchant_uid, product_id, discount_type, discount_value,
                       original_amount_minor, discount_amount_minor, final_amount_minor, currency,
                       maximum_redemptions, expires_at, purpose, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s, %s)
                    """,
                    (
                        offer.offer_id,
                        offer.token_ref,
                        offer.merchant_uid,
                        offer.product_id,
                        discount_type,
                        discount_value,
                        offer.original_amount_minor,
                        offer.discount_amount_minor,
                        offer.final_amount_minor,
                        offer.currency,
                        offer.maximum_redemptions,
                        offer.expires_at,
                        offer.purpose,
                        offer.status,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO coupon_tokens
                      (token_ref, jti, issuer_uid, issuer_ref, coupon_id, offer_id,
                       intent_json, envelope_json, policy_version, expires_at, status, redeemed_operation_id)
                    VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s, to_timestamp(%s), %s, NULL)
                    """,
                    (
                        token.token_ref,
                        envelope.jti,
                        token.issuer_uid,
                        token.issuer_ref,
                        token.offer_id,
                        Jsonb(token.intent),
                        Jsonb(token.envelope),
                        envelope.policy_version,
                        token.expires_at,
                        token.status,
                    ),
                )
                return self._append_audit_conn(conn, **audit)
        except (LedgerError, StoreConflict):
            raise
        except Exception as exc:
            raise StoreConflict("LIVE_OFFER_CREATE_FAILED") from exc

    def get_offer_by_token(self, token_ref: str) -> OfferRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                self._offer_select() + " WHERE o.token_ref = %s",
                (token_ref,),
            ).fetchone()
        return self._offer(row) if row else None

    def expire_offer(self, token_ref: str, **audit: Any) -> None:
        with self.pool.connection() as conn, conn.transaction():
            keys = conn.execute(
                "SELECT merchant_uid, product_id, offer_id FROM live_offers WHERE token_ref = %s",
                (token_ref,),
            ).fetchone()
            if not keys:
                raise StoreNotFound("OFFER_NOT_FOUND")
            conn.execute(
                "SELECT firebase_uid FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                (keys["merchant_uid"],),
            )
            conn.execute(
                "SELECT product_id FROM products WHERE product_id = %s FOR UPDATE",
                (keys["product_id"],),
            )
            offer = conn.execute(
                "SELECT status, expires_at FROM live_offers WHERE offer_id = %s FOR UPDATE",
                (keys["offer_id"],),
            ).fetchone()
            if not offer:
                raise StoreNotFound("OFFER_NOT_FOUND")
            if offer["status"] == "EXPIRED":
                return
            if offer["status"] not in {"ACTIVE", "PAUSED"} or offer["expires_at"].timestamp() > time.time():
                return
            conn.execute(
                "UPDATE live_offers SET status = 'EXPIRED', updated_at = now() WHERE offer_id = %s",
                (keys["offer_id"],),
            )
            conn.execute(
                "UPDATE coupon_tokens SET status = 'EXPIRED' WHERE token_ref = %s AND status = 'ISSUED'",
                (token_ref,),
            )
            self._append_audit_conn(conn, **audit)

    def list_offers(self, uid: str) -> list[OfferRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                self._offer_select() + " WHERE o.merchant_uid = %s ORDER BY o.created_at DESC",
                (uid,),
            ).fetchall()
        return [self._offer(row) for row in rows]

    def get_visitor_purchases(self, uid: str, limit: int, offset: int) -> dict[str, Any]:
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            totals = conn.execute(
                """
                SELECT currency, COUNT(*)::INTEGER AS purchase_count,
                       COALESCE(SUM(quantity), 0)::BIGINT AS units_purchased,
                       COALESCE(SUM(final_amount_minor), 0)::BIGINT AS spent_amount_minor,
                       COALESCE(SUM(amount_saved_minor), 0)::BIGINT AS saved_amount_minor,
                       COUNT(*) FILTER (WHERE final_amount_minor IS NULL)::INTEGER
                           AS amounts_unavailable_count
                  FROM coupon_redemptions
                 WHERE buyer_uid = %s AND status = 'REDEEMED'
                 GROUP BY currency ORDER BY currency
                """,
                (uid,),
            ).fetchall()
            items = conn.execute(
                """
                SELECT r.redemption_id::TEXT, r.merchant_uid,
                       COALESCE(m.display_name, 'Empreendedor') AS merchant_name,
                       m.establishment_name, r.product_id,
                       COALESCE(p.title, 'Produto indisponível') AS product_title,
                       r.quantity, r.currency, r.original_amount_minor, r.final_amount_minor,
                       r.amount_saved_minor AS saved_amount_minor,
                       r.committed_at AS purchased_at
                  FROM coupon_redemptions r
                  LEFT JOIN merchant_accounts m ON m.firebase_uid = r.merchant_uid
                  LEFT JOIN products p ON p.product_id = r.product_id
                 WHERE r.buyer_uid = %s AND r.status = 'REDEEMED'
                 ORDER BY r.committed_at DESC, r.redemption_id DESC
                 LIMIT %s OFFSET %s
                """,
                (uid, limit, offset),
            ).fetchall()
        total_purchases = sum(row["purchase_count"] for row in totals)
        return {
            "total_purchases": total_purchases,
            "total_units": sum(row["units_purchased"] for row in totals),
            "totals": totals, "items": items, "limit": limit, "offset": offset,
            "has_more": offset + len(items) < total_purchases,
        }

    def revoke_offer(self, uid: str, offer_id: str, **audit: Any) -> OfferRecord:
        with self.pool.connection() as conn, conn.transaction():
            merchant = conn.execute(
                "SELECT status FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                (uid,),
            ).fetchone()
            if not merchant or merchant["status"] != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            current = conn.execute(
                """
                SELECT token_ref, status
                  FROM live_offers
                 WHERE offer_id = %s AND merchant_uid = %s
                 FOR UPDATE
                """,
                (offer_id, uid),
            ).fetchone()
            if current is None or current["status"] == "REVOKED":
                raise StoreNotFound("OFFER_NOT_FOUND")
            conn.execute(
                """
                UPDATE coupon_tokens
                   SET status = 'REVOKED'
                 WHERE token_ref = %s AND offer_id = %s AND status = 'ISSUED'
                """,
                (current["token_ref"], offer_id),
            )
            conn.execute(
                """
                UPDATE live_offers
                   SET status = 'REVOKED', updated_at = now()
                 WHERE offer_id = %s AND merchant_uid = %s
                """,
                (offer_id, uid),
            )
            self._append_audit_conn(conn, **audit)
            row = conn.execute(
                self._offer_select() + " WHERE o.offer_id = %s",
                (offer_id,),
            ).fetchone()
            if row is None:
                raise StoreNotFound("OFFER_NOT_FOUND")
            return self._offer(row)

    def get_offers_for_batch(
        self,
        uid: str,
        offer_ids: tuple[str, ...],
    ) -> list[OfferRecord]:
        if not offer_ids or len(set(offer_ids)) != len(offer_ids):
            raise StoreConflict("OFFER_BATCH_IDS_INVALID")
        with self.pool.connection() as conn:
            rows = conn.execute(
                self._offer_select()
                + """
                WHERE o.merchant_uid = %s AND o.offer_id = ANY(%s)
                  AND m.status = 'ACTIVE'
                  AND p.status = 'ACTIVE' AND p.stock_quantity > 0
                  AND o.status IN ('ACTIVE', 'PAUSED')
                  AND o.expires_at > now()
                  AND o.redeemed_count < o.maximum_redemptions
                  AND EXISTS (
                    SELECT 1 FROM coupon_tokens t
                     WHERE t.token_ref = o.token_ref AND t.offer_id = o.offer_id
                       AND t.status = 'ISSUED' AND t.expires_at > now()
                  )
                """,
                (uid, list(offer_ids)),
            ).fetchall()
        if len(rows) != len(offer_ids):
            raise StoreNotFound("OFFER_BATCH_NOT_FOUND_OR_FINAL")
        by_id = {row["offer_id"]: self._offer(row) for row in rows}
        return [by_id[offer_id] for offer_id in offer_ids]

    @staticmethod
    def _lock_batch_offer_rows_conn(conn, uid: str, offer_ids: tuple[str, ...]):
        merchant = conn.execute(
            "SELECT status FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
            (uid,),
        ).fetchone()
        if not merchant or merchant["status"] != "ACTIVE":
            raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
        rows = conn.execute(
            """
            SELECT o.*, p.price_minor AS product_price_minor,
                   p.currency AS product_currency, p.stock_quantity,
                   p.status AS product_status,
                   t.status AS token_status,
                   EXTRACT(EPOCH FROM t.expires_at)::BIGINT AS token_expires_at
              FROM live_offers o
              JOIN products p ON p.product_id = o.product_id
              JOIN coupon_tokens t
                ON t.token_ref = o.token_ref AND t.offer_id = o.offer_id
             WHERE o.merchant_uid = %s AND o.offer_id = ANY(%s)
             ORDER BY o.offer_id
             FOR UPDATE OF o, p, t
            """,
            (uid, list(offer_ids)),
        ).fetchall()
        now = int(time.time())
        if len(rows) != len(offer_ids):
            raise StoreNotFound("OFFER_BATCH_NOT_FOUND_OR_FINAL")
        for row in rows:
            if (
                row["status"] not in {"ACTIVE", "PAUSED"}
                or int(row["expires_at"].timestamp()) <= now
                or row["token_status"] != "ISSUED"
                or int(row["token_expires_at"]) <= now
                or row["product_status"] != "ACTIVE"
                or int(row["stock_quantity"]) <= 0
                or int(row["redeemed_count"]) >= int(row["maximum_redemptions"])
                or int(row["product_price_minor"]) != int(row["original_amount_minor"])
                or row["product_currency"] != row["currency"]
            ):
                raise StoreNotFound("OFFER_BATCH_NOT_FOUND_OR_FINAL")
        return rows

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
        if not offer_ids or len(set(offer_ids)) != len(offer_ids):
            raise StoreConflict("OFFER_BATCH_IDS_INVALID")
        with self.pool.connection() as conn, conn.transaction():
            prior = self._claim_marketplace_batch_conn(
                conn,
                uid=uid,
                client_request_id=client_request_id,
                operation_kind=operation_kind,
                command_hash=command_hash,
                operation_id=batch_operation_id,
            )
            if prior is not None:
                return prior
            rows = self._lock_batch_offer_rows_conn(conn, uid, offer_ids)
            token_refs = [row["token_ref"] for row in rows]
            revoked_tokens = conn.execute(
                """
                UPDATE coupon_tokens SET status = 'REVOKED'
                 WHERE token_ref = ANY(%s) AND status = 'ISSUED'
                RETURNING token_ref
                """,
                (token_refs,),
            ).fetchall()
            if len(revoked_tokens) != len(token_refs):
                raise StoreConflict("OFFER_BATCH_TOKEN_CHANGED")
            updated_rows = conn.execute(
                """
                UPDATE live_offers SET status = 'REVOKED', updated_at = now()
                 WHERE offer_id = ANY(%s) AND merchant_uid = %s
                   AND status IN ('ACTIVE', 'PAUSED')
                RETURNING offer_id
                """,
                (list(offer_ids), uid),
            ).fetchall()
            if len(updated_rows) != len(offer_ids):
                raise StoreConflict("OFFER_BATCH_CHANGED_RETRY")
            self._append_audit_conn(conn, **audit)
            result_rows = conn.execute(
                self._offer_select() + " WHERE o.offer_id = ANY(%s)",
                (list(offer_ids),),
            ).fetchall()
            by_id = {row["offer_id"]: self._offer(row) for row in result_rows}
            offers = [by_id[offer_id] for offer_id in offer_ids]
            response = response_factory(offers)
            self._complete_marketplace_batch_conn(
                conn,
                uid=uid,
                client_request_id=client_request_id,
                response=response,
            )
            return response

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
        offer_ids = tuple(mutation.offer_id for mutation in mutations)
        if not offer_ids or len(set(offer_ids)) != len(offer_ids):
            raise StoreConflict("OFFER_BATCH_IDS_INVALID")
        mutation_by_id = {mutation.offer_id: mutation for mutation in mutations}
        with self.pool.connection() as conn, conn.transaction():
            prior = self._claim_marketplace_batch_conn(
                conn,
                uid=uid,
                client_request_id=client_request_id,
                operation_kind=operation_kind,
                command_hash=command_hash,
                operation_id=batch_operation_id,
            )
            if prior is not None:
                return prior
            rows = self._lock_batch_offer_rows_conn(conn, uid, offer_ids)
            for row in rows:
                mutation = mutation_by_id[row["offer_id"]]
                current_expires_at = int(row["expires_at"].timestamp())
                if (
                    row["token_ref"] != mutation.expected_token_ref
                    or row["discount_type"] != mutation.expected_discount_type
                    or int(row["discount_value"]) != mutation.expected_discount_value
                    or current_expires_at != mutation.expected_expires_at
                ):
                    raise StoreConflict("OFFER_BATCH_CHANGED_RETRY")
                price_minor = int(row["product_price_minor"])
                if mutation.new_discount_type == "PERCENT":
                    expected_discount_amount = (
                        price_minor * mutation.new_discount_value // 100
                    )
                    valid_discount = 1 <= mutation.new_discount_value <= 90
                elif mutation.new_discount_type == "FIXED_AMOUNT":
                    expected_discount_amount = mutation.new_discount_value
                    valid_discount = mutation.new_discount_value > 0
                else:
                    raise StoreConflict("OFFER_BATCH_DISCOUNT_INVALID")
                if (
                    mutation.new_discount_type != row["discount_type"]
                    or not valid_discount
                    or expected_discount_amount <= 0
                    or expected_discount_amount >= price_minor
                    or mutation.new_discount_amount_minor != expected_discount_amount
                    or mutation.new_final_amount_minor
                    != price_minor - expected_discount_amount
                    or mutation.new_expires_at <= int(time.time())
                ):
                    raise StoreConflict("OFFER_BATCH_DISCOUNT_INVALID")
                token = mutation.new_token
                envelope = CryptoEnvelope.from_dict(token.envelope)
                if (
                    token.offer_id != mutation.offer_id
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
                revoked = conn.execute(
                    """
                    UPDATE coupon_tokens SET status = 'REVOKED'
                     WHERE token_ref = %s AND offer_id = %s AND status = 'ISSUED'
                    RETURNING token_ref
                    """,
                    (mutation.expected_token_ref, mutation.offer_id),
                ).fetchone()
                if revoked is None:
                    raise StoreConflict("OFFER_BATCH_TOKEN_CHANGED")
                conn.execute(
                    """
                    INSERT INTO coupon_tokens
                      (token_ref, jti, issuer_uid, issuer_ref, coupon_id, offer_id,
                       intent_json, envelope_json, policy_version, expires_at,
                       status, redeemed_operation_id)
                    VALUES (%s, %s, %s, %s, NULL, %s, %s, %s, %s,
                            to_timestamp(%s), 'ISSUED', NULL)
                    """,
                    (
                        token.token_ref,
                        envelope.jti,
                        token.issuer_uid,
                        token.issuer_ref,
                        token.offer_id,
                        Jsonb(token.intent),
                        Jsonb(token.envelope),
                        envelope.policy_version,
                        token.expires_at,
                    ),
                )
                updated = conn.execute(
                    """
                    UPDATE live_offers
                       SET token_ref = %s, discount_type = %s, discount_value = %s,
                           discount_amount_minor = %s, final_amount_minor = %s,
                           expires_at = to_timestamp(%s), updated_at = now()
                     WHERE offer_id = %s AND merchant_uid = %s
                       AND token_ref = %s AND status IN ('ACTIVE', 'PAUSED')
                    RETURNING offer_id
                    """,
                    (
                        token.token_ref,
                        mutation.new_discount_type,
                        mutation.new_discount_value,
                        mutation.new_discount_amount_minor,
                        mutation.new_final_amount_minor,
                        mutation.new_expires_at,
                        mutation.offer_id,
                        uid,
                        mutation.expected_token_ref,
                    ),
                ).fetchone()
                if updated is None:
                    raise StoreConflict("OFFER_BATCH_CHANGED_RETRY")
            self._append_audit_conn(conn, **audit)
            result_rows = conn.execute(
                self._offer_select() + " WHERE o.offer_id = ANY(%s)",
                (list(offer_ids),),
            ).fetchall()
            by_id = {row["offer_id"]: self._offer(row) for row in result_rows}
            offers = [by_id[offer_id] for offer_id in offer_ids]
            response = response_factory(offers)
            self._complete_marketplace_batch_conn(
                conn,
                uid=uid,
                client_request_id=client_request_id,
                response=response,
            )
            return response

    def update_offer_status(
        self,
        uid: str,
        offer_id: str,
        status: str,
        **audit: Any,
    ) -> OfferRecord:
        expired = False
        with self.pool.connection() as conn, conn.transaction():
            merchant = conn.execute(
                "SELECT status FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                (uid,),
            ).fetchone()
            if not merchant or merchant["status"] != "ACTIVE":
                raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
            keys = conn.execute(
                "SELECT product_id FROM live_offers WHERE offer_id = %s AND merchant_uid = %s",
                (offer_id, uid),
            ).fetchone()
            if not keys:
                raise StoreNotFound("OFFER_NOT_FOUND_OR_FINAL")
            conn.execute(
                "SELECT product_id FROM products WHERE product_id = %s FOR UPDATE",
                (keys["product_id"],),
            )
            current = conn.execute(
                "SELECT token_ref, product_id, expires_at, status FROM live_offers WHERE offer_id = %s AND merchant_uid = %s FOR UPDATE",
                (offer_id, uid),
            ).fetchone()
            if (
                not current
                or current["product_id"] != keys["product_id"]
                or current["status"] in {"EXHAUSTED", "EXPIRED", "REVOKED", "CANCELLED"}
            ):
                raise StoreNotFound("OFFER_NOT_FOUND_OR_FINAL")
            if current["expires_at"].timestamp() <= time.time():
                conn.execute(
                    "UPDATE live_offers SET status = 'EXPIRED', updated_at = now() WHERE offer_id = %s",
                    (offer_id,),
                )
                conn.execute(
                    "UPDATE coupon_tokens SET status = 'EXPIRED' WHERE offer_id = %s AND status = 'ISSUED'",
                    (offer_id,),
                )
                expiry_audit = {
                    **audit,
                    "event_type": "OFFER_EXPIRED",
                    "result": "EXPIRED",
                    "reason_codes": ("OFFER_EXPIRED",),
                }
                self._append_audit_conn(conn, **expiry_audit)
                expired = True
            else:
                conn.execute(
                """
                UPDATE live_offers SET status = %s, updated_at = now()
                WHERE offer_id = %s AND merchant_uid = %s
                """,
                (status, offer_id, uid),
                )
                if status == "CANCELLED":
                    conn.execute(
                        "UPDATE coupon_tokens SET status = 'REVOKED' WHERE offer_id = %s AND status = 'ISSUED'",
                        (offer_id,),
                    )
                self._append_audit_conn(conn, **audit)
            row = conn.execute(
                self._offer_select() + " WHERE o.offer_id = %s",
                (offer_id,),
            ).fetchone()
            if row is None:
                raise StoreNotFound("OFFER_NOT_FOUND_OR_FINAL")
            offer = self._offer(row)
        if expired:
            raise StoreConflict("OFFER_EXPIRED")
        return offer

    def store_token(self, token: TokenRecord) -> None:
        envelope = CryptoEnvelope.from_dict(token.envelope)
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO coupon_tokens
                  (token_ref, jti, issuer_uid, issuer_ref, coupon_id, offer_id, intent_json, envelope_json,
                   policy_version, expires_at, status, redeemed_operation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s, %s)
                """,
                (
                    token.token_ref,
                    envelope.jti,
                    token.issuer_uid,
                    token.issuer_ref,
                    token.coupon_id,
                    token.offer_id,
                    Jsonb(token.intent),
                    Jsonb(token.envelope),
                    envelope.policy_version,
                    token.expires_at,
                    token.status,
                    token.redeemed_operation_id,
                ),
            )

    def get_token(self, token_ref: str) -> TokenRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT token_ref, issuer_uid, issuer_ref, coupon_id, offer_id, intent_json AS intent,
                       envelope_json AS envelope, EXTRACT(EPOCH FROM expires_at)::BIGINT AS expires_at,
                       status, redeemed_operation_id
                FROM coupon_tokens WHERE token_ref = %s
                """,
                (token_ref,),
            ).fetchone()
        return TokenRecord(**row) if row else None

    def create_operation(self, operation: OperationRecord, **audit: Any) -> None:
        with self.pool.connection() as conn, conn.transaction():
            token = conn.execute(
                "SELECT offer_id, status, expires_at FROM coupon_tokens WHERE token_ref = %s",
                (operation.token_ref,),
            ).fetchone()
            if not token or token["status"] != "ISSUED" or token["expires_at"].timestamp() <= time.time():
                raise StoreConflict("TOKEN_NOT_REDEEMABLE")
            if token["offer_id"]:
                keys = conn.execute(
                    "SELECT merchant_uid, product_id FROM live_offers WHERE offer_id = %s",
                    (token["offer_id"],),
                ).fetchone()
                if not keys:
                    raise StoreConflict("OFFER_NOT_FOUND")
                merchant = conn.execute(
                    "SELECT status FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                    (keys["merchant_uid"],),
                ).fetchone()
                product = conn.execute(
                    "SELECT status, stock_quantity FROM products WHERE product_id = %s FOR UPDATE",
                    (keys["product_id"],),
                ).fetchone()
                offer = conn.execute(
                    "SELECT status, expires_at, redeemed_count, maximum_redemptions FROM live_offers WHERE offer_id = %s FOR UPDATE",
                    (token["offer_id"],),
                ).fetchone()
                token = conn.execute(
                    "SELECT offer_id, status, expires_at FROM coupon_tokens WHERE token_ref = %s FOR UPDATE",
                    (operation.token_ref,),
                ).fetchone()
                if not merchant or merchant["status"] != "ACTIVE":
                    raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
                if not product or product["status"] != "ACTIVE" or int(product["stock_quantity"]) <= 0:
                    raise StoreConflict("PRODUCT_NOT_ACTIVE_OR_OUT_OF_STOCK")
                if (
                    not offer
                    or offer["status"] != "ACTIVE"
                    or offer["expires_at"].timestamp() <= time.time()
                    or int(offer["redeemed_count"]) >= int(offer["maximum_redemptions"])
                ):
                    raise StoreConflict("OFFER_NOT_ACTIVE")
                if not token or token["status"] != "ISSUED":
                    raise StoreConflict("TOKEN_NOT_REDEEMABLE")
            conn.execute(
                """
                INSERT INTO redemption_operations
                  (operation_id, firebase_uid, session_id, token_ref, device_key_id,
                   challenge_id, replay_jti, expires_at, status, result_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, to_timestamp(%s), %s, %s)
                """,
                (
                    operation.operation_id,
                    operation.firebase_uid,
                    operation.session_id,
                    operation.token_ref,
                    operation.device_key_id,
                    operation.challenge_id,
                    operation.replay_jti,
                    operation.expires_at,
                    operation.status,
                    Jsonb(operation.result) if operation.result else None,
                ),
            )
            self._append_audit_conn(conn, **audit)

    def get_operation(self, operation_id: str) -> OperationRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT operation_id, firebase_uid, session_id, token_ref, device_key_id,
                       challenge_id, replay_jti, EXTRACT(EPOCH FROM expires_at)::BIGINT AS expires_at,
                       status, result_json AS result
                FROM redemption_operations WHERE operation_id = %s
                """,
                (operation_id,),
            ).fetchone()
        return OperationRecord(**row) if row else None

    def _append_audit_conn(
        self,
        conn,
        *,
        operation_id: str,
        suite_id: str,
        key_ref_token: str,
        event_type: str,
        result: str,
        reason_codes: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        details = details or {}
        _validate_sanitized(details)
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (AUDIT_LOCK_ID,))
        previous = conn.execute(
            "SELECT seq, event_hash FROM audit_events ORDER BY seq DESC LIMIT 1",
        ).fetchone()
        seq = int(previous["seq"]) + 1 if previous else 1
        prev_hash = previous["event_hash"] if previous else ZERO_HASH
        event_id = str(uuid.uuid4())
        body = {
            "event_id": event_id,
            "seq": seq,
            "operation_id": operation_id,
            "suite_id": suite_id,
            "key_ref_token": key_ref_token,
            "event_type": event_type,
            "result": result,
            "reason_codes": list(reason_codes),
            "evidence_refs": list(evidence_refs),
            "details": details,
            "prev_hash": prev_hash,
        }
        event_hash = sha3_hex(body, "TRQ-BEC/audit/v1")
        conn.execute(
            """
            INSERT INTO audit_events
              (seq, event_id, operation_id, suite_id, key_ref_token, event_type, result,
               reason_codes, evidence_refs, details_json, prev_hash, event_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                seq,
                event_id,
                operation_id,
                suite_id,
                key_ref_token,
                event_type,
                result,
                Jsonb(list(reason_codes)),
                Jsonb(list(evidence_refs)),
                Jsonb(details),
                prev_hash,
                event_hash,
            ),
        )
        return AuditRecord(event_id=f"event:{event_id}", seq=seq, event_hash=event_hash)

    def append_audit(self, **kwargs: Any) -> AuditRecord:
        try:
            with self.pool.connection() as conn, conn.transaction():
                return self._append_audit_conn(conn, **kwargs)
        except Exception as exc:
            raise LedgerError("POSTGRES_LEDGER_APPEND_FAILED") from exc

    def finalize_authorization(
        self,
        operation_id: str,
        token_ref: str,
        decision: str,
        result: dict[str, Any],
        **audit: Any,
    ) -> tuple[AuditRecord, dict[str, Any]]:
        with self.pool.connection() as conn, conn.transaction():
            operation = conn.execute(
                "SELECT status, result_json, firebase_uid, device_key_id FROM redemption_operations WHERE operation_id = %s FOR UPDATE",
                (operation_id,),
            ).fetchone()
            if not operation:
                raise StoreNotFound("OPERATION_NOT_FOUND")
            if operation["status"] != "PENDING":
                raise StoreConflict("OPERATION_ALREADY_COMPLETED")

            status = {
                "ALLOW": "COMPLETED",
                "STEP_UP": "STEP_UP_REQUIRED",
                "HOLD_OR_REVIEW": "HELD",
                "DENY": "DENIED",
            }[decision]

            token = conn.execute(
                "SELECT coupon_id, offer_id, status FROM coupon_tokens WHERE token_ref = %s",
                (token_ref,),
            ).fetchone()
            if not token:
                raise StoreNotFound("TOKEN_NOT_FOUND")

            result_with_commit = dict(result)
            pending_context = operation["result_json"] or {}
            if not isinstance(pending_context, dict):
                raise StoreConflict("OFFER_QR_QUANTITY_INVALID")
            try:
                purchase_quantity = int(pending_context.get("purchase_quantity", 1))
            except (TypeError, ValueError) as exc:
                raise StoreConflict("OFFER_QR_QUANTITY_INVALID") from exc
            if purchase_quantity < 1 or purchase_quantity > 1_000:
                raise StoreConflict("OFFER_QR_QUANTITY_INVALID")
            pending_redemption: dict[str, Any] | None = None
            if decision == "ALLOW" and token["offer_id"]:
                keys = conn.execute(
                    "SELECT merchant_uid, product_id FROM live_offers WHERE offer_id = %s",
                    (token["offer_id"],),
                ).fetchone()
                if not keys:
                    raise StoreConflict("OFFER_NOT_FOUND")
                # Ordem global: merchant -> produto -> oferta -> token.
                # Cancelamento, estoque, suspensão e resgate usam a mesma ordem.
                conn.execute(
                    "SELECT firebase_uid FROM merchant_accounts WHERE firebase_uid = %s FOR UPDATE",
                    (keys["merchant_uid"],),
                )
                conn.execute(
                    "SELECT product_id FROM products WHERE product_id = %s FOR UPDATE",
                    (keys["product_id"],),
                )
                offer = conn.execute(
                    """
                    SELECT o.*, p.stock_quantity, p.status AS product_status,
                           m.status AS merchant_status
                    FROM live_offers o
                    JOIN products p ON p.product_id = o.product_id
                    JOIN merchant_accounts m ON m.firebase_uid = o.merchant_uid
                    WHERE o.offer_id = %s
                    FOR UPDATE OF o
                    """,
                    (token["offer_id"],),
                ).fetchone()
                if not offer:
                    raise StoreConflict("OFFER_NOT_FOUND")
                token = conn.execute(
                    "SELECT coupon_id, offer_id, status FROM coupon_tokens WHERE token_ref = %s FOR UPDATE",
                    (token_ref,),
                ).fetchone()
                if not token or token["offer_id"] != offer["offer_id"]:
                    raise StoreConflict("TOKEN_NOT_REDEEMABLE")
                if token["status"] != "ISSUED":
                    raise StoreConflict("TOKEN_NOT_REDEEMABLE")
                if offer["merchant_status"] != "ACTIVE":
                    raise StoreConflict("MERCHANT_ACCOUNT_INACTIVE")
                if offer["status"] != "ACTIVE":
                    raise StoreConflict("OFFER_NOT_ACTIVE")
                if offer["expires_at"].timestamp() <= time.time():
                    conn.execute("UPDATE live_offers SET status = 'EXPIRED' WHERE offer_id = %s", (offer["offer_id"],))
                    conn.execute("UPDATE coupon_tokens SET status = 'EXPIRED' WHERE token_ref = %s", (token_ref,))
                    raise StoreConflict("OFFER_EXPIRED")
                if int(offer["redeemed_count"]) >= int(offer["maximum_redemptions"]):
                    raise StoreConflict("OFFER_REDEMPTION_LIMIT_REACHED")
                if offer["product_status"] != "ACTIVE" or int(offer["stock_quantity"]) <= 0:
                    raise StoreConflict("PRODUCT_OUT_OF_STOCK")
                available = min(
                    int(offer["maximum_redemptions"]) - int(offer["redeemed_count"]),
                    int(offer["stock_quantity"]),
                )
                if purchase_quantity > available:
                    raise StoreConflict("OFFER_QR_QUANTITY_EXCEEDS_AVAILABLE")
                prior = conn.execute(
                    "SELECT 1 FROM coupon_redemptions WHERE offer_id = %s AND buyer_uid = %s",
                    (offer["offer_id"], operation["firebase_uid"]),
                ).fetchone()
                if prior:
                    raise StoreConflict("OFFER_ALREADY_REDEEMED_BY_USER")

                new_redeemed = int(offer["redeemed_count"]) + purchase_quantity
                new_stock = int(offer["stock_quantity"]) - purchase_quantity
                exhausted = new_redeemed >= int(offer["maximum_redemptions"]) or new_stock == 0
                conn.execute(
                    "UPDATE products SET stock_quantity = %s, updated_at = now() WHERE product_id = %s",
                    (new_stock, offer["product_id"]),
                )
                conn.execute(
                    "UPDATE live_offers SET redeemed_count = %s, status = %s, updated_at = now() WHERE offer_id = %s",
                    (new_redeemed, "EXHAUSTED" if exhausted else "ACTIVE", offer["offer_id"]),
                )
                if exhausted:
                    conn.execute(
                        "UPDATE coupon_tokens SET status = 'REDEEMED', redeemed_at = now(), redeemed_operation_id = %s WHERE token_ref = %s",
                        (operation_id, token_ref),
                    )
                remaining = max(0, min(int(offer["maximum_redemptions"]) - new_redeemed, new_stock))
                result_with_commit.update(
                    {
                        "coupon_id": offer["offer_id"],
                        "offer_id": offer["offer_id"],
                        "product_id": offer["product_id"],
                        "amount_saved_minor": int(offer["discount_amount_minor"]) * purchase_quantity,
                        "final_amount_minor": int(offer["final_amount_minor"]) * purchase_quantity,
                        "remaining_redemptions": remaining,
                        "quantity": purchase_quantity,
                    }
                )
                details = dict(audit.get("details") or {})
                audit["details"] = {
                    **details,
                    "offer_id": offer["offer_id"],
                    "product_id": offer["product_id"],
                    "amount_saved_minor": int(offer["discount_amount_minor"]) * purchase_quantity,
                    "remaining_redemptions": remaining,
                    "quantity": purchase_quantity,
                }
                pending_redemption = {
                    "redemption_id": str(uuid.uuid4()),
                    "offer_id": offer["offer_id"],
                    "merchant_uid": offer["merchant_uid"],
                    "product_id": offer["product_id"],
                    "buyer_uid": operation["firebase_uid"],
                    "device_key_id": operation["device_key_id"],
                    "amount_saved_minor": int(offer["discount_amount_minor"]) * purchase_quantity,
                    "original_amount_minor": int(offer["original_amount_minor"]) * purchase_quantity,
                    "final_amount_minor": int(offer["final_amount_minor"]) * purchase_quantity,
                    "currency": offer["currency"],
                    "quantity": purchase_quantity,
                }
            elif decision == "ALLOW":
                token = conn.execute(
                    "SELECT coupon_id, offer_id, status FROM coupon_tokens WHERE token_ref = %s FOR UPDATE",
                    (token_ref,),
                ).fetchone()
                updated = conn.execute(
                    """
                    UPDATE coupon_tokens
                    SET status = 'REDEEMED', redeemed_at = now(), redeemed_operation_id = %s
                    WHERE token_ref = %s AND status = 'ISSUED' AND expires_at > now()
                    RETURNING token_ref
                    """,
                    (operation_id, token_ref),
                ).fetchone()
                if not updated:
                    raise StoreConflict("TOKEN_ALREADY_USED_OR_EXPIRED")
            elif decision == "HOLD_OR_REVIEW" and token["coupon_id"]:
                conn.execute(
                    "UPDATE coupon_tokens SET status = 'HELD', redeemed_operation_id = %s WHERE token_ref = %s AND status = 'ISSUED'",
                    (operation_id, token_ref),
                )

            event = self._append_audit_conn(conn, operation_id=operation_id, result=decision, **audit)
            result_with_event = {**result_with_commit, "event_ref": event.event_id}
            if pending_redemption is not None:
                conn.execute(
                    """
                    INSERT INTO coupon_redemptions
                      (redemption_id, offer_id, buyer_uid, device_key_id, operation_id,
                       status, amount_saved_minor, ledger_event_id, merchant_uid,
                       product_id, original_amount_minor, final_amount_minor,
                       currency, quantity, snapshot_quality)
                    VALUES (%s, %s, %s, %s, %s, 'REDEEMED', %s, %s,
                            %s, %s, %s, %s, %s, %s, 'CURRENT')
                    """,
                    (
                        pending_redemption["redemption_id"],
                        pending_redemption["offer_id"],
                        pending_redemption["buyer_uid"],
                        pending_redemption["device_key_id"],
                        operation_id,
                        pending_redemption["amount_saved_minor"],
                        event.event_id,
                        pending_redemption["merchant_uid"],
                        pending_redemption["product_id"],
                        pending_redemption["original_amount_minor"],
                        pending_redemption["final_amount_minor"],
                        pending_redemption["currency"],
                        pending_redemption["quantity"],
                    ),
                )
            conn.execute(
                """
                UPDATE redemption_operations
                SET status = %s, result_json = %s, completed_at = now()
                WHERE operation_id = %s
                """,
                (status, Jsonb(result_with_event), operation_id),
            )
            return event, result_with_event

    @staticmethod
    def _public_profile(row: dict[str, Any]) -> PublicProfileRecord:
        return PublicProfileRecord(
            firebase_uid=row["firebase_uid"],
            display_name=row["display_name"],
            normalized_name=row["normalized_name"],
            role=row["role"],
            city=row["city"],
            address=row["address"],
            category=row["category"],
            interests=tuple(row["interests"] or ()),
            avatar_uri=row["avatar_uri"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def upsert_public_profile(self, profile: PublicProfileRecord) -> PublicProfileRecord:
        try:
            with self.pool.connection() as conn, conn.transaction():
                row = conn.execute(
                    """
                    INSERT INTO public_profile_directory
                      (firebase_uid, display_name, normalized_name, role, city,
                       address, category, interests, avatar_uri, created_at, updated_at)
                    SELECT a.firebase_uid, %s, %s, a.role, %s, %s, %s, %s, %s, %s, %s
                      FROM access_accounts a
                     WHERE a.firebase_uid = %s
                       AND a.status = 'ACTIVE'
                       AND a.role IN ('visitor', 'entrepreneur', 'institution')
                       AND a.role = %s
                    ON CONFLICT (firebase_uid) DO UPDATE SET
                      display_name = EXCLUDED.display_name,
                      normalized_name = EXCLUDED.normalized_name,
                      role = EXCLUDED.role,
                      city = EXCLUDED.city,
                      address = EXCLUDED.address,
                      category = EXCLUDED.category,
                      interests = EXCLUDED.interests,
                      avatar_uri = EXCLUDED.avatar_uri,
                      updated_at = EXCLUDED.updated_at
                    RETURNING *
                    """,
                    (
                        profile.display_name,
                        profile.normalized_name,
                        profile.city,
                        profile.address,
                        profile.category,
                        Jsonb(list(profile.interests)),
                        profile.avatar_uri,
                        profile.created_at,
                        profile.updated_at,
                        profile.firebase_uid,
                        profile.role,
                    ),
                ).fetchone()
                if row is None:
                    raise StoreConflict("PUBLIC_PROFILE_ACCOUNT_NOT_ELIGIBLE")
        except UniqueViolation as exc:
            raise StoreConflict("DISPLAY_NAME_ALREADY_IN_USE") from exc
        return self._public_profile(row)

    def get_public_profile(self, uid: str) -> PublicProfileRecord | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                SELECT p.*
                  FROM public_profile_directory p
                  JOIN access_accounts a USING (firebase_uid)
                 WHERE p.firebase_uid = %s
                   AND a.status = 'ACTIVE'
                   AND a.role = p.role
                   AND p.role IN ('visitor', 'entrepreneur', 'institution')
                """,
                (uid,),
            ).fetchone()
        return self._public_profile(row) if row else None

    def search_directory(
        self,
        query: str,
        types: tuple[str, ...],
        limit: int,
    ) -> list[GlobalSearchItemRecord]:
        bounded_limit = max(1, min(int(limit), 50))
        pattern = f"%{query}%"
        items: list[GlobalSearchItemRecord] = []
        with self.pool.connection() as conn:
            if "PROFILE" in types:
                rows = conn.execute(
                    """
                    SELECT p.firebase_uid AS item_id, p.display_name AS title,
                           concat_ws(' · ', nullif(p.category, ''), p.city) AS subtitle,
                           p.firebase_uid AS owner_uid, p.role AS status, p.updated_at AS created_at
                      FROM public_profile_directory p
                      JOIN access_accounts a USING (firebase_uid)
                     WHERE a.status = 'ACTIVE' AND a.role = p.role
                       AND p.role IN ('visitor', 'entrepreneur', 'institution')
                       AND (p.normalized_name LIKE %s
                            OR trim(regexp_replace(lower(unaccent(p.city)), '[^a-z0-9]+', ' ', 'g')) LIKE %s
                            OR trim(regexp_replace(lower(unaccent(p.category)), '[^a-z0-9]+', ' ', 'g')) LIKE %s)
                     ORDER BY p.updated_at DESC
                     LIMIT %s
                    """,
                    (pattern, pattern, pattern, bounded_limit),
                ).fetchall()
                items.extend(
                    GlobalSearchItemRecord(
                        type="PROFILE",
                        item_id=row["item_id"],
                        title=row["title"],
                        subtitle=row["subtitle"] or None,
                        owner_uid=row["owner_uid"],
                        route=f"/profile/{row['owner_uid']}",
                        status=row["status"],
                        created_at=row["created_at"],
                    )
                    for row in rows
                )
            if "PRODUCT" in types:
                rows = conn.execute(
                    """
                    SELECT p.product_id AS item_id, p.title,
                           concat_ws(' · ', m.display_name, p.description) AS subtitle,
                           p.merchant_uid AS owner_uid, p.status, p.created_at
                      FROM products p
                      JOIN merchant_accounts m ON m.firebase_uid = p.merchant_uid
                      JOIN access_accounts a ON a.firebase_uid = p.merchant_uid
                     WHERE a.status = 'ACTIVE' AND m.status = 'ACTIVE'
                       AND p.status = 'ACTIVE' AND p.stock_quantity > 0
                       AND trim(regexp_replace(
                             lower(unaccent(concat_ws(' ', p.title, p.description, m.display_name))),
                             '[^a-z0-9]+', ' ', 'g'
                           )) LIKE %s
                     ORDER BY p.created_at DESC
                     LIMIT %s
                    """,
                    (pattern, bounded_limit),
                ).fetchall()
                items.extend(
                    GlobalSearchItemRecord(
                        type="PRODUCT", item_id=row["item_id"], title=row["title"],
                        subtitle=row["subtitle"] or None, owner_uid=row["owner_uid"],
                        route=f"/profile/{row['owner_uid']}?product={row['item_id']}",
                        status=row["status"], created_at=row["created_at"],
                    )
                    for row in rows
                )
            if "OFFER" in types:
                rows = conn.execute(
                    """
                    SELECT o.offer_id AS item_id, p.title,
                           concat_ws(' · ', m.display_name, m.establishment_name) AS subtitle,
                           o.merchant_uid AS owner_uid, o.status, o.created_at
                      FROM live_offers o
                      JOIN products p ON p.product_id = o.product_id
                      JOIN merchant_accounts m ON m.firebase_uid = o.merchant_uid
                      JOIN access_accounts a ON a.firebase_uid = o.merchant_uid
                      JOIN coupon_tokens t ON t.offer_id = o.offer_id AND t.token_ref = o.token_ref
                     WHERE a.status = 'ACTIVE' AND m.status = 'ACTIVE'
                       AND p.status = 'ACTIVE' AND p.stock_quantity > 0
                       AND o.status = 'ACTIVE' AND o.starts_at <= now() AND o.expires_at > now()
                       AND o.redeemed_count < o.maximum_redemptions
                       AND t.status = 'ISSUED' AND t.expires_at > now()
                       AND trim(regexp_replace(
                             lower(unaccent(concat_ws(' ', p.title, m.display_name, m.establishment_name))),
                             '[^a-z0-9]+', ' ', 'g'
                           )) LIKE %s
                     ORDER BY o.created_at DESC
                     LIMIT %s
                    """,
                    (pattern, bounded_limit),
                ).fetchall()
                items.extend(
                    GlobalSearchItemRecord(
                        type="OFFER", item_id=row["item_id"], title=row["title"],
                        subtitle=row["subtitle"] or None, owner_uid=row["owner_uid"],
                        route=f"/profile/{row['owner_uid']}?offer={row['item_id']}",
                        status=row["status"], created_at=row["created_at"],
                    )
                    for row in rows
                )
            if "POST" in types:
                rows = conn.execute(
                    """
                    SELECT s.post_id AS item_id, s.body AS title,
                           p.display_name AS subtitle, s.author_uid AS owner_uid,
                           'ACTIVE' AS status, s.created_at
                      FROM community_post_search s
                      JOIN public_profile_directory p ON p.firebase_uid = s.author_uid
                      JOIN access_accounts a ON a.firebase_uid = s.author_uid
                     WHERE s.active = TRUE AND a.status = 'ACTIVE'
                       AND trim(regexp_replace(
                             lower(unaccent(concat_ws(' ', s.body, p.display_name))),
                             '[^a-z0-9]+', ' ', 'g'
                           )) LIKE %s
                     ORDER BY s.created_at DESC
                     LIMIT %s
                    """,
                    (pattern, bounded_limit),
                ).fetchall()
                items.extend(
                    GlobalSearchItemRecord(
                        type="POST", item_id=row["item_id"], title=row["title"],
                        subtitle=row["subtitle"], owner_uid=row["owner_uid"],
                        route=f"/feed?post={row['item_id']}", status=row["status"],
                        created_at=row["created_at"],
                    )
                    for row in rows
                )
        items.sort(
            key=lambda item: item.created_at
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return items[:bounded_limit]

    def index_community_post(
        self,
        post_id: str,
        author_uid: str,
        body: str,
        created_at: datetime,
    ) -> None:
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO community_post_search (post_id, author_uid, body, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (post_id) DO UPDATE SET
                  body = EXCLUDED.body, active = TRUE
                """,
                (post_id, author_uid, body, created_at),
            )

    def update_community_post(
        self,
        post_id: str,
        author_uid: str,
        body: str,
    ) -> None:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                UPDATE community_post_search
                   SET body = %s
                 WHERE post_id = %s AND author_uid = %s AND active = TRUE
                RETURNING post_id
                """,
                (body, post_id, author_uid),
            ).fetchone()
            if row is not None:
                return
            existing = conn.execute(
                "SELECT author_uid FROM community_post_search WHERE post_id = %s AND active = TRUE",
                (post_id,),
            ).fetchone()
            if existing is None:
                raise StoreNotFound("COMMUNITY_POST_NOT_FOUND")
            raise StoreConflict("COMMUNITY_POST_FORBIDDEN")

    def delete_community_post(self, post_id: str, author_uid: str) -> None:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                DELETE FROM community_post_search
                 WHERE post_id = %s AND author_uid = %s
                RETURNING post_id
                """,
                (post_id, author_uid),
            ).fetchone()
            if row is not None:
                return
            existing = conn.execute(
                "SELECT author_uid FROM community_post_search WHERE post_id = %s",
                (post_id,),
            ).fetchone()
            if existing is None:
                raise StoreNotFound("COMMUNITY_POST_NOT_FOUND")
            raise StoreConflict("COMMUNITY_POST_FORBIDDEN")

    def create_community_comment(
        self, comment: CommunityCommentRecord
    ) -> CommunityCommentRecord:
        with self.pool.connection() as conn, conn.transaction():
            post = conn.execute(
                "SELECT 1 FROM community_post_search WHERE post_id = %s AND active = TRUE",
                (comment.post_id,),
            ).fetchone()
            account = conn.execute(
                """
                SELECT 1 FROM access_accounts
                 WHERE firebase_uid = %s AND status = 'ACTIVE'
                   AND role IN ('visitor', 'entrepreneur')
                """,
                (comment.author_uid,),
            ).fetchone()
            if post is None:
                raise StoreNotFound("COMMUNITY_POST_NOT_FOUND")
            if account is None:
                raise StoreNotFound("COMMUNITY_COMMENT_AUTHOR_NOT_AVAILABLE")
            if comment.parent_comment_id is not None:
                parent = conn.execute(
                    """
                    SELECT post_id, parent_comment_id
                      FROM community_post_comments
                     WHERE comment_id = %s
                    """,
                    (comment.parent_comment_id,),
                ).fetchone()
                if parent is None or parent["post_id"] != comment.post_id:
                    raise StoreConflict("COMMUNITY_COMMENT_PARENT_INVALID")
                if parent["parent_comment_id"] is not None:
                    raise StoreConflict("COMMUNITY_COMMENT_REPLY_DEPTH_EXCEEDED")
            row = conn.execute(
                """
                INSERT INTO community_post_comments
                  (comment_id, post_id, author_uid, parent_comment_id,
                   client_comment_id, body, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (author_uid, client_comment_id) DO NOTHING
                RETURNING comment_id, post_id, author_uid, parent_comment_id,
                          client_comment_id, body, created_at, updated_at
                """,
                (
                    comment.comment_id,
                    comment.post_id,
                    comment.author_uid,
                    comment.parent_comment_id,
                    comment.client_comment_id,
                    comment.body,
                    comment.created_at,
                ),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT comment_id, post_id, author_uid, parent_comment_id,
                           client_comment_id, body, created_at, updated_at
                      FROM community_post_comments
                     WHERE author_uid = %s AND client_comment_id = %s
                    """,
                    (comment.author_uid, comment.client_comment_id),
                ).fetchone()
                if (
                    row is None
                    or row["post_id"] != comment.post_id
                    or row["parent_comment_id"] != comment.parent_comment_id
                    or row["body"] != comment.body
                ):
                    raise StoreConflict("CLIENT_COMMENT_ID_CONFLICT")
        return CommunityCommentRecord(
            **row,
            like_count=0,
            liked_by_viewer=False,
        )

    def list_community_comments(
        self, post_id: str, viewer_uid: str, limit: int
    ) -> list[CommunityCommentRecord]:
        with self.pool.connection() as conn:
            post = conn.execute(
                "SELECT 1 FROM community_post_search WHERE post_id = %s AND active = TRUE",
                (post_id,),
            ).fetchone()
            if post is None:
                raise StoreNotFound("COMMUNITY_POST_NOT_FOUND")
            rows = conn.execute(
                """
                SELECT c.comment_id, c.post_id, c.author_uid,
                       c.parent_comment_id, c.client_comment_id, c.body,
                       c.created_at, c.updated_at,
                       count(l.firebase_uid)::int AS like_count,
                       bool_or(l.firebase_uid = %s) AS liked_by_viewer
                  FROM community_post_comments c
                  LEFT JOIN community_comment_likes l
                    ON l.comment_id = c.comment_id
                 WHERE c.post_id = %s
                 GROUP BY c.comment_id
                 ORDER BY c.created_at, c.comment_id
                 LIMIT %s
                """,
                (viewer_uid, post_id, max(1, min(int(limit), 200))),
            ).fetchall()
        return [
            CommunityCommentRecord(
                **{
                    **row,
                    "like_count": int(row["like_count"]),
                    "liked_by_viewer": bool(row["liked_by_viewer"]),
                },
            )
            for row in rows
        ]

    def update_community_comment(
        self,
        comment_id: str,
        author_uid: str,
        body: str,
        updated_at: datetime,
    ) -> CommunityCommentRecord:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                UPDATE community_post_comments AS c
                   SET body = %s, updated_at = %s
                  FROM community_post_search AS p
                 WHERE c.comment_id = %s
                   AND c.author_uid = %s
                   AND p.post_id = c.post_id
                   AND p.active = TRUE
                RETURNING c.comment_id, c.post_id, c.author_uid,
                          c.parent_comment_id, c.client_comment_id, c.body,
                          c.created_at, c.updated_at
                """,
                (body, updated_at, comment_id, author_uid),
            ).fetchone()
            if row is None:
                existing = conn.execute(
                    "SELECT author_uid FROM community_post_comments WHERE comment_id = %s",
                    (comment_id,),
                ).fetchone()
                if existing is None:
                    raise StoreNotFound("COMMUNITY_COMMENT_NOT_FOUND")
                raise StoreConflict("COMMUNITY_COMMENT_FORBIDDEN")
            likes = conn.execute(
                """
                SELECT count(*)::int AS total,
                       bool_or(firebase_uid = %s) AS liked_by_viewer
                  FROM community_comment_likes
                 WHERE comment_id = %s
                """,
                (author_uid, comment_id),
            ).fetchone()
        return CommunityCommentRecord(
            **row,
            like_count=int(likes["total"]),
            liked_by_viewer=bool(likes["liked_by_viewer"]),
        )

    def delete_community_comment(self, comment_id: str, author_uid: str) -> None:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                DELETE FROM community_post_comments
                 WHERE comment_id = %s AND author_uid = %s
                RETURNING comment_id
                """,
                (comment_id, author_uid),
            ).fetchone()
            if row is not None:
                return
            existing = conn.execute(
                "SELECT author_uid FROM community_post_comments WHERE comment_id = %s",
                (comment_id,),
            ).fetchone()
            if existing is None:
                raise StoreNotFound("COMMUNITY_COMMENT_NOT_FOUND")
            raise StoreConflict("COMMUNITY_COMMENT_FORBIDDEN")

    def set_community_comment_like(
        self,
        comment_id: str,
        viewer_uid: str,
        liked: bool,
        changed_at: datetime,
    ) -> tuple[bool, int]:
        with self.pool.connection() as conn, conn.transaction():
            comment = conn.execute(
                """
                SELECT 1
                  FROM community_post_comments c
                  JOIN community_post_search p ON p.post_id = c.post_id
                 WHERE c.comment_id = %s AND p.active = TRUE
                """,
                (comment_id,),
            ).fetchone()
            if comment is None:
                raise StoreNotFound("COMMUNITY_COMMENT_NOT_FOUND")
            if liked:
                conn.execute(
                    """
                    INSERT INTO community_comment_likes
                      (comment_id, firebase_uid, created_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (comment_id, firebase_uid) DO NOTHING
                    """,
                    (comment_id, viewer_uid, changed_at),
                )
            else:
                conn.execute(
                    """
                    DELETE FROM community_comment_likes
                     WHERE comment_id = %s AND firebase_uid = %s
                    """,
                    (comment_id, viewer_uid),
                )
            count = conn.execute(
                "SELECT count(*)::int AS total FROM community_comment_likes WHERE comment_id = %s",
                (comment_id,),
            ).fetchone()
        return liked, int(count["total"])

    @staticmethod
    def _conversation(row: dict[str, Any]) -> ConversationRecord:
        return ConversationRecord(
            conversation_id=row["conversation_id"], kind=row["kind"],
            status=row["status"], subject=row["subject"],
            created_by_uid=row["created_by_uid"], requester_uid=row["requester_uid"],
            assigned_support_uid=row["assigned_support_uid"],
            participant_uids=tuple(row["participant_uids"] or ()),
            last_message=row["last_message"], last_message_at=row["last_message_at"],
            unread_count=int(row["unread_count"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _conversation_select(support_inbox: bool = False) -> str:
        unread_sender_predicate = (
            "pm.sender_uid = c.requester_uid AND %s::text IS NOT NULL"
            if support_inbox
            else "pm.sender_uid <> %s"
        )
        return f"""
            SELECT c.*,
                   ARRAY(SELECT m.firebase_uid FROM private_conversation_members m
                          WHERE m.conversation_id = c.conversation_id
                          ORDER BY m.firebase_uid) AS participant_uids,
                   (SELECT pm.body FROM private_messages pm
                     WHERE pm.conversation_id = c.conversation_id
                     ORDER BY pm.created_at DESC, pm.message_id DESC LIMIT 1) AS last_message,
                   (SELECT count(*) FROM private_messages pm
                     WHERE pm.conversation_id = c.conversation_id
                       AND {unread_sender_predicate}
                       AND pm.created_at > COALESCE(
                         (SELECT r.read_at FROM private_conversation_reads r
                           WHERE r.conversation_id = c.conversation_id AND r.firebase_uid = %s),
                         '-infinity'::timestamptz
                       ))::integer AS unread_count
              FROM private_conversations c
        """

    def create_direct_conversation(
        self, conversation_id: str, sender_uid: str, recipient_uid: str
    ) -> ConversationRecord:
        direct_key = sha3_hex(
            sorted((sender_uid, recipient_uid)),
            "TRQ-BEC/direct-conversation/v1",
        )
        with self.pool.connection() as conn, conn.transaction():
            eligible = conn.execute(
                """
                SELECT count(*) AS total
                  FROM access_accounts a
                  JOIN public_profile_directory p USING (firebase_uid)
                 WHERE a.firebase_uid IN (%s, %s) AND a.status = 'ACTIVE'
                   AND a.role = p.role
                   AND a.role IN ('visitor', 'entrepreneur', 'institution')
                """,
                (sender_uid, recipient_uid),
            ).fetchone()
            if sender_uid == recipient_uid or int(eligible["total"]) != 2:
                raise StoreConflict("MESSAGE_RECIPIENT_NOT_AVAILABLE")
            blocked = conn.execute(
                """
                SELECT 1 FROM message_blocks
                 WHERE (blocker_uid = %s AND blocked_uid = %s)
                    OR (blocker_uid = %s AND blocked_uid = %s)
                """,
                (sender_uid, recipient_uid, recipient_uid, sender_uid),
            ).fetchone()
            if blocked:
                raise StoreConflict("MESSAGE_RECIPIENT_NOT_AVAILABLE")
            row = conn.execute(
                """
                INSERT INTO private_conversations
                  (conversation_id, kind, status, created_by_uid, direct_key)
                VALUES (%s, 'DIRECT', 'OPEN', %s, %s)
                ON CONFLICT (direct_key) DO UPDATE SET updated_at = private_conversations.updated_at
                RETURNING conversation_id
                """,
                (conversation_id, sender_uid, direct_key),
            ).fetchone()
            actual_id = row["conversation_id"]
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO private_conversation_members (conversation_id, firebase_uid)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """,
                    [(actual_id, sender_uid), (actual_id, recipient_uid)],
                )
        result = self.get_conversation(sender_uid, actual_id, support_inbox=False)
        if result is None:
            raise StoreConflict("CONVERSATION_NOT_AVAILABLE")
        return result

    def create_support_conversation(
        self, conversation_id: str, requester_uid: str, subject: str
    ) -> ConversationRecord:
        with self.pool.connection() as conn, conn.transaction():
            eligible = conn.execute(
                """
                SELECT 1 FROM access_accounts
                 WHERE firebase_uid = %s AND status = 'ACTIVE'
                   AND role IN ('visitor', 'entrepreneur', 'institution')
                """,
                (requester_uid,),
            ).fetchone()
            if not eligible:
                raise StoreConflict("SUPPORT_REQUESTER_NOT_ELIGIBLE")
            conn.execute(
                """
                INSERT INTO private_conversations
                  (conversation_id, kind, status, subject, created_by_uid, requester_uid)
                VALUES (%s, 'SUPPORT', 'OPEN', %s, %s, %s)
                """,
                (conversation_id, subject, requester_uid, requester_uid),
            )
            conn.execute(
                """INSERT INTO private_conversation_members (conversation_id, firebase_uid)
                   VALUES (%s, %s)""",
                (conversation_id, requester_uid),
            )
        result = self.get_conversation(requester_uid, conversation_id, support_inbox=False)
        if result is None:
            raise StoreConflict("CONVERSATION_NOT_AVAILABLE")
        return result

    def list_conversations(
        self, uid: str, *, support_inbox: bool, limit: int
    ) -> list[ConversationRecord]:
        bounded_limit = max(1, min(int(limit), 100))
        with self.pool.connection() as conn:
            if support_inbox:
                rows = conn.execute(
                    self._conversation_select(support_inbox=True)
                    + " WHERE c.kind = 'SUPPORT' ORDER BY COALESCE(c.last_message_at, c.created_at) DESC LIMIT %s",
                    (uid, uid, bounded_limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    self._conversation_select()
                    + " WHERE EXISTS (SELECT 1 FROM private_conversation_members m WHERE m.conversation_id = c.conversation_id AND m.firebase_uid = %s) ORDER BY COALESCE(c.last_message_at, c.created_at) DESC LIMIT %s",
                    (uid, uid, uid, bounded_limit),
                ).fetchall()
        return [self._conversation(row) for row in rows]

    def get_conversation(
        self, uid: str, conversation_id: str, *, support_inbox: bool
    ) -> ConversationRecord | None:
        with self.pool.connection() as conn:
            if support_inbox:
                row = conn.execute(
                    self._conversation_select(support_inbox=True)
                    + " WHERE c.conversation_id = %s AND c.kind = 'SUPPORT'",
                    (uid, uid, conversation_id),
                ).fetchone()
            else:
                row = conn.execute(
                    self._conversation_select()
                    + " WHERE c.conversation_id = %s AND EXISTS (SELECT 1 FROM private_conversation_members m WHERE m.conversation_id = c.conversation_id AND m.firebase_uid = %s)",
                    (uid, uid, conversation_id, uid),
                ).fetchone()
        return self._conversation(row) if row else None

    def send_private_message(
        self, message: PrivateMessageRecord, *, support_actor: bool
    ) -> PrivateMessageRecord:
        with self.pool.connection() as conn, conn.transaction():
            conversation = conn.execute(
                "SELECT * FROM private_conversations WHERE conversation_id = %s FOR UPDATE",
                (message.conversation_id,),
            ).fetchone()
            account = conn.execute(
                "SELECT role, status FROM access_accounts WHERE firebase_uid = %s",
                (message.sender_uid,),
            ).fetchone()
            if conversation is None or account is None or account["status"] != "ACTIVE":
                raise StoreNotFound("CONVERSATION_NOT_FOUND")
            member = conn.execute(
                "SELECT 1 FROM private_conversation_members WHERE conversation_id = %s AND firebase_uid = %s",
                (message.conversation_id, message.sender_uid),
            ).fetchone()
            if support_actor:
                allowed = conversation["kind"] == "SUPPORT" and account["role"] == "support"
            else:
                allowed = bool(member) and account["role"] in {"visitor", "entrepreneur", "institution"}
            if not allowed:
                raise StoreNotFound("CONVERSATION_NOT_FOUND")
            if conversation["status"] == "CLOSED" or (
                conversation["kind"] == "SUPPORT"
                and conversation["status"] == "RESOLVED"
            ):
                raise StoreConflict("CONVERSATION_CLOSED")
            if conversation["kind"] == "DIRECT":
                members = conn.execute(
                    "SELECT firebase_uid FROM private_conversation_members WHERE conversation_id = %s",
                    (message.conversation_id,),
                ).fetchall()
                other_uids = [row["firebase_uid"] for row in members if row["firebase_uid"] != message.sender_uid]
                if not other_uids:
                    raise StoreNotFound("CONVERSATION_NOT_FOUND")
                recipient_active = conn.execute(
                    """
                    SELECT 1 FROM access_accounts a
                    JOIN public_profile_directory p USING (firebase_uid)
                    WHERE a.firebase_uid = %s AND a.status = 'ACTIVE'
                      AND a.role = p.role
                      AND a.role IN ('visitor', 'entrepreneur', 'institution')
                    """,
                    (other_uids[0],),
                ).fetchone()
                if not recipient_active:
                    raise StoreNotFound("CONVERSATION_NOT_FOUND")
                blocked = conn.execute(
                    """SELECT 1 FROM message_blocks WHERE
                       (blocker_uid = %s AND blocked_uid = %s) OR
                       (blocker_uid = %s AND blocked_uid = %s)""",
                    (message.sender_uid, other_uids[0], other_uids[0], message.sender_uid),
                ).fetchone()
                if blocked:
                    raise StoreConflict("MESSAGE_DELIVERY_BLOCKED")
            elif conversation["kind"] == "SUPPORT" and support_actor:
                requester_active = conn.execute(
                    """
                    SELECT 1 FROM access_accounts
                     WHERE firebase_uid = %s AND status = 'ACTIVE'
                       AND role IN ('visitor', 'entrepreneur', 'institution')
                    """,
                    (conversation["requester_uid"],),
                ).fetchone()
                if not requester_active:
                    raise StoreNotFound("CONVERSATION_NOT_FOUND")
            row = conn.execute(
                """
                INSERT INTO private_messages
                  (message_id, conversation_id, sender_uid, client_message_id,
                   body, media_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (sender_uid, client_message_id) DO NOTHING
                RETURNING message_id, conversation_id, sender_uid, body,
                          media_id, created_at
                """,
                (
                    message.message_id, message.conversation_id, message.sender_uid,
                    message.client_message_id,
                    message.body, message.media_id, message.created_at,
                ),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """SELECT message_id, conversation_id, sender_uid, body,
                              media_id, created_at
                         FROM private_messages WHERE sender_uid = %s AND client_message_id = %s""",
                    (message.sender_uid, message.client_message_id),
                ).fetchone()
                if (
                    row is None
                    or row["conversation_id"] != message.conversation_id
                    or row["body"] != message.body
                    or (
                        str(row["media_id"]) if row["media_id"] else None
                    ) != message.media_id
                ):
                    raise StoreConflict("CLIENT_MESSAGE_ID_CONFLICT")
            next_status = conversation["status"]
            if conversation["kind"] == "SUPPORT":
                if support_actor and next_status == "OPEN":
                    next_status = "IN_PROGRESS"
            conn.execute(
                """
                UPDATE private_conversations
                   SET last_message_at = %s, updated_at = %s, status = %s,
                       assigned_support_uid = CASE WHEN %s THEN COALESCE(assigned_support_uid, %s)
                                                   ELSE assigned_support_uid END
                 WHERE conversation_id = %s
                """,
                (
                    row["created_at"], row["created_at"], next_status,
                    support_actor, message.sender_uid, message.conversation_id,
                ),
            )
        return PrivateMessageRecord(
            message_id=row["message_id"], conversation_id=row["conversation_id"],
            sender_uid=row["sender_uid"], client_message_id=message.client_message_id,
            body=row["body"], media_id=str(row["media_id"]) if row["media_id"] else None,
            created_at=row["created_at"],
        )

    def list_private_messages(
        self, uid: str, conversation_id: str, *, support_inbox: bool, limit: int
    ) -> list[PrivateMessageRecord]:
        conversation = self.get_conversation(uid, conversation_id, support_inbox=support_inbox)
        if conversation is None:
            raise StoreNotFound("CONVERSATION_NOT_FOUND")
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT message_id, conversation_id, sender_uid, client_message_id,
                       body, media_id, created_at
                  FROM private_messages WHERE conversation_id = %s
                 ORDER BY created_at ASC, message_id ASC LIMIT %s
                """,
                (conversation_id, max(1, min(int(limit), 200))),
            ).fetchall()
        return [
            PrivateMessageRecord(
                **{
                    **row,
                    "media_id": str(row["media_id"]) if row["media_id"] else None,
                },
            )
            for row in rows
        ]

    def mark_conversation_read(
        self, uid: str, conversation_id: str, *, support_inbox: bool, read_at: datetime
    ) -> None:
        if self.get_conversation(uid, conversation_id, support_inbox=support_inbox) is None:
            raise StoreNotFound("CONVERSATION_NOT_FOUND")
        with self.pool.connection() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO private_conversation_reads (conversation_id, firebase_uid, read_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (conversation_id, firebase_uid) DO UPDATE
                  SET read_at = GREATEST(private_conversation_reads.read_at, EXCLUDED.read_at)
                """,
                (conversation_id, uid, read_at),
            )

    def resolve_support_conversation(
        self, support_uid: str, conversation_id: str, resolved_at: datetime
    ) -> ConversationRecord:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                UPDATE private_conversations c
                   SET status = 'RESOLVED', updated_at = %s,
                       assigned_support_uid = COALESCE(assigned_support_uid, %s)
                 WHERE c.conversation_id = %s AND c.kind = 'SUPPORT'
                   AND c.status NOT IN ('RESOLVED', 'CLOSED')
                   AND EXISTS (SELECT 1 FROM access_accounts a
                                WHERE a.firebase_uid = %s AND a.role = 'support' AND a.status = 'ACTIVE')
                RETURNING conversation_id
                """,
                (resolved_at, support_uid, conversation_id, support_uid),
            ).fetchone()
            if row is None:
                raise StoreConflict("SUPPORT_REQUEST_NOT_RESOLVABLE")
        result = self.get_conversation(support_uid, conversation_id, support_inbox=True)
        if result is None:
            raise StoreNotFound("CONVERSATION_NOT_FOUND")
        return result

    def set_message_block(
        self, blocker_uid: str, blocked_uid: str, blocked_at: datetime
    ) -> MessageBlockRecord:
        if blocker_uid == blocked_uid or self.get_public_profile(blocked_uid) is None:
            raise StoreConflict("MESSAGE_BLOCK_TARGET_INVALID")
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                INSERT INTO message_blocks (blocker_uid, blocked_uid, created_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (blocker_uid, blocked_uid) DO UPDATE
                  SET created_at = message_blocks.created_at
                RETURNING blocker_uid, blocked_uid, created_at
                """,
                (blocker_uid, blocked_uid, blocked_at),
            ).fetchone()
        return MessageBlockRecord(**row)

    def delete_message_block(self, blocker_uid: str, blocked_uid: str) -> bool:
        with self.pool.connection() as conn, conn.transaction():
            row = conn.execute(
                "DELETE FROM message_blocks WHERE blocker_uid = %s AND blocked_uid = %s RETURNING blocked_uid",
                (blocker_uid, blocked_uid),
            ).fetchone()
        return row is not None

    def list_message_blocks(self, blocker_uid: str, limit: int) -> list[MessageBlockRecord]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT b.blocker_uid, b.blocked_uid, b.created_at
                  FROM message_blocks b
                  JOIN public_profile_directory p ON p.firebase_uid = b.blocked_uid
                  JOIN access_accounts a ON a.firebase_uid = b.blocked_uid
                 WHERE b.blocker_uid = %s AND a.status = 'ACTIVE' AND a.role = p.role
                 ORDER BY b.created_at DESC LIMIT %s
                """,
                (blocker_uid, max(1, min(int(limit), 200))),
            ).fetchall()
        return [MessageBlockRecord(**row) for row in rows]

    def get_message_block_state(
        self, viewer_uid: str, other_uid: str
    ) -> tuple[bool, bool]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT blocker_uid, blocked_uid FROM message_blocks
                 WHERE (blocker_uid = %s AND blocked_uid = %s)
                    OR (blocker_uid = %s AND blocked_uid = %s)
                """,
                (viewer_uid, other_uid, other_uid, viewer_uid),
            ).fetchall()
        pairs = {(row["blocker_uid"], row["blocked_uid"]) for row in rows}
        return (viewer_uid, other_uid) in pairs, (other_uid, viewer_uid) in pairs

    def create_checkpoint(self, checkpoint_key_id: str, policy_version: str) -> dict[str, Any]:
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (AUDIT_LOCK_ID,))
            first = conn.execute("SELECT seq FROM audit_events ORDER BY seq ASC LIMIT 1").fetchone()
            last = conn.execute("SELECT seq, event_hash FROM audit_events ORDER BY seq DESC LIMIT 1").fetchone()
            if not first or not last:
                raise LedgerError("LEDGER_EMPTY")
            body = {
                "first_seq": int(first["seq"]),
                "last_seq": int(last["seq"]),
                "root_hash": last["event_hash"],
                "policy_version": policy_version,
            }
            signature = self.signing_provider.sign(
                checkpoint_key_id,
                domain_message("TRQ-BEC/checkpoint/v1", body),
                "checkpoint-signing",
            )
            signature_b64u = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
            checkpoint_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO audit_checkpoints
                  (checkpoint_id, first_seq, last_seq, root_hash, policy_version, signature_b64u)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (checkpoint_id, body["first_seq"], body["last_seq"], body["root_hash"], policy_version, signature_b64u),
            )
            return {**body, "checkpoint_id": checkpoint_id, "signature_b64u": signature_b64u}
