from fastapi.routing import APIRoute

from trq_bec.server.app import app
from trq_bec.server.routers.coupons import router as coupons_router
from trq_bec.server.routers.marketplace import router as marketplace_router


def _route_contract(router) -> set[tuple[str, str, str]]:
    return {
        (route.path, next(iter(route.methods)), route.operation_id)
        for route in router.routes
        if isinstance(route, APIRoute)
    }


def test_marketplace_router_preserves_public_contract() -> None:
    assert _route_contract(marketplace_router) == {
        ("/v1/marketplace/catalog/feed", "GET", "listAuthenticatedMarketplaceCatalog"),
        ("/v1/marketplace/catalog/merchants/{firebase_uid}", "GET", "getAuthenticatedMarketplaceMerchantProfile"),
        ("/v1/marketplace/products", "POST", "createMarketplaceProduct"),
        ("/v1/marketplace/products/mine", "GET", "listOwnMarketplaceProducts"),
        ("/v1/marketplace/products/batch/archive", "POST", "archiveMarketplaceProductsBatch"),
        ("/v1/marketplace/products/batch/activate", "POST", "activateMarketplaceProductsBatch"),
        ("/v1/marketplace/products/{product_id}/stock", "POST", "updateMarketplaceProductStock"),
        ("/v1/marketplace/offers/mine", "GET", "listOwnLiveOffers"),
        ("/v1/marketplace/offers/{offer_id}/qr", "GET", "getOwnLiveOfferQr"),
        ("/v1/marketplace/offers/{offer_id}", "DELETE", "deleteOwnLiveOffer"),
        ("/v1/marketplace/offers/batch/actions", "POST", "updateMarketplaceOffersBatch"),
        ("/v1/marketplace/offers/{offer_id}/status", "POST", "updateLiveOfferStatus"),
    }


def test_coupons_router_preserves_public_contract() -> None:
    assert _route_contract(coupons_router) == {
        ("/v1/trq-bec/coupons/purchases/mine", "GET", "getOwnVisitorPurchases"),
        ("/v1/trq-bec/coupons/issue", "POST", "issueCoupon"),
        ("/v1/trq-bec/coupons/preview", "POST", "previewCouponOffer"),
        ("/v1/trq-bec/coupons/redeem/begin", "POST", "beginCouponRedemption"),
        ("/v1/trq-bec/coupons/redeem/authorize", "POST", "authorizeCouponRedemption"),
    }


def test_marketplace_and_coupons_routers_are_present_in_public_openapi() -> None:
    schema = app.openapi()
    assert schema["paths"]["/v1/trq-bec/coupons/purchases/mine"]["get"]["operationId"] == "getOwnVisitorPurchases"

    assert schema["paths"]["/v1/marketplace/products"]["post"]["operationId"] == (
        "createMarketplaceProduct"
    )
    assert schema["paths"]["/v1/marketplace/offers/batch/actions"]["post"][
        "operationId"
    ] == "updateMarketplaceOffersBatch"
    assert schema["paths"]["/v1/trq-bec/coupons/issue"]["post"]["operationId"] == (
        "issueCoupon"
    )
    assert schema["paths"]["/v1/trq-bec/coupons/redeem/authorize"]["post"][
        "operationId"
    ] == "authorizeCouponRedemption"
