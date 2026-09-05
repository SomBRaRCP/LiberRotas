import { describe, expect, it, vi } from "vitest";

import type { AuthenticatedRequest } from "../src/api/http-client";
import { createMarketplaceApi } from "../src/features/marketplace/api";


class TestServiceError extends Error {
  constructor(
    message: string,
    public readonly code: string,
  ) {
    super(message);
  }
}

function buildApi(requestAuthenticated: AuthenticatedRequest, enrollDevice = vi.fn(async () => ({ keyId: "device-1" }))) {
  return {
    api: createMarketplaceApi({
      requestAuthenticated,
      enrollDevice,
      createError: (message, code) => new TestServiceError(message, code),
    }),
    enrollDevice,
  };
}

describe("marketplace api", () => {
  it("converte produto para o contrato autoritativo do backend", async () => {
    const request = vi.fn(async () => ({})) as unknown as AuthenticatedRequest;

    await buildApi(request).api.createMarketplaceProduct({
      title: "Cesta local",
      description: "Produtos da feira",
      priceMinor: 15_900,
      stockQuantity: 8,
    });

    expect(request).toHaveBeenCalledWith("POST", "/v1/marketplace/products", {
      title: "Cesta local",
      description: "Produtos da feira",
      price_minor: 15_900,
      currency: "BRL",
      stock_quantity: 8,
    });
  });

  it("remove produtos repetidos antes do lote de arquivamento", async () => {
    const request = vi.fn(async () => ({})) as unknown as AuthenticatedRequest;

    await buildApi(request).api.batchArchiveMarketplaceProducts(
      ["PROD-1", "PROD-1", "PROD-2"],
      "request-1",
    );

    expect(request).toHaveBeenCalledWith("POST", "/v1/marketplace/products/batch/archive", {
      product_ids: ["PROD-1", "PROD-2"],
      client_request_id: "request-1",
    });
  });

  it("vincula o dispositivo somente às ações de oferta que rotacionam o QR", async () => {
    const requestMock = vi.fn(async (_method: string, _path: string, _body?: unknown) => ({}));
    const { api, enrollDevice } = buildApi(requestMock as unknown as AuthenticatedRequest);

    await api.batchUpdateLiveOffers({ action: "DELETE", offerIds: ["OFFER-1"] }, "request-delete");
    await api.batchUpdateLiveOffers({
      action: "EXTEND_VALIDITY",
      offerIds: ["OFFER-2"],
      extensionMinutes: 30,
    }, "request-extend");

    expect(enrollDevice).toHaveBeenCalledTimes(1);
    expect(requestMock.mock.calls[0][2]).not.toHaveProperty("device_key_id");
    expect(requestMock.mock.calls[1][2]).toMatchObject({
      extension_minutes: 30,
      device_key_id: "device-1",
    });
  });

  it("rejeita quantidade inválida antes de solicitar o QR", async () => {
    const request = vi.fn() as unknown as AuthenticatedRequest;

    await expect(buildApi(request).api.getOwnLiveOfferQr("OFFER-1", 0)).rejects.toMatchObject({
      code: "OFFER_QR_QUANTITY_INVALID",
    });
    expect(request).not.toHaveBeenCalled();
  });
});
