"""Rotas da caixa privada de chamados de suporte."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request

from ..auth import require_principal
from ..docs import AUTHENTICATION_RESPONSE
from ..models import (
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageCreateRequest,
    ConversationResponse,
    Principal,
    PrivateMessageResponse,
    SupportRequestCreateRequest,
)
from ..service import CouponSecurityService


router = APIRouter()


def _service(request: Request) -> CouponSecurityService:
    return request.app.state.service


@router.post(
    "/v1/support/requests",
    response_model=ConversationDetailResponse,
    status_code=201,
    tags=["Suporte"],
    summary="Abrir uma solicitacao privada de suporte",
    operation_id="createSupportRequest",
    responses=AUTHENTICATION_RESPONSE,
)
def create_support_request(
    payload: SupportRequestCreateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> ConversationDetailResponse:
    return _service(request).create_support_request(principal, payload)


@router.get(
    "/v1/support/requests",
    response_model=ConversationListResponse,
    tags=["Suporte"],
    summary="Listar a caixa de entrada do suporte",
    operation_id="listSupportRequests",
    responses=AUTHENTICATION_RESPONSE,
)
def list_support_requests(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_principal),
) -> ConversationListResponse:
    return _service(request).list_support_requests(principal, limit)


@router.get(
    "/v1/support/requests/{conversation_id}",
    response_model=ConversationDetailResponse,
    tags=["Suporte"],
    summary="Consultar uma solicitacao de suporte",
    operation_id="getSupportRequest",
    responses=AUTHENTICATION_RESPONSE,
)
def get_support_request(
    request: Request,
    conversation_id: str = Path(min_length=1, max_length=160),
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(require_principal),
) -> ConversationDetailResponse:
    return _service(request).get_support_request(principal, conversation_id, limit)


@router.post(
    "/v1/support/requests/{conversation_id}/messages",
    response_model=PrivateMessageResponse,
    status_code=201,
    tags=["Suporte"],
    summary="Responder uma solicitacao de suporte",
    operation_id="sendSupportRequestMessage",
    responses=AUTHENTICATION_RESPONSE,
)
def send_support_request_message(
    payload: ConversationMessageCreateRequest,
    request: Request,
    conversation_id: str = Path(min_length=1, max_length=160),
    principal: Principal = Depends(require_principal),
) -> PrivateMessageResponse:
    return _service(request).send_conversation_message(
        principal,
        conversation_id,
        payload,
        support_actor=True,
    )


@router.post(
    "/v1/support/requests/{conversation_id}/resolve",
    response_model=ConversationResponse,
    tags=["Suporte"],
    summary="Resolver uma solicitacao de suporte",
    operation_id="resolveSupportRequest",
    responses=AUTHENTICATION_RESPONSE,
)
def resolve_support_request(
    request: Request,
    conversation_id: str = Path(min_length=1, max_length=160),
    principal: Principal = Depends(require_principal),
) -> ConversationResponse:
    return _service(request).resolve_support_request(principal, conversation_id)
