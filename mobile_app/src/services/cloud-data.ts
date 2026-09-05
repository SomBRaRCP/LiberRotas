import {
  collection,
  deleteField,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  limit,
  onSnapshot,
  orderBy,
  query,
  setDoc,
  where,
  type DocumentData,
  type Unsubscribe,
} from "firebase/firestore";
import { auth, db } from "@/services/firebase";
import type { AccountType, FeedPost, PostMedia, UserProfile } from "@/context/app-context";
import {
  estimatePinhaisMapPosition,
  pinhaisCategoryLabels,
  resolveLiveFairStatus,
  type LiveFair,
  type LiveFairStatus,
  type PinhaisCategory,
  type PinhaisPlace,
} from "@/data/pinhais";

const LGPD_NOTICE_VERSION = "2026-06-23";
const MAX_SYNCED_POSTS = 80;
const MAX_PUBLIC_ENTREPRENEURS = 200;
const LIVE_FAIR_CLOCK_REFRESH_MS = 30_000;
const MAX_LIVE_FAIR_DURATION_MS = 24 * 60 * 60 * 1000;
const MIN_PUBLIC_ADDRESS_LENGTH = 10;
const MAX_PUBLIC_ADDRESS_LENGTH = 240;
const MIN_PRIVATE_PIX_KEY_LENGTH = 3;
const MAX_PRIVATE_PIX_KEY_LENGTH = 140;

const PINHAIS_CATEGORIES: readonly PinhaisCategory[] = [
  "pontos_turisticos",
  "parques",
  "feiras_livres",
  "artesanato",
  "bordados",
  "gastronomia",
  "eventos",
  "comercio_local",
];

export type NetworkInteractionKind = "post_like" | "route_save" | "favorite";

export type PublicEntrepreneurProfileSummary = {
  id: string;
  name: string;
  city: string;
  address?: string;
  category: string;
  avatarUri?: string;
  createdAtMs: number;
  updatedAtMs: number;
};

export type OwnPrivateProfile = {
  pixKey: string;
};

function nowMs() {
  return Date.now();
}

