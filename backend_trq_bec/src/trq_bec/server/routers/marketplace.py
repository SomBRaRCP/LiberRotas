"""Rotas públicas de catálogo, produtos e ofertas do marketplace."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request

from ..auth import require_principal
from ..docs import (
    AUTHENTICATION_RESPONSE,
    CATALOG_NOT_FOUND_RESPONSE,
    ISSUE_FORBIDDEN_RESPONSE,
    ISSUE_NOT_FOUND_RESPONSE,
)
from ..models import (
    CatalogFeedResponse,
    CatalogMerchantProfileResponse,
    OfferBatchActionRequest,
    OfferBatchActionResponse,
    OfferListResponse,
    OfferPreviewResponse,
    OfferQrResponse,
    OfferStatusRequest,
    Principal,
    ProductBatchActivateRequest,
    ProductBatchActivateResponse,
    ProductBatchArchiveRequest,
    ProductBatchArchiveResponse,
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductStockRequest,
)
from ..service import CouponSecurityService


router = APIRouter()


def _service(request: Request) -> CouponSecurityService:
    return request.app.state.service


@router.get(
    "/v1/marketplace/catalog/feed",
    response_model=CatalogFeedResponse,
    tags=["Marketplace"],
    summary="Listar o catálogo público autenticado",
    description=(
        "Retorna produtos de comerciantes ativos e suas ofertas resgatáveis sem expor QR, "
        "referências de token, dispositivos ou dados administrativos."
    ),
    operation_id="listAuthenticatedMarketplaceCatalog",
    responses=AUTHENTICATION_RESPONSE,
)
def list_catalog_feed(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    principal: Principal = Depends(require_principal),
) -> CatalogFeedResponse:
    return _service(request).list_catalog_feed(principal, limit)


@router.get(
    "/v1/marketplace/catalog/merchants/{firebase_uid}",
    response_model=CatalogMerchantProfileResponse,
    tags=["Marketplace"],
    summary="Consultar o perfil comercial público",
    description=(
        "Retorna o nome público, o estabelecimento e os produtos disponíveis de um empreendedor ativo. "
        "UID inexistente e conta suspensa são indistinguíveis."
    ),
    operation_id="getAuthenticatedMarketplaceMerchantProfile",
    responses={**AUTHENTICATION_RESPONSE, **CATALOG_NOT_FOUND_RESPONSE},
)
def get_catalog_merchant_profile(
    request: Request,
    firebase_uid: str = Path(min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=50),
    principal: Principal = Depends(require_principal),
) -> CatalogMerchantProfileResponse:
    return _service(request).get_catalog_merchant_profile(principal, firebase_uid, limit)


@router.post(
    "/v1/marketplace/products",
    response_model=ProductResponse,
    tags=["Marketplace"],
    summary="Cadastrar produto comercializável",
    description="Cadastra preço e estoque autoritativos para uma conta comercial ativa.",
    operation_id="createMarketplaceProduct",
    responses={**AUTHENTICATION_RESPONSE, **ISSUE_FORBIDDEN_RESPONSE},
)
def create_product(
    payload: ProductCreateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> ProductResponse:
    return _service(request).create_product(principal, payload)


@router.get(
    "/v1/marketplace/products/mine",
    response_model=ProductListResponse,
    tags=["Marketplace"],
    summary="Listar produtos do empreendedor",
    operation_id="listOwnMarketplaceProducts",
    responses={**AUTHENTICATION_RESPONSE, **ISSUE_FORBIDDEN_RESPONSE},
)
def list_products(
    request: Request,
    principal: Principal = Depends(require_principal),
) -> ProductListResponse:
    return _service(request).list_products(principal)


@router.post(
    "/v1/marketplace/products/batch/archive",
    response_model=ProductBatchArchiveResponse,
    tags=["Marketplace"],
    summary="Arquivar produtos selecionados em uma transacao",
    operation_id="archiveMarketplaceProductsBatch",
    responses={**AUTHENTICATION_RESPONSE, **ISSUE_FORBIDDEN_RESPONSE},
)
def archive_products_batch(
    payload: ProductBatchArchiveRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> ProductBatchArchiveResponse:
    return _service(request).archive_products_batch(principal, payload)


@router.post(
    "/v1/marketplace/products/batch/activate",
    response_model=ProductBatchActivateResponse,
    tags=["Marketplace"],
    summary="Ativar produtos e estoques selecionados em uma transacao",
    operation_id="activateMarketplaceProductsBatch",
    responses={**AUTHENTICATION_RESPONSE, **ISSUE_FORBIDDEN_RESPONSE},
)
def activate_products_batch(
    payload: ProductBatchActivateRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> ProductBatchActivateResponse:
    return _service(request).activate_products_batch(principal, payload)


@router.post(
    "/v1/marketplace/products/{product_id}/stock",
    response_model=ProductResponse,
    tags=["Marketplace"],
    summary="Atualizar estoque autoritativo",
    operation_id="updateMarketplaceProductStock",
    responses={**AUTHENTICATION_RESPONSE, **ISSUE_FORBIDDEN_RESPONSE, **ISSUE_NOT_FOUND_RESPONSE},
)
def update_product_stock(
    payload: ProductStockRequest,
    request: Request,
    product_id: str = Path(pattern=r"^PROD-[A-Z0-9]{8,32}$"),
    principal: Principal = Depends(require_principal),
) -> ProductResponse:
    return _service(request).update_product_stock(principal, product_id, payload)


@router.get(
    "/v1/marketplace/offers/mine",
    response_model=OfferListResponse,
    tags=["Marketplace"],
    summary="Listar ofertas ao vivo do empreendedor",
    operation_id="listOwnLiveOffers",
    responses={**AUTHENTICATION_RESPONSE, **ISSUE_FORBIDDEN_RESPONSE},
)
def list_offers(
    request: Request,
    principal: Principal = Depends(require_principal),
) -> OfferListResponse:
    return _service(request).list_offers(principal)


@router.get(
    "/v1/marketplace/offers/{offer_id}/qr",
    response_model=OfferQrResponse,
    tags=["Marketplace"],
    summary="Gerar novamente a visualizacao do QR atual da propria oferta",
    operation_id="getOwnLiveOfferQr",
    responses={
        **AUTHENTICATION_RESPONSE,
        **ISSUE_FORBIDDEN_RESPONSE,
        **ISSUE_NOT_FOUND_RESPONSE,
    },
)
def get_offer_qr(
    request: Request,
    offer_id: str = Path(pattern=r"^OFFER-[A-Z0-9]{12,32}$"),
    quantity: int = Query(default=1, ge=1, le=1_000),
    principal: Principal = Depends(require_principal),
) -> OfferQrResponse:
    return _service(request).get_offer_qr(principal, offer_id, quantity)


@router.delete(
    "/v1/marketplace/offers/{offer_id}",
    response_model=OfferPreviewResponse,
    tags=["Marketplace"],
    summary="Excluir uma oferta da vitrine e revogar seu QR",
    operation_id="deleteOwnLiveOffer",
    responses={
        **AUTHENTICATION_RESPONSE,
        **ISSUE_FORBIDDEN_RESPONSE,
        **ISSUE_NOT_FOUND_RESPONSE,
    },
)
def revoke_offer(
    request: Request,
    offer_id: str = Path(pattern=r"^OFFER-[A-Z0-9]{12,32}$"),
    principal: Principal = Depends(require_principal),
) -> OfferPreviewResponse:
    return _service(request).revoke_offer(principal, offer_id)


@router.post(
    "/v1/marketplace/offers/batch/actions",
    response_model=OfferBatchActionResponse,
    tags=["Marketplace"],
    summary="Aplicar uma acao transacional a ofertas selecionadas",
    operation_id="updateMarketplaceOffersBatch",
    responses={**AUTHENTICATION_RESPONSE, **ISSUE_FORBIDDEN_RESPONSE},
)
def batch_offer_actions(
    payload: OfferBatchActionRequest,
    request: Request,
    principal: Principal = Depends(require_principal),
) -> OfferBatchActionResponse:
    return _service(request).batch_offer_actions(principal, payload)


@router.post(
    "/v1/marketplace/offers/{offer_id}/status",
    response_model=OfferPreviewResponse,
    tags=["Marketplace"],
    summary="Pausar, reativar ou cancelar uma oferta",
    operation_id="updateLiveOfferStatus",
    responses={**AUTHENTICATION_RESPONSE, **ISSUE_FORBIDDEN_RESPONSE, **ISSUE_NOT_FOUND_RESPONSE},
)
def update_offer_status(
    payload: OfferStatusRequest,
    request: Request,
    offer_id: str = Path(pattern=r"^OFFER-[A-Z0-9]{12,32}$"),
    principal: Principal = Depends(require_principal),
) -> OfferPreviewResponse:
    return _service(request).update_offer_status(principal, offer_id, payload)
