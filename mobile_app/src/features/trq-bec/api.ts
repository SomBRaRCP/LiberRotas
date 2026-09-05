import type { AuthenticatedRequest } from "@/api/http-client";
import type {
  AuthorizationResponse,
  CouponQrGroupResult,
  CouponQrResult,
  CouponRedemptionResult,
  OfferPreview,
  ProtectedQrBundlePayload,
  ProtectedQrPayload,
  RedemptionBeginResponse,
} from "@/security/trq-bec/contracts";

export const MAX_COMBINED_COUPONS = 5;

export type IssueLiveOfferInput = {
  productId: string;
  discountType: "PERCENT" | "FIXED_AMOUNT";
  discountValue: number;
  maximumRedemptions: number;
  validUntil: string;
};

export type CouponRedemptionGroupFailure = {
  code: string;
  message: string;
  position: number;
};

export type CouponRedemptionGroupResult = {
  completed: CouponRedemptionResult[];
  failures: CouponRedemptionGroupFailure[];
};

type ServiceErrorLike = Error & {
  code: string;
  userMessage: string;
};

type IssueOfferResponse = {
  offer_id: string;
  qr_payload: ProtectedQrPayload;
  expires_at: number;
  offer: OfferPreview;
};

type TrqBecApiOptions = {
  requestAuthenticated: AuthenticatedRequest;
  enrollDevice: () => Promise<{ keyId: string }>;
  getOwnerUid: () => string;
  decodeBase64Url: (value: string) => Uint8Array;
  signDeviceProof: (message: Uint8Array, ownerUid: string) => Promise<string>;
  createError: (message: string, code: string) => ServiceErrorLike;
  isServiceError: (error: unknown) => error is ServiceErrorLike;
  getFriendlyMessage: (code: string) => string | undefined;
};

