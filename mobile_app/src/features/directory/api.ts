import type { AuthenticatedRequest } from "@/api/http-client";

export type PublicDirectoryRole = "entrepreneur" | "visitor" | "institution";

export type PublicDirectoryProfile = {
  firebase_uid: string;
  role: PublicDirectoryRole;
  display_name: string;
  city: string;
  category: string;
  interests: string[];
  address: string | null;
  avatar_uri: string | null;
  created_at_ms: number | null;
  updated_at: string | null;
};

export type PublicDirectoryProfileInput = {
  displayName: string;
  city: string;
  category: string;
  interests: string[];
  address?: string | null;
  avatarUri?: string | null;
};

export type GlobalSearchKind = "profile" | "post" | "product" | "offer" | "fair" | "place";

export type GlobalSearchResult = {
  id: string;
  kind: GlobalSearchKind;
  title: string;
  subtitle: string;
  profile_id: string | null;
  created_at: string | null;
  target_url: string | null;
  status: string | null;
};

type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function normalizeDirectoryProfile(value: unknown): PublicDirectoryProfile {
  const item = asRecord(value);
  const role = asString(item.role, "visitor") as PublicDirectoryRole;
  const createdAt = asNullableString(item.created_at);
  return {
    firebase_uid: asString(item.firebase_uid || item.uid),
    role: ["visitor", "entrepreneur", "institution"].includes(role) ? role : "visitor",
    display_name: asString(item.display_name, "Usuário LiberRotas"),
    city: asString(item.city),
    category: asString(item.category),
    interests: Array.isArray(item.interests)
      ? item.interests.filter((entry): entry is string => typeof entry === "string")
      : [],
    address: asNullableString(item.address),
    avatar_uri: asNullableString(item.avatar_uri),
    created_at_ms: typeof item.created_at_ms === "number"
      ? item.created_at_ms
      : createdAt ? Date.parse(createdAt) : null,
    updated_at: asNullableString(item.updated_at),
  };
}

export function createDirectoryApi(requestAuthenticated: AuthenticatedRequest) {
  async function syncPublicDirectoryProfile(
    input: PublicDirectoryProfileInput,
  ): Promise<PublicDirectoryProfile> {
    const response = await requestAuthenticated<unknown>("PUT", "/v1/profile/public", {
      display_name: input.displayName.trim(),
      city: input.city.trim(),
      category: input.category.trim(),
      interests: input.interests.map((interest) => interest.trim()).filter(Boolean).slice(0, 8),
      address: input.address?.trim() || null,
      avatar_uri: input.avatarUri && /^https?:\/\//i.test(input.avatarUri) ? input.avatarUri.trim() : null,
    });
    return normalizeDirectoryProfile(response);
  }

  async function loadOwnPublicDirectoryProfile(): Promise<PublicDirectoryProfile> {
    const response = await requestAuthenticated<unknown>("GET", "/v1/directory/profile/me");
    return normalizeDirectoryProfile(response);
  }

  async function loadPublicDirectoryProfile(firebaseUid: string): Promise<PublicDirectoryProfile> {
    const response = await requestAuthenticated<unknown>(
      "GET",
      `/v1/profile/public/${encodeURIComponent(firebaseUid)}`,
    );
    return normalizeDirectoryProfile(response);
  }

  async function searchGlobalDirectory(query: string, limit = 30): Promise<GlobalSearchResult[]> {
    const normalized = query.trim();
    if (normalized.length < 2) return [];
    const safeLimit = Math.max(1, Math.min(50, Math.trunc(limit)));
    const response = await requestAuthenticated<{ results?: unknown[]; items?: unknown[] }>(
      "GET",
      `/v1/search?q=${encodeURIComponent(normalized)}&types=${encodeURIComponent("PROFILE,PRODUCT,OFFER,POST")}&limit=${safeLimit}`,
    );
    return (response.results || response.items || []).map((value) => {
      const item = asRecord(value);
      const rawKind = asString(item.kind || item.type).toLowerCase();
      const kind: GlobalSearchKind = ["profile", "post", "product", "offer", "fair", "place"].includes(rawKind)
        ? rawKind as GlobalSearchKind
        : "post";
      return {
        id: asString(item.id),
        kind,
        title: asString(item.title),
        subtitle: asString(item.subtitle),
        profile_id: asNullableString(item.profile_id || item.owner_uid),
        created_at: asNullableString(item.created_at),
        target_url: asNullableString(item.target_url || item.route),
        status: asNullableString(item.status),
      };
    }).filter((item) => Boolean(item.id && item.title));
  }

  return {
    syncPublicDirectoryProfile,
    loadOwnPublicDirectoryProfile,
    loadPublicDirectoryProfile,
    searchGlobalDirectory,
  };
}
