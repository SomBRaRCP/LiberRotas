"""Rotas de conversas privadas e bloqueio de perfis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from ..auth import require_principal
from ..docs import AUTHENTICATION_RESPONSE
from ..models import (
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageCreateRequest,
    ConversationReadResponse,
    DirectMessageCreateRequest,
    MessageBlockListResponse,
    MessageBlockResponse,
    Principal,
    PrivateMessageResponse,
)
from ..service import CouponSecurityService


router = APIRouter()


def _service(request: Request) -> CouponSecurityService:
    return request.app.state.service


@router.get(
    "/v1/messages/conversations",
    response_model=ConversationListResponse,
    tags=["Mensagens"],
    summary="Listar as conversas privadas da conta",
    operation_id="listPrivateConversations",
    responses=AUTHENTICATION_RESPONSE,
)
def list_message_conversations(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_principal),
) -> ConversationListResponse:
    return _service(request).list_message_conversations(principal, limit)


@router.get(
    "/v1/messages/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    tags=["Mensagens"],
    summary="Consultar uma conversa privada",
    operation_id="getPrivateConversation",
    responses=AUTHENTICATION_RESPONSE,
)
def get_message_conversation(
    request: Request,
    conversation_id: str = Path(min_length=1, max_length=160),
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(require_principal),
) -> ConversationDetailResponse:
    return _service(request).get_message_conversation(principal, conversation_id, limit)


@router.post(
    "/v1/messages",
    response_model=ConversationDetailResponse,
    status_code=201,
    tags=["Mensagens"],
    summary="Iniciar ou reutilizar uma conversa direta",
    operation_id="createDirectMessage",
    responses=AUTHENTICATION_RESPONSE,
)
def create_direct_message(
    payload: DirectMessageCreateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> ConversationDetailResponse:
    return _service(request).create_direct_message(principal, payload)


@router.post(
    "/v1/messages/conversations/{conversation_id}/messages",
    response_model=PrivateMessageResponse,
    status_code=201,
    tags=["Mensagens"],
    summary="Enviar uma mensagem na conversa",
    operation_id="sendPrivateConversationMessage",
    responses=AUTHENTICATION_RESPONSE,
)
def send_conversation_message(
    payload: ConversationMessageCreateRequest,
    request: Request,
    conversation_id: str = Path(min_length=1, max_length=160),
    principal: Principal = Depends(require_principal),
) -> PrivateMessageResponse:
    return _service(request).send_conversation_message(principal, conversation_id, payload)


@router.post(
    "/v1/messages/conversations/{conversation_id}/read",
    response_model=ConversationReadResponse,
    tags=["Mensagens"],
    summary="Marcar a conversa como lida",
    operation_id="markPrivateConversationRead",
    responses=AUTHENTICATION_RESPONSE,
)
def mark_conversation_read(
    request: Request,
    conversation_id: str = Path(min_length=1, max_length=160),
    principal: Principal = Depends(require_principal),
) -> ConversationReadResponse:
    return _service(request).mark_conversation_read(principal, conversation_id)


@router.get(
    "/v1/messages/blocks",
    response_model=MessageBlockListResponse,
    tags=["Mensagens"],
    summary="Listar perfis bloqueados",
    operation_id="listMessageBlocks",
    responses=AUTHENTICATION_RESPONSE,
)
def list_message_blocks(
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(require_principal),
) -> MessageBlockListResponse:
    return _service(request).list_message_blocks(principal, limit)


@router.post(
    "/v1/messages/blocks/{uid}",
    response_model=MessageBlockResponse,
    tags=["Mensagens"],
    summary="Bloquear um perfil",
    operation_id="blockMessageProfile",
    responses=AUTHENTICATION_RESPONSE,
)
@router.put(
    "/v1/messages/blocks/{uid}",
    response_model=MessageBlockResponse,
    tags=["Mensagens"],
    summary="Bloquear um perfil (alias idempotente)",
    operation_id="putMessageBlock",
    include_in_schema=False,
)
def block_profile(
    request: Request,
    uid: str = Path(min_length=1, max_length=128),
    principal: Principal = Depends(require_principal),
) -> MessageBlockResponse:
    return _service(request).block_profile(principal, uid)


@router.delete(
    "/v1/messages/blocks/{uid}",
    status_code=204,
    tags=["Mensagens"],
    summary="Desbloquear um perfil",
    operation_id="unblockMessageProfile",
    responses=AUTHENTICATION_RESPONSE,
)
def unblock_profile(
    request: Request,
    uid: str = Path(min_length=1, max_length=128),
    principal: Principal = Depends(require_principal),
) -> Response:
    _service(request).unblock_profile(principal, uid)
    return Response(status_code=204)
