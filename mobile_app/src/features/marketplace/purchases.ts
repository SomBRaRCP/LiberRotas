export type PurchaseCurrencyTotal = {
  currency: string;
  purchase_count: number;
  units_purchased: number;
  spent_amount_minor: number;
  saved_amount_minor: number;
  amounts_unavailable_count: number;
};

export type VisitorPurchase = {
  redemption_id: string;
  merchant_uid: string;
  merchant_name: string;
  establishment_name: string | null;
  product_id: string;
  product_title: string;
  quantity: number;
  currency: string;
  original_amount_minor: number | null;
  final_amount_minor: number | null;
  saved_amount_minor: number;
  purchased_at: string;
};

export type VisitorPurchasesReport = {
  total_purchases: number;
  total_units: number;
  totals: PurchaseCurrencyTotal[];
  items: VisitorPurchase[];
  limit: number;
  offset: number;
  has_more: boolean;
};

export function formatPurchaseMoney(valueMinor: number, currency: string) {
  try {
    return new Intl.NumberFormat("pt-BR", { currency, style: "currency" }).format(valueMinor / 100);
  } catch {
    return `${currency} ${(valueMinor / 100).toFixed(2)}`;
  }
}
