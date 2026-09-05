import { Platform } from "react-native";

const APPROVAL_TOKEN_PATTERN = /^[A-Za-z0-9_-]{32,128}$/;
let pendingApprovalTokenInMemory: string | null = null;

type WebApprovalGlobal = typeof globalThis & {
  location?: Location;
  history?: History;
};

function isApprovalToken(value: string | null | undefined): value is string {
  return Boolean(value && APPROVAL_TOKEN_PATTERN.test(value));
}

/**
 * Consome o token somente do fragmento Web, que não é enviado ao Nginx.
 * O fragmento some da barra imediatamente e o valor permanece apenas na
 * memória da aba durante o redirecionamento anônimo -> login -> dispositivos.
 */
export function consumePendingDeviceApprovalToken(): string | null {
  if (Platform.OS !== "web") return null;
  const web = globalThis as WebApprovalGlobal;
  const hash = web.location?.hash || "";
  const prefix = "#approval_token=";
  const tokenFromHash = hash.startsWith(prefix) && !hash.slice(prefix.length).includes("&")
    ? hash.slice(prefix.length)
    : "";

  if (hash && web.location && web.history) {
    web.history.replaceState(web.history.state, "", `${web.location.pathname}${web.location.search}`);
  }

  if (isApprovalToken(tokenFromHash)) {
    pendingApprovalTokenInMemory = tokenFromHash;
  } else if (hash) {
    pendingApprovalTokenInMemory = null;
  }
  return pendingApprovalTokenInMemory;
}

export function clearPendingDeviceApprovalToken(): void {
  pendingApprovalTokenInMemory = null;
}
