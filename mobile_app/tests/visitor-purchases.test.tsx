import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { PurchaseReport } from "../src/components/purchase-report";
import { createMarketplaceApi } from "../src/features/marketplace/api";
import type { VisitorPurchasesReport } from "../src/features/marketplace/purchases";

const report: VisitorPurchasesReport = {
  total_purchases: 1, total_units: 3, limit: 20, offset: 0, has_more: false,
  totals: [{ currency: "BRL", purchase_count: 1, units_purchased: 3, spent_amount_minor: 12000, saved_amount_minor: 3000, amounts_unavailable_count: 0 }],
  items: [{ redemption_id: "purchase", merchant_uid: "seller", merchant_name: "Ana", establishment_name: "Banca da Ana",
    product_id: "product", product_title: "Bordado", quantity: 3, currency: "BRL", original_amount_minor: 15000,
    final_amount_minor: 12000, saved_amount_minor: 3000, purchased_at: "2026-10-08T12:00:00Z" }],
};

function markup(data: VisitorPurchasesReport) {
  return renderToStaticMarkup(createElement(PurchaseReport, { report: data })).replaceAll("\u00a0", " ");
}

describe("Minhas compras do visitante", () => {
  it("mostra onde comprou e os valores totais da compra sem multiplicar novamente pela quantidade", () => {
    const html = markup(report);
    expect(html).toContain("Banca da Ana");
    expect(html).toContain("Vendedor: Ana");
    expect(html).toContain("Bordado");
    expect(html).toContain("3 unidades");
    expect(html).toContain("R$ 120,00");
    expect(html).toContain("R$ 30,00");
    expect(html).not.toContain("R$ 360,00");
  });

  it("informa histórico vazio e distingue valor antigo indisponível de gasto zero", () => {
    expect(markup({ ...report, total_purchases: 0, total_units: 0, totals: [], items: [] })).toContain("Você ainda não tem compras confirmadas");
    const html = markup({ ...report,
      totals: [{ ...report.totals[0], spent_amount_minor: 0, amounts_unavailable_count: 1 }],
      items: [{ ...report.items[0], original_amount_minor: null, final_amount_minor: null }],
    });
    expect(html).toContain("Indisponível");
    expect(html).toContain("compra antiga sem valor gasto disponível");
    expect(html).toContain("Gasto com valor registrado");
  });

  it("mantém resumos de moedas diferentes separados", () => {
    const html = markup({ ...report, totals: [...report.totals, { ...report.totals[0], currency: "USD", spent_amount_minor: 800 }] });
    expect(html).toContain("Resumo · BRL");
    expect(html).toContain("Resumo · USD");
    expect(html).toContain("US$ 8,00");
  });

  it("consulta histórico autenticado paginado sem enviar identificador de comprador", async () => {
    const request = vi.fn().mockResolvedValue(report);
    const api = createMarketplaceApi({ requestAuthenticated: request, enrollDevice: vi.fn(), createError: (message) => new Error(message) });
    expect(await api.loadOwnPurchases(20)).toBe(report);
    expect(request).toHaveBeenCalledExactlyOnceWith("GET", "/v1/trq-bec/coupons/purchases/mine?limit=20&offset=20");
  });
});
