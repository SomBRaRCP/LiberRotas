"""Rotas de perfil, grupos, filiacao, eventos financiados e relatorios institucionais."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Request

from ..auth import require_principal
from ..docs import AUTHENTICATION_RESPONSE
from ..models import (
    EntrepreneurFundedEventListResponse,
    EntrepreneurFundedEventReportResponse,
    EntrepreneurFundedEventResponse,
    InstitutionEventProductAllocationUpdateRequest,
    InstitutionEventSellerAllocationUpdateRequest,
    InstitutionFundedEventCreateRequest,
    InstitutionFundedEventListResponse,
    InstitutionFundedEventReportResponse,
    InstitutionFundedEventResponse,
    InstitutionGroupCreateRequest,
    InstitutionGroupListResponse,
    InstitutionGroupResponse,
    InstitutionMembershipListResponse,
    InstitutionMembershipResponse,
    InstitutionProfileUpdateRequest,
    InstitutionReportSummaryResponse,
    InstitutionResponse,
    InstitutionSalesReportResponse,
    InstitutionSellerInvitationCreateRequest,
    Principal,
)
from ..service import CouponSecurityService


router = APIRouter()


def _service(request: Request) -> CouponSecurityService:
    return request.app.state.service


@router.get(
    "/v1/institution/profile",
    response_model=InstitutionResponse,
    tags=["Instituicao"],
    summary="Consultar o proprio perfil institucional",
    operation_id="getOwnInstitutionProfile",
    responses=AUTHENTICATION_RESPONSE,
)
def get_institution_profile(
    request: Request,
    principal: Principal = Depends(require_principal),
) -> InstitutionResponse:
    return _service(request).get_institution_profile(principal)


@router.patch(
    "/v1/institution/profile",
    response_model=InstitutionResponse,
    tags=["Instituicao"],
    summary="Atualizar campos publicos do proprio perfil institucional",
    operation_id="updateOwnInstitutionProfile",
    responses=AUTHENTICATION_RESPONSE,
)
def update_institution_profile(
    payload: InstitutionProfileUpdateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> InstitutionResponse:
    return _service(request).update_institution_profile(principal, payload)


@router.get(
    "/v1/institution/reports/summary",
    response_model=InstitutionReportSummaryResponse,
    tags=["Instituicao"],
    summary="Consultar agregados dos proprios grupos",
    operation_id="getOwnInstitutionReportSummary",
    responses=AUTHENTICATION_RESPONSE,
)
def institution_report_summary(
    request: Request,
    principal: Principal = Depends(require_principal),
) -> InstitutionReportSummaryResponse:
    return _service(request).institution_report_summary(principal)


@router.post(
    "/v1/institution/groups",
    response_model=InstitutionGroupResponse,
    status_code=201,
    tags=["Instituicao"],
    summary="Criar um grupo da instituicao autenticada",
    operation_id="createInstitutionGroup",
    responses=AUTHENTICATION_RESPONSE,
)
def create_institution_group(
    payload: InstitutionGroupCreateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> InstitutionGroupResponse:
    return _service(request).create_institution_group(principal, payload)


@router.get(
    "/v1/institution/groups",
    response_model=InstitutionGroupListResponse,
    tags=["Instituicao"],
    summary="Listar somente os grupos da instituicao autenticada",
    operation_id="listInstitutionGroups",
    responses=AUTHENTICATION_RESPONSE,
)
def list_institution_groups(
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(require_principal),
) -> InstitutionGroupListResponse:
    return _service(request).list_institution_groups(principal, limit)


@router.post(
    "/v1/institution/groups/{group_id}/close",
    response_model=InstitutionGroupResponse,
    tags=["Instituicao"],
    summary="Encerrar um grupo proprio",
    operation_id="closeInstitutionGroup",
    responses=AUTHENTICATION_RESPONSE,
)
def close_institution_group(
    request: Request,
    group_id: str = Path(
        min_length=13,
        max_length=40,
        pattern=r"^IGRP-[A-Z0-9]+$",
    ),
    principal: Principal = Depends(require_principal),
) -> InstitutionGroupResponse:
    return _service(request).close_institution_group(principal, group_id)


@router.post(
    "/v1/institution/groups/{group_id}/invitations",
    response_model=InstitutionMembershipResponse,
    status_code=201,
    tags=["Instituicao"],
    summary="Convidar vendedor pelo nome publico unico",
    operation_id="inviteInstitutionSeller",
    responses=AUTHENTICATION_RESPONSE,
)
def invite_institution_seller(
    payload: InstitutionSellerInvitationCreateRequest,
    request: Request,
    group_id: str = Path(min_length=13, max_length=40, pattern=r"^IGRP-[A-Z0-9]+$"),
    principal: Principal = Depends(require_principal),
) -> InstitutionMembershipResponse:
    return _service(request).invite_institution_seller(principal, group_id, payload)


@router.get(
    "/v1/institution/groups/{group_id}/members",
    response_model=InstitutionMembershipListResponse,
    tags=["Instituicao"],
    summary="Listar filiacoes de um grupo proprio",
    operation_id="listInstitutionGroupMembers",
    responses=AUTHENTICATION_RESPONSE,
)
def list_institution_group_memberships(
    request: Request,
    group_id: str = Path(min_length=13, max_length=40, pattern=r"^IGRP-[A-Z0-9]+$"),
    status: Literal["PENDING", "ACTIVE", "DECLINED", "REMOVED", "LEFT"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    principal: Principal = Depends(require_principal),
) -> InstitutionMembershipListResponse:
    return _service(request).list_institution_group_memberships(
        principal, group_id, status, limit, offset
    )


@router.get(
    "/v1/entrepreneur/institution-invitations",
    response_model=InstitutionMembershipListResponse,
    tags=["Instituicao"],
    summary="Listar convites e filiacoes do empreendedor autenticado",
    operation_id="listOwnInstitutionInvitations",
    responses=AUTHENTICATION_RESPONSE,
)
def list_entrepreneur_institution_memberships(
    request: Request,
    status: Literal["PENDING", "ACTIVE", "DECLINED", "REMOVED", "LEFT"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    principal: Principal = Depends(require_principal),
) -> InstitutionMembershipListResponse:
    return _service(request).list_entrepreneur_institution_memberships(
        principal, status, limit, offset
    )


@router.post(
    "/v1/entrepreneur/institution-invitations/{membership_id}/accept",
    response_model=InstitutionMembershipResponse,
    tags=["Instituicao"],
    summary="Aceitar convite institucional proprio",
    operation_id="acceptInstitutionInvitation",
    responses=AUTHENTICATION_RESPONSE,
)
def accept_institution_invitation(
    request: Request,
    membership_id: str = Path(min_length=20, max_length=36, pattern=r"^IGM-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> InstitutionMembershipResponse:
    return _service(request).respond_institution_invitation(
        principal, membership_id, "ACCEPT"
    )


@router.post(
    "/v1/entrepreneur/institution-invitations/{membership_id}/decline",
    response_model=InstitutionMembershipResponse,
    tags=["Instituicao"],
    summary="Recusar convite institucional proprio",
    operation_id="declineInstitutionInvitation",
    responses=AUTHENTICATION_RESPONSE,
)
def decline_institution_invitation(
    request: Request,
    membership_id: str = Path(min_length=20, max_length=36, pattern=r"^IGM-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> InstitutionMembershipResponse:
    return _service(request).respond_institution_invitation(
        principal, membership_id, "DECLINE"
    )


@router.post(
    "/v1/entrepreneur/institution-memberships/{membership_id}/leave",
    response_model=InstitutionMembershipResponse,
    tags=["Instituicao"],
    summary="Sair da filiacao institucional ativa",
    operation_id="leaveInstitutionMembership",
    responses=AUTHENTICATION_RESPONSE,
)
def leave_institution_membership(
    request: Request,
    membership_id: str = Path(min_length=20, max_length=36, pattern=r"^IGM-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> InstitutionMembershipResponse:
    return _service(request).leave_institution_membership(principal, membership_id)


@router.post(
    "/v1/institution/groups/{group_id}/members/{membership_id}/remove",
    response_model=InstitutionMembershipResponse,
    tags=["Instituicao"],
    summary="Remover convite pendente ou vendedor ativo de grupo proprio",
    operation_id="removeInstitutionGroupMember",
    responses=AUTHENTICATION_RESPONSE,
)
def remove_institution_group_member(
    request: Request,
    group_id: str = Path(min_length=13, max_length=40, pattern=r"^IGRP-[A-Z0-9]+$"),
    membership_id: str = Path(min_length=20, max_length=36, pattern=r"^IGM-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> InstitutionMembershipResponse:
    return _service(request).remove_institution_group_member(
        principal, group_id, membership_id
    )


@router.get(
    "/v1/institution/reports/sales",
    response_model=InstitutionSalesReportResponse,
    tags=["Instituicao"],
    summary="Relatorio de resgates dos vendedores afiliados",
    description=(
        "Conta somente resgates REDEEMED durante a vigencia da filiacao. "
        "Valores nao comprovam recebimento financeiro."
    ),
    operation_id="getInstitutionSalesReport",
    responses=AUTHENTICATION_RESPONSE,
)
def institution_sales_report(
    request: Request,
    group_id: str | None = Query(
        default=None, min_length=13, max_length=40, pattern=r"^IGRP-[A-Z0-9]+$"
    ),
    period_from: datetime | None = Query(default=None, alias="from"),
    period_to: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
    principal: Principal = Depends(require_principal),
) -> InstitutionSalesReportResponse:
    return _service(request).institution_sales_report(
        principal, group_id, period_from, period_to, limit, offset
    )


@router.post(
    "/v1/institution/funded-events",
    response_model=InstitutionFundedEventResponse,
    status_code=201,
    tags=["Instituicao"],
    summary="Criar evento com verba promocional",
    description=(
        "Cria o evento em rascunho e divide a verba igualmente entre os "
        "afiliados ativos. A instituicao pode ajustar as cotas antes de ativar."
    ),
    operation_id="createInstitutionFundedEvent",
    responses=AUTHENTICATION_RESPONSE,
)
def create_institution_funded_event(
    payload: InstitutionFundedEventCreateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> InstitutionFundedEventResponse:
    return _service(request).create_institution_funded_event(principal, payload)


@router.get(
    "/v1/institution/funded-events",
    response_model=InstitutionFundedEventListResponse,
    tags=["Instituicao"],
    summary="Listar eventos promocionais da instituicao",
    operation_id="listInstitutionFundedEvents",
    responses=AUTHENTICATION_RESPONSE,
)
def list_institution_funded_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_principal),
) -> InstitutionFundedEventListResponse:
    return _service(request).list_institution_funded_events(principal, limit)


@router.put(
    "/v1/institution/funded-events/{event_id}/seller-allocations",
    response_model=InstitutionFundedEventResponse,
    tags=["Instituicao"],
    summary="Ajustar a divisao da verba entre afiliados",
    operation_id="setInstitutionEventSellerAllocations",
    responses=AUTHENTICATION_RESPONSE,
)
def set_institution_event_seller_allocations(
    payload: InstitutionEventSellerAllocationUpdateRequest,
    request: Request,
    event_id: str = Path(min_length=21, max_length=37, pattern=r"^IEVT-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> InstitutionFundedEventResponse:
    return _service(request).set_institution_event_seller_allocations(
        principal, event_id, payload
    )


@router.post(
    "/v1/institution/funded-events/{event_id}/activate",
    response_model=InstitutionFundedEventResponse,
    tags=["Instituicao"],
    summary="Ativar evento e congelar a divisao da verba",
    operation_id="activateInstitutionFundedEvent",
    responses=AUTHENTICATION_RESPONSE,
)
def activate_institution_funded_event(
    request: Request,
    event_id: str = Path(min_length=21, max_length=37, pattern=r"^IEVT-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> InstitutionFundedEventResponse:
    return _service(request).activate_institution_funded_event(principal, event_id)


@router.post(
    "/v1/institution/funded-events/{event_id}/end",
    response_model=InstitutionFundedEventResponse,
    tags=["Instituicao"],
    summary="Encerrar manualmente um evento ativo",
    operation_id="endInstitutionFundedEvent",
    responses=AUTHENTICATION_RESPONSE,
)
def end_institution_funded_event(
    request: Request,
    event_id: str = Path(min_length=21, max_length=37, pattern=r"^IEVT-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> InstitutionFundedEventResponse:
    return _service(request).end_institution_funded_event(principal, event_id)


@router.get(
    "/v1/institution/funded-events/{event_id}/report",
    response_model=InstitutionFundedEventReportResponse,
    tags=["Instituicao"],
    summary="Consultar relatorio financeiro do evento",
    description=(
        "Calcula vendas, descontos financiados, saldo e valor a pagar por "
        "afiliado e produto. Nao executa pagamentos."
    ),
    operation_id="getInstitutionFundedEventReport",
    responses=AUTHENTICATION_RESPONSE,
)
def institution_funded_event_report(
    request: Request,
    event_id: str = Path(min_length=21, max_length=37, pattern=r"^IEVT-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> InstitutionFundedEventReportResponse:
    return _service(request).institution_funded_event_report(principal, event_id)


@router.get(
    "/v1/entrepreneur/funded-events",
    response_model=EntrepreneurFundedEventListResponse,
    tags=["Instituicao"],
    summary="Listar eventos em que o empreendedor recebeu verba",
    operation_id="listEntrepreneurFundedEvents",
    responses=AUTHENTICATION_RESPONSE,
)
def list_entrepreneur_funded_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_principal),
) -> EntrepreneurFundedEventListResponse:
    return _service(request).list_entrepreneur_funded_events(principal, limit)


@router.get(
    "/v1/entrepreneur/funded-events/{event_id}/report",
    response_model=EntrepreneurFundedEventReportResponse,
    tags=["Instituicao"],
    summary="Consultar o proprio repasse de um evento financiado",
    description=(
        "Devolve apenas as vendas e os valores do empreendedor autenticado, "
        "separados por produto. Nao expoe os dados dos demais afiliados."
    ),
    operation_id="getEntrepreneurFundedEventReport",
    responses=AUTHENTICATION_RESPONSE,
)
def entrepreneur_funded_event_report(
    request: Request,
    event_id: str = Path(min_length=21, max_length=37, pattern=r"^IEVT-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> EntrepreneurFundedEventReportResponse:
    return _service(request).entrepreneur_funded_event_report(principal, event_id)


@router.put(
    "/v1/entrepreneur/funded-events/{event_id}/product-allocations",
    response_model=EntrepreneurFundedEventResponse,
    tags=["Instituicao"],
    summary="Ajustar a verba do empreendedor entre seus produtos",
    operation_id="setInstitutionEventProductAllocations",
    responses=AUTHENTICATION_RESPONSE,
)
def set_institution_event_product_allocations(
    payload: InstitutionEventProductAllocationUpdateRequest,
    request: Request,
    event_id: str = Path(min_length=21, max_length=37, pattern=r"^IEVT-[A-Z0-9]{16,32}$"),
    principal: Principal = Depends(require_principal),
) -> EntrepreneurFundedEventResponse:
    return _service(request).set_institution_event_product_allocations(
        principal, event_id, payload
    )
