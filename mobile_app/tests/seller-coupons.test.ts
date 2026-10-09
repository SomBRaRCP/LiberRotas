import { describe, expect, it } from "vitest";
import { canGenerateSaleQr, fundedEventsForOffer, fundedProductTotals } from "../src/features/marketplace/seller-coupons";
import type { EntrepreneurFundedEvent, EntrepreneurFundedEventReport, InstitutionMembership } from "../src/features/institutions/api";
import type { MarketplaceProduct, OfferPreview } from "../src/security/trq-bec/contracts";

const nowMs = Date.UTC(2026, 9, 8, 12);
const offer = {
  offer_id: "offer-own", product_id: "product-own", status: "ACTIVE", currency: "BRL",
  expires_at: nowMs / 1_000 + 3_600, remaining_redemptions: 8,
} as OfferPreview;
const product = { product_id: "product-own", status: "ACTIVE", stock_quantity: 10 } as MarketplaceProduct;
const membership = { group_id: "group-partner", seller_uid: "seller-own", status: "ACTIVE" } as InstitutionMembership;
const event = {
  event_id: "event-partner", group_id: "group-partner", institution_name: "Instituição parceira",
  status: "ACTIVE", currency: "BRL", starts_at: new Date(nowMs - 1_000).toISOString(),
  end_mode: "TIME", ends_at: new Date(nowMs + 3_600_000).toISOString(),
  coupon_limit: null, current_coupon_redemptions: 0,
  product_allocations: [{ product_id: "product-own", allocated_amount_minor: 10_000 }],
} as EntrepreneurFundedEvent;

describe("QR de vendas do empreendedor", () => {
  it("libera somente oferta ativa, dentro da validade e com produto ativo em estoque", () => {
    expect(canGenerateSaleQr(offer, product, nowMs)).toBe(true);
    expect(canGenerateSaleQr({ ...offer, status: "PAUSED" }, product, nowMs)).toBe(false);
    expect(canGenerateSaleQr({ ...offer, status: "CANCELLED" }, product, nowMs)).toBe(false);
    expect(canGenerateSaleQr({ ...offer, expires_at: nowMs / 1_000 }, product, nowMs)).toBe(false);
    expect(canGenerateSaleQr({ ...offer, remaining_redemptions: 0 }, product, nowMs)).toBe(false);
    expect(canGenerateSaleQr(offer, { ...product, stock_quantity: 0 }, nowMs)).toBe(false);
    expect(canGenerateSaleQr(offer, { ...product, status: "PAUSED" }, nowMs)).toBe(false);
    expect(canGenerateSaleQr(offer, { ...product, product_id: "product-other" }, nowMs)).toBe(false);
    expect(canGenerateSaleQr(offer, undefined, nowMs)).toBe(false);
  });

  it("identifica apoio pelo grupo da filiação ativa do próprio vendedor", () => {
    expect(fundedEventsForOffer(offer, [event], [membership], "seller-own", nowMs)).toEqual([event]);
    expect(fundedEventsForOffer(offer, [event], [{ ...membership, status: "LEFT" }], "seller-own", nowMs)).toEqual([]);
    expect(fundedEventsForOffer(offer, [event], [membership], "seller-other", nowMs)).toEqual([]);
    expect(fundedEventsForOffer(offer, [{ ...event, group_id: "group-other" }], [membership], "seller-own", nowMs)).toEqual([]);
  });

  it("não apresenta evento encerrado, futuro, em outra moeda ou sem verba para o produto como benefício ativo", () => {
    const unavailableEvents = [
      { ...event, status: "DRAFT" as const },
      { ...event, starts_at: new Date(nowMs + 1_000).toISOString() },
      { ...event, ends_at: new Date(nowMs).toISOString() },
      { ...event, currency: "USD" },
      { ...event, product_allocations: [{ ...event.product_allocations[0], allocated_amount_minor: 0 }] },
      { ...event, product_allocations: [{ ...event.product_allocations[0], product_id: "product-other" }] },
    ];
    expect(fundedEventsForOffer(offer, unavailableEvents, [membership], "seller-own", nowMs)).toEqual([]);
  });

  it("respeita o limite de cupons de um evento institucional", () => {
    const couponEvent = { ...event, end_mode: "COUPONS" as const, ends_at: null, coupon_limit: 5, current_coupon_redemptions: 4 };
    expect(fundedEventsForOffer(offer, [couponEvent], [membership], "seller-own", nowMs)).toHaveLength(1);
    expect(fundedEventsForOffer(offer, [{ ...couponEvent, current_coupon_redemptions: 5 }], [membership], "seller-own", nowMs)).toEqual([]);
  });

  it("soma saldo e unidades do produto nos relatórios, preservando valores de eventos encerrados e separando moedas", () => {
    const report = {
      event,
      products: [
        { product_id: "product-own", amount_due_minor: 600, units_sold: 3 },
        { product_id: "product-other", amount_due_minor: 9_999, units_sold: 99 },
      ],
    } as EntrepreneurFundedEventReport;
    const historical = { ...report, event: { ...event, status: "ENDED" as const }, products: [{ ...report.products[0], amount_due_minor: 400, units_sold: 2 }] };
    expect(fundedProductTotals("product-own", "BRL", [report, historical, { ...report, event: { ...event, currency: "USD" } }]))
      .toEqual({ hasFunding: true, amountDueMinor: 1_000, unitsSold: 5 });
    expect(fundedProductTotals("no-funding", "BRL", [report])).toEqual({ hasFunding: false, amountDueMinor: 0, unitsSold: 0 });
  });
});
