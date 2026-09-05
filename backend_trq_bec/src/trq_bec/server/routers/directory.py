"""Rotas de perfis públicos, diretório e pesquisa global."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request

from ..auth import require_principal
from ..docs import AUTHENTICATION_RESPONSE
from ..models import (
    GlobalSearchResponse,
    Principal,
    PublicProfileResponse,
    PublicProfileUpsertRequest,
)
from ..service import CouponSecurityService


router = APIRouter()


def _service(request: Request) -> CouponSecurityService:
    return request.app.state.service


def _media_request_context(request: Request) -> dict[str, str | None]:
    return {
        "request_id": getattr(request.state, "request_id", ""),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


@router.put(
    "/v1/profile/public",
    response_model=PublicProfileResponse,
    tags=["Diretorio"],
    summary="Salvar o perfil publico autoritativo",
    operation_id="upsertAuthoritativePublicProfile",
    responses=AUTHENTICATION_RESPONSE,
)
@router.put(
    "/v1/directory/profile",
    response_model=PublicProfileResponse,
    tags=["Diretorio"],
    summary="Salvar o perfil publico autoritativo (alias)",
    operation_id="upsertAuthoritativeDirectoryProfile",
    include_in_schema=False,
)
def upsert_public_profile(
    payload: PublicProfileUpsertRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> PublicProfileResponse:
    return _service(request).upsert_public_profile(
        principal,
        payload,
        **_media_request_context(request),
    )


@router.get(
    "/v1/profile/public/{uid}",
    response_model=PublicProfileResponse,
    tags=["Diretorio"],
    summary="Consultar um perfil publico ativo",
    operation_id="getAuthoritativePublicProfile",
    responses=AUTHENTICATION_RESPONSE,
)
def get_public_profile(
    request: Request,
    uid: str = Path(min_length=1, max_length=128),
    principal: Principal = Depends(require_principal),
) -> PublicProfileResponse:
    return _service(request).get_public_profile(principal, uid)


@router.get(
    "/v1/directory/profile/me",
    response_model=PublicProfileResponse,
    tags=["Diretorio"],
    summary="Consultar o proprio perfil publico (alias)",
    operation_id="getOwnAuthoritativeDirectoryProfile",
    include_in_schema=False,
)
def get_own_public_profile(
    request: Request,
    principal: Principal = Depends(require_principal),
) -> PublicProfileResponse:
    return _service(request).get_public_profile(principal, principal.uid)


@router.get(
    "/v1/search",
    response_model=GlobalSearchResponse,
    tags=["Diretorio"],
    summary="Pesquisar perfis, produtos, ofertas e publicacoes",
    operation_id="searchLiberRotas",
    responses=AUTHENTICATION_RESPONSE,
)
def search_liberrotas(
    request: Request,
    q: str = Query(min_length=2, max_length=100),
    types: list[str] = Query(default=["PROFILE", "PRODUCT", "OFFER", "POST"]),
    limit: int = Query(default=20, ge=1, le=50),
    principal: Principal = Depends(require_principal),
) -> GlobalSearchResponse:
    selected_types = tuple(
        item.strip()
        for value in types
        for item in value.split(",")
        if item.strip()
    )
    return _service(request).search(principal, q, selected_types, limit)
