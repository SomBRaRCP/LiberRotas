import type { EntrepreneurFundedEvent, EntrepreneurFundedEventReport, InstitutionMembership } from "@/features/institutions/api";
import type { MarketplaceProduct, OfferPreview } from "@/security/trq-bec/contracts";

export function canGenerateSaleQr(offer: OfferPreview, product: MarketplaceProduct | undefined, nowMs: number) {
  return offer.status === "ACTIVE"
    && offer.expires_at * 1_000 > nowMs
    && offer.remaining_redemptions > 0
    && product?.product_id === offer.product_id
    && product.status === "ACTIVE"
    && product.stock_quantity > 0;
}

/** Apoio possível; o repasse efetivo é calculado pelo backend na confirmação. */
export function fundedEventsForOffer(
  offer: OfferPreview,
  events: EntrepreneurFundedEvent[],
  memberships: InstitutionMembership[],
  sellerUid: string,
  nowMs: number,
) {
  const activeGroupIds = new Set(memberships
    .filter((membership) => membership.status === "ACTIVE" && membership.seller_uid === sellerUid)
    .map((membership) => membership.group_id));
  return events.filter((event) => (
    activeGroupIds.has(event.group_id)
    && event.status === "ACTIVE"
    && event.currency === offer.currency
    && Date.parse(event.starts_at) <= nowMs
    && (event.end_mode === "TIME"
      ? event.ends_at !== null && Date.parse(event.ends_at) > nowMs
      : event.coupon_limit !== null && event.current_coupon_redemptions < event.coupon_limit)
    && event.product_allocations.some((allocation) => (
      allocation.product_id === offer.product_id && allocation.allocated_amount_minor > 0
    ))
  ));
}

export function fundedProductTotals(productId: string, currency: string, reports: EntrepreneurFundedEventReport[]) {
  const products = reports
    .filter((report) => report.event.currency === currency)
    .flatMap((report) => report.products.filter((product) => product.product_id === productId));
  return {
    hasFunding: products.length > 0,
    amountDueMinor: products.reduce((sum, product) => sum + product.amount_due_minor, 0),
    unitsSold: products.reduce((sum, product) => sum + product.units_sold, 0),
  };
}
