"""Rotas de publicações, comentários, pontos curados e feiras."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request

from ..auth import require_principal
from ..docs import AUTHENTICATION_RESPONSE
from ..models import (
    CommunityCommentCreateRequest,
    CommunityCommentDeleteResponse,
    CommunityCommentLikeResponse,
    CommunityCommentListResponse,
    CommunityCommentResponse,
    CommunityCommentUpdateRequest,
    CommunityContentMutationResponse,
    CommunityDocumentResponse,
    CommunityPostCreateRequest,
    CommunityPostUpdateRequest,
    CuratedPlaceCreateRequest,
    LiveFairCreateRequest,
    Principal,
)
from ..service import CouponSecurityService


router = APIRouter()


def _service(request: Request) -> CouponSecurityService:
    return request.app.state.service


@router.get(
    "/v1/feed/posts/{post_id}/comments",
    response_model=CommunityCommentListResponse,
    tags=["Feed"],
    summary="Listar comentarios e respostas de uma publicacao",
    operation_id="listPostComments",
    responses=AUTHENTICATION_RESPONSE,
)
def list_post_comments(
    request: Request,
    post_id: str = Path(min_length=1, max_length=160),
    limit: int = Query(default=100, ge=1, le=200),
    principal: Principal = Depends(require_principal),
) -> CommunityCommentListResponse:
    return _service(request).list_post_comments(principal, post_id, limit)


@router.post(
    "/v1/feed/posts/{post_id}/comments",
    response_model=CommunityCommentResponse,
    status_code=201,
    tags=["Feed"],
    summary="Comentar ou responder uma publicacao",
    operation_id="createPostComment",
    responses=AUTHENTICATION_RESPONSE,
)
def create_post_comment(
    payload: CommunityCommentCreateRequest,
    request: Request,
    post_id: str = Path(min_length=1, max_length=160),
    principal: Principal = Depends(require_principal),
) -> CommunityCommentResponse:
    return _service(request).create_post_comment(principal, post_id, payload)


@router.patch(
    "/v1/feed/comments/{comment_id}",
    response_model=CommunityCommentResponse,
    tags=["Feed"],
    summary="Editar um comentario proprio",
    operation_id="updatePostComment",
    responses=AUTHENTICATION_RESPONSE,
)
def update_post_comment(
    payload: CommunityCommentUpdateRequest,
    request: Request,
    comment_id: str = Path(min_length=8, max_length=160),
    principal: Principal = Depends(require_principal),
) -> CommunityCommentResponse:
    return _service(request).update_post_comment(principal, comment_id, payload)


@router.delete(
    "/v1/feed/comments/{comment_id}",
    response_model=CommunityCommentDeleteResponse,
    tags=["Feed"],
    summary="Excluir um comentario proprio",
    operation_id="deletePostComment",
    responses=AUTHENTICATION_RESPONSE,
)
def delete_post_comment(
    request: Request,
    comment_id: str = Path(min_length=8, max_length=160),
    principal: Principal = Depends(require_principal),
) -> CommunityCommentDeleteResponse:
    return _service(request).delete_post_comment(principal, comment_id)


@router.put(
    "/v1/feed/comments/{comment_id}/like",
    response_model=CommunityCommentLikeResponse,
    tags=["Feed"],
    summary="Curtir um comentario ou resposta",
    operation_id="likePostComment",
    responses=AUTHENTICATION_RESPONSE,
)
def like_post_comment(
    request: Request,
    comment_id: str = Path(min_length=8, max_length=160),
    principal: Principal = Depends(require_principal),
) -> CommunityCommentLikeResponse:
    return _service(request).set_post_comment_like(principal, comment_id, liked=True)


@router.delete(
    "/v1/feed/comments/{comment_id}/like",
    response_model=CommunityCommentLikeResponse,
    tags=["Feed"],
    summary="Remover curtida de um comentario ou resposta",
    operation_id="unlikePostComment",
    responses=AUTHENTICATION_RESPONSE,
)
def unlike_post_comment(
    request: Request,
    comment_id: str = Path(min_length=8, max_length=160),
    principal: Principal = Depends(require_principal),
) -> CommunityCommentLikeResponse:
    return _service(request).set_post_comment_like(principal, comment_id, liked=False)


@router.post(
    "/v1/community/posts",
    response_model=CommunityDocumentResponse,
    status_code=201,
    tags=["Comunidade"],
    summary="Publicar no Feed comunitario",
    description=(
        "Aceita texto e, opcionalmente, uma imagem JPEG, PNG ou WebP ja "
        "validada. O backend valida status, funcao e feed.publish "
        "no PostgreSQL e deriva a autoria do token e do perfil publico."
    ),
    operation_id="createCommunityPost",
    responses=AUTHENTICATION_RESPONSE,
)
def create_community_post(
    payload: CommunityPostCreateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> CommunityDocumentResponse:
    return _service(request).create_community_post(principal, payload)


@router.patch(
    "/v1/community/posts/{post_id}",
    response_model=CommunityContentMutationResponse,
    tags=["Comunidade"],
    summary="Editar uma publicacao propria",
    operation_id="updateCommunityPost",
    responses=AUTHENTICATION_RESPONSE,
)
def update_community_post(
    payload: CommunityPostUpdateRequest,
    request: Request,
    post_id: str = Path(min_length=1, max_length=160),
    principal: Principal = Depends(require_principal),
) -> CommunityContentMutationResponse:
    return _service(request).update_community_post(principal, post_id, payload)


@router.delete(
    "/v1/community/posts/{post_id}",
    response_model=CommunityContentMutationResponse,
    tags=["Comunidade"],
    summary="Excluir uma publicacao propria",
    operation_id="deleteCommunityPost",
    responses=AUTHENTICATION_RESPONSE,
)
def delete_community_post(
    request: Request,
    post_id: str = Path(min_length=1, max_length=160),
    principal: Principal = Depends(require_principal),
) -> CommunityContentMutationResponse:
    return _service(request).delete_community_post(principal, post_id)


@router.post(
    "/v1/community/places",
    response_model=CommunityDocumentResponse,
    status_code=201,
    tags=["Comunidade"],
    summary="Publicar um ponto do empreendedor",
    description=(
        "Valida locations.publish e o status atual no PostgreSQL antes de gravar "
        "o ponto público no Firestore por Firebase Admin."
    ),
    operation_id="createCuratedPlace",
    responses=AUTHENTICATION_RESPONSE,
)
def create_curated_place(
    payload: CuratedPlaceCreateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> CommunityDocumentResponse:
    return _service(request).create_curated_place(principal, payload)


@router.delete(
    "/v1/community/places/{place_id}",
    response_model=CommunityContentMutationResponse,
    tags=["Comunidade"],
    summary="Excluir o ponto proprio do empreendedor",
    description=(
        "Confirma locations.publish e a autoria no Firestore antes de remover o ponto do mapa publico."
    ),
    operation_id="deleteCuratedPlace",
    responses=AUTHENTICATION_RESPONSE,
)
def delete_curated_place(
    request: Request,
    place_id: str = Path(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_-]+$"),
    principal: Principal = Depends(require_principal),
) -> CommunityContentMutationResponse:
    return _service(request).delete_curated_place(principal, place_id)


@router.post(
    "/v1/community/live-fairs",
    response_model=CommunityDocumentResponse,
    status_code=201,
    tags=["Comunidade"],
    summary="Publicar uma feira ao vivo",
    description=(
        "Valida locations.publish, função e status no backend e grava a feira pelo Firebase Admin."
    ),
    operation_id="createLiveFair",
    responses=AUTHENTICATION_RESPONSE,
)
def create_live_fair(
    payload: LiveFairCreateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> CommunityDocumentResponse:
    return _service(request).create_live_fair(principal, payload)


@router.post(
    "/v1/community/live-fairs/{fair_id}/end",
    response_model=CommunityDocumentResponse,
    tags=["Comunidade"],
    summary="Encerrar uma feira ao vivo",
    description=(
        "Confirma a permissão no PostgreSQL e a propriedade da feira antes do encerramento."
    ),
    operation_id="endLiveFair",
    responses=AUTHENTICATION_RESPONSE,
)
def end_live_fair(
    request: Request,
    fair_id: str = Path(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_-]+$"),
    principal: Principal = Depends(require_principal),
) -> CommunityDocumentResponse:
    return _service(request).end_live_fair(principal, fair_id)


@router.delete(
    "/v1/community/live-fairs/{fair_id}",
    response_model=CommunityContentMutationResponse,
    tags=["Comunidade"],
    summary="Excluir uma feira propria",
    description=(
        "Confirma a permissao no PostgreSQL e a autoria no Firestore antes de "
        "excluir definitivamente a feira publica."
    ),
    operation_id="deleteLiveFair",
    responses=AUTHENTICATION_RESPONSE,
)
def delete_live_fair(
    request: Request,
    fair_id: str = Path(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_-]+$"),
    principal: Principal = Depends(require_principal),
) -> CommunityContentMutationResponse:
    return _service(request).delete_live_fair(principal, fair_id)
