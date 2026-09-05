"""Rotas públicas de emissão, prévia e autorização de resgates TRQ-BEC."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import require_principal
from ..docs import (
    AUTHENTICATION_RESPONSE,
    AUTHORIZE_CONFLICT_RESPONSE,
    AUTHORIZE_NOT_FOUND_RESPONSE,
    AUTHORIZE_UNAVAILABLE_RESPONSE,
    BEGIN_BAD_REQUEST_RESPONSE,
    BEGIN_CONFLICT_RESPONSE,
    BEGIN_EXPIRED_RESPONSE,
    BEGIN_FORBIDDEN_RESPONSE,
    BEGIN_NOT_FOUND_RESPONSE,
    BEGIN_UNAVAILABLE_RESPONSE,
    ISSUE_FORBIDDEN_RESPONSE,
    ISSUE_NOT_FOUND_RESPONSE,
    ISSUE_UNAVAILABLE_RESPONSE,
)
from ..models import (
    AuthorizationResponse,
    AuthorizeRedemptionRequest,
    BeginRedemptionRequest,
    BeginRedemptionResponse,
    IssueCouponRequest,
    IssueCouponResponse,
    OfferPreviewResponse,
    PreviewCouponRequest,
    Principal,
)
from ..service import CouponSecurityService


router = APIRouter()


def _service(request: Request) -> CouponSecurityService:
    return request.app.state.service


@router.post(
    "/v1/trq-bec/coupons/issue",
    response_model=IssueCouponResponse,
    tags=["Cupons"],
    summary="Emitir um cupom protegido",
    description=(
        "Busca produto, preço e estoque no PostgreSQL, calcula o desconto e emite uma oferta opaca. "
        "Exige claim `role=entrepreneur`, conta comercial ativa e dispositivo previamente cadastrado."
    ),
    operation_id="issueCoupon",
    response_description="Payload compacto para QR e prazo de validade do envelope.",
    responses={
        **AUTHENTICATION_RESPONSE,
        **ISSUE_FORBIDDEN_RESPONSE,
        **ISSUE_NOT_FOUND_RESPONSE,
        **ISSUE_UNAVAILABLE_RESPONSE,
    },
)
def issue_coupon(
    payload: IssueCouponRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> IssueCouponResponse:
    return _service(request).issue_coupon(principal, payload)


@router.post(
    "/v1/trq-bec/coupons/preview",
    response_model=OfferPreviewResponse,
    tags=["Cupons"],
    summary="Consultar oferta sem produzir resgate",
    description="Resolve a referência opaca e devolve preço, desconto, validade e saldo calculados no servidor.",
    operation_id="previewCouponOffer",
    responses={
        **AUTHENTICATION_RESPONSE,
        **BEGIN_BAD_REQUEST_RESPONSE,
        **BEGIN_NOT_FOUND_RESPONSE,
        **BEGIN_CONFLICT_RESPONSE,
        **BEGIN_EXPIRED_RESPONSE,
        **BEGIN_UNAVAILABLE_RESPONSE,
    },
)
def preview_coupon(
    payload: PreviewCouponRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> OfferPreviewResponse:
    return _service(request).preview_coupon(principal, payload)


@router.post(
    "/v1/trq-bec/coupons/redeem/begin",
    response_model=BeginRedemptionResponse,
    tags=["Resgate"],
    summary="Iniciar o resgate e emitir um desafio",
    description=(
        "Valida o vínculo do QR, o estado do token e o dispositivo do visitante. "
        "Cria uma operação, uma sessão e um desafio de uso único, retornando a mensagem exata que deverá ser assinada no dispositivo."
    ),
    operation_id="beginCouponRedemption",
    response_description="Operação pendente, desafio de frescor e mensagem para prova de posse.",
    responses={
        **AUTHENTICATION_RESPONSE,
        **BEGIN_BAD_REQUEST_RESPONSE,
        **BEGIN_FORBIDDEN_RESPONSE,
        **BEGIN_NOT_FOUND_RESPONSE,
        **BEGIN_CONFLICT_RESPONSE,
        **BEGIN_EXPIRED_RESPONSE,
        **BEGIN_UNAVAILABLE_RESPONSE,
    },
)
def begin_redemption(
    payload: BeginRedemptionRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> BeginRedemptionResponse:
    return _service(request).begin_redemption(principal, payload)


@router.post(
    "/v1/trq-bec/coupons/redeem/authorize",
    response_model=AuthorizationResponse,
    tags=["Resgate"],
    summary="Autorizar o resgate mediante prova de posse",
    description=(
        "Consome o desafio de uso único, valida a assinatura do dispositivo, reserva replay de forma distribuída, "
        "executa os gates criptográficos e aplica a política determinística. Repetições da mesma operação são idempotentes."
    ),
    operation_id="authorizeCouponRedemption",
    response_description="Decisão autoritativa e referência de evidência no ledger.",
    responses={
        **AUTHENTICATION_RESPONSE,
        **AUTHORIZE_NOT_FOUND_RESPONSE,
        **AUTHORIZE_CONFLICT_RESPONSE,
        **AUTHORIZE_UNAVAILABLE_RESPONSE,
    },
)
def authorize_redemption(
    payload: AuthorizeRedemptionRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> AuthorizationResponse:
    return _service(request).authorize_redemption(principal, payload)
