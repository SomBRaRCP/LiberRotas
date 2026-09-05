export type AuthorizationDecision = "DENY" | "ALLOW" | "STEP_UP" | "HOLD_OR_REVIEW";

export type DeviceStorageProfile = "EXPO_SECURE_STORE_LAB" | "WEB_CRYPTO_INDEXEDDB_LAB";

export type DeviceIdentity = {
  keyId: string;
  publicKeyB64u: string;
  algorithm: "ED25519_LAB";
  storageProfile: DeviceStorageProfile;
};

export type ProtectedQrPayload = {
  type: "trq-bec-offer-v1";
  v: 1;
  token_ref: string;
  issuer_ref: string;
  expires_at: number;
  quantity: number;
  quantity_proof_b64u?: string;
};

export type ProtectedQrBundlePayload = {
  type: "trq-bec-offer-bundle-v1";
  v: 1;
  offers: ProtectedQrPayload[];
};

export type MarketplaceProduct = {
  product_id: string;
  title: string;
  description: string;
  price_minor: number;
  currency: string;
  stock_quantity: number;
  status: "ACTIVE" | "PAUSED" | "ARCHIVED";
};

export type CatalogMerchantSummary = {
  firebase_uid: string;
  display_name: string;
  establishment_name: string;
};

export type CatalogOfferSummary = {
  offer_id: string;
  original_amount_minor: number;
  discount_amount_minor: number;
  final_amount_minor: number;
  currency: string;
  remaining_redemptions: number;
  expires_at: number;
  created_at: number;
  updated_at: number;
  status: "ACTIVE" | "PAUSED" | "ENDED";
  status_reason:
    | "PAUSED"
    | "PRODUCT_PAUSED"
    | "CANCELLED"
    | "EXHAUSTED"
    | "EXPIRED"
    | "OUT_OF_STOCK"
    | null;
  ended_at: number | null;
};

export type CatalogProductItem = {
  product_id: string;
  title: string;
  description: string;
  price_minor: number;
  currency: string;
  stock_quantity: number;
  created_at: number;
  updated_at: number;
  status: "ACTIVE" | "PAUSED" | "ENDED";
  status_reason: "PAUSED" | "OUT_OF_STOCK" | null;
  ended_at: number | null;
  merchant: CatalogMerchantSummary;
  offers: CatalogOfferSummary[];
};

export type CatalogFeedResponse = {
  items: CatalogProductItem[];
};

export type CatalogMerchantResponse = {
  merchant: CatalogMerchantSummary;
  products: CatalogProductItem[];
};

export type OfferStatus = "ACTIVE" | "PAUSED" | "EXHAUSTED" | "EXPIRED" | "REVOKED" | "CANCELLED";

export type OfferDiscountType = "PERCENT" | "FIXED_AMOUNT";

export type OfferPreview = {
  offer_id: string;
  product_id: string;
  product_title: string;
  merchant_name: string;
  establishment_name: string;
  original_amount_minor: number;
  discount_type: OfferDiscountType;
  discount_value: number;
  discount_amount_minor: number;
  final_amount_minor: number;
  currency: string;
  maximum_redemptions: number;
  redeemed_count: number;
  remaining_redemptions: number;
  expires_at: number;
  purpose: "LIVE_FAIR_DISCOUNT";
  status: OfferStatus;
  purchase_quantity: number;
};

export type CouponQrResult = {
  qrValue: string;
  expiresAt: number;
  offer: OfferPreview;
};

export type CouponQrGroupResult = {
  qrValue: string;
  expiresAt: number;
  offers: OfferPreview[];
};

/** Resultado de uma exclusão segura: o backend arquiva, mas preserva o histórico. */
export type MarketplaceProductBatchResult = {
  operation_id: string;
  archived_count: number;
  products: MarketplaceProduct[];
};

export type MarketplaceProductBatchActivateResult = {
  operation_id: string;
  activated_count: number;
  products: MarketplaceProduct[];
};

export type LiveOfferBatchUpdateInput =
  | {
      action: "DELETE";
      offerIds: string[];
    }
  | {
      action: "INCREASE_DISCOUNT";
      offerIds: string[];
      discountType: OfferDiscountType;
      discountDelta: number;
    }
  | {
      action: "EXTEND_VALIDITY";
      offerIds: string[];
      extensionMinutes: number;
    };

export type LiveOfferBatchItemResult = {
  offer: OfferPreview;
  /** Presente quando a operação rotaciona o QR protegido. */
  qr_payload: ProtectedQrPayload | null;
};

export type LiveOfferBatchResult = {
  operation_id: string;
  action: LiveOfferBatchUpdateInput["action"];
  updated_count: number;
  items: LiveOfferBatchItemResult[];
};

export type CouponRedemptionResult = {
  decision: AuthorizationDecision;
  reasonCodes: string[];
  operationId: string;
  offerId?: string;
  productId?: string;
  amountSavedMinor?: number;
  finalAmountMinor?: number;
  remainingRedemptions?: number;
  quantity?: number;
};

export type RedemptionBeginResponse = {
  operation_id: string;
  session_id: string;
  challenge: {
    challenge_id: string;
    expires_at: number;
  };
  proof_message_b64u: string;
  offer: OfferPreview;
};

export type AuthorizationResponse = {
  decision: AuthorizationDecision;
  operation_id: string;
  crypto_ok: boolean;
  reason_codes: string[];
  coupon_id?: string;
  offer_id?: string;
  product_id?: string;
  amount_saved_minor?: number;
  final_amount_minor?: number;
  remaining_redemptions?: number;
  quantity?: number;
  event_ref?: string;
  idempotent: boolean;
};
