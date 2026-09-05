export type HttpMethod = "DELETE" | "GET" | "PATCH" | "POST" | "PUT";

export type HttpProblem = {
  code: string;
  message: string;
};

export type AuthenticatedRequest = <T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  forceTokenRefresh?: boolean,
) => Promise<T>;

export type PublicPostRequest = <T>(path: string, body: unknown) => Promise<T>;

type TrqBecHttpClientOptions = {
  baseUrl: string;
  timeoutMs: number;
  getIdToken: (forceRefresh?: boolean) => Promise<string>;
  mapError: (data: unknown, status: number) => HttpProblem;
  onRejectedSession: () => Promise<void>;
  createError: (message: string, code: string) => Error;
  isServiceError: (error: unknown) => boolean;
};

const REVOKED_SESSION_CODES = new Set([
  "AUTH_REQUIRED",
  "AUTH_BEARER_REQUIRED",
  "AUTH_TOKEN_INVALID",
  "AUTH_TOKEN_REVOKED",
  "SESSION_REVOKED",
]);

/**
 * Infraestrutura HTTP compartilhada pelos módulos do aplicativo.
 *
 * Este arquivo não conhece Firebase, telas ou domínios. As dependências de
 * autenticação, tradução de erro e limpeza de sessão são recebidas por injeção,
 * o que mantém o transporte testável sem duplicar regras entre features.
 */
export function createTrqBecHttpClient(options: TrqBecHttpClientOptions): {
  requestAuthenticated: AuthenticatedRequest;
  requestPublic: PublicPostRequest;
} {
  function assertConfigured() {
    if (!options.baseUrl) {
      throw options.createError(
        "Configure EXPO_PUBLIC_TRQ_BEC_API_URL para usar produtos, ofertas e resgates.",
        "BACKEND_NOT_CONFIGURED",
      );
    }
  }

  const requestAuthenticated: AuthenticatedRequest = async <T>(
    method: HttpMethod,
    path: string,
    body?: unknown,
    forceTokenRefresh = false,
  ): Promise<T> => {
    assertConfigured();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs);

    try {
      const send = async (refreshToken = false) => fetch(`${options.baseUrl}${path}`, {
        method,
        headers: {
          authorization: `Bearer ${await options.getIdToken(refreshToken)}`,
          ...(body === undefined ? {} : { "content-type": "application/json" }),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: controller.signal,
      });

      let response = await send(forceTokenRefresh);
      let data = await response.json().catch(() => null) as T | unknown;

      // Uma claim recém-aplicada pode ainda não estar no token em cache. A API
      // rejeita antes de qualquer efeito, portanto a repetição com token novo é segura.
      const firstProblem = response.ok ? null : options.mapError(data, response.status);
      if (firstProblem?.code === "ENTREPRENEUR_CLAIM_REQUIRED") {
        response = await send(true);
        data = await response.json().catch(() => null) as T | unknown;
      }

      if (!response.ok) {
        const problem = options.mapError(data, response.status);
        if (response.status === 401 && REVOKED_SESSION_CODES.has(problem.code)) {
          await options.onRejectedSession();
        }
        throw options.createError(problem.message, problem.code);
      }
      return data as T;
    } catch (error) {
      if (options.isServiceError(error)) throw error;
      if (error instanceof Error && error.name === "AbortError") {
        throw options.createError("O servidor TRQ-BEC demorou para responder.", "BACKEND_TIMEOUT");
      }
      throw options.createError(
        "Não foi possível alcançar o backend TRQ-BEC. Verifique sua internet e se a API pública está disponível.",
        "BACKEND_UNREACHABLE",
      );
    } finally {
      clearTimeout(timeout);
    }
  };

  const requestPublic: PublicPostRequest = async <T>(path: string, body: unknown): Promise<T> => {
    assertConfigured();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs);
    try {
      const response = await fetch(`${options.baseUrl}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => null) as T | unknown;
      if (!response.ok) {
        const problem = options.mapError(data, response.status);
        throw options.createError(problem.message, problem.code);
      }
      return data as T;
    } catch (error) {
      if (options.isServiceError(error)) throw error;
      if (error instanceof Error && error.name === "AbortError") {
        throw options.createError("O servidor demorou para receber a solicitação.", "BACKEND_TIMEOUT");
      }
      throw options.createError(
        "Não foi possível enviar a solicitação ao Suporte. Verifique sua conexão e tente novamente.",
        "BACKEND_UNREACHABLE",
      );
    } finally {
      clearTimeout(timeout);
    }
  };

  return { requestAuthenticated, requestPublic };
}
