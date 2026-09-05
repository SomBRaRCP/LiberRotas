import { afterEach, describe, expect, it, vi } from "vitest";

import { createTrqBecHttpClient } from "../src/api/http-client";


class TestServiceError extends Error {
  constructor(
    message: string,
    public readonly code: string,
  ) {
    super(message);
  }
}

function buildClient(overrides: Partial<Parameters<typeof createTrqBecHttpClient>[0]> = {}) {
  return createTrqBecHttpClient({
    baseUrl: "https://api.example.test",
    timeoutMs: 1_000,
    getIdToken: async (refresh = false) => refresh ? "token-new" : "token-old",
    mapError: (data, status) => {
      const payload = data as { code?: string; message?: string } | null;
      return {
        code: payload?.code || `HTTP_${status}`,
        message: payload?.message || "Erro de teste",
      };
    },
    onRejectedSession: async () => undefined,
    createError: (message, code) => new TestServiceError(message, code),
    isServiceError: (error) => error instanceof TestServiceError,
    ...overrides,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TRQ-BEC HTTP client", () => {
  it("renova a claim uma vez antes de devolver o resultado", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: "ENTREPRENEUR_CLAIM_REQUIRED",
      }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await buildClient().requestAuthenticated<{ ok: boolean }>(
      "GET",
      "/v1/access/me",
    );

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][1].headers.authorization).toBe("Bearer token-old");
    expect(fetchMock.mock.calls[1][1].headers.authorization).toBe("Bearer token-new");
  });

  it("limpa a sessão quando o backend informa token revogado", async () => {
    const onRejectedSession = vi.fn(async () => undefined);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: "AUTH_TOKEN_REVOKED",
      message: "Sessão revogada",
    }), { status: 401 })));

    await expect(buildClient({ onRejectedSession }).requestAuthenticated(
      "GET",
      "/v1/access/me",
    )).rejects.toMatchObject({ code: "AUTH_TOKEN_REVOKED" });
    expect(onRejectedSession).toHaveBeenCalledOnce();
  });
});
