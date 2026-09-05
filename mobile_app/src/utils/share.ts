import { Alert, Platform, Share } from "react-native";

const PUBLIC_APP_ORIGIN = "https://app.liberrotas.com.br";

export type LiberRotasShareKind =
  | "profile"
  | "post"
  | "product"
  | "offer"
  | "fair"
  | "place"
  | "event";

export type ProfileShareTab = "posts" | "products" | "offers" | "fairs";

type ProfileShareTarget = {
  tab: ProfileShareTab;
  itemId: string;
};

export type LiberRotasShareInput = {
  kind: LiberRotasShareKind;
  title: string;
  description?: string | null;
  /** Informe apenas rotas públicas que realmente existem no aplicativo. */
  path?: string | null;
};

function normalizeText(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function publicUrl(path?: string | null): string {
  const normalizedPath = normalizeText(path);
  if (!normalizedPath) return `${PUBLIC_APP_ORIGIN}/`;
  return `${PUBLIC_APP_ORIGIN}/${normalizedPath.replace(/^\/+/, "")}`;
}

function kindLabel(kind: LiberRotasShareKind): string {
  switch (kind) {
    case "profile": return "Perfil no LiberRotas";
    case "post": return "Publicação no LiberRotas";
    case "product": return "Produto no LiberRotas";
    case "offer": return "Oferta no LiberRotas";
    case "fair": return "Feira ao vivo no LiberRotas";
    case "place": return "Local no LiberRotas";
    case "event": return "Evento no LiberRotas";
  }
}

export function profileSharePath(profileId: string, target?: ProfileShareTarget | null): string {
  const normalizedProfileId = profileId.trim();
  if (!normalizedProfileId) return "/";
  const basePath = `/profile/${encodeURIComponent(normalizedProfileId)}`;
  const normalizedItemId = target?.itemId.trim() || "";
  if (!target || !normalizedItemId) return basePath;
  return `${basePath}?tab=${encodeURIComponent(target.tab)}&item=${encodeURIComponent(normalizedItemId)}`;
}

/**
 * Aceita somente retornos internos para perfis públicos. A reconstrução da URL
 * elimina parâmetros desconhecidos, barras codificadas e tentativas de usar
 * outro domínio antes que o login faça qualquer redirecionamento.
 */
export function normalizeSafeProfileReturnTo(value: string | string[] | null | undefined): string | null {
  const candidate = (Array.isArray(value) ? value[0] : value)?.trim() || "";
  if (
    !candidate
    || candidate.length > 1_024
    || !candidate.startsWith("/")
    || candidate.startsWith("//")
    || candidate.includes("\\")
    || /[\u0000-\u001f\u007f]/.test(candidate)
  ) {
    return null;
  }

  try {
    const parsed = new URL(candidate, PUBLIC_APP_ORIGIN);
    if (parsed.origin !== PUBLIC_APP_ORIGIN || parsed.hash) return null;
    const routeMatch = parsed.pathname.match(/^\/profile\/([^/]+)$/);
    if (!routeMatch?.[1]) return null;
    const profileId = decodeURIComponent(routeMatch[1]).trim();
    if (!profileId || profileId.length > 256 || profileId.includes("/") || profileId.includes("\\")) return null;

    const allowedKeys = new Set(["tab", "item"]);
    if ([...parsed.searchParams.keys()].some((key) => !allowedKeys.has(key))) return null;
    if (parsed.searchParams.getAll("tab").length > 1 || parsed.searchParams.getAll("item").length > 1) return null;

    const tab = parsed.searchParams.get("tab");
    const itemId = parsed.searchParams.get("item")?.trim() || "";
    const validTab = tab === "posts" || tab === "products" || tab === "offers" || tab === "fairs";
    if (!tab && !itemId) return profileSharePath(profileId);
    if (!validTab || !itemId || itemId.length > 256 || /[\u0000-\u001f\u007f]/.test(itemId)) return null;
    return profileSharePath(profileId, { tab, itemId });
  } catch {
    return null;
  }
}

/**
 * Retorno pós-login restrito a rotas internas conhecidas. O token de aprovação
 * de dispositivo nunca passa pela query: ele fica somente no fragmento Web,
 * que é consumido pela tela de segurança antes do redirecionamento ao login.
 */
export function normalizeSafeReturnTo(value: string | string[] | null | undefined): string | null {
  const candidate = (Array.isArray(value) ? value[0] : value)?.trim() || "";
  if (
    !candidate
    || candidate.length > 1_024
    || !candidate.startsWith("/")
    || candidate.startsWith("//")
    || candidate.includes("\\")
    || /[\u0000-\u001f\u007f]/.test(candidate)
  ) {
    return null;
  }

  try {
    const parsed = new URL(candidate, PUBLIC_APP_ORIGIN);
    if (
      parsed.origin === PUBLIC_APP_ORIGIN
      && parsed.pathname === "/account/devices"
      && !parsed.search
      && !parsed.hash
    ) {
      return "/account/devices";
    }
  } catch {
    return null;
  }

  return normalizeSafeProfileReturnTo(candidate);
}

export function createLiberRotasSharePayload(input: LiberRotasShareInput): {
  title: string;
  text: string;
  url: string;
} {
  const title = normalizeText(input.title) || kindLabel(input.kind);
  const description = normalizeText(input.description);
  const url = publicUrl(input.path);
  const text = [kindLabel(input.kind), title, description, url].filter(Boolean).join("\n");
  return { title, text, url };
}

async function shareOnWeb(payload: ReturnType<typeof createLiberRotasSharePayload>): Promise<void> {
  const browserNavigator = typeof navigator === "undefined" ? undefined : navigator;
  if (browserNavigator?.share) {
    try {
      const textWithoutDuplicatedUrl = payload.text.endsWith(`\n${payload.url}`)
        ? payload.text.slice(0, -(payload.url.length + 1))
        : payload.text;
      await browserNavigator.share({ title: payload.title, text: textWithoutDuplicatedUrl, url: payload.url });
      return;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
    }
  }

  if (browserNavigator?.clipboard?.writeText) {
    try {
      await browserNavigator.clipboard.writeText(payload.text);
      if (typeof window !== "undefined") {
        window.alert("Conteúdo copiado. Agora você pode colar onde quiser compartilhar.");
      }
      return;
    } catch {
      // Alguns navegadores bloqueiam a área de transferência fora de HTTPS.
    }
  }

  if (typeof window !== "undefined") {
    window.prompt("Copie este conteúdo para compartilhar:", payload.text);
  }
}

export async function shareLiberRotasItem(input: LiberRotasShareInput): Promise<void> {
  const payload = createLiberRotasSharePayload(input);
  try {
    if (Platform.OS === "web") {
      await shareOnWeb(payload);
      return;
    }
    if (Platform.OS === "ios") {
      const message = payload.text.endsWith(`\n${payload.url}`)
        ? payload.text.slice(0, -(payload.url.length + 1))
        : payload.text;
      await Share.share({ title: payload.title, message, url: payload.url });
      return;
    }
    await Share.share({ title: payload.title, message: payload.text });
  } catch (error) {
    console.warn("Não foi possível abrir o compartilhamento do sistema.", error);
    if (Platform.OS === "web" && typeof window !== "undefined") {
      window.alert("Não foi possível compartilhar agora. Tente novamente.");
      return;
    }
    Alert.alert("Não foi possível compartilhar", "O sistema não conseguiu abrir as opções de compartilhamento. Tente novamente.");
  }
}
