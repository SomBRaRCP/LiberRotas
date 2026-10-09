"""Contratos estritos de HTTP e persistência."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ApiErrorResponse(StrictModel):
    """Envelope estável de erro retornado nas fronteiras de autenticação e serviço."""

    code: str = Field(description="Código de motivo legível por máquina.", examples=["AUTH_TOKEN_INVALID"])
    message: str = Field(description="Mensagem de erro legível por pessoa ou operador.", examples=["AUTH_TOKEN_INVALID"])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "AUTH_TOKEN_INVALID",
                    "message": "AUTH_TOKEN_INVALID",
                }
            ]
        }
    )


class AccountDeletionPreparationResponse(StrictModel):
    """Confirma que os dados removíveis foram tratados antes de apagar o login."""

    status: Literal["READY_FOR_AUTH_DELETION"]
    firestore_documents_deleted: int = Field(ge=0)
    commercial_data_disabled: bool = True
    security_records_retained: bool = True


class AccessSessionResponse(StrictModel):
    """Decisão de acesso calculada após token, claims, permissões e status."""

    access_state: Literal["AUTHORIZED", "PENDING", "SUSPENDED", "DENIED"]
    role: Literal["admin", "support", "security", "institution", "entrepreneur", "visitor"] | None
    panel: Literal["admin", "support", "security", "institution", "entrepreneur", "visitor", "access_pending"]
    permissions: list[str] = Field(max_length=100)
    reason: str = Field(min_length=3, max_length=80)


class PublicRegistrationRequest(StrictModel):
    """Dados públicos aceitos somente durante o cadastro da própria conta."""

    role: Literal["entrepreneur", "visitor"]
    display_name: str = Field(min_length=3, max_length=60)
    establishment_name: str | None = Field(default=None, min_length=2, max_length=160)

    @model_validator(mode="after")
    def require_establishment_for_entrepreneur(self) -> "PublicRegistrationRequest":
        if self.role == "entrepreneur" and not self.establishment_name:
            raise ValueError("establishment_name is required for entrepreneur")
        if self.role == "visitor" and self.establishment_name is not None:
            raise ValueError("establishment_name is accepted only for entrepreneur")
        return self


class EmailVerificationQueueResponse(StrictModel):
    status: Literal["QUEUED", "ALREADY_VERIFIED", "NOT_REQUIRED"]
    role: Literal["entrepreneur", "visitor"]


class InstitutionCreateRequest(StrictModel):
    email: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, min_length=2, max_length=120)


class InstitutionResponse(StrictModel):
    firebase_uid: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=5, max_length=254)
    name: str = Field(min_length=2, max_length=160)
    description: str | None
    city: str | None
    status: Literal["ACTIVE", "PENDING", "SUSPENDED", "DISABLED"]
    created_at: datetime
    updated_at: datetime


class InstitutionListResponse(StrictModel):
    institutions: list[InstitutionResponse] = Field(max_length=200)


class PublicInstitutionApplicationCreateRequest(StrictModel):
    """Dados de contato aceitos na página pública; não cria uma conta."""

    organization_type: Literal["COMPANY", "NGO"]
    organization_name: str = Field(min_length=2, max_length=160)
    contact_name: str = Field(min_length=3, max_length=120)
    email: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    phone: str | None = Field(
        default=None,
        min_length=8,
        max_length=30,
        pattern=r"^[0-9()+.\-\s]+$",
    )
    registration_number: str | None = Field(default=None, min_length=3, max_length=30)
    city: str = Field(min_length=2, max_length=120)
    state: str = Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    website_or_social: str | None = Field(default=None, max_length=500)
    description: str = Field(min_length=20, max_length=2000)
    privacy_accepted: Literal[True]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()

    @field_validator("state")
    @classmethod
    def normalize_state(cls, value: str) -> str:
        return value.upper()


class PublicInstitutionApplicationCreatedResponse(StrictModel):
    application_id: UUID
    status: Literal["NEW"]
    created_at: datetime


class InstitutionApplicationStatusUpdateRequest(StrictModel):
    status: Literal["IN_REVIEW", "CONTACTED", "APPROVED", "REJECTED"]
    support_notes: str | None = Field(default=None, max_length=1000)


class InstitutionApplicationResponse(StrictModel):
    application_id: UUID
    organization_type: Literal["COMPANY", "NGO"]
    organization_name: str = Field(min_length=2, max_length=160)
    contact_name: str = Field(min_length=3, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    phone: str | None
    registration_number: str | None
    city: str = Field(min_length=2, max_length=120)
    state: str = Field(min_length=2, max_length=2)
    website_or_social: str | None
    description: str = Field(min_length=20, max_length=2000)
    status: Literal["NEW", "IN_REVIEW", "CONTACTED", "APPROVED", "REJECTED"]
    support_notes: str | None
    reviewed_by_uid: str | None
    provisioned_uid: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InstitutionApplicationListResponse(StrictModel):
    applications: list[InstitutionApplicationResponse] = Field(max_length=200)


class InstitutionProfileUpdateRequest(StrictModel):
    """Campos publicos que a propria instituicao pode alterar."""

    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, min_length=2, max_length=120)


class InstitutionGroupCreateRequest(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, min_length=2, max_length=120)


class InstitutionBadgePolicy(StrictModel):
    green_percent: int = Field(ge=0, le=100, strict=True)
    yellow_percent: int = Field(ge=0, le=100, strict=True)
    red_percent: int = Field(ge=0, le=100, strict=True)

    @model_validator(mode="after")
    def validate_total(self) -> "InstitutionBadgePolicy":
        if self.green_percent + self.yellow_percent + self.red_percent != 100:
            raise ValueError("Os percentuais dos três selos devem somar 100%.")
        return self


class InstitutionBadgeUpdateRequest(StrictModel):
    support_badge: Literal["GREEN", "YELLOW", "RED"]


class InstitutionBadgeDistribution(StrictModel):
    policy: InstitutionBadgePolicy
    seller_badges: dict[str, Literal["GREEN", "YELLOW", "RED"]]


class InstitutionGroupResponse(StrictModel):
    group_id: str = Field(
        min_length=13,
        max_length=40,
        pattern=r"^IGRP-[A-Z0-9]+$",
    )
    owner_uid: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=2, max_length=160)
    description: str | None
    city: str | None
    status: Literal["ACTIVE", "CLOSED"]
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    badge_policy: InstitutionBadgePolicy | None = None


class InstitutionGroupListResponse(StrictModel):
    groups: list[InstitutionGroupResponse] = Field(max_length=200)


class InstitutionSellerInvitationCreateRequest(StrictModel):
    """Convite resolvido exclusivamente pelo nome publico unico do vendedor."""

    seller_name: str = Field(min_length=3, max_length=60)


class InstitutionMembershipResponse(StrictModel):
    membership_id: str = Field(
        min_length=20,
        max_length=36,
        pattern=r"^IGM-[A-Z0-9]{16,32}$",
    )
    group_id: str = Field(min_length=13, max_length=40, pattern=r"^IGRP-[A-Z0-9]+$")
    group_name: str = Field(min_length=2, max_length=160)
    institution_name: str = Field(min_length=2, max_length=160)
    seller_uid: str = Field(min_length=1, max_length=128)
    seller_name: str = Field(min_length=3, max_length=60)
    status: Literal["PENDING", "ACTIVE", "DECLINED", "REMOVED", "LEFT"]
    invited_at: datetime
    responded_at: datetime | None
    active_from: datetime | None
    ended_at: datetime | None
    updated_at: datetime
    support_badge: Literal["GREEN", "YELLOW", "RED"] | None = None


class InstitutionMembershipListResponse(StrictModel):
    memberships: list[InstitutionMembershipResponse] = Field(max_length=100)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0, le=10_000)
    has_more: bool


class InstitutionSalesCurrencyTotalResponse(StrictModel):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    gross_original_amount_minor: int = Field(ge=0)
    gross_final_amount_minor: int = Field(ge=0)
    total_discount_amount_minor: int = Field(ge=0)


class InstitutionSellerSalesResponse(StrictModel):
    group_name: str = Field(min_length=2, max_length=160)
    seller_name: str = Field(min_length=3, max_length=60)
    membership_status: Literal["PENDING", "ACTIVE", "DECLINED", "REMOVED", "LEFT"]
    active_from: datetime
    ended_at: datetime | None
    confirmed_redemptions: int = Field(ge=0)
    units_sold: int = Field(ge=0)
    amounts_unavailable_count: int = Field(ge=0)
    totals_by_currency: list[InstitutionSalesCurrencyTotalResponse] = Field(max_length=20)


class InstitutionSalesReportResponse(StrictModel):
    period_from: datetime
    period_to: datetime
    group_filter: str | None
    confirmed_redemptions: int = Field(ge=0)
    units_sold: int = Field(ge=0)
    amounts_unavailable_count: int = Field(ge=0)
    totals_by_currency: list[InstitutionSalesCurrencyTotalResponse] = Field(max_length=20)
    sellers: list[InstitutionSellerSalesResponse] = Field(max_length=100)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0, le=10_000)
    has_more: bool
    generated_at: datetime
    financial_notice: str = Field(min_length=20, max_length=500)


class InstitutionFundedEventCreateRequest(StrictModel):
    group_id: str = Field(min_length=13, max_length=40, pattern=r"^IGRP-[A-Z0-9]+$")
    name: str = Field(min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    funding_source: Literal["DONATION", "INSTITUTION_BUDGET", "OTHER"]
    budget_amount_minor: int = Field(ge=1, le=100_000_000_000)
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    end_mode: Literal["TIME", "COUPONS"]
    starts_at: datetime
    ends_at: datetime | None = None
    coupon_limit: int | None = Field(default=None, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def validate_funded_event_window(self) -> "InstitutionFundedEventCreateRequest":
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must include an explicit timezone")
        if self.end_mode == "TIME":
            if self.ends_at is None:
                raise ValueError("ends_at is required when end_mode is TIME")
            if self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None:
                raise ValueError("ends_at must include an explicit timezone")
            if self.ends_at <= self.starts_at:
                raise ValueError("ends_at must be after starts_at")
            if self.ends_at - self.starts_at > timedelta(days=365):
                raise ValueError("funded event duration cannot exceed 365 days")
            if self.coupon_limit is not None:
                raise ValueError("coupon_limit must be empty when end_mode is TIME")
        else:
            if self.ends_at is not None:
                raise ValueError("ends_at must be empty when end_mode is COUPONS")
            if self.coupon_limit is None:
                raise ValueError("coupon_limit is required when end_mode is COUPONS")
        return self


class InstitutionEventSellerAllocationInput(StrictModel):
    seller_uid: str = Field(min_length=1, max_length=128)
    allocated_amount_minor: int = Field(ge=0, le=100_000_000_000)


class InstitutionEventSellerAllocationUpdateRequest(StrictModel):
    allocations: list[InstitutionEventSellerAllocationInput] = Field(
        min_length=1,
        max_length=100,
    )


class InstitutionEventProductAllocationInput(StrictModel):
    product_id: str = Field(pattern=r"^PROD-[A-Z0-9]{8,32}$")
    allocated_amount_minor: int = Field(ge=0, le=100_000_000_000)


class InstitutionEventProductAllocationUpdateRequest(StrictModel):
    allocations: list[InstitutionEventProductAllocationInput] = Field(
        min_length=1,
        max_length=200,
    )


class InstitutionFundedEventProductAllocationResponse(StrictModel):
    product_id: str
    product_title: str
    allocated_amount_minor: int = Field(ge=0)
    allocation_mode: Literal["EQUAL", "CUSTOM"]


class InstitutionFundedEventSellerAllocationResponse(StrictModel):
    membership_id: str
    seller_uid: str
    seller_name: str
    allocated_amount_minor: int = Field(ge=0)
    allocation_mode: Literal["EQUAL", "CUSTOM"]
    product_allocation_configured: bool
    product_allocations: list[InstitutionFundedEventProductAllocationResponse] = Field(
        max_length=200
    )


class InstitutionFundedEventResponse(StrictModel):
    event_id: str
    group_id: str
    group_name: str
    name: str
    description: str | None
    funding_source: Literal["DONATION", "INSTITUTION_BUDGET", "OTHER"]
    budget_amount_minor: int = Field(ge=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    end_mode: Literal["TIME", "COUPONS"]
    starts_at: datetime
    ends_at: datetime | None
    coupon_limit: int | None
    current_coupon_redemptions: int = Field(ge=0)
    status: Literal["DRAFT", "ACTIVE", "ENDED"]
    end_reason: Literal["TIME", "COUPONS", "MANUAL"] | None
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None
    ended_at: datetime | None
    seller_allocations: list[InstitutionFundedEventSellerAllocationResponse] = Field(
        max_length=100
    )
    badge_distribution: InstitutionBadgeDistribution | None = None


class InstitutionFundedEventListResponse(StrictModel):
    events: list[InstitutionFundedEventResponse] = Field(max_length=100)


class EntrepreneurFundedEventResponse(StrictModel):
    event_id: str
    group_id: str
    institution_name: str
    group_name: str
    name: str
    description: str | None
    allocated_amount_minor: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    end_mode: Literal["TIME", "COUPONS"]
    starts_at: datetime
    ends_at: datetime | None
    coupon_limit: int | None
    current_coupon_redemptions: int = Field(ge=0)
    status: Literal["DRAFT", "ACTIVE", "ENDED"]
    product_allocation_configured: bool
    product_allocations: list[InstitutionFundedEventProductAllocationResponse] = Field(
        max_length=200
    )


class EntrepreneurFundedEventListResponse(StrictModel):
    events: list[EntrepreneurFundedEventResponse] = Field(max_length=100)


class InstitutionFundedEventProductReportResponse(StrictModel):
    product_id: str
    product_title: str
    allocated_amount_minor: int = Field(ge=0)
    confirmed_redemptions: int = Field(ge=0)
    units_sold: int = Field(ge=0)
    gross_original_amount_minor: int = Field(ge=0)
    gross_final_amount_minor: int = Field(ge=0)
    discount_used_minor: int = Field(ge=0)
    amount_due_minor: int = Field(ge=0)
    unfunded_discount_minor: int = Field(ge=0)
    remaining_budget_minor: int = Field(ge=0)


class InstitutionFundedEventSellerReportResponse(StrictModel):
    seller_uid: str
    seller_name: str
    allocated_amount_minor: int = Field(ge=0)
    confirmed_redemptions: int = Field(ge=0)
    units_sold: int = Field(ge=0)
    gross_original_amount_minor: int = Field(ge=0)
    gross_final_amount_minor: int = Field(ge=0)
    discount_used_minor: int = Field(ge=0)
    amount_due_minor: int = Field(ge=0)
    unfunded_discount_minor: int = Field(ge=0)
    remaining_budget_minor: int = Field(ge=0)
    products: list[InstitutionFundedEventProductReportResponse] = Field(max_length=200)


class InstitutionFundedEventReportResponse(StrictModel):
    event: InstitutionFundedEventResponse
    confirmed_redemptions: int = Field(ge=0)
    units_sold: int = Field(ge=0)
    gross_original_amount_minor: int = Field(ge=0)
    gross_final_amount_minor: int = Field(ge=0)
    discount_used_minor: int = Field(ge=0)
    amount_due_minor: int = Field(ge=0)
    unfunded_discount_minor: int = Field(ge=0)
    remaining_budget_minor: int = Field(ge=0)
    sellers: list[InstitutionFundedEventSellerReportResponse] = Field(max_length=100)
    generated_at: datetime
    financial_notice: str = Field(min_length=20, max_length=600)


class EntrepreneurFundedEventReportResponse(StrictModel):
    event: EntrepreneurFundedEventResponse
    confirmed_redemptions: int = Field(ge=0)
    units_sold: int = Field(ge=0)
    gross_original_amount_minor: int = Field(ge=0)
    gross_final_amount_minor: int = Field(ge=0)
    discount_used_minor: int = Field(ge=0)
    amount_due_minor: int = Field(ge=0)
    unfunded_discount_minor: int = Field(ge=0)
    remaining_budget_minor: int = Field(ge=0)
    products: list[InstitutionFundedEventProductReportResponse] = Field(max_length=200)
    generated_at: datetime
    financial_notice: str = Field(min_length=20, max_length=600)


class InstitutionReportSummaryResponse(StrictModel):
    total_groups: int = Field(ge=0)
    active_groups: int = Field(ge=0)
    closed_groups: int = Field(ge=0)
    last_group_created_at: datetime | None
    generated_at: datetime


class AccessAccountStatusRequest(StrictModel):
    status: Literal["ACTIVE", "SUSPENDED"]
    reason: str = Field(min_length=10, max_length=500)


class StaffAccountCreateRequest(StrictModel):
    """Solicitação fechada: o backend deriva claims e permissões pela função."""

    email: str = Field(
        min_length=5,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    display_name: str = Field(min_length=3, max_length=120)
    role: Literal["admin", "support", "security"]


class StaffAccountValidationRequest(StrictModel):
    reason: str = Field(min_length=10, max_length=500)


class AccessAccountSummaryResponse(StrictModel):
    firebase_uid: str = Field(min_length=1, max_length=128)
    email: str | None
    role: Literal["admin", "support", "security", "institution", "entrepreneur", "visitor"]
    status: Literal["ACTIVE", "PENDING", "SUSPENDED", "DISABLED"]
    permissions: list[str] = Field(max_length=100)
    created_at: datetime | None
    updated_at: datetime | None
    authority_validation_state: Literal["PENDING", "APPROVED", "REJECTED", "REVOKED"] | None = None
    protection_level: Literal["SYSTEM", "PRIVILEGED"] | None = None
    account_origin: Literal["BOOTSTRAP", "ADMIN_INVITATION"] | None = None
    authority_validated_at: datetime | None = None
    authority_validated_by_uid: str | None = Field(default=None, max_length=128)
    created_by_uid: str | None = Field(default=None, max_length=128)


class AdminAccountListResponse(StrictModel):
    accounts: list[AccessAccountSummaryResponse] = Field(max_length=200)


class SupportAccountSummaryResponse(StrictModel):
    """Visao minima de conta para atendimento, sem claims ou permissoes internas."""

    firebase_uid: str = Field(min_length=1, max_length=128)
    email: str | None
    role: Literal["admin", "support", "security", "institution", "entrepreneur", "visitor"]
    status: Literal["ACTIVE", "PENDING", "SUSPENDED", "DISABLED"]
    created_at: datetime | None
    updated_at: datetime | None


class SupportAccountListResponse(StrictModel):
    accounts: list[SupportAccountSummaryResponse] = Field(max_length=200)


class AccessAuditEventResponse(StrictModel):
    event_id: str = Field(min_length=1, max_length=160)
    actor_uid: str = Field(min_length=1, max_length=128)
    target_uid: str = Field(min_length=1, max_length=128)
    event_type: Literal[
        "INSTITUTION_PROVISIONED",
        "ACCOUNT_STATUS_CHANGED",
        "OFFICIAL_ACCOUNT_VALIDATED",
        "STAFF_ACCOUNT_CREATED",
        "STAFF_ACCOUNT_VALIDATED",
    ]
    previous_status: Literal["ACTIVE", "PENDING", "SUSPENDED", "DISABLED"] | None
    new_status: Literal["ACTIVE", "PENDING", "SUSPENDED", "DISABLED"]
    reason: str = Field(min_length=10, max_length=500)
    created_at: datetime


class SecurityAccountListResponse(StrictModel):
    accounts: list[AccessAccountSummaryResponse] = Field(max_length=200)
    recent_events: list[AccessAuditEventResponse] = Field(max_length=200)


class AdminOperationsSummaryResponse(StrictModel):
    accounts_total: int = Field(ge=0)
    accounts_by_role: dict[str, int]
    accounts_by_status: dict[str, int]
    institutions_total: int = Field(ge=0)
    groups_total: int = Field(ge=0)
    groups_active: int = Field(ge=0)
    merchants_active: int = Field(ge=0)
    merchants_suspended: int = Field(ge=0)
    products_active: int = Field(ge=0)
    offers_active: int = Field(ge=0)
    health_status: Literal["ok", "degraded"]
    database_ok: bool
    redis_ok: bool
    pqc_ready: bool
    server_time_iso: datetime


class SecurityMonitoringSummaryResponse(StrictModel):
    accounts_total: int = Field(ge=0)
    active_accounts: int = Field(ge=0)
    suspended_accounts: int = Field(ge=0)
    pending_accounts: int = Field(ge=0)
    disabled_accounts: int = Field(ge=0)
    recent_events_total: int = Field(ge=0)
    last_event_at: datetime | None
    recent_events: list[AccessAuditEventResponse] = Field(max_length=50)
    health_status: Literal["ok", "degraded"]
    database_ok: bool
    redis_ok: bool
    pqc_ready: bool
    server_time_iso: datetime


class TrqBecSecurityStatusResponse(StrictModel):
    """Telemetria sanitizada dos controles do TRQ-BEC, sem segredos."""

    policy_version: str = Field(min_length=1, max_length=120)
    environment: str = Field(min_length=1, max_length=40)
    lab_suite_enabled: bool
    token_revocation_checks_enabled: bool = True
    access_validation_enforced: bool = True
    audit_ledger_append_only: bool = True
    database_ok: bool
    redis_ok: bool
    pqc_provider_name: str = Field(min_length=1, max_length=120)
    pqc_provider_version: str = Field(min_length=1, max_length=120)
    pqc_ready: bool
    privileged_accounts_total: int = Field(ge=0)
    official_accounts_total: int = Field(ge=0)
    privileged_accounts_pending_validation: int = Field(ge=0)
    access_events_total: int = Field(ge=0)
    access_events_last_24h: int = Field(ge=0)
    audit_events_total: int = Field(ge=0)
    audit_checkpoints_total: int = Field(ge=0)
    devices_active: int = Field(ge=0)
    devices_pending: int = Field(ge=0)
    devices_revoked: int = Field(ge=0)
    device_notifications_failed: int = Field(ge=0)
    email_verifications_pending: int = Field(ge=0)
    email_verifications_failed: int = Field(ge=0)
    latest_schema_migration: str | None = Field(default=None, max_length=120)
    server_time_iso: datetime


class CuratedPlaceCreateRequest(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    address: str = Field(min_length=3, max_length=240)
    category: Literal[
        "pontos_turisticos",
        "parques",
        "feiras_livres",
        "artesanato",
        "bordados",
        "gastronomia",
        "eventos",
        "comercio_local",
    ]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LiveFairCreateRequest(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    address: str = Field(min_length=10, max_length=240)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    starts_at_ms: int = Field(gt=0)
    ends_at_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_window(self) -> "LiveFairCreateRequest":
        if self.ends_at_ms <= self.starts_at_ms:
            raise ValueError("ends_at_ms must be after starts_at_ms")
        if self.ends_at_ms - self.starts_at_ms > 86_400_000:
            raise ValueError("live fair duration cannot exceed 24 hours")
        return self


class CommunityPostMedia(StrictModel):
    type: Literal["image"] = "image"
    media_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
        description="Imagem pronta e pertencente ao autor, validada pelo backend.",
    )


class CommunityPostCreateRequest(StrictModel):
    """Conteudo permitido ao cliente; autoria e funcao sao sempre derivadas no backend."""

    text: str = Field(min_length=1, max_length=2000)
    media: CommunityPostMedia | None = None


class CommunityPostUpdateRequest(StrictModel):
    """Somente o texto pode ser alterado; autoria e midia permanecem imutaveis."""

    text: str = Field(min_length=1, max_length=2000)


class CommunityDocumentResponse(StrictModel):
    document_id: str = Field(min_length=1, max_length=160)
    status: Literal["approved", "scheduled", "live", "ended"]


class CommunityContentMutationResponse(StrictModel):
    document_id: str = Field(min_length=1, max_length=160)
    status: Literal["updated", "deleted"]


MediaEntityType = Literal[
    "user",
    "entrepreneur",
    "product",
    "post",
    "fair",
    "institution",
    "support",
]
MediaRole = Literal[
    "avatar",
    "entrepreneur_logo",
    "institution_logo",
    "product_image",
    "post_image",
    "fair_cover",
    "support_attachment",
]
ImageContentType = Literal["image/jpeg", "image/png", "image/webp"]


class MediaUploadCreateRequest(StrictModel):
    entity_type: MediaEntityType
    entity_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9:_-]+$",
    )
    media_role: MediaRole
    original_filename: str = Field(min_length=1, max_length=255)
    content_type: ImageContentType
    size_bytes: int = Field(gt=0, le=52_428_800)
    client_request_id: str = Field(
        min_length=8,
        max_length=100,
        pattern=r"^[A-Za-z0-9:_-]+$",
    )

    @field_validator("original_filename")
    @classmethod
    def validate_original_filename(cls, value: str) -> str:
        if (
            value in {".", ".."}
            or "/" in value
            or "\\" in value
            or "\x00" in value
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("original_filename is invalid")
        return value


class MediaUploadAuthorizationResponse(StrictModel):
    media_id: str
    object_key: str
    upload_url: str = Field(min_length=20, max_length=8192)
    method: Literal["PUT"] = "PUT"
    expires_in: int = Field(ge=60, le=3600)
    required_headers: dict[str, str]


class MediaAssetResponse(StrictModel):
    media_id: str
    owner_user_id: str
    entity_type: MediaEntityType
    entity_id: str
    media_role: MediaRole
    declared_content_type: ImageContentType
    detected_content_type: ImageContentType | None
    declared_size_bytes: int = Field(gt=0)
    size_bytes: int | None = Field(default=None, gt=0)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    status: Literal[
        "pending",
        "uploaded",
        "processing",
        "ready",
        "rejected",
        "quarantined",
        "deleted",
        "orphaned",
    ]
    visibility: Literal["private", "public_processed", "restricted"]
    moderation_status: Literal["pending", "approved", "rejected", "flagged"]
    created_at: datetime
    uploaded_at: datetime | None
    confirmed_at: datetime | None
    deleted_at: datetime | None
    download_url: str | None = Field(default=None, max_length=8192)
    download_expires_in: int | None = Field(default=None, ge=60, le=3600)


class MediaAssetListResponse(StrictModel):
    items: list[MediaAssetResponse] = Field(max_length=100)
    has_more: bool


class MediaCleanupResponse(StrictModel):
    scanned: int = Field(ge=0, le=100)
    cleaned: int = Field(ge=0, le=100)
    failed: int = Field(ge=0, le=100)


class MediaStorageHealth(StrictModel):
    provider: Literal["gcs"]
    enabled: bool
    configured: bool
    status: Literal["disabled", "ok", "unavailable"]


class PublicProfileUpsertRequest(StrictModel):
    """Campos publicos aceitos; identidade e funcao sempre vem do token validado."""

    display_name: str = Field(min_length=3, max_length=60)
    city: str = Field(min_length=2, max_length=120)
    address: str | None = Field(default=None, min_length=3, max_length=240)
    category: str = Field(default="", max_length=160)
    interests: list[str] = Field(default_factory=list, max_length=8)
    avatar_uri: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_public_fields(self) -> "PublicProfileUpsertRequest":
        normalized_interests = [item.strip() for item in self.interests]
        if any(not item or len(item) > 80 for item in normalized_interests):
            raise ValueError("each interest must contain between 1 and 80 characters")
        if len({item.casefold() for item in normalized_interests}) != len(normalized_interests):
            raise ValueError("interests must be unique")
        if self.avatar_uri is not None and not self.avatar_uri.startswith(("https://", "http://")):
            raise ValueError("avatar_uri must be an HTTP(S) URL")
        return self


class PublicProfileResponse(StrictModel):
    uid: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=3, max_length=60)
    role: Literal["visitor", "entrepreneur", "institution"]
    city: str = Field(min_length=2, max_length=120)
    address: str | None
    category: str
    interests: list[str] = Field(max_length=8)
    avatar_uri: str | None
    created_at: datetime
    updated_at: datetime


class GlobalSearchItemResponse(StrictModel):
    type: Literal["PROFILE", "PRODUCT", "OFFER", "POST"]
    id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=2000)
    subtitle: str | None = Field(default=None, max_length=2000)
    owner_uid: str | None = Field(default=None, max_length=128)
    route: str = Field(min_length=1, max_length=500)
    status: str | None = Field(default=None, max_length=40)
    created_at: datetime | None


class GlobalSearchResponse(StrictModel):
    query: str = Field(min_length=2, max_length=100)
    items: list[GlobalSearchItemResponse] = Field(max_length=50)


class MessageIdentityResponse(StrictModel):
    """Identidade publica. O suporte usa o identificador virtual `support`."""

    uid: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=2, max_length=60)
    role: Literal["visitor", "entrepreneur", "institution", "support", "unavailable"]
    avatar_uri: str | None = Field(default=None, max_length=4096)


class DirectMessageCreateRequest(StrictModel):
    recipient_uid: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=2000)
    client_message_id: str | None = Field(default=None, min_length=8, max_length=100)


class ConversationMessageCreateRequest(StrictModel):
    content: str = Field(min_length=1, max_length=2000)
    client_message_id: str | None = Field(default=None, min_length=8, max_length=100)
    media_id: UUID | None = None


class SupportRequestCreateRequest(StrictModel):
    subject: str = Field(min_length=3, max_length=160)
    content: str = Field(min_length=1, max_length=2000)
    client_message_id: str | None = Field(default=None, min_length=8, max_length=100)


class PrivateMessageResponse(StrictModel):
    message_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=160)
    sender: MessageIdentityResponse
    content: str = Field(min_length=1, max_length=2000)
    media_id: UUID | None = None
    mine: bool
    created_at: datetime


class CommunityCommentCreateRequest(StrictModel):
    content: str = Field(min_length=1, max_length=1000)
    parent_comment_id: str | None = Field(default=None, min_length=8, max_length=160)
    client_comment_id: str | None = Field(default=None, min_length=8, max_length=100)


class CommunityCommentUpdateRequest(StrictModel):
    content: str = Field(min_length=1, max_length=1000)


class CommunityCommentResponse(StrictModel):
    comment_id: str = Field(min_length=8, max_length=160)
    post_id: str = Field(min_length=1, max_length=160)
    parent_comment_id: str | None = Field(default=None, min_length=8, max_length=160)
    author: MessageIdentityResponse
    content: str = Field(min_length=1, max_length=1000)
    mine: bool
    liked_by_me: bool
    like_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime | None = None


class CommunityCommentDeleteResponse(StrictModel):
    comment_id: str = Field(min_length=8, max_length=160)
    status: Literal["deleted"]


class CommunityCommentListResponse(StrictModel):
    comments: list[CommunityCommentResponse] = Field(max_length=200)


class CommunityCommentLikeResponse(StrictModel):
    comment_id: str = Field(min_length=8, max_length=160)
    liked: bool
    like_count: int = Field(ge=0)


class ConversationResponse(StrictModel):
    conversation_id: str = Field(min_length=1, max_length=160)
    kind: Literal["DIRECT", "SUPPORT"]
    status: Literal["OPEN", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED"]
    subject: str | None
    counterpart: MessageIdentityResponse
    last_message: str | None = Field(default=None, max_length=2000)
    last_message_at: datetime | None
    unread_count: int = Field(ge=0)
    blocked_by_me: bool
    blocked_me: bool
    can_message: bool
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(StrictModel):
    conversations: list[ConversationResponse] = Field(max_length=100)


class ConversationDetailResponse(StrictModel):
    conversation: ConversationResponse
    messages: list[PrivateMessageResponse] = Field(max_length=200)


class MessageBlockResponse(StrictModel):
    profile: PublicProfileResponse
    blocked_at: datetime


class MessageBlockListResponse(StrictModel):
    blocks: list[MessageBlockResponse] = Field(max_length=200)


class ConversationReadResponse(StrictModel):
    conversation_id: str = Field(min_length=1, max_length=160)
    read_at: datetime


class EnrollDeviceRequest(StrictModel):
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        pattern=r"^device:[A-Za-z0-9:_-]+$",
        description="Identificador estável da aplicação para a chave local do dispositivo.",
        examples=["device:expo:feirante:01"],
    )
    public_key_b64u: str = Field(
        min_length=43,
        max_length=43,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Chave pública Ed25519 bruta codificada em Base64URL sem preenchimento (perfil de laboratório).",
        examples=["iOZAaQkSG1nU4MV5kY_IRQAxIQ1o9S87b2m3oxygTlw"],
    )
    algorithm: Literal["ED25519_LAB"] = Field(description="Algoritmo de prova do dispositivo habilitado nesta versão de laboratório.")
    storage_profile: Literal["EXPO_SECURE_STORE_LAB", "WEB_CRYPTO_INDEXEDDB_LAB"] = Field(
        description=(
            "Perfil de armazenamento local da chave privada: SecureStore no aplicativo Expo "
            "ou Web Crypto com persistência no IndexedDB no navegador."
        ),
        examples=["EXPO_SECURE_STORE_LAB", "WEB_CRYPTO_INDEXEDDB_LAB"],
    )

    device_name: str | None = Field(default=None, min_length=1, max_length=80)
    platform: Literal[
        "android", "ios", "web", "windows", "macos", "linux", "unknown"
    ] = "unknown"
    model_name: str | None = Field(default=None, min_length=1, max_length=120)
    app_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=40,
        pattern=r"^[A-Za-z0-9._+()-]+$",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "device_key_id": "device:expo:feirante:01",
                    "public_key_b64u": "iOZAaQkSG1nU4MV5kY_IRQAxIQ1o9S87b2m3oxygTlw",
                    "algorithm": "ED25519_LAB",
                    "storage_profile": "EXPO_SECURE_STORE_LAB",
                },
                {
                    "device_key_id": "device:web:feirante:01",
                    "public_key_b64u": "iOZAaQkSG1nU4MV5kY_IRQAxIQ1o9S87b2m3oxygTlw",
                    "algorithm": "ED25519_LAB",
                    "storage_profile": "WEB_CRYPTO_INDEXEDDB_LAB",
                }
            ]
        }
    )


class EnrollDeviceResponse(StrictModel):
    device_key_id: str = Field(description="Identificador da chave do dispositivo aceito pelo backend.")
    status: Literal["ENROLLED", "ALREADY_ENROLLED"] = Field(description="Resultado idempotente do cadastro.")
    device_status: Literal["ACTIVE", "PENDING_APPROVAL"]
    is_new_device: bool
    is_additional_device: bool
    notification_status: Literal[
        "NOT_REQUIRED", "PENDING", "SENT", "NOT_CONFIGURED", "FAILED"
    ]
    key_ref: str = Field(description="Referência pseudonimizada da chave, segura para registros de auditoria.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "device_key_id": "device:expo:feirante:01",
                    "status": "ENROLLED",
                    "key_ref": "devref:3x6vT0ph2QmN8sYk",
                    "device_status": "ACTIVE",
                    "is_new_device": True,
                    "is_additional_device": False,
                    "notification_status": "NOT_REQUIRED",
                }
            ]
        }
    )


class AccountDeviceResponse(StrictModel):
    device_key_id: str = Field(min_length=12, max_length=160)
    key_ref: str = Field(min_length=1, max_length=200)
    device_name: str | None = Field(default=None, max_length=80)
    platform: Literal["android", "ios", "web", "windows", "macos", "linux", "unknown"]
    model_name: str | None = Field(default=None, max_length=120)
    app_version: str | None = Field(default=None, max_length=40)
    storage_profile: Literal["EXPO_SECURE_STORE_LAB", "WEB_CRYPTO_INDEXEDDB_LAB"]
    status: Literal["ACTIVE", "PENDING_APPROVAL", "REVOKED"]
    notification_status: Literal[
        "NOT_REQUIRED", "PENDING", "SENT", "NOT_CONFIGURED", "FAILED"
    ]
    created_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None
    approval_expires_at: datetime | None
    approval_last_sent_at: datetime | None
    approved_at: datetime | None


class AccountDeviceListResponse(StrictModel):
    devices: list[AccountDeviceResponse] = Field(max_length=100)


class DeviceApprovalRequest(StrictModel):
    approval_token: str = Field(
        min_length=32,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class DeviceApprovalResponse(StrictModel):
    status: Literal["DEVICE_APPROVED"]
    device_key_id: str = Field(min_length=12, max_length=160)
    device_status: Literal["ACTIVE"]


class DeviceApprovalResendRequest(StrictModel):
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        pattern=r"^device:[A-Za-z0-9:_-]+$",
    )


class DeviceApprovalResendResponse(StrictModel):
    device_key_id: str = Field(min_length=12, max_length=160)
    device_status: Literal["PENDING_APPROVAL"]
    notification_status: Literal["PENDING", "SENT", "NOT_CONFIGURED", "FAILED"]


class RevokeAllDevicesResponse(StrictModel):
    status: Literal["ALL_DEVICES_REVOKED"]
    revoked_devices: int = Field(ge=0)
    sessions_revoked: bool


class MerchantStatusRequest(StrictModel):
    firebase_uid: str = Field(min_length=1, max_length=128, description="Firebase UID do empreendedor.")
    display_name: str = Field(min_length=2, max_length=120, description="Nome público do empreendedor.")
    establishment_id: str = Field(
        min_length=4,
        max_length=64,
        pattern=r"^EST-[A-Z0-9_-]+$",
        description="Identificador autoritativo do estabelecimento.",
    )
    establishment_name: str = Field(min_length=2, max_length=160, description="Nome do estabelecimento autorizado.")
    status: Literal["ACTIVE", "SUSPENDED"] = Field(description="Estado administrativo da conta comercial.")


class MerchantResponse(StrictModel):
    firebase_uid: str
    display_name: str
    establishment_id: str
    establishment_name: str
    status: Literal["ACTIVE", "SUSPENDED"]


class ProductCreateRequest(StrictModel):
    title: str = Field(min_length=2, max_length=160, description="Nome comercial do produto.")
    description: str = Field(default="", max_length=1000, description="Descrição pública do produto.")
    price_minor: int = Field(gt=0, le=1_000_000_000, description="Preço em centavos; nunca use ponto flutuante.")
    currency: Literal["BRL"] = Field(default="BRL", description="Moeda ISO 4217 da primeira fase.")
    stock_quantity: int = Field(ge=0, le=1_000_000, description="Estoque autoritativo inicial.")


class ProductStockRequest(StrictModel):
    stock_quantity: int = Field(ge=0, le=1_000_000, description="Novo estoque autoritativo do produto.")


class ProductResponse(StrictModel):
    product_id: str
    title: str
    description: str
    price_minor: int
    currency: str
    stock_quantity: int
    status: Literal["ACTIVE", "PAUSED", "ARCHIVED"]


class ProductListResponse(StrictModel):
    products: list[ProductResponse]


ProductId = Annotated[str, Field(pattern=r"^PROD-[A-Z0-9]{8,32}$")]
OfferId = Annotated[str, Field(pattern=r"^OFFER-[A-Z0-9]{12,32}$")]
ClientRequestId = Annotated[str, Field(min_length=8, max_length=100)]


class ProductBatchArchiveRequest(StrictModel):
    client_request_id: ClientRequestId
    product_ids: list[ProductId] = Field(min_length=1, max_length=25)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "ProductBatchArchiveRequest":
        if len(set(self.product_ids)) != len(self.product_ids):
            raise ValueError("product_ids must be unique")
        return self


class ProductBatchArchiveResponse(StrictModel):
    operation_id: str = Field(min_length=1, max_length=160)
    archived_count: int = Field(ge=1, le=25)
    products: list[ProductResponse] = Field(min_length=1, max_length=25)


class ProductBatchActivateItem(StrictModel):
    product_id: ProductId
    stock_quantity: int = Field(
        gt=0,
        le=1_000_000,
        description="Estoque que ficará disponível ao reativar o produto.",
    )


class ProductBatchActivateRequest(StrictModel):
    client_request_id: ClientRequestId
    items: list[ProductBatchActivateItem] = Field(min_length=1, max_length=25)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "ProductBatchActivateRequest":
        product_ids = [item.product_id for item in self.items]
        if len(set(product_ids)) != len(product_ids):
            raise ValueError("product_ids must be unique")
        return self


class ProductBatchActivateResponse(StrictModel):
    operation_id: str = Field(min_length=1, max_length=160)
    activated_count: int = Field(ge=1, le=25)
    products: list[ProductResponse] = Field(min_length=1, max_length=25)


class CatalogMerchantSummary(StrictModel):
    firebase_uid: str = Field(
        min_length=1,
        max_length=128,
        description="Identificador público do empreendedor usado na navegação para o perfil.",
    )
    display_name: str = Field(description="Nome público do empreendedor.")
    establishment_name: str = Field(description="Nome público do estabelecimento.")


class CatalogOfferSummary(StrictModel):
    offer_id: str = Field(description="Identificador público da oferta ao vivo.")
    original_amount_minor: int = Field(gt=0, description="Preço original autoritativo em centavos.")
    discount_amount_minor: int = Field(gt=0, description="Desconto autoritativo em centavos.")
    final_amount_minor: int = Field(gt=0, description="Preço final autoritativo em centavos.")
    currency: str = Field(description="Moeda ISO 4217 da oferta.")
    remaining_redemptions: int = Field(ge=0, description="Saldo resgatável considerando limite e estoque.")
    expires_at: int = Field(gt=0, description="Expiração da oferta em tempo Unix, em segundos.")
    created_at: int = Field(gt=0, description="Criação da oferta em tempo Unix, em segundos.")
    updated_at: int = Field(gt=0, description="Última alteração da oferta em tempo Unix, em segundos.")
    status: Literal["ACTIVE", "PAUSED", "ENDED"] = Field(description="Estado público da oferta.")
    status_reason: Literal[
        "PAUSED",
        "PRODUCT_PAUSED",
        "CANCELLED",
        "EXHAUSTED",
        "EXPIRED",
        "OUT_OF_STOCK",
    ] | None = Field(description="Motivo público da indisponibilidade, sem detalhes internos do token.")
    ended_at: int | None = Field(
        ge=1,
        description="Instante Unix do término definitivo; nulo em ofertas ativas ou pausadas.",
    )


class CatalogProductItem(StrictModel):
    product_id: str = Field(description="Identificador público do produto.")
    title: str = Field(description="Nome comercial do produto.")
    description: str = Field(description="Descrição pública do produto.")
    price_minor: int = Field(gt=0, description="Preço autoritativo do produto em centavos.")
    currency: str = Field(description="Moeda ISO 4217 do produto.")
    stock_quantity: int = Field(ge=0, description="Estoque autoritativo disponível.")
    created_at: int = Field(gt=0, description="Criação do produto em tempo Unix, em segundos.")
    updated_at: int = Field(gt=0, description="Última alteração do produto em tempo Unix, em segundos.")
    status: Literal["ACTIVE", "PAUSED", "ENDED"] = Field(description="Estado público do produto.")
    status_reason: Literal["PAUSED", "OUT_OF_STOCK"] | None = Field(
        description="Motivo público da indisponibilidade do produto."
    )
    ended_at: int | None = Field(
        ge=1,
        description="Instante Unix do término definitivo; nulo em produtos ativos ou pausados.",
    )
    merchant: CatalogMerchantSummary
    offers: list[CatalogOfferSummary] = Field(
        max_length=50,
        description="Até cinquenta ofertas atuais ou encerradas para o produto.",
    )


class CatalogFeedResponse(StrictModel):
    items: list[CatalogProductItem] = Field(
        max_length=50,
        description="Produtos públicos ordenados dos mais recentes para os mais antigos.",
    )


class PurchaseCurrencyTotalResponse(StrictModel):
    currency: str
    purchase_count: int = Field(ge=0)
    units_purchased: int = Field(ge=0)
    spent_amount_minor: int = Field(ge=0)
    saved_amount_minor: int = Field(ge=0)
    amounts_unavailable_count: int = Field(ge=0)


class VisitorPurchaseResponse(StrictModel):
    redemption_id: str
    merchant_uid: str
    merchant_name: str
    establishment_name: str | None
    product_id: str
    product_title: str
    quantity: int = Field(ge=1)
    currency: str
    original_amount_minor: int | None = Field(default=None, ge=0)
    final_amount_minor: int | None = Field(default=None, ge=0)
    saved_amount_minor: int = Field(ge=0)
    purchased_at: datetime


class VisitorPurchasesResponse(StrictModel):
    total_purchases: int = Field(ge=0)
    total_units: int = Field(ge=0)
    totals: list[PurchaseCurrencyTotalResponse]
    items: list[VisitorPurchaseResponse]
    limit: int = Field(ge=1, le=50)
    offset: int = Field(ge=0)
    has_more: bool


class CatalogMerchantProfileResponse(StrictModel):
    merchant: CatalogMerchantSummary
    products: list[CatalogProductItem] = Field(
        max_length=50,
        description="Produtos públicos atuais ou encerrados, exceto os arquivados.",
    )


class IssueCouponRequest(StrictModel):
    product_id: str = Field(
        pattern=r"^PROD-[A-Z0-9]{8,32}$",
        description="Produto autoritativo do próprio empreendedor.",
        examples=["PROD-A1B2C3D4E5F6"],
    )
    discount_type: Literal["PERCENT", "FIXED_AMOUNT"] = Field(
        description="Percentual inteiro ou valor fixo em centavos."
    )
    discount_value: int = Field(
        gt=0,
        le=1_000_000_000,
        description="Percentual inteiro quando PERCENT; centavos quando FIXED_AMOUNT.",
    )
    maximum_redemptions: int = Field(ge=1, le=10_000, description="Quantidade global máxima de resgates.")
    valid_until: datetime = Field(description="Validade com fuso horário explícito em ISO 8601.")
    purpose: Literal["LIVE_FAIR_DISCOUNT"] = Field(
        default="LIVE_FAIR_DISCOUNT",
        description="Finalidade fechada da oferta presencial da Fase 1.",
    )
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        description="Chave do dispositivo emissor previamente cadastrada.",
        examples=["device:expo:feirante:01"],
    )

    @model_validator(mode="after")
    def validate_discount_and_time(self) -> "IssueCouponRequest":
        if self.discount_type == "PERCENT" and self.discount_value > 90:
            raise ValueError("discount_value must be between 1 and 90 for PERCENT")
        if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:
            raise ValueError("valid_until must include an explicit timezone")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "product_id": "PROD-A1B2C3D4E5F6",
                    "discount_type": "PERCENT",
                    "discount_value": 20,
                    "maximum_redemptions": 10,
                    "valid_until": "2026-07-12T18:00:00-03:00",
                    "purpose": "LIVE_FAIR_DISCOUNT",
                    "device_key_id": "device:expo:feirante:01",
                }
            ]
        }
    )


class CompactQrPayload(StrictModel):
    type: Literal["trq-bec-offer-v1"] = Field(
        default="trq-bec-offer-v1",
        description="Discriminador do contrato compacto de QR da oferta ao vivo.",
    )
    v: Literal[1] = Field(default=1, description="Versão do contrato de QR.")
    token_ref: str = Field(
        min_length=22,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Referência opaca do token no servidor; o envelope assinado não é exposto no QR.",
        examples=["y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un"],
    )
    issuer_ref: str = Field(
        min_length=1,
        max_length=160,
        description="Referência pseudonimizada do emissor vinculada ao token.",
        examples=["issuer:4f1c5f4a93f2"],
    )
    expires_at: int = Field(
        description="Expiração do token em tempo Unix, em segundos.",
        examples=[1783811490],
    )
    quantity: int = Field(
        default=1,
        ge=1,
        le=1_000,
        description="Quantidade de unidades autorizada pelo vendedor para esta leitura.",
    )
    quantity_proof_b64u: str | None = Field(
        default=None,
        min_length=86,
        max_length=88,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Assinatura do backend que impede alteração da quantidade no QR.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "trq-bec-offer-v1",
                    "v": 1,
                    "token_ref": "y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un",
                    "issuer_ref": "issuer:4f1c5f4a93f2",
                    "expires_at": 1783811490,
                }
            ]
        }
    )


class OfferPreviewResponse(StrictModel):
    offer_id: str
    product_id: str
    product_title: str
    merchant_name: str
    establishment_name: str
    original_amount_minor: int
    discount_type: Literal["PERCENT", "FIXED_AMOUNT"]
    discount_value: int = Field(gt=0)
    discount_amount_minor: int
    final_amount_minor: int
    currency: str
    maximum_redemptions: int
    redeemed_count: int
    remaining_redemptions: int
    expires_at: int
    purpose: Literal["LIVE_FAIR_DISCOUNT"]
    status: Literal["ACTIVE", "PAUSED", "EXHAUSTED", "EXPIRED", "REVOKED", "CANCELLED"]
    purchase_quantity: int = Field(default=1, ge=1, le=1_000)


class OfferListResponse(StrictModel):
    offers: list[OfferPreviewResponse]


class OfferQrResponse(StrictModel):
    qr_payload: CompactQrPayload
    expires_at: int
    offer: OfferPreviewResponse


class OfferStatusRequest(StrictModel):
    status: Literal["ACTIVE", "PAUSED", "CANCELLED"]


class OfferBatchActionRequest(StrictModel):
    client_request_id: ClientRequestId
    action: Literal["DELETE", "INCREASE_DISCOUNT", "EXTEND_VALIDITY"]
    offer_ids: list[OfferId] = Field(min_length=1, max_length=25)
    discount_type: Literal["PERCENT", "FIXED_AMOUNT"] | None = None
    discount_delta: int | None = Field(default=None, gt=0, le=1_000_000_000)
    extension_minutes: int | None = Field(default=None, ge=1, le=360)
    device_key_id: str | None = Field(default=None, min_length=12, max_length=160)

    @model_validator(mode="after")
    def validate_action_fields(self) -> "OfferBatchActionRequest":
        if len(set(self.offer_ids)) != len(self.offer_ids):
            raise ValueError("offer_ids must be unique")
        if self.action == "DELETE":
            if any(
                value is not None
                for value in (
                    self.discount_type,
                    self.discount_delta,
                    self.extension_minutes,
                    self.device_key_id,
                )
            ):
                raise ValueError("DELETE does not accept rotation fields")
        elif self.action == "INCREASE_DISCOUNT":
            if (
                self.discount_type is None
                or self.discount_delta is None
                or self.device_key_id is None
                or self.extension_minutes is not None
            ):
                raise ValueError(
                    "INCREASE_DISCOUNT requires discount_type, discount_delta and device_key_id"
                )
        elif (
            self.extension_minutes is None
            or self.device_key_id is None
            or self.discount_type is not None
            or self.discount_delta is not None
        ):
            raise ValueError(
                "EXTEND_VALIDITY requires extension_minutes and device_key_id"
            )
        return self


class OfferBatchActionItemResponse(StrictModel):
    offer: OfferPreviewResponse
    qr_payload: CompactQrPayload | None


class OfferBatchActionResponse(StrictModel):
    operation_id: str = Field(min_length=1, max_length=160)
    action: Literal["DELETE", "INCREASE_DISCOUNT", "EXTEND_VALIDITY"]
    updated_count: int = Field(ge=1, le=25)
    items: list[OfferBatchActionItemResponse] = Field(min_length=1, max_length=25)


class PreviewCouponRequest(StrictModel):
    qr_payload: CompactQrPayload


class IssueCouponResponse(StrictModel):
    offer_id: str = Field(description="Identificador autoritativo da oferta ao vivo.")
    qr_payload: CompactQrPayload = Field(description="Payload compacto para codificação no QR do cupom.")
    expires_at: int = Field(description="Expiração do envelope em tempo Unix, em segundos.", examples=[1783811490])
    offer: OfferPreviewResponse = Field(description="Preço, desconto e disponibilidade calculados pelo backend.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "qr_payload": {
                        "type": "trq-bec-offer-v1",
                        "v": 1,
                        "token_ref": "y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un",
                        "issuer_ref": "issuer:4f1c5f4a93f2",
                        "expires_at": 1783811490,
                    },
                    "expires_at": 1783811490,
                }
            ]
        }
    )


class BeginRedemptionRequest(StrictModel):
    qr_payload: CompactQrPayload = Field(description="Payload de QR produzido pelo endpoint de emissão.")
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        description="Chave do dispositivo de resgate previamente cadastrada.",
        examples=["device:expo:visitante:01"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "qr_payload": {
                        "type": "trq-bec-offer-v1",
                        "v": 1,
                        "token_ref": "y2Q33r5Tgpiz7ibyWkFI9L7tt-Xah6un",
                        "issuer_ref": "issuer:4f1c5f4a93f2",
                        "expires_at": 1783811490,
                    },
                    "device_key_id": "device:expo:visitante:01",
                }
            ]
        }
    )


class ChallengeResponse(StrictModel):
    challenge_id: str = Field(description="Identificador do desafio de frescor de uso único.", examples=["challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e"])
    expires_at: int = Field(description="Expiração do desafio em tempo Unix, em segundos.", examples=[1783811445])


class BeginRedemptionResponse(StrictModel):
    operation_id: str = Field(description="Identificador estável da operação de resgate.", examples=["op:eea2915b-8783-4c98-9766-39df9c5fcf2e"])
    session_id: str = Field(description="Identificador da sessão vinculado ao desafio e ao dispositivo.", examples=["session:9d9f36e2-69ac-433d-a168-e4a4af1365ac"])
    challenge: ChallengeResponse
    proof_message_b64u: str = Field(
        description="Bytes exatos da mensagem, codificados em Base64URL sem preenchimento, que o dispositivo deve assinar.",
        examples=["VFJRLUJFQy9kZXZpY2UtcHJvb2YvdjE6ZXhhbXBsZS1wcm9vZi1tZXNzYWdl"],
    )
    offer: OfferPreviewResponse = Field(description="Snapshot autoritativo exibido antes da confirmação.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "operation_id": "op:eea2915b-8783-4c98-9766-39df9c5fcf2e",
                    "session_id": "session:9d9f36e2-69ac-433d-a168-e4a4af1365ac",
                    "challenge": {
                        "challenge_id": "challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e",
                        "expires_at": 1783811445,
                    },
                    "proof_message_b64u": "VFJRLUJFQy9kZXZpY2UtcHJvb2YvdjE6ZXhhbXBsZS1wcm9vZi1tZXNzYWdl",
                }
            ]
        }
    )


class AuthorizeRedemptionRequest(StrictModel):
    operation_id: str = Field(
        min_length=8,
        max_length=160,
        description="Identificador da operação retornado pela etapa de início.",
        examples=["op:eea2915b-8783-4c98-9766-39df9c5fcf2e"],
    )
    session_id: str = Field(
        min_length=8,
        max_length=160,
        description="Identificador da sessão retornado pela etapa de início.",
        examples=["session:9d9f36e2-69ac-433d-a168-e4a4af1365ac"],
    )
    challenge_id: str = Field(
        min_length=16,
        max_length=160,
        description="Identificador do desafio de uso único retornado pela etapa de início.",
        examples=["challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e"],
    )
    device_key_id: str = Field(
        min_length=12,
        max_length=160,
        description="Chave do dispositivo de resgate vinculada à operação.",
        examples=["device:expo:visitante:01"],
    )
    device_proof_b64u: str = Field(
        min_length=86,
        max_length=88,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Assinatura Ed25519 sobre `proof_message_b64u`, codificada em Base64URL sem preenchimento.",
        examples=["9gAbmslLvGHuEFDf8h39jnVSrzC-ns48Boo5yHpFtOuXJEh3tockZ39gAbmslLvGHuEFDf8h39jnVSrzC-ns48"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "operation_id": "op:eea2915b-8783-4c98-9766-39df9c5fcf2e",
                    "session_id": "session:9d9f36e2-69ac-433d-a168-e4a4af1365ac",
                    "challenge_id": "challenge:8d74f40a-70f0-4aa1-ae42-ef6749b6020e",
                    "device_key_id": "device:expo:visitante:01",
                    "device_proof_b64u": "9gAbmslLvGHuEFDf8h39jnVSrzC-ns48Boo5yHpFtOuXJEh3tockZ39gAbmslLvGHuEFDf8h39jnVSrzC-ns48",
                }
            ]
        }
    )


class AuthorizationResponse(StrictModel):
    decision: Literal["DENY", "ALLOW", "STEP_UP", "HOLD_OR_REVIEW"] = Field(
        description="Decisão determinística de autorização."
    )
    operation_id: str = Field(description="Identificador da operação de resgate.")
    crypto_ok: bool = Field(description="Indica se todos os gates criptográficos obrigatórios foram aprovados.")
    reason_codes: list[str] = Field(description="Motivos legíveis por máquina que sustentam a decisão.")
    coupon_id: str | None = Field(default=None, description="Cupom liberado somente quando a política permite sua exposição.")
    offer_id: str | None = Field(default=None, description="Oferta ao vivo resgatada.")
    product_id: str | None = Field(default=None, description="Produto vinculado à decisão.")
    amount_saved_minor: int | None = Field(default=None, description="Valor economizado em centavos.")
    final_amount_minor: int | None = Field(default=None, description="Preço final autoritativo em centavos.")
    remaining_redemptions: int | None = Field(default=None, description="Quantidade restante após o commit.")
    quantity: int | None = Field(default=None, ge=1, le=1_000, description="Unidades confirmadas nesta venda.")
    event_ref: str | None = Field(default=None, description="Referência do evento no ledger append-only.")
    idempotent: bool = Field(default=False, description="Verdadeiro quando se trata de repetição segura de uma operação já concluída.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "decision": "ALLOW",
                    "operation_id": "op:eea2915b-8783-4c98-9766-39df9c5fcf2e",
                    "crypto_ok": True,
                    "reason_codes": [],
                    "coupon_id": "OFFER-A1B2C3D4E5F6",
                    "event_ref": "event:36cc48bf-908f-4b90-b91e-57951a97be10",
                    "idempotent": False,
                }
            ]
        }
    )


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"] = Field(description="Estado geral da infraestrutura.")
    database: bool = Field(description="Conectividade com PostgreSQL.")
    redis: bool = Field(description="Conectividade com Redis.")
    crypto_provider: str = Field(description="Provider ativo ou estado explícito de laboratório com PQ bloqueado.")
    pqc_ready: bool = Field(description="Verdadeiro somente quando o provider PQC aprovado está pronto e passou pelo autoteste.")
    media_storage: MediaStorageHealth

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "database": True,
                    "redis": True,
                    "crypto_provider": "LAB_ED25519_PQ_BLOCKED",
                    "pqc_ready": False,
                    "media_storage": {
                        "provider": "gcs",
                        "enabled": False,
                        "configured": False,
                        "status": "disabled",
                    },
                }
            ]
        }
    )


class ServerTimeResponse(StrictModel):
    server_time_ms: int = Field(gt=0)
    server_time_iso: datetime
    timezone: Literal["UTC"] = "UTC"


class CryptoHealthResponse(StrictModel):
    provider: str = Field(description="Nome da implementação do provider.", examples=["UNAVAILABLE"])
    version: str = Field(description="Versão da implementação do provider.", examples=["0"])
    approved: bool = Field(description="Estado explícito de aprovação administrativa.", examples=[False])
    self_test_passed: bool = Field(description="Resultado do autoteste do provider na inicialização.", examples=[False])
    ml_kem_768: bool = Field(description="Disponibilidade de ML-KEM-768.", examples=[False])
    ml_dsa_65: bool = Field(description="Disponibilidade de ML-DSA-65.", examples=[False])
    ready: bool = Field(description="Prontidão agregada do provider usada pelos gates fail-closed.", examples=[False])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "provider": "UNAVAILABLE",
                    "version": "0",
                    "approved": False,
                    "self_test_passed": False,
                    "ml_kem_768": False,
                    "ml_dsa_65": False,
                    "ready": False,
                }
            ]
        }
    )


class LedgerCheckpointResponse(StrictModel):
    first_seq: int = Field(description="Primeira sequência do ledger incluída no checkpoint.", examples=[1])
    last_seq: int = Field(description="Última sequência do ledger incluída no checkpoint.", examples=[128])
    root_hash: str = Field(description="Hash do último evento da cadeia append-only coberta.", examples=["6fb9c64085cbd1e2234916f2ab6ad37c3de9a9d2c731e6052ee742c67358ee2a"])
    policy_version: str = Field(description="Versão de política vinculada ao checkpoint assinado.", examples=["liberrotas-policy-1"])
    checkpoint_id: str = Field(description="UUID do checkpoint.", examples=["574cfa87-0c9b-4f0c-9ee0-719ee5c06f80"])
    signature_b64u: str = Field(description="Assinatura do checkpoint codificada em Base64URL sem preenchimento.", examples=["K7vQnUi9x5xJjK0KruPz3XFGVyw4Hn8lF0GZwp5nVxFA3x7TQ9kZgD0tUnqLUc7G_BFQxw3V7v7aDzc9t5LjCg"])

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "first_seq": 1,
                    "last_seq": 128,
                    "root_hash": "6fb9c64085cbd1e2234916f2ab6ad37c3de9a9d2c731e6052ee742c67358ee2a",
                    "policy_version": "liberrotas-policy-1",
                    "checkpoint_id": "574cfa87-0c9b-4f0c-9ee0-719ee5c06f80",
                    "signature_b64u": "K7vQnUi9x5xJjK0KruPz3XFGVyw4Hn8lF0GZwp5nVxFA3x7TQ9kZgD0tUnqLUc7G_BFQxw3V7v7aDzc9t5LjCg",
                }
            ]
        }
    )


@dataclass(frozen=True, slots=True)
class Principal:
    uid: str
    role: str | None
    email: str | None
    claims: dict[str, Any]

    @property
    def is_entrepreneur(self) -> bool:
        return self.role == "entrepreneur"

    @property
    def is_visitor(self) -> bool:
        return self.role == "visitor"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin" and self.claims.get("admin") is True


@dataclass(frozen=True, slots=True)
class AccessAccountRecord:
    firebase_uid: str
    email: str | None
    role: str
    status: str
    allow_entrepreneur_fallback: bool
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrivilegedAccountValidationRecord:
    firebase_uid: str
    requested_role: str
    validation_state: str
    protection_level: str
    account_origin: str
    created_by_uid: str
    validated_by_uid: str | None
    validation_reason: str | None
    validated_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EmailVerificationQueueRecord:
    queue_id: UUID
    firebase_uid: str
    email: str
    status: str
    attempt_count: int
    next_attempt_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PublicProfileRecord:
    firebase_uid: str
    display_name: str
    normalized_name: str
    role: str
    city: str
    address: str | None
    category: str
    interests: tuple[str, ...]
    avatar_uri: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MediaAssetRecord:
    media_id: str
    owner_user_id: str
    entity_type: str
    entity_id: str
    media_role: str
    bucket_name: str
    object_key: str
    original_filename: str
    declared_content_type: str
    detected_content_type: str | None
    declared_size_bytes: int
    size_bytes: int | None
    checksum_sha256: str | None
    crc32c: str | None
    object_generation: int | None
    width: int | None
    height: int | None
    status: str
    visibility: str
    moderation_status: str
    rejection_reason: str | None
    client_request_id: str
    upload_expires_at: datetime
    created_at: datetime
    uploaded_at: datetime | None
    confirmed_at: datetime | None
    deleted_at: datetime | None
    created_by: str
    deleted_by: str | None
    version: int = 1


@dataclass(frozen=True, slots=True)
class MediaVariantRecord:
    media_id: str
    variant: str
    bucket_name: str
    object_key: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    crc32c: str | None
    object_generation: int | None
    width: int
    height: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GlobalSearchItemRecord:
    type: str
    item_id: str
    title: str
    subtitle: str | None
    owner_uid: str | None
    route: str
    status: str | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class ConversationRecord:
    conversation_id: str
    kind: str
    status: str
    subject: str | None
    created_by_uid: str
    requester_uid: str | None
    assigned_support_uid: str | None
    participant_uids: tuple[str, ...]
    last_message: str | None
    last_message_at: datetime | None
    unread_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PrivateMessageRecord:
    message_id: str
    conversation_id: str
    sender_uid: str
    client_message_id: str
    body: str
    media_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CommunityCommentRecord:
    comment_id: str
    post_id: str
    author_uid: str
    parent_comment_id: str | None
    client_comment_id: str
    body: str
    like_count: int
    liked_by_viewer: bool
    created_at: datetime
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MessageBlockRecord:
    blocker_uid: str
    blocked_uid: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AccessAccountSummaryRecord:
    firebase_uid: str
    email: str | None
    role: str
    status: str
    permissions: tuple[str, ...]
    created_at: datetime | None
    updated_at: datetime | None
    authority_validation_state: str | None = None
    protection_level: str | None = None
    account_origin: str | None = None
    authority_validated_at: datetime | None = None
    authority_validated_by_uid: str | None = None
    created_by_uid: str | None = None


@dataclass(frozen=True, slots=True)
class InstitutionProfileRecord:
    firebase_uid: str
    email: str
    name: str
    description: str | None
    city: str | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class InstitutionApplicationRecord:
    application_id: UUID
    organization_type: str
    organization_name: str
    contact_name: str
    email: str
    phone: str | None
    registration_number: str | None
    city: str
    state: str
    website_or_social: str | None
    description: str
    status: str
    support_notes: str | None
    reviewed_by_uid: str | None
    provisioned_uid: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class InstitutionGroupRecord:
    group_id: str
    owner_uid: str
    name: str
    description: str | None
    city: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    badge_policy: InstitutionBadgePolicy | None = None


@dataclass(frozen=True, slots=True)
class InstitutionMembershipRecord:
    membership_id: str
    group_id: str
    group_name: str
    institution_name: str
    seller_uid: str
    seller_name: str
    status: str
    invited_at: datetime
    responded_at: datetime | None
    active_from: datetime | None
    ended_at: datetime | None
    updated_at: datetime
    support_badge: str | None = None


@dataclass(frozen=True, slots=True)
class InstitutionSalesCurrencyTotalRecord:
    currency: str
    gross_original_amount_minor: int
    gross_final_amount_minor: int
    total_discount_amount_minor: int


@dataclass(frozen=True, slots=True)
class InstitutionSellerSalesRecord:
    membership_id: str
    group_id: str
    group_name: str
    seller_uid: str
    seller_name: str
    membership_status: str
    active_from: datetime
    ended_at: datetime | None
    confirmed_redemptions: int
    units_sold: int
    amounts_unavailable_count: int
    totals_by_currency: tuple[InstitutionSalesCurrencyTotalRecord, ...]


@dataclass(frozen=True, slots=True)
class InstitutionSalesReportRecord:
    confirmed_redemptions: int
    units_sold: int
    amounts_unavailable_count: int
    totals_by_currency: tuple[InstitutionSalesCurrencyTotalRecord, ...]
    sellers: tuple[InstitutionSellerSalesRecord, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class InstitutionFundedEventProductAllocationRecord:
    product_id: str
    product_title: str
    allocated_amount_minor: int
    allocation_mode: str


@dataclass(frozen=True, slots=True)
class InstitutionFundedEventSellerAllocationRecord:
    membership_id: str
    seller_uid: str
    seller_name: str
    allocated_amount_minor: int
    allocation_mode: str
    product_allocations: tuple[
        InstitutionFundedEventProductAllocationRecord, ...
    ]


@dataclass(frozen=True, slots=True)
class InstitutionFundedEventRecord:
    event_id: str
    owner_uid: str
    institution_name: str
    group_id: str
    group_name: str
    name: str
    description: str | None
    funding_source: str
    budget_amount_minor: int
    currency: str
    end_mode: str
    starts_at: datetime
    ends_at: datetime | None
    coupon_limit: int | None
    current_coupon_redemptions: int
    status: str
    end_reason: str | None
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None
    ended_at: datetime | None
    seller_allocations: tuple[InstitutionFundedEventSellerAllocationRecord, ...]
    badge_distribution: InstitutionBadgeDistribution | None = None


@dataclass(frozen=True, slots=True)
class InstitutionFundedEventProductReportRecord:
    product_id: str
    product_title: str
    allocated_amount_minor: int
    confirmed_redemptions: int
    units_sold: int
    gross_original_amount_minor: int
    gross_final_amount_minor: int
    discount_used_minor: int
    amount_due_minor: int
    unfunded_discount_minor: int
    remaining_budget_minor: int


@dataclass(frozen=True, slots=True)
class InstitutionFundedEventSellerReportRecord:
    seller_uid: str
    seller_name: str
    allocated_amount_minor: int
    confirmed_redemptions: int
    units_sold: int
    gross_original_amount_minor: int
    gross_final_amount_minor: int
    discount_used_minor: int
    amount_due_minor: int
    unfunded_discount_minor: int
    remaining_budget_minor: int
    products: tuple[InstitutionFundedEventProductReportRecord, ...]


@dataclass(frozen=True, slots=True)
class InstitutionFundedEventReportRecord:
    event: InstitutionFundedEventRecord
    confirmed_redemptions: int
    units_sold: int
    gross_original_amount_minor: int
    gross_final_amount_minor: int
    discount_used_minor: int
    amount_due_minor: int
    unfunded_discount_minor: int
    remaining_budget_minor: int
    sellers: tuple[InstitutionFundedEventSellerReportRecord, ...]


@dataclass(frozen=True, slots=True)
class AccessAuditEventRecord:
    event_id: str
    actor_uid: str
    target_uid: str
    event_type: str
    previous_status: str | None
    new_status: str
    reason: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InstitutionReportSummaryRecord:
    total_groups: int
    active_groups: int
    closed_groups: int
    last_group_created_at: datetime | None


@dataclass(frozen=True, slots=True)
class AdminOperationsSummaryRecord:
    accounts_total: int
    accounts_by_role: dict[str, int]
    accounts_by_status: dict[str, int]
    institutions_total: int
    groups_total: int
    groups_active: int
    merchants_active: int
    merchants_suspended: int
    products_active: int
    offers_active: int


@dataclass(frozen=True, slots=True)
class SecurityMonitoringSummaryRecord:
    accounts_total: int
    active_accounts: int
    suspended_accounts: int
    pending_accounts: int
    disabled_accounts: int
    recent_events_total: int
    last_event_at: datetime | None


@dataclass(frozen=True, slots=True)
class TrqBecSecurityStatusRecord:
    privileged_accounts_total: int
    official_accounts_total: int
    privileged_accounts_pending_validation: int
    access_events_total: int
    access_events_last_24h: int
    audit_events_total: int
    audit_checkpoints_total: int
    devices_active: int
    devices_pending: int
    devices_revoked: int
    device_notifications_failed: int
    email_verifications_pending: int
    email_verifications_failed: int
    latest_schema_migration: str | None


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    firebase_uid: str
    device_key_id: str
    public_key_b64u: str
    algorithm: str
    storage_profile: str
    status: str
    device_name: str | None = None
    platform: str = "unknown"
    model_name: str | None = None
    app_version: str | None = None
    notification_status: str = "NOT_REQUIRED"
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    approval_expires_at: datetime | None = None
    approval_last_sent_at: datetime | None = None
    approved_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CouponRecord:
    coupon_id: str
    owner_uid: str | None
    active: bool
    valid_until: int | None


@dataclass(frozen=True, slots=True)
class TokenRecord:
    token_ref: str
    issuer_uid: str
    issuer_ref: str
    coupon_id: str | None
    offer_id: str | None
    intent: dict[str, Any]
    envelope: dict[str, Any]
    expires_at: int
    status: str
    redeemed_operation_id: str | None


@dataclass(frozen=True, slots=True)
class OperationRecord:
    operation_id: str
    firebase_uid: str
    session_id: str
    token_ref: str
    device_key_id: str
    challenge_id: str
    replay_jti: str
    expires_at: int
    status: str
    result: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class AuditRecord:
    event_id: str
    seq: int
    event_hash: str


@dataclass(frozen=True, slots=True)
class MerchantRecord:
    firebase_uid: str
    display_name: str
    establishment_id: str
    establishment_name: str
    status: str


@dataclass(frozen=True, slots=True)
class CatalogMerchantRecord:
    firebase_uid: str
    display_name: str
    establishment_name: str


@dataclass(frozen=True, slots=True)
class CatalogOfferRecord:
    offer_id: str
    original_amount_minor: int
    discount_amount_minor: int
    final_amount_minor: int
    currency: str
    remaining_redemptions: int
    expires_at: int
    created_at: int
    updated_at: int
    status: str
    status_reason: str | None
    ended_at: int | None


@dataclass(frozen=True, slots=True)
class CatalogProductRecord:
    product_id: str
    title: str
    description: str
    price_minor: int
    currency: str
    stock_quantity: int
    created_at: int
    updated_at: int
    status: str
    status_reason: str | None
    ended_at: int | None
    merchant: CatalogMerchantRecord
    offers: tuple[CatalogOfferRecord, ...]


@dataclass(frozen=True, slots=True)
class ProductRecord:
    product_id: str
    merchant_uid: str
    title: str
    description: str
    price_minor: int
    currency: str
    stock_quantity: int
    status: str
    created_at: int | None = None
    updated_at: int | None = None


@dataclass(frozen=True, slots=True)
class OfferRecord:
    offer_id: str
    token_ref: str
    merchant_uid: str
    merchant_name: str
    establishment_name: str
    product_id: str
    product_title: str
    original_amount_minor: int
    discount_amount_minor: int
    final_amount_minor: int
    currency: str
    maximum_redemptions: int
    redeemed_count: int
    stock_quantity: int
    merchant_status: str
    product_status: str
    expires_at: int
    purpose: str
    status: str
    created_at: int | None = None
    updated_at: int | None = None
    discount_type: str = "PERCENT"
    discount_value: int = 1


@dataclass(frozen=True, slots=True)
class OfferBatchMutationRecord:
    offer_id: str
    expected_token_ref: str
    expected_discount_type: str
    expected_discount_value: int
    expected_expires_at: int
    new_discount_type: str
    new_discount_value: int
    new_discount_amount_minor: int
    new_final_amount_minor: int
    new_expires_at: int
    new_token: TokenRecord