function sanitizeDocId(value: string) {
  return value.replace(/[/?#[\]\s]+/g, "_");
}

function sanitizeText(value: unknown, fallback = "") {
  return typeof value === "string" ? value.trim() : fallback;
}

function sanitizeFiniteNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function isPinhaisCategory(value: unknown): value is PinhaisCategory {
  return typeof value === "string" && PINHAIS_CATEGORIES.includes(value as PinhaisCategory);
}

function sanitizeRole(value: unknown): AccountType {
  return value === "entrepreneur" ? "entrepreneur" : "visitor";
}

function sanitizeInterests(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string").map((item) => item.trim()).filter(Boolean).slice(0, 8)
    : [];
}

function normalizePublicAddress(value: unknown, role: AccountType) {
  if (role !== "entrepreneur") return undefined;
  const address = sanitizeText(value);
  if (!address) return undefined;
  if (address.length < MIN_PUBLIC_ADDRESS_LENGTH || address.length > MAX_PUBLIC_ADDRESS_LENGTH) return undefined;
  return address;
}

function isRemoteUri(uri?: string) {
  return Boolean(uri?.startsWith("https://") || uri?.startsWith("http://"));
}

function normalizeCloudMedia(value: unknown): PostMedia | undefined {
  if (!value || typeof value !== "object") return undefined;
  const media = value as {
    media_id?: unknown;
    mediaId?: unknown;
    type?: unknown;
    uri?: unknown;
  };
  const mediaId = sanitizeText(media.mediaId || media.media_id);
  const legacyUri = typeof media.uri === "string" && isRemoteUri(media.uri) ? media.uri : undefined;

  if (media.type === "image" && (mediaId || legacyUri)) {
    return {
      type: "image",
      ...(mediaId ? { mediaId } : {}),
      ...(legacyUri ? { uri: legacyUri } : {}),
    };
  }
  if (media.type === "video" && legacyUri) return { type: "video", uri: legacyUri };
  return undefined;
}

function basePrivacyMetadata(fields: string[]) {
  return {
    lgpdNoticeVersion: LGPD_NOTICE_VERSION,
    syncedAtMs: nowMs(),
    minimizedFields: fields,
  };
}

/**
 * Perfil publico sincronizado na nuvem.
 *
 * Por LGPD, este documento nao recebe senha, e-mail, foto local do aparelho
 * nem qualquer dado sensivel. Ele guarda apenas dados que ja aparecem na
 * interface publica do app.
 */
export async function savePublicProfile(profile: UserProfile) {
  const profileRef = doc(db, "public_profiles", sanitizeDocId(profile.id));
  const currentSnapshot = await getDoc(profileRef);
  const currentData = currentSnapshot.exists() ? currentSnapshot.data() : null;
  const currentCreatedAtMs = sanitizeFiniteNumber(currentData?.createdAtMs);
  const legacyCreatedAtMs = sanitizeFiniteNumber(currentData?.updatedAtMs);
  const proposedCreatedAtMs = sanitizeFiniteNumber(profile.createdAtMs);
  const createdAtMs = currentCreatedAtMs && currentCreatedAtMs > 0
    ? currentCreatedAtMs
    : legacyCreatedAtMs && legacyCreatedAtMs > 0
      ? legacyCreatedAtMs
      : proposedCreatedAtMs && proposedCreatedAtMs > 0
        ? proposedCreatedAtMs
        : nowMs();
  const address = normalizePublicAddress(profile.address, profile.role);
  if (profile.role === "entrepreneur" && profile.address?.trim() && !address) {
    throw new Error(`O endereco publico deve ter entre ${MIN_PUBLIC_ADDRESS_LENGTH} e ${MAX_PUBLIC_ADDRESS_LENGTH} caracteres.`);
  }

  await setDoc(
    profileRef,
    {
      userId: profile.id,
      displayName: profile.name.trim(),
      role: profile.role,
      city: profile.city.trim(),
      address: address || null,
      category: profile.category.trim(),
      interests: sanitizeInterests(profile.interests),
      avatarUri: isRemoteUri(profile.avatarUri) ? profile.avatarUri : null,
      // Remove qualquer campo Pix legado que possa ter sido gravado por um
      // cliente antigo. A chave atual existe somente em private_profiles.
      pixKey: deleteField(),
      createdAtMs,
      updatedAtMs: nowMs(),
      privacy: basePrivacyMetadata([
        "userId",
        "displayName",
        "role",
        "city",
        ...(address ? ["address"] : []),
        "category",
        "interests",
        "createdAtMs",
      ]),
    },
    { merge: true },
  );
}

/**
 * Carrega os dados privados somente da conta autenticada.
 *
 * A regra do Firestore bloqueia leitura por visitantes e por outros UIDs.
 * A função também evita que o cliente escolha arbitrariamente outro usuário.
 */
export async function loadOwnPrivateProfile(): Promise<OwnPrivateProfile> {
  const userId = auth.currentUser?.uid;
  if (!userId) throw new Error("Entre novamente para carregar os dados privados.");

  const snapshot = await getDoc(doc(db, "private_profiles", sanitizeDocId(userId)));
  if (!snapshot.exists()) return { pixKey: "" };

  const data = snapshot.data();
  if (data.userId !== userId) throw new Error("O perfil privado retornado não pertence a esta conta.");

  const pixKey = sanitizeText(data.pixKey);
  if (pixKey.length > MAX_PRIVATE_PIX_KEY_LENGTH) {
    throw new Error("A chave Pix salva ultrapassa o limite permitido.");
  }

  return { pixKey };
}

/** Salva ou remove a chave Pix privada da conta autenticada. */
export async function saveOwnPixKey(value: string) {
  const userId = auth.currentUser?.uid;
  if (!userId) throw new Error("Entre novamente para salvar a chave Pix.");

  const profileRef = doc(db, "private_profiles", sanitizeDocId(userId));
  const pixKey = value.trim();

  if (!pixKey) {
    await deleteDoc(profileRef);
    return;
  }

  if (pixKey.length < MIN_PRIVATE_PIX_KEY_LENGTH) {
    throw new Error(`A chave Pix deve ter pelo menos ${MIN_PRIVATE_PIX_KEY_LENGTH} caracteres.`);
  }
  if (pixKey.length > MAX_PRIVATE_PIX_KEY_LENGTH) {
    throw new Error(`A chave Pix deve ter no máximo ${MAX_PRIVATE_PIX_KEY_LENGTH} caracteres.`);
  }

  await setDoc(profileRef, {
    userId,
    pixKey,
    updatedAtMs: nowMs(),
  });
}


export async function loadPublicProfile(userId: string, emailFallback = ""): Promise<UserProfile | null> {
  const snapshot = await getDoc(doc(db, "public_profiles", sanitizeDocId(userId)));
  if (!snapshot.exists()) return null;

  const data = snapshot.data();
  const role = sanitizeRole(data.role);
  const updatedAtMs = sanitizeFiniteNumber(data.updatedAtMs) ?? 0;
  const createdAtMs = sanitizeFiniteNumber(data.createdAtMs) ?? updatedAtMs;
  const displayName = sanitizeText(data.displayName, emailFallback || "Usuário LiberRotas");

  return {
    id: userId,
    role,
    name: displayName,
    email: emailFallback,
    city: sanitizeText(data.city, "Pinhais - PR"),
    address: normalizePublicAddress(data.address, role),
    category: sanitizeText(data.category, role === "entrepreneur" ? "Turismo comunitário" : "Visitante LiberRotas"),
    interests: sanitizeInterests(data.interests),
    avatarUri: isRemoteUri(data.avatarUri) ? data.avatarUri : undefined,
    createdAtMs: createdAtMs > 0 ? createdAtMs : undefined,
  };
}

function normalizePublicEntrepreneurProfile(
  documentId: string,
  data: DocumentData,
): PublicEntrepreneurProfileSummary | null {
  if (data.role !== "entrepreneur") return null;

  const name = sanitizeText(data.displayName);
  if (!documentId || !name) return null;

  const updatedAtMs = sanitizeFiniteNumber(data.updatedAtMs) ?? 0;
  const createdAtMs = sanitizeFiniteNumber(data.createdAtMs) ?? updatedAtMs;
  const avatarUri = isRemoteUri(data.avatarUri) ? (data.avatarUri as string) : undefined;
  const address = normalizePublicAddress(data.address, "entrepreneur");

  return {
    id: documentId,
    name,
    city: sanitizeText(data.city, "Pinhais - PR"),
    ...(address ? { address } : {}),
    category: sanitizeText(data.category, "Empreendedor local"),
    ...(avatarUri ? { avatarUri } : {}),
    createdAtMs,
    updatedAtMs,
  };
}

export function subscribeToPublicEntrepreneurProfiles(
  onProfiles: (profiles: PublicEntrepreneurProfileSummary[]) => void,
  onError: (error: Error) => void,
): Unsubscribe {
  const profilesQuery = query(
    collection(db, "public_profiles"),
    where("role", "==", "entrepreneur"),
    limit(MAX_PUBLIC_ENTREPRENEURS),
  );

  return onSnapshot(
    profilesQuery,
    (snapshot) => {
      const profiles = snapshot.docs
        .map((documentSnapshot) => normalizePublicEntrepreneurProfile(documentSnapshot.id, documentSnapshot.data()))
        .filter((profile): profile is PublicEntrepreneurProfileSummary => Boolean(profile))
        .sort((left, right) => right.createdAtMs - left.createdAtMs || left.name.localeCompare(right.name, "pt-BR"));
      onProfiles(profiles);
    },
    onError,
  );
}

function normalizeApprovedCuratedPlace(documentId: string, data: DocumentData): PinhaisPlace | null {
  if (data.status !== "approved") return null;

  const ownerId = sanitizeText(data.ownerId);
  const createdBy = sanitizeText(data.createdBy);
  const ownerName = sanitizeText(data.ownerName);
  const nome = sanitizeText(data.name, sanitizeText(data.nome));
  const endereco = sanitizeText(data.address, sanitizeText(data.endereco));
  const latitude = sanitizeFiniteNumber(data.latitude);
  const longitude = sanitizeFiniteNumber(data.longitude);
  const createdAtMs = sanitizeFiniteNumber(data.createdAtMs);

  if (
    !documentId ||
    !ownerId ||
    createdBy !== ownerId ||
    ownerName.length < 2 ||
    ownerName.length > 100 ||
    nome.length < 2 ||
    nome.length > 120 ||
    endereco.length < 3 ||
    endereco.length > 240 ||
    !isPinhaisCategory(data.category ?? data.categoriaApp) ||
    latitude === null ||
    longitude === null ||
    createdAtMs === null ||
    !Number.isInteger(createdAtMs) ||
    createdAtMs <= 0 ||
    latitude < -90 ||
    latitude > 90 ||
    longitude < -180 ||
    longitude > 180
  ) {
    return null;
  }

  const categoriaApp = (data.category ?? data.categoriaApp) as PinhaisCategory;
  return {
    id: documentId,
    ownerId,
    ownerName,
    createdAtMs,
    nome,
    categoriaApp,
    endereco,
    latitude,
    longitude,
    rating: null,
    totalAvaliacoes: 0,
    origem: "curadoria_manual",
    buscaOrigem: "cadastro publico do empreendedor",
    ativo: true,
    curadoriaManual: true,
    potencialTuristico: 55,
    tags: ["empreendedor local", pinhaisCategoryLabels[categoriaApp]],
    resumo: `Ponto publicado por ${ownerName}.`,
    googleMapsUri: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${latitude},${longitude}`)}`,
    mapPosition: estimatePinhaisMapPosition(latitude, longitude),
  };
}

export function subscribeToApprovedCuratedPlaces(
  onPlaces: (places: PinhaisPlace[]) => void,
  onError: (error: Error) => void,
): Unsubscribe {
  const placesQuery = query(collection(db, "curated_places"), where("status", "==", "approved"));

  return onSnapshot(
    placesQuery,
    (snapshot) => {
      const places = snapshot.docs
        .map((documentSnapshot) => normalizeApprovedCuratedPlace(documentSnapshot.id, documentSnapshot.data()))
        .filter((place): place is PinhaisPlace => Boolean(place))
        .sort((left, right) => (right.createdAtMs ?? 0) - (left.createdAtMs ?? 0) || left.nome.localeCompare(right.nome, "pt-BR"));
      onPlaces(places);
    },
    onError,
  );
}

function sanitizeLiveFairStatus(value: unknown): LiveFairStatus | null {
  if (value === "scheduled" || value === "live" || value === "ended") return value;
  return null;
}

function normalizePublicLiveFair(documentId: string, data: DocumentData, referenceTimeMs = nowMs()): LiveFair | null {
  const ownerId = sanitizeText(data.ownerId);
  const createdBy = sanitizeText(data.createdBy);
  const ownerName = sanitizeText(data.ownerName);
  const name = sanitizeText(data.name);
  const address = sanitizeText(data.address);
  const latitude = sanitizeFiniteNumber(data.latitude);
  const longitude = sanitizeFiniteNumber(data.longitude);
  const startsAtMs = sanitizeFiniteNumber(data.startsAtMs);
  const endsAtMs = sanitizeFiniteNumber(data.endsAtMs);
  const createdAtMs = sanitizeFiniteNumber(data.createdAtMs);
  const storedStatus = sanitizeLiveFairStatus(data.status);
  const storedEndedAtMs = sanitizeFiniteNumber(data.endedAtMs);

  if (
    !documentId ||
    !ownerId ||
    createdBy !== ownerId ||
    ownerName.length < 2 ||
    ownerName.length > 100 ||
    name.length < 2 ||
    name.length > 120 ||
    address.length < 10 ||
    address.length > 240 ||
    latitude === null ||
    longitude === null ||
    startsAtMs === null ||
    endsAtMs === null ||
    createdAtMs === null ||
    !storedStatus ||
    !Number.isInteger(startsAtMs) ||
    !Number.isInteger(endsAtMs) ||
    !Number.isInteger(createdAtMs) ||
    startsAtMs <= 0 ||
    endsAtMs <= startsAtMs ||
    endsAtMs - startsAtMs > MAX_LIVE_FAIR_DURATION_MS ||
    createdAtMs <= 0 ||
    latitude < -90 ||
    latitude > 90 ||
    longitude < -180 ||
    longitude > 180 ||
    (storedEndedAtMs !== null && (!Number.isInteger(storedEndedAtMs) || storedEndedAtMs <= 0))
  ) {
    return null;
  }

  const status = resolveLiveFairStatus(
    {
      status: storedStatus,
      startsAtMs,
      endsAtMs,
      ...(storedEndedAtMs ? { endedAtMs: storedEndedAtMs } : {}),
    },
    referenceTimeMs,
  );
  const endedAtMs = status === "ended" ? storedEndedAtMs ?? endsAtMs : undefined;
  const endReason = status === "ended" && storedStatus === "ended" && data.endReason === "manual" ? "manual" : status === "ended" ? "scheduled" : undefined;

  return {
    id: documentId,
    ownerId,
    ownerName,
    name,
    address,
    latitude,
    longitude,
    startsAtMs,
    endsAtMs,
    createdAtMs,
    status,
    ...(endedAtMs ? { endedAtMs } : {}),
    ...(endReason ? { endReason } : {}),
    googleMapsUri: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${latitude},${longitude}`)}`,
    mapPosition: estimatePinhaisMapPosition(latitude, longitude),
  };
}

function sortPublicLiveFairs(fairs: LiveFair[]) {
  const statusOrder: Record<LiveFairStatus, number> = { live: 0, scheduled: 1, ended: 2 };
  return fairs.sort(
    (left, right) =>
      statusOrder[left.status] - statusOrder[right.status] ||
      (left.status === "ended" ? (right.endedAtMs ?? right.endsAtMs) - (left.endedAtMs ?? left.endsAtMs) : left.startsAtMs - right.startsAtMs) ||
      left.name.localeCompare(right.name, "pt-BR"),
  );
}

/**
 * Assina todas as feiras publicas. A lista e recalculada a cada 30 segundos
 * para mudar automaticamente de agendada/ao vivo para encerrada pelo horario.
 */
export function subscribeToPublicLiveFairs(
  onFairs: (fairs: LiveFair[]) => void,
  onError: (error: Error) => void,
): Unsubscribe {
  let cachedDocuments: { id: string; data: DocumentData }[] = [];
  const emit = () => {
    const fairs = cachedDocuments
      .map((item) => normalizePublicLiveFair(item.id, item.data))
      .filter((fair): fair is LiveFair => Boolean(fair));
    onFairs(sortPublicLiveFairs(fairs));
  };

  const fairsQuery = query(collection(db, "live_fairs"));
  const unsubscribeSnapshot = onSnapshot(
    fairsQuery,
    (snapshot) => {
      cachedDocuments = snapshot.docs.map((documentSnapshot) => ({
        id: documentSnapshot.id,
        data: documentSnapshot.data(),
      }));
      emit();
    },
    onError,
  );
  const clock = setInterval(emit, LIVE_FAIR_CLOCK_REFRESH_MS);

  return () => {
    clearInterval(clock);
    unsubscribeSnapshot();
  };
}

export function subscribeToCloudPosts(onPosts: (posts: FeedPost[]) => void, onError: (error: Error) => void): Unsubscribe {
  const postsQuery = query(collection(db, "posts"), orderBy("createdAtMs", "desc"), limit(MAX_SYNCED_POSTS));

  return onSnapshot(
    postsQuery,
    (snapshot) => {
      const posts = snapshot.docs
        .map((documentSnapshot) => normalizeCloudPost(documentSnapshot.id, documentSnapshot.data()))
        .filter((post): post is FeedPost => Boolean(post));
      onPosts(posts);
    },
    onError,
  );
}

function normalizeCloudPost(documentId: string, data: DocumentData): FeedPost | null {
  const text = sanitizeText(data.text);
  const author = sanitizeText(data.author);
  const createdAt = sanitizeText(data.createdAt);
  const authorId = sanitizeText(data.authorId);
  if (!text || !author || !createdAt || !authorId) return null;

  return {
    id: sanitizeText(data.id, documentId),
    authorId,
    author,
    authorRole: sanitizeRole(data.authorRole),
    authorAvatarUri: isRemoteUri(data.authorAvatarUri) ? data.authorAvatarUri : undefined,
    authorCity: sanitizeText(data.authorCity) || undefined,
    authorCategory: sanitizeText(data.authorCategory) || undefined,
    text,
    createdAt,
    updatedAt: sanitizeText(data.updatedAt) || undefined,
    media: normalizeCloudMedia(data.media),
  };
}

export async function saveNetworkInteraction(profile: UserProfile, targetId: string, kind: NetworkInteractionKind, enabled: boolean) {
  const documentId = sanitizeDocId(`${profile.id}_${targetId}_${kind}`);
  const reference = doc(db, "network_interactions", documentId);

  if (!enabled) {
    await deleteDoc(reference);
    return;
  }

  await setDoc(
    reference,
    {
      userId: profile.id,
      targetId,
      kind,
      createdAtMs: nowMs(),
      privacy: basePrivacyMetadata(["userId", "targetId", "kind"]),
    },
    { merge: true },
  );
}

/** Recarrega as interacoes da conta para manter Web e Expo Go sincronizados. */
export async function loadNetworkInteractionIds(userId: string): Promise<string[]> {
  const cleanUserId = sanitizeText(userId);
  if (!cleanUserId || auth.currentUser?.uid !== cleanUserId) {
    throw new Error("Entre novamente para carregar suas interacoes.");
  }

  const snapshot = await getDocs(
    query(
      collection(db, "network_interactions"),
      where("userId", "==", cleanUserId),
      limit(500),
    ),
  );
  return [...new Set(
    snapshot.docs
      .map((documentSnapshot) => sanitizeText(documentSnapshot.data().targetId))
      .filter(Boolean),
  )];
}

export async function saveCouponValidation(profile: UserProfile, couponId: string) {
  await setDoc(
    doc(db, "coupon_validations", sanitizeDocId(`${profile.id}_${couponId}`)),
    {
      userId: profile.id,
      couponId,
      validatedAtMs: nowMs(),
      privacy: basePrivacyMetadata(["userId", "couponId", "validatedAtMs"]),
    },
    { merge: true },
  );
}

/** Recarrega os cupons usados pela conta autenticada em qualquer dispositivo. */
export async function loadCouponValidationIds(userId: string): Promise<string[]> {
  const cleanUserId = sanitizeText(userId);
  if (!cleanUserId || auth.currentUser?.uid !== cleanUserId) {
    throw new Error("Entre novamente para carregar seus cupons usados.");
  }

  const snapshot = await getDocs(
    query(
      collection(db, "coupon_validations"),
      where("userId", "==", cleanUserId),
      limit(500),
    ),
  );
  return [...new Set(
    snapshot.docs
      .map((documentSnapshot) => sanitizeText(documentSnapshot.data().couponId))
      .filter(Boolean),
  )];
}