export function createTrqBecApi(options: TrqBecApiOptions) {
  const { requestAuthenticated } = options;

  function parseSingleProtectedQrPayload(value: unknown): ProtectedQrPayload {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw options.createError("Estrutura do QR Code inválida.", "QR_SCHEMA_INVALID");
    }

    const payload = value as Record<string, unknown>;
    const quantity = payload.quantity === undefined ? 1 : payload.quantity;
    const quantityProof = payload.quantity_proof_b64u == null ? undefined : payload.quantity_proof_b64u;
    if (
      payload.type === "trq-bec-offer-v1"
      && payload.v === 1
      && typeof payload.token_ref === "string"
      && /^[A-Za-z0-9_-]{22,128}$/.test(payload.token_ref)
      && typeof payload.issuer_ref === "string"
      && payload.issuer_ref.length > 0
      && payload.issuer_ref.length <= 160
      && Number.isInteger(payload.expires_at)
      && Number.isInteger(quantity)
      && Number(quantity) >= 1
      && Number(quantity) <= 1_000
      && (
        quantityProof === undefined
        || (typeof quantityProof === "string" && /^[A-Za-z0-9_-]{86,88}$/.test(quantityProof))
      )
      && (Number(quantity) === 1 || typeof quantityProof === "string")
    ) {
      return {
        type: "trq-bec-offer-v1",
        v: 1,
        token_ref: payload.token_ref,
        issuer_ref: payload.issuer_ref,
        expires_at: payload.expires_at as number,
        quantity: Number(quantity),
        ...(typeof quantityProof === "string" ? { quantity_proof_b64u: quantityProof } : {}),
      };
    }

    throw options.createError("Este QR não contém uma oferta LiberRotas válida.", "QR_TYPE_INVALID");
  }

  function parseProtectedQrPayloads(raw: string): ProtectedQrPayload[] {
    if (raw.length === 0 || raw.length > 16_384) {
      throw options.createError("O QR Code está vazio ou excede o limite permitido.", "QR_SIZE_INVALID");
    }

    let value: unknown;
    try {
      value = JSON.parse(raw);
    } catch {
      throw options.createError("O QR Code não pertence ao formato seguro do LiberRotas.", "QR_JSON_INVALID");
    }

    if (
      value
      && typeof value === "object"
      && !Array.isArray(value)
      && (value as Record<string, unknown>).type === "trq-bec-offer-bundle-v1"
    ) {
      const bundle = value as Partial<ProtectedQrBundlePayload>;
      if (
        bundle.v !== 1
        || !Array.isArray(bundle.offers)
        || bundle.offers.length < 2
        || bundle.offers.length > MAX_COMBINED_COUPONS
      ) {
        throw options.createError(
          `O QR combinado deve conter entre 2 e ${MAX_COMBINED_COUPONS} cupons.`,
          "QR_BUNDLE_SIZE_INVALID",
        );
      }
      const offers = bundle.offers.map(parseSingleProtectedQrPayload);
      if (new Set(offers.map((offer) => offer.token_ref)).size !== offers.length) {
        throw options.createError("O QR combinado contém cupons repetidos.", "QR_BUNDLE_DUPLICATE");
      }
      if (new Set(offers.map((offer) => offer.issuer_ref)).size !== 1) {
        throw options.createError(
          "O QR combinado mistura ofertas de vendedores diferentes.",
          "QR_BUNDLE_ISSUER_MISMATCH",
        );
      }
      return offers;
    }

    return [parseSingleProtectedQrPayload(value)];
  }

  function parseProtectedQrPayload(raw: string): ProtectedQrPayload {
    const payloads = parseProtectedQrPayloads(raw);
    if (payloads.length !== 1) {
      throw options.createError("Esta operação aceita somente um cupom.", "QR_SINGLE_COUPON_REQUIRED");
    }
    return payloads[0];
  }

  async function issueLiveOffer(input: IssueLiveOfferInput): Promise<CouponQrResult> {
    const identity = await options.enrollDevice();
    const response = await requestAuthenticated<IssueOfferResponse>("POST", "/v1/trq-bec/coupons/issue", {
      product_id: input.productId,
      discount_type: input.discountType,
      discount_value: input.discountValue,
      maximum_redemptions: input.maximumRedemptions,
      valid_until: input.validUntil,
      purpose: "LIVE_FAIR_DISCOUNT",
      device_key_id: identity.keyId,
    });

    return {
      qrValue: JSON.stringify(response.qr_payload),
      expiresAt: response.expires_at,
      offer: response.offer,
    };
  }

  function createCombinedCouponQr(results: CouponQrResult[]): CouponQrGroupResult {
    if (results.length < 2 || results.length > MAX_COMBINED_COUPONS) {
      throw options.createError(
        `Selecione entre 2 e ${MAX_COMBINED_COUPONS} ofertas para gerar um QR único.`,
        "QR_BUNDLE_SIZE_INVALID",
      );
    }
    if (results.some((result) => result.offer.status !== "ACTIVE" || result.offer.remaining_redemptions <= 0)) {
      throw options.createError(
        "O QR único aceita somente ofertas ativas e com estoque disponível.",
        "QR_BUNDLE_OFFER_UNAVAILABLE",
      );
    }
    const payloads = results.map((result) => parseProtectedQrPayload(result.qrValue));
    if (new Set(payloads.map((payload) => payload.token_ref)).size !== payloads.length) {
      throw options.createError("Selecione ofertas diferentes para o QR único.", "QR_BUNDLE_DUPLICATE");
    }
    if (new Set(payloads.map((payload) => payload.issuer_ref)).size !== 1) {
      throw options.createError(
        "Um QR único só pode reunir ofertas do mesmo vendedor.",
        "QR_BUNDLE_ISSUER_MISMATCH",
      );
    }
    const bundle: ProtectedQrBundlePayload = {
      type: "trq-bec-offer-bundle-v1",
      v: 1,
      offers: payloads,
    };
    return {
      qrValue: JSON.stringify(bundle),
      expiresAt: Math.min(...payloads.map((payload) => payload.expires_at)),
      offers: results.map((result) => result.offer),
    };
  }

  async function previewCouponQr(rawQr: string): Promise<OfferPreview> {
    const qrPayload = parseProtectedQrPayload(rawQr);
    return requestAuthenticated("POST", "/v1/trq-bec/coupons/preview", { qr_payload: qrPayload });
  }

  async function previewCouponQrGroup(rawQr: string): Promise<OfferPreview[]> {
    const qrPayloads = parseProtectedQrPayloads(rawQr);
    return Promise.all(qrPayloads.map((qrPayload) => (
      requestAuthenticated<OfferPreview>("POST", "/v1/trq-bec/coupons/preview", { qr_payload: qrPayload })
    )));
  }

  function canRetryRedemptionAuthorization(error: unknown) {
    return options.isServiceError(error)
      && ["BACKEND_TIMEOUT", "BACKEND_UNREACHABLE", "OPERATION_IN_PROGRESS"].includes(error.code);
  }

  async function authorizeRedemptionWithRetry(request: {
    operation_id: string;
    session_id: string;
    challenge_id: string;
    device_key_id: string;
    device_proof_b64u: string;
  }): Promise<AuthorizationResponse> {
    const maximumAttempts = 3;
    for (let attempt = 1; attempt <= maximumAttempts; attempt += 1) {
      try {
        return await requestAuthenticated("POST", "/v1/trq-bec/coupons/redeem/authorize", request);
      } catch (error) {
        if (attempt === maximumAttempts || !canRetryRedemptionAuthorization(error)) throw error;
        await new Promise<void>((resolve) => setTimeout(resolve, attempt * 350));
      }
    }
    throw options.createError("Não foi possível confirmar o resgate.", "AUTHORIZATION_UNAVAILABLE");
  }

  async function redeemCouponPayload(
    qrPayload: ProtectedQrPayload,
    identity: { keyId: string },
  ): Promise<CouponRedemptionResult> {
    const begin = await requestAuthenticated<RedemptionBeginResponse>(
      "POST",
      "/v1/trq-bec/coupons/redeem/begin",
      { qr_payload: qrPayload, device_key_id: identity.keyId },
    );
    const proof = await options.signDeviceProof(
      options.decodeBase64Url(begin.proof_message_b64u),
      options.getOwnerUid(),
    );
    const authorization = await authorizeRedemptionWithRetry({
      operation_id: begin.operation_id,
      session_id: begin.session_id,
      challenge_id: begin.challenge.challenge_id,
      device_key_id: identity.keyId,
      device_proof_b64u: proof,
    });

    return {
      decision: authorization.decision,
      reasonCodes: authorization.reason_codes,
      operationId: authorization.operation_id,
      offerId: authorization.offer_id,
      productId: authorization.product_id,
      amountSavedMinor: authorization.amount_saved_minor,
      finalAmountMinor: authorization.final_amount_minor,
      remainingRedemptions: authorization.remaining_redemptions,
      quantity: authorization.quantity,
    };
  }

  async function redeemCouponQr(rawQr: string): Promise<CouponRedemptionResult> {
    const qrPayload = parseProtectedQrPayload(rawQr);
    const identity = await options.enrollDevice();
    return redeemCouponPayload(qrPayload, identity);
  }

  async function redeemCouponQrGroup(rawQr: string): Promise<CouponRedemptionGroupResult> {
    const qrPayloads = parseProtectedQrPayloads(rawQr);
    const identity = await options.enrollDevice();
    const completed: CouponRedemptionResult[] = [];
    const failures: CouponRedemptionGroupFailure[] = [];

    for (let position = 0; position < qrPayloads.length; position += 1) {
      try {
        const result = await redeemCouponPayload(qrPayloads[position], identity);
        if (result.decision === "ALLOW") {
          completed.push(result);
        } else {
          const code = result.reasonCodes[0] || result.decision;
          failures.push({
            code,
            message: options.getFriendlyMessage(code) || `O cupom ${position + 1} não foi autorizado.`,
            position,
          });
        }
      } catch (error) {
        failures.push({
          code: options.isServiceError(error) ? error.code : "REDEMPTION_FAILED",
          message: errorMessageForGroup(error, position),
          position,
        });
      }
    }

    return { completed, failures };
  }

  function errorMessageForGroup(error: unknown, position: number) {
    if (options.isServiceError(error)) return error.userMessage;
    return `Não foi possível validar o cupom ${position + 1}.`;
  }

  return {
    createCombinedCouponQr,
    issueLiveOffer,
    previewCouponQr,
    previewCouponQrGroup,
    redeemCouponQr,
    redeemCouponQrGroup,
  };
}
