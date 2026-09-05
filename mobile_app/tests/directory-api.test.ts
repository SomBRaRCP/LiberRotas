import { describe, expect, it, vi } from "vitest";

import {
  createDirectoryApi,
  normalizeDirectoryProfile,
} from "../src/features/directory/api";
import type { AuthenticatedRequest } from "../src/api/http-client";


describe("directory api", () => {
  it("normaliza o perfil sem aceitar papel desconhecido", () => {
    expect(normalizeDirectoryProfile({
      uid: "user-1",
      role: "admin",
      display_name: "Pessoa Teste",
      interests: ["Feiras", 42],
      created_at: "2026-08-03T12:00:00Z",
    })).toEqual({
      firebase_uid: "user-1",
      role: "visitor",
      display_name: "Pessoa Teste",
      city: "",
      category: "",
      interests: ["Feiras"],
      address: null,
      avatar_uri: null,
      created_at_ms: Date.parse("2026-08-03T12:00:00Z"),
      updated_at: null,
    });
  });

  it("preserva o contrato de atualização do perfil", async () => {
    const request = vi.fn(async () => ({
      firebase_uid: "user-1",
      role: "entrepreneur",
      display_name: "Ateliê Local",
      interests: ["Artesanato"],
    })) as unknown as AuthenticatedRequest;
    const api = createDirectoryApi(request);

    const result = await api.syncPublicDirectoryProfile({
      displayName: "  Ateliê Local  ",
      city: "  Pinhais - PR ",
      category: " Artesanato ",
      interests: [" Artesanato ", "", " Turismo "],
      address: " Rua de Teste, 100 ",
      avatarUri: "file:///foto-local.jpg",
    });

    expect(request).toHaveBeenCalledWith("PUT", "/v1/profile/public", {
      display_name: "Ateliê Local",
      city: "Pinhais - PR",
      category: "Artesanato",
      interests: ["Artesanato", "Turismo"],
      address: "Rua de Teste, 100",
      avatar_uri: null,
    });
    expect(result.role).toBe("entrepreneur");
  });

  it("não chama o backend para pesquisa menor que dois caracteres", async () => {
    const request = vi.fn() as unknown as AuthenticatedRequest;
    const api = createDirectoryApi(request);

    await expect(api.searchGlobalDirectory(" a ")).resolves.toEqual([]);
    expect(request).not.toHaveBeenCalled();
  });
});
