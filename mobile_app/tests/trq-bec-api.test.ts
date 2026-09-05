import { describe, expect, it, vi } from "vitest";

import type { AuthenticatedRequest } from "../src/api/http-client";
import { createTrqBecApi } from "../src/features/trq-bec/api";
import type { CouponQrResult, OfferPreview, ProtectedQrPayload } from "../src/security/trq-bec/contracts";


class TestServiceError extends Error {
  public readonly userMessage: string;

  constructor(message: string, public readonly code: string) {
    super(message);
    this.userMessage = message;
  }
}

function qrPayload(
  token = "A".repeat(24),
  issuer = "issuer-1",
  expiresAt = 1_900_000_000,
): ProtectedQrPayload {
  return {
    type: "trq-bec-offer-v1",
    v: 1,
    token_ref: token,
    issuer_ref: issuer,
    expires_at: expiresAt,
    quantity: 1,
  };
}

function offer(overrides: Partial<OfferPreview> = {}): OfferPreview {
  return {
    offer_id: "OFFER-1",
    product_id: "PROD-1",
    product_title: "Produto",
    merchant_name: "Empreendedor",
    establishment_name: "Feira",
    original_amount_minor: 10_000,
    discount_type: "PERCENT",
    discount_value: 10,
    discount_amount_minor: 1_000,
    final_amount_minor: 9_000,
    currency: "BRL",
    maximum_redemptions: 10,
    redeemed_count: 0,
    remaining_redemptions: 10,
    expires_at: 1_900_000_000,
    purpose: "LIVE_FAIR_DISCOUNT",
    status: "ACTIVE",
    purchase_quantity: 1,
    ...overrides,
  };
}

function buildApi(requestAuthenticated: AuthenticatedRequest) {
  const sign = vi.fn(async () => "device-proof");
  const api = createTrqBecApi({
    requestAuthenticated,
    enrollDevice: async () => ({ keyId: "device-1" }),
    getOwnerUid: () => "visitor-1",
    decodeBase64Url: () => new Uint8Array([1, 2, 3]),
    signDeviceProof: sign,
    createError: (message, code) => new TestServiceError(message, code),
    isServiceError: (error): error is TestServiceError => error instanceof TestServiceError,
    getFriendlyMessage: (code) => code === "DENIED" ? "Resgate negado." : undefined,
  });
  return { api, sign };
}

describe("trq-bec api", () => {
  it("emite a oferta vinculada ao dispositivo cadastrado", async () => {
    const payload = qrPayload();
    const request = vi.fn(async () => ({
      offer_id: "OFFER-1",
      qr_payload: payload,
      expires_at: payload.expires_at,
      offer: offer(),
    })) as unknown as AuthenticatedRequest;

    const result = await buildApi(request).api.issueLiveOffer({
      productId: "PROD-1",
      discountType: "PERCENT",
      discountValue: 10,
      maximumRedemptions: 5,
      validUntil: "2030-03-17T17:46:40Z",
    });

    expect(request).toHaveBeenCalledWith("POST", "/v1/trq-bec/coupons/issue", {
      product_id: "PROD-1",
      discount_type: "PERCENT",
      discount_value: 10,
      maximum_redemptions: 5,
      valid_until: "2030-03-17T17:46:40Z",
      purpose: "LIVE_FAIR_DISCOUNT",
      device_key_id: "device-1",
    });
    expect(JSON.parse(result.qrValue)).toEqual(payload);
  });

  it("rejeita QR fora do schema antes de consultar o backend", async () => {
    const request = vi.fn() as unknown as AuthenticatedRequest;

    await expect(buildApi(request).api.previewCouponQr("{}"))
      .rejects.toMatchObject({ code: "QR_TYPE_INVALID" });
    expect(request).not.toHaveBeenCalled();
  });

  it("combina apenas ofertas distintas do mesmo emissor", () => {
    const request = vi.fn() as unknown as AuthenticatedRequest;
    const first: CouponQrResult = {
      qrValue: JSON.stringify(qrPayload("A".repeat(24))),
      expiresAt: 1_900_000_000,
      offer: offer({ offer_id: "OFFER-1" }),
    };
    const second: CouponQrResult = {
      qrValue: JSON.stringify(qrPayload("B".repeat(24), "issuer-1", 1_899_999_000)),
      expiresAt: 1_899_999_000,
      offer: offer({ offer_id: "OFFER-2" }),
    };

    const combined = buildApi(request).api.createCombinedCouponQr([first, second]);

    expect(combined.expiresAt).toBe(1_899_999_000);
    expect(JSON.parse(combined.qrValue)).toMatchObject({
      type: "trq-bec-offer-bundle-v1",
      v: 1,
    });
  });

  it("executa begin, assina a mensagem exata e envia authorize", async () => {
    const requestMock = vi.fn(async (_method: string, path: string) => {
      if (path.endsWith("/begin")) {
        return {
          operation_id: "op-1",
          session_id: "session-1",
          challenge: { challenge_id: "challenge-1", expires_at: 1_900_000_000 },
          proof_message_b64u: "AQID",
          offer: offer(),
        };
      }
      return {
        decision: "ALLOW",
        operation_id: "op-1",
        crypto_ok: true,
        reason_codes: [],
        offer_id: "OFFER-1",
        product_id: "PROD-1",
        remaining_redemptions: 9,
        quantity: 1,
        idempotent: false,
      };
    });
    const { api, sign } = buildApi(requestMock as unknown as AuthenticatedRequest);

    const result = await api.redeemCouponQr(JSON.stringify(qrPayload()));

    expect(sign).toHaveBeenCalledWith(new Uint8Array([1, 2, 3]), "visitor-1");
    expect(requestMock.mock.calls[1]).toEqual([
      "POST",
      "/v1/trq-bec/coupons/redeem/authorize",
      {
        operation_id: "op-1",
        session_id: "session-1",
        challenge_id: "challenge-1",
        device_key_id: "device-1",
        device_proof_b64u: "device-proof",
      },
    ]);
    expect(result).toMatchObject({ decision: "ALLOW", operationId: "op-1", remainingRedemptions: 9 });
  });
});
