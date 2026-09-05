import type { AuthenticatedRequest } from "@/api/http-client";
import type {
  CatalogFeedResponse,
  CatalogMerchantResponse,
  CatalogProductItem,
  CouponQrResult,
  LiveOfferBatchResult,
  LiveOfferBatchUpdateInput,
  MarketplaceProduct,
  MarketplaceProductBatchActivateResult,
  MarketplaceProductBatchResult,
  OfferPreview,
  OfferStatus,
  ProtectedQrPayload,
} from "@/security/trq-bec/contracts";

type ProductListResponse = { products: MarketplaceProduct[] };
type OfferListResponse = { offers: OfferPreview[] };
type OfferQrResponse = {
  qr_payload: ProtectedQrPayload;
  expires_at: number;
  offer: OfferPreview;
};

export type CreateProductInput = {
  title: string;
  description: string;
  priceMinor: number;
  stockQuantity: number;
};

type MarketplaceApiOptions = {
  requestAuthenticated: AuthenticatedRequest;
  enrollDevice: () => Promise<{ keyId: string }>;
  createError: (message: string, code: string) => Error;
};

export function createMarketplaceApi(options: MarketplaceApiOptions) {
  const { requestAuthenticated } = options;

  function createMarketplaceProduct(input: CreateProductInput): Promise<MarketplaceProduct> {
    return requestAuthenticated("POST", "/v1/marketplace/products", {
      title: input.title,
      description: input.description,
      price_minor: input.priceMinor,
      currency: "BRL",
      stock_quantity: input.stockQuantity,
    });
  }

  async function listOwnMarketplaceProducts(): Promise<MarketplaceProduct[]> {
    const response = await requestAuthenticated<ProductListResponse>("GET", "/v1/marketplace/products/mine");
    return response.products;
  }

  async function listPublicCatalogFeed(): Promise<CatalogProductItem[]> {
    const response = await requestAuthenticated<CatalogFeedResponse>("GET", "/v1/marketplace/catalog/feed?limit=50");
    return response.items;
  }

  function getPublicMerchantCatalog(firebaseUid: string): Promise<CatalogMerchantResponse> {
    return requestAuthenticated(
      "GET",
      `/v1/marketplace/catalog/merchants/${encodeURIComponent(firebaseUid)}`,
    );
  }

  function updateMarketplaceProductStock(
    productId: string,
    stockQuantity: number,
  ): Promise<MarketplaceProduct> {
    return requestAuthenticated(
      "POST",
      `/v1/marketplace/products/${encodeURIComponent(productId)}/stock`,
      { stock_quantity: stockQuantity },
    );
  }

  function batchArchiveMarketplaceProducts(
    productIds: string[],
    clientRequestId: string,
  ): Promise<MarketplaceProductBatchResult> {
    return requestAuthenticated("POST", "/v1/marketplace/products/batch/archive", {
      product_ids: [...new Set(productIds)],
      client_request_id: clientRequestId,
    });
  }

  function batchActivateMarketplaceProducts(
    items: { productId: string; stockQuantity: number }[],
    clientRequestId: string,
  ): Promise<MarketplaceProductBatchActivateResult> {
    return requestAuthenticated("POST", "/v1/marketplace/products/batch/activate", {
      items: items.map((item) => ({
        product_id: item.productId,
        stock_quantity: item.stockQuantity,
      })),
      client_request_id: clientRequestId,
    });
  }

  async function listOwnLiveOffers(): Promise<OfferPreview[]> {
    const response = await requestAuthenticated<OfferListResponse>("GET", "/v1/marketplace/offers/mine");
    return response.offers;
  }

  async function getOwnLiveOfferQr(offerId: string, quantity = 1): Promise<CouponQrResult> {
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 1_000) {
      throw options.createError("Informe uma quantidade válida entre 1 e 1000.", "OFFER_QR_QUANTITY_INVALID");
    }
    const response = await requestAuthenticated<OfferQrResponse>(
      "GET",
      `/v1/marketplace/offers/${encodeURIComponent(offerId)}/qr?quantity=${quantity}`,
    );
    return {
      qrValue: JSON.stringify(response.qr_payload),
      expiresAt: response.expires_at,
      offer: response.offer,
    };
  }

  function deleteOwnLiveOffer(offerId: string): Promise<OfferPreview> {
    return requestAuthenticated("DELETE", `/v1/marketplace/offers/${encodeURIComponent(offerId)}`);
  }

  function updateLiveOfferStatus(
    offerId: string,
    status: Extract<OfferStatus, "ACTIVE" | "PAUSED" | "CANCELLED">,
  ): Promise<OfferPreview> {
    return requestAuthenticated(
      "POST",
      `/v1/marketplace/offers/${encodeURIComponent(offerId)}/status`,
      { status },
    );
  }

  async function batchUpdateLiveOffers(
    input: LiveOfferBatchUpdateInput,
    clientRequestId: string,
  ): Promise<LiveOfferBatchResult> {
    const payload: Record<string, unknown> = {
      action: input.action,
      offer_ids: [...new Set(input.offerIds)],
      client_request_id: clientRequestId,
    };

    if (input.action === "INCREASE_DISCOUNT") {
      const identity = await options.enrollDevice();
      payload.discount_type = input.discountType;
      payload.discount_delta = input.discountDelta;
      payload.device_key_id = identity.keyId;
    } else if (input.action === "EXTEND_VALIDITY") {
      const identity = await options.enrollDevice();
      payload.extension_minutes = input.extensionMinutes;
      payload.device_key_id = identity.keyId;
    }

    return requestAuthenticated("POST", "/v1/marketplace/offers/batch/actions", payload);
  }

  return {
    batchActivateMarketplaceProducts,
    batchArchiveMarketplaceProducts,
    batchUpdateLiveOffers,
    createMarketplaceProduct,
    deleteOwnLiveOffer,
    getOwnLiveOfferQr,
    getPublicMerchantCatalog,
    listOwnLiveOffers,
    listOwnMarketplaceProducts,
    listPublicCatalogFeed,
    updateLiveOfferStatus,
    updateMarketplaceProductStock,
  };
}
