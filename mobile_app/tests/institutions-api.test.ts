import { describe, expect, it, vi } from "vitest";

import type { AuthenticatedRequest } from "../src/api/http-client";
import { createInstitutionsApi } from "../src/features/institutions/api";


function buildApi(requestAuthenticated: AuthenticatedRequest) {
  return createInstitutionsApi(requestAuthenticated);
}

describe("institutions api", () => {
  it("normaliza os campos do grupo sem alterar o contrato", async () => {
    const request = vi.fn(async () => ({ group_id: "IGRP-EXEMPLO123" })) as unknown as AuthenticatedRequest;

    await buildApi(request).createInstitutionGroup({
      name: "  Rede Local  ",
      description: "  Produtores locais  ",
      city: "  Curitiba  ",
    });

    expect(request).toHaveBeenCalledWith("POST", "/v1/institution/groups", {
      name: "Rede Local",
      description: "Produtores locais",
      city: "Curitiba",
    });
  });

  it("pagina todas as filiacões do grupo", async () => {
    const requestMock = vi.fn()
      .mockResolvedValueOnce({ memberships: [{ membership_id: "IGM-1" }], has_more: true })
      .mockResolvedValueOnce({ memberships: [{ membership_id: "IGM-2" }], has_more: false });
    const request = requestMock as unknown as AuthenticatedRequest;

    const result = await buildApi(request).listInstitutionGroupMemberships("IGRP-A/B");

    expect(result.map((item) => item.membership_id)).toEqual(["IGM-1", "IGM-2"]);
    expect(requestMock.mock.calls[0][1]).toBe("/v1/institution/groups/IGRP-A%2FB/members?limit=100&offset=0");
    expect(requestMock.mock.calls[1][1]).toBe("/v1/institution/groups/IGRP-A%2FB/members?limit=100&offset=100");
  });

  it("codifica o periodo e o filtro do relatorio de vendas", async () => {
    const request = vi.fn(async () => ({})) as unknown as AuthenticatedRequest;

    await buildApi(request).loadInstitutionSalesReport({
      groupId: "IGRP-A/B",
      periodFrom: "2026-08-01T00:00:00-03:00",
      periodTo: "2026-08-31T23:59:59-03:00",
    });

    expect(request).toHaveBeenCalledWith(
      "GET",
      "/v1/institution/reports/sales?from=2026-08-01T00%3A00%3A00-03%3A00&to=2026-08-31T23%3A59%3A59-03%3A00&group_id=IGRP-A%2FB&limit=100&offset=0",
    );
  });

  it("converte cotas de vendedores e produtos para snake case", async () => {
    const requestMock = vi.fn(async () => ({}));
    const api = buildApi(requestMock as unknown as AuthenticatedRequest);

    await api.setInstitutionFundedEventSellerAllocations("IEVT-A/B", [
      { sellerUid: "seller-1", allocatedAmountMinor: 12_500 },
    ]);
    await api.setEntrepreneurFundedEventProductAllocations("IEVT-A/B", [
      { productId: "product-1", allocatedAmountMinor: 7_500 },
    ]);

    expect(requestMock.mock.calls[0]).toEqual([
      "PUT",
      "/v1/institution/funded-events/IEVT-A%2FB/seller-allocations",
      { allocations: [{ seller_uid: "seller-1", allocated_amount_minor: 12_500 }] },
    ]);
    expect(requestMock.mock.calls[1]).toEqual([
      "PUT",
      "/v1/entrepreneur/funded-events/IEVT-A%2FB/product-allocations",
      { allocations: [{ product_id: "product-1", allocated_amount_minor: 7_500 }] },
    ]);
  });

  it("envia somente os campos definidos do perfil institucional", async () => {
    const request = vi.fn(async () => ({})) as unknown as AuthenticatedRequest;

    await buildApi(request).updateInstitutionProfile({
      name: "  Instituto Escola  ",
      description: "   ",
    });

    expect(request).toHaveBeenCalledWith("PATCH", "/v1/institution/profile", {
      name: "Instituto Escola",
      description: null,
    });
  });
});
