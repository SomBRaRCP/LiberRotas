import AsyncStorage from "@react-native-async-storage/async-storage";
import { PropsWithChildren, useCallback, useEffect, useRef, useState } from "react";
import {
  createUserWithEmailAndPassword,
  deleteUser,
  EmailAuthProvider,
  onAuthStateChanged,
  reauthenticateWithCredential,
  signInWithEmailAndPassword,
  signOut,
  type User,
} from "firebase/auth";
import { showStaffAlert } from "@/components/staff-panel-ui";
import { auth } from "@/services/firebase";
import { clearPendingDeviceApprovalToken } from "@/security/device-approval-token";
import {
  loadCouponValidationIds,
  loadNetworkInteractionIds,
  loadPublicProfile,
  saveCouponValidation,
  saveNetworkInteraction,
  subscribeToCloudPosts,
  type NetworkInteractionKind,
} from "@/services/cloud-data";
import { removeDeviceIdentity } from "@/security/trq-bec/device-signer";
import {
  listMessageConversations,
  deleteCommunityPost,
  loadOwnPublicDirectoryProfile,
  enrollCurrentDevice,
  prepareAccountDeletion,
  publishCommunityPost,
  registerPublicAccount,
  updateCommunityPost,
  resolveAuthenticatedAccess,
  syncPublicDirectoryProfile,
  TrqBecServiceError,
  type AccessRole,
  type AccessSession,
  type CurrentDeviceEnrollment,
  type PublicDirectoryProfile,
} from "@/security/trq-bec/service";
import {
  AppStateProviders,
  usePreferencesState,
  useProfileState,
  usePublicCacheState,
  useSessionState,
} from "@/context/app-state-contexts";

/**
 * Estado global e persistência local do aplicativo.
 *
 * Na V3, Firebase Authentication é a fonte real da sessão. AsyncStorage fica
 * apenas como cache local de perfil, favoritos, cupons usados e publicações.
 */
export type AccountType = "entrepreneur" | "visitor";

export type UserProfile = {
  id: string;
  role: AccountType;
  name: string;
  email: string;
  city: string;
  /** Endereco que o empreendedor escolheu tornar publico no perfil. */
  address?: string;
  category: string;
  interests: string[];
  avatarUri?: string;
  /** Data original de criacao usada para ordenar novos perfis no Feed. */
  createdAtMs?: number;
};

export type PostMedia =
  | {
    type: "image";
    /** Referência permanente; a URL assinada é resolvida somente para exibição. */
    mediaId?: string;
    /** Compatibilidade temporária com publicações antigas que gravavam URL remota. */
    uri?: string;
  }
  | {
    /** Vídeo permanece apenas para leitura de publicações legadas. */
    type: "video";
    uri: string;
  };

export type NewPostMedia = {
  type: "image";
  mediaId: string;
};

export type FeedPost = {
  id: string;
  authorId: string;
  author: string;
  authorRole: AccountType;
  authorAvatarUri?: string;
  authorCity?: string;
  authorCategory?: string;
  text: string;
  createdAt: string;
  updatedAt?: string;
  media?: PostMedia;
};

export type AccessDestination =
  | "/admin"
  | "/support"
  | "/security"
  | "/institution"
  | "/account/devices"
  | "/(tabs)/feed"
  | "/access-pending";

export type LoginResult =
  | { ok: true; destination: AccessDestination }
  | { ok: false; reason: "empty" | "not-found" | "password" | "too-many" | "disabled" | "network" | "backend" | "unknown" };

export type AppContextValue = {
  isHydrated: boolean;
  isAuthenticated: boolean;
  hasFirebaseSession: boolean;
  isResolvingAccess: boolean;
  deviceApprovalRequired: boolean;
  accessSession: AccessSession | null;
  accessError: string;
  accessDestination: AccessDestination;
  profile: UserProfile;
  favorites: string[];
  usedCoupons: string[];
  userPosts: FeedPost[];
  unreadMessageCount: number;
  login: (email: string, password: string) => Promise<LoginResult>;
  register: (profile: UserProfile, password: string) => Promise<AccessDestination>;
  refreshAccess: () => Promise<AccessDestination>;
  hasPermission: (permission: string) => boolean;
  deleteAccount: (password: string) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (profile: UserProfile) => Promise<void>;
  toggleFavorite: (id: string) => Promise<void>;
  markCouponUsed: (id: string) => Promise<void>;
  createPost: (text: string, media?: NewPostMedia) => Promise<void>;
  updatePost: (postId: string, text: string) => Promise<void>;
  deletePost: (postId: string) => Promise<void>;
  refreshUnreadMessageCount: () => Promise<number>;
};

const STORAGE_KEYS = {
  session: "feitour:session", // legado: removido na hidratacao da V3.
  legacyPasswordHashes: "feitour:password-hashes", // legado: credenciais locais removidas na hidratacao.
  profile: "feitour:profile",
  favorites: "feitour:favorites",
  usedCoupons: "feitour:used-coupons",
  userPosts: "feitour:user-posts",
};

const DEPRECATED_PROFILE_IDS = new Set(["local-reginaldo"]);
const DEPRECATED_PROFILE_TERMS = ["reginaldo", "pires"];
const MIN_PUBLIC_ADDRESS_LENGTH = 10;
const MAX_PUBLIC_ADDRESS_LENGTH = 240;

const defaultProfile: UserProfile = {
  id: "guest",
  role: "visitor",
  name: "Visitante LiberRotas",
  email: "",
  city: "Pinhais - PR",
  category: "Visitante LiberRotas",
  interests: ["Artesanato", "Gastronomia"],
};

function normalizeProfile(savedProfile: Partial<UserProfile>): UserProfile {
  const role: AccountType = savedProfile.role === "entrepreneur" ? "entrepreneur" : "visitor";
  const address = role === "entrepreneur" ? savedProfile.address?.trim().slice(0, MAX_PUBLIC_ADDRESS_LENGTH) : undefined;
  return {
    ...defaultProfile,
    ...savedProfile,
    id: savedProfile.id || defaultProfile.id,
    role,
    address: address || undefined,
    createdAtMs: typeof savedProfile.createdAtMs === "number" && savedProfile.createdAtMs > 0
      ? savedProfile.createdAtMs
      : undefined,
    interests: Array.isArray(savedProfile.interests) ? savedProfile.interests : defaultProfile.interests,
  };
}

function validatePublicAddress(value: string | undefined, role: AccountType) {
  if (role !== "entrepreneur") return undefined;

  const address = value?.trim() || "";
  if (!address) return undefined;
  if (address.length < MIN_PUBLIC_ADDRESS_LENGTH) {
    throw new Error(`O endereco completo deve ter pelo menos ${MIN_PUBLIC_ADDRESS_LENGTH} caracteres.`);
  }
  if (address.length > MAX_PUBLIC_ADDRESS_LENGTH) {
    throw new Error(`O endereco completo deve ter no maximo ${MAX_PUBLIC_ADDRESS_LENGTH} caracteres.`);
  }
  return address;
}

function hasDeprecatedProfileTerm(value?: string) {
  const normalizedValue = value?.trim().toLowerCase() || "";
  return DEPRECATED_PROFILE_TERMS.some((term) => normalizedValue.includes(term));
}

function isDeprecatedProfile(savedProfile: Partial<UserProfile>) {
  return (
    DEPRECATED_PROFILE_IDS.has(savedProfile.id || "") ||
    hasDeprecatedProfileTerm(savedProfile.name) ||
    hasDeprecatedProfileTerm(savedProfile.email)
  );
}

function normalizeStoredMedia(value: unknown): PostMedia | undefined {
  if (!value || typeof value !== "object") return undefined;
  const media = value as { mediaId?: unknown; type?: unknown; uri?: unknown };
  const mediaId = typeof media.mediaId === "string" ? media.mediaId.trim() : "";
  const remoteUri = typeof media.uri === "string" && /^https?:\/\//i.test(media.uri)
    ? media.uri
    : undefined;
  if (media.type === "image" && (mediaId || remoteUri)) {
    return {
      type: "image",
      ...(mediaId ? { mediaId } : {}),
      ...(remoteUri ? { uri: remoteUri } : {}),
    };
  }
  if (media.type === "video" && remoteUri) return { type: "video", uri: remoteUri };
  return undefined;
}

function normalizeStoredPost(savedPost: Partial<FeedPost>): FeedPost | null {
  if (!savedPost.id || !savedPost.author || !savedPost.text || !savedPost.createdAt) return null;

  return {
    id: savedPost.id,
    authorId: savedPost.authorId || "unknown-author",
    author: savedPost.author,
    authorRole: savedPost.authorRole === "entrepreneur" ? "entrepreneur" : "visitor",
    authorAvatarUri: savedPost.authorAvatarUri,
    authorCity: savedPost.authorCity,
    authorCategory: savedPost.authorCategory,
    text: savedPost.text,
    createdAt: savedPost.createdAt,
    updatedAt: savedPost.updatedAt,
    media: normalizeStoredMedia(savedPost.media),
  };
}

function isDeprecatedPost(post: FeedPost) {
  return DEPRECATED_PROFILE_IDS.has(post.authorId) || hasDeprecatedProfileTerm(post.author);
}

function mergePosts(posts: FeedPost[]) {
  const postsById = new Map<string, FeedPost>();
  posts.forEach((post) => postsById.set(post.id, post));
  return Array.from(postsById.values()).sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt));
}

function getInteractionKind(id: string): NetworkInteractionKind {
  if (id.startsWith("post-") || id === "melancia" || id === "ceramica") return "post_like";
  if (/^\d+$/.test(id)) return "route_save";
  return "favorite";
}

function normalizeEmail(value: string) {
  return value.trim().toLowerCase();
}

function getFirebaseAuthCode(error: unknown) {
  return typeof error === "object" && error !== null && "code" in error ? String((error as { code?: string }).code) : "";
}

function mapLoginError(error: unknown): LoginResult {
  if (error instanceof TrqBecServiceError) return { ok: false, reason: "backend" };
  const code = getFirebaseAuthCode(error);
  if (code.includes("user-not-found") || code.includes("invalid-email")) return { ok: false, reason: "not-found" };
  if (code.includes("wrong-password") || code.includes("invalid-credential")) return { ok: false, reason: "password" };
  if (code.includes("too-many-requests")) return { ok: false, reason: "too-many" };
  if (code.includes("user-disabled")) return { ok: false, reason: "disabled" };
  if (code.includes("network-request-failed")) return { ok: false, reason: "network" };
  return { ok: false, reason: "unknown" };
}

function getRegistrationMessage(error: unknown) {
  const code = getFirebaseAuthCode(error);
  if (code.includes("email-already-in-use")) return "Este e-mail já está cadastrado. Use a tela de entrada.";
  if (code.includes("invalid-email")) return "Informe um e-mail válido.";
  if (code.includes("weak-password")) return "A senha deve ter pelo menos 6 caracteres.";
  if (code.includes("network-request-failed")) return "Sem conexão com o Firebase. Confira a internet e tente novamente.";
  return "Não foi possível criar a conta no Firebase Authentication.";
}

function getAccountDeletionMessage(error: unknown) {
  const code = getFirebaseAuthCode(error);
  if (code.includes("invalid-credential") || code.includes("wrong-password")) {
    return "A senha atual está incorreta. Nenhum dado foi excluído.";
  }
  if (code.includes("too-many-requests")) {
    return "Muitas tentativas incorretas. Aguarde alguns minutos e tente novamente.";
  }
  if (code.includes("network-request-failed")) {
    return "Sem conexão com o Firebase. Verifique a internet e tente novamente.";
  }
  if (code.includes("requires-recent-login")) {
    return "Por segurança, saia, entre novamente e repita a exclusão.";
  }
  if (error instanceof Error && error.message) return error.message;
  return "Não foi possível excluir a conta. O login foi preservado; tente novamente.";
}

export function getAccessDestination(access: AccessSession | null): AccessDestination {
  if (access?.access_state !== "AUTHORIZED") return "/access-pending";
  const destinations: Partial<Record<AccessRole, AccessDestination>> = {
    admin: "/admin",
    support: "/support",
    security: "/security",
    institution: "/institution",
    entrepreneur: "/(tabs)/feed",
    visitor: "/(tabs)/feed",
  };
  return access.role ? destinations[access.role] || "/access-pending" : "/access-pending";
}

function requiresMandatoryDeviceApproval(access: AccessSession | null, deviceApprovalRequired: boolean) {
  return Boolean(
    deviceApprovalRequired
    && access?.access_state === "AUTHORIZED"
    && access.role
    && access.role !== "visitor",
  );
}

function getDeviceAwareAccessDestination(
  access: AccessSession | null,
  deviceApprovalRequired: boolean,
): AccessDestination {
  return requiresMandatoryDeviceApproval(access, deviceApprovalRequired)
    ? "/account/devices"
    : getAccessDestination(access);
}

function getDeviceApprovalNotice(enrollment: CurrentDeviceEnrollment, role: AccessRole) {
  const notification = enrollment.notification_status;
  const emailStatus = notification === "SENT"
    ? "Enviamos um alerta de segurança ao e-mail cadastrado."
    : notification === "PENDING"
      ? "O alerta de segurança está na fila de envio."
      : notification === "NOT_CONFIGURED" || notification === "FAILED"
        ? "O alerta por e-mail não pôde ser enviado agora, mas a contagem continua normalmente."
        : "Confira a tela de dispositivos para acompanhar a contagem.";
  const accessStatus = role === "visitor"
    ? "Sua conta de visitante continua liberada; o e-mail serve apenas para confirmar se você reconhece o acesso."
    : "As áreas protegidas serão liberadas automaticamente após 10 minutos.";
  return `Um novo dispositivo foi conectado à sua conta. ${emailStatus} ${accessStatus}`;
}

function isPublicAppRole(role: AccessRole | null | undefined): role is "entrepreneur" | "visitor" {
  return role === "entrepreneur" || role === "visitor";
}

function profileFromAuthUser(authUser: User, role: "entrepreneur" | "visitor", cachedProfile?: UserProfile | null): UserProfile {
  const email = authUser.email || cachedProfile?.email || "";
  const emailName = email.split("@")[0] || "Usuário LiberRotas";

  return {
    ...defaultProfile,
    ...cachedProfile,
    id: authUser.uid,
    // A classificação pública nunca substitui a função autorizada pelo backend.
    role,
    name: cachedProfile?.name || authUser.displayName || emailName,
    email,
    category: cachedProfile?.category || (role === "entrepreneur" ? "Turismo comunitário" : "Visitante LiberRotas"),
  };
}

function profileFromDirectory(
  authUser: User,
  role: "entrepreneur" | "visitor",
  directoryProfile: PublicDirectoryProfile,
  cachedProfile?: UserProfile | null,
): UserProfile {
  const fallback = profileFromAuthUser(authUser, role, cachedProfile);
  return {
    ...fallback,
    id: authUser.uid,
    role,
    name: directoryProfile.display_name.trim() || fallback.name,
    city: directoryProfile.city.trim() || fallback.city,
    category: role === "entrepreneur"
      ? directoryProfile.category.trim() || fallback.category
      : "Visitante LiberRotas",
    interests: directoryProfile.interests.length > 0 ? directoryProfile.interests : fallback.interests,
    address: role === "entrepreneur" ? directoryProfile.address || undefined : undefined,
    avatarUri: directoryProfile.avatar_uri || undefined,
    createdAtMs: directoryProfile.created_at_ms || fallback.createdAtMs,
  };
}

async function persistProfile(profile: UserProfile) {
  await AsyncStorage.setItem(STORAGE_KEYS.profile, JSON.stringify(profile));
}

async function loadCachedLocalData() {
  const [savedProfile, savedFavorites, savedCoupons, savedPosts] = await Promise.all([
    AsyncStorage.getItem(STORAGE_KEYS.profile),
    AsyncStorage.getItem(STORAGE_KEYS.favorites),
    AsyncStorage.getItem(STORAGE_KEYS.usedCoupons),
    AsyncStorage.getItem(STORAGE_KEYS.userPosts),
  ]);

  let cachedProfile: UserProfile | null = null;
  const cleanupTasks: Promise<void>[] = [
    AsyncStorage.removeItem(STORAGE_KEYS.session),
    AsyncStorage.removeItem(STORAGE_KEYS.legacyPasswordHashes),
  ];

  if (savedProfile) {
    const parsedProfile = JSON.parse(savedProfile) as Partial<UserProfile>;
    if (isDeprecatedProfile(parsedProfile)) {
      cleanupTasks.push(AsyncStorage.removeItem(STORAGE_KEYS.profile));
    } else {
      cachedProfile = normalizeProfile(parsedProfile);
    }
  }

  const favorites = savedFavorites ? (JSON.parse(savedFavorites) as string[]) : [];
  const usedCoupons = savedCoupons ? (JSON.parse(savedCoupons) as string[]) : [];
  const userPosts = savedPosts ? (JSON.parse(savedPosts) as Partial<FeedPost>[]) : [];
  const normalizedPosts = Array.isArray(userPosts) ? userPosts.map(normalizeStoredPost).filter(Boolean) as FeedPost[] : [];
  const activePosts = normalizedPosts.filter((post) => !isDeprecatedPost(post));

  if (activePosts.length !== normalizedPosts.length) {
    cleanupTasks.push(AsyncStorage.setItem(STORAGE_KEYS.userPosts, JSON.stringify(activePosts)));
  }

  await Promise.all(cleanupTasks);

  return {
    cachedProfile,
    favorites: Array.isArray(favorites) ? favorites : [],
    usedCoupons: Array.isArray(usedCoupons) ? usedCoupons : [],
    userPosts: activePosts,
  };
}

export function AppProvider({ children }: PropsWithChildren) {
  const [isHydrated, setIsHydrated] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [hasFirebaseSession, setHasFirebaseSession] = useState(false);
  const [isResolvingAccess, setIsResolvingAccess] = useState(false);
  const [deviceApprovalRequired, setDeviceApprovalRequired] = useState(false);
  const [accessSession, setAccessSession] = useState<AccessSession | null>(null);
  const [accessError, setAccessError] = useState("");
  const [profile, setProfile] = useState(defaultProfile);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [usedCoupons, setUsedCoupons] = useState<string[]>([]);
  const [userPosts, setUserPosts] = useState<FeedPost[]>([]);
  const [unreadMessageCount, setUnreadMessageCount] = useState(0);
  const isDeletingAccountRef = useRef(false);
  const accessResolutionIdRef = useRef(0);
  const authenticatedUidRef = useRef<string | null>(auth.currentUser?.uid || null);
  const deviceEnrollmentRef = useRef<{ uid: string; promise: Promise<CurrentDeviceEnrollment> } | null>(null);
  const deviceNoticeKeyRef = useRef("");
  const accessDestination = getDeviceAwareAccessDestination(accessSession, deviceApprovalRequired);

  function resolveCurrentDeviceEnrollment(uid: string): Promise<CurrentDeviceEnrollment> {
    const current = deviceEnrollmentRef.current;
    if (current?.uid === uid) return current.promise;
    const promise = enrollCurrentDevice();
    deviceEnrollmentRef.current = { uid, promise };
    void promise.catch(() => {
      if (deviceEnrollmentRef.current?.promise === promise) deviceEnrollmentRef.current = null;
    });
    return promise;
  }

  async function resolveUserAccess(
    authUser: User,
    localData?: Awaited<ReturnType<typeof loadCachedLocalData>>,
  ): Promise<AccessDestination> {
    const resolutionId = ++accessResolutionIdRef.current;
    setHasFirebaseSession(true);
    setIsAuthenticated(false);
    setIsResolvingAccess(true);
    setDeviceApprovalRequired(false);
    setAccessError("");

    try {
      const cachedData = localData || await loadCachedLocalData();
      let access = await resolveAuthenticatedAccess();
      const cachedRegistration = cachedData.cachedProfile;
      if (
        access.reason === "ACCESS_NOT_PROVISIONED"
        && cachedRegistration?.id === authUser.uid
        && isPublicAppRole(cachedRegistration.role)
      ) {
        await registerPublicAccount({
          role: cachedRegistration.role,
          displayName: cachedRegistration.name,
          establishmentName: cachedRegistration.category,
        });
        access = await resolveAuthenticatedAccess();
      }
      const baseDestination = getAccessDestination(access);
      let approvalRequiredForResolution = false;

      if (resolutionId !== accessResolutionIdRef.current || auth.currentUser?.uid !== authUser.uid) {
        return baseDestination;
      }

      setAccessSession(access);
      if (access.access_state !== "AUTHORIZED" || !access.role) {
        setDeviceApprovalRequired(false);
        setProfile(
          cachedData.cachedProfile?.id === authUser.uid
            ? cachedData.cachedProfile
            : defaultProfile,
        );
        return "/access-pending";
      }

      try {
        const enrollment = await resolveCurrentDeviceEnrollment(authUser.uid);
        if (resolutionId !== accessResolutionIdRef.current || auth.currentUser?.uid !== authUser.uid) {
          return baseDestination;
        }
        approvalRequiredForResolution = enrollment.device_status === "PENDING_APPROVAL";
        setDeviceApprovalRequired(approvalRequiredForResolution);
        if (approvalRequiredForResolution && deviceNoticeKeyRef.current !== enrollment.device_key_id) {
          deviceNoticeKeyRef.current = enrollment.device_key_id;
          showStaffAlert("Novo dispositivo em período de segurança", getDeviceApprovalNotice(enrollment, access.role));
        }
      } catch (error) {
        // Sem conseguir confirmar a chave, áreas privilegiadas falham fechadas
        // na tela de dispositivos. O visitante ainda pode consultar o Feed,
        // enquanto o backend impede operações TRQ-BEC durante o cooldown.
        approvalRequiredForResolution = true;
        setDeviceApprovalRequired(true);
        console.warn("Não foi possível atualizar o cadastro deste dispositivo.", error);
      }

      if (resolutionId !== accessResolutionIdRef.current || auth.currentUser?.uid !== authUser.uid) {
        return getDeviceAwareAccessDestination(access, approvalRequiredForResolution);
      }
      if (isPublicAppRole(access.role)) {
        const cachedProfile = cachedData.cachedProfile?.id === authUser.uid ? cachedData.cachedProfile : null;
        let cloudProfile: UserProfile | null = null;
        let directoryProfile: PublicDirectoryProfile | null = null;
        let directoryProfileMissing = false;
        try {
          directoryProfile = await loadOwnPublicDirectoryProfile();
        } catch (error) {
          directoryProfileMissing = error instanceof TrqBecServiceError
            && error.code === "PUBLIC_PROFILE_NOT_FOUND";
          console.warn(
            directoryProfileMissing
              ? "O perfil ainda não existe no diretório autoritativo; será criado uma única vez a partir do cadastro atual."
              : "Não foi possível carregar o perfil público autoritativo; usando o Firebase ou cache local sem regravá-lo no backend.",
            error,
          );
        }
        try {
          cloudProfile = await loadPublicProfile(authUser.uid, authUser.email || "");
        } catch (error) {
          console.warn("Não foi possível carregar o perfil público; usando o cache local.", error);
        }

        if (resolutionId !== accessResolutionIdRef.current || auth.currentUser?.uid !== authUser.uid) {
          return getDeviceAwareAccessDestination(access, approvalRequiredForResolution);
        }

        const nextProfile = directoryProfile
          ? profileFromDirectory(authUser, access.role, directoryProfile, cloudProfile || cachedProfile)
          : profileFromAuthUser(authUser, access.role, cloudProfile || cachedProfile);
        if (directoryProfileMissing) {
          try {
            await syncPublicDirectoryProfile({
              displayName: nextProfile.name,
              city: nextProfile.city,
              category: nextProfile.category,
              interests: nextProfile.interests,
              address: nextProfile.address,
              avatarUri: nextProfile.avatarUri,
            });
          } catch (error) {
            console.warn("Não foi possível criar o perfil no diretório autoritativo. Salve o perfil escolhendo um nome público único.", error);
          }
        }
        setProfile(nextProfile);
        AsyncStorage.setItem(STORAGE_KEYS.profile, JSON.stringify(nextProfile)).catch((error) => {
          console.warn("Não foi possível atualizar o cache local do perfil.", error);
        });
      } else {
        if (resolutionId !== accessResolutionIdRef.current || auth.currentUser?.uid !== authUser.uid) {
          return getDeviceAwareAccessDestination(access, approvalRequiredForResolution);
        }
        const email = authUser.email || "";
        setProfile({
          ...defaultProfile,
          id: authUser.uid,
          name: authUser.displayName || email.split("@")[0] || "Equipe LiberRotas",
          email,
          category: "Equipe autorizada do LiberRotas",
        });
      }

      if (resolutionId === accessResolutionIdRef.current && auth.currentUser?.uid === authUser.uid) {
        setIsAuthenticated(true);
      }
      return getDeviceAwareAccessDestination(access, approvalRequiredForResolution);
    } catch (error) {
      if (resolutionId === accessResolutionIdRef.current) {
        setAccessSession(null);
        setDeviceApprovalRequired(false);
        setProfile(defaultProfile);
        setIsAuthenticated(false);
        setAccessError(
          error instanceof TrqBecServiceError
            ? error.userMessage
            : "Não foi possível confirmar as permissões da conta no backend.",
        );
      }
      throw error;
    } finally {
      if (resolutionId === accessResolutionIdRef.current) setIsResolvingAccess(false);
    }
  }

  useEffect(() => {
    let mounted = true;
    const localDataPromise = loadCachedLocalData();

    const unsubscribe = onAuthStateChanged(auth, async (authUser) => {
      try {
        const localData = await localDataPromise;
        if (!mounted) return;

        const previousUid = authenticatedUidRef.current;
        if (authUser) {
          if (previousUid && previousUid !== authUser.uid) clearPendingDeviceApprovalToken();
          authenticatedUidRef.current = authUser.uid;
        } else {
          if (previousUid) clearPendingDeviceApprovalToken();
          authenticatedUidRef.current = null;
        }

        if (isDeletingAccountRef.current) {
          accessResolutionIdRef.current += 1;
          deviceEnrollmentRef.current = null;
          deviceNoticeKeyRef.current = "";
          setProfile(defaultProfile);
          setFavorites([]);
          setUsedCoupons([]);
          setUserPosts([]);
          setUnreadMessageCount(0);
          setIsAuthenticated(false);
          setHasFirebaseSession(false);
          setIsResolvingAccess(false);
          setDeviceApprovalRequired(false);
          setAccessSession(null);
          setAccessError("");
          return;
        }

        if (!authUser) {
          accessResolutionIdRef.current += 1;
          deviceEnrollmentRef.current = null;
          deviceNoticeKeyRef.current = "";
          setProfile(defaultProfile);
          setFavorites([]);
          setUsedCoupons([]);
          setUserPosts(localData.userPosts);
          setUnreadMessageCount(0);
          setIsAuthenticated(false);
          setHasFirebaseSession(false);
          setIsResolvingAccess(false);
          setDeviceApprovalRequired(false);
          setAccessSession(null);
          setAccessError("");
          return;
        }

        const localDataForUser = localData.cachedProfile?.id === authUser.uid
          ? localData
          : { ...localData, cachedProfile: null, favorites: [], usedCoupons: [] };
        setFavorites(localDataForUser.favorites);
        setUsedCoupons(localDataForUser.usedCoupons);
        setUserPosts(localDataForUser.userPosts);
        await resolveUserAccess(authUser, localDataForUser);
      } catch (error) {
        console.warn("Não foi possível validar a sessão Firebase no backend.", error);
        if (mounted) setIsAuthenticated(false);
      } finally {
        if (mounted) setIsHydrated(true);
      }
    });

    return () => {
      mounted = false;
      unsubscribe();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- inscrição única durante a vida do provider

  useEffect(() => {
    if (!isHydrated || !isAuthenticated || !isPublicAppRole(accessSession?.role)) return undefined;

    return subscribeToCloudPosts(
      (cloudPosts) => {
        if (isDeletingAccountRef.current) return;
        setUserPosts(cloudPosts);
        AsyncStorage.setItem(STORAGE_KEYS.userPosts, JSON.stringify(cloudPosts)).catch((error) => {
          console.warn("Não foi possível atualizar o cache local das publicações.", error);
        });
      },
      (error) => {
        console.warn("Não foi possível sincronizar publicações do Firebase.", error);
      },
    );
  }, [accessSession?.role, isAuthenticated, isHydrated]);

  useEffect(() => {
    const userId = auth.currentUser?.uid;
    if (
      !isHydrated
      || !isAuthenticated
      || !isPublicAppRole(accessSession?.role)
      || !userId
      || profile.id !== userId
    ) {
      return undefined;
    }

    let isActive = true;
    Promise.all([
      loadNetworkInteractionIds(userId),
      loadCouponValidationIds(userId),
    ])
      .then(([remoteFavorites, remoteCoupons]) => {
        if (!isActive || auth.currentUser?.uid !== userId) return;
        setFavorites(remoteFavorites);
        setUsedCoupons(remoteCoupons);
        return AsyncStorage.multiSet([
          [STORAGE_KEYS.favorites, JSON.stringify(remoteFavorites)],
          [STORAGE_KEYS.usedCoupons, JSON.stringify(remoteCoupons)],
        ]);
      })
      .catch((error) => {
        // O cache local continua disponivel quando o Firestore estiver offline.
        console.warn("Nao foi possivel atualizar favoritos e cupons usados da nuvem.", error);
      });

    return () => {
      isActive = false;
    };
  }, [accessSession?.role, isAuthenticated, isHydrated, profile.id]);

  const refreshUnreadMessageCount = useCallback(async () => {
    if (!auth.currentUser || !isAuthenticated || !isPublicAppRole(accessSession?.role)) {
      return 0;
    }
    try {
      const conversations = await listMessageConversations();
      const count = conversations.reduce((total, conversation) => total + Math.max(0, conversation.unread_count || 0), 0);
      setUnreadMessageCount(count);
      return count;
    } catch (error) {
      console.warn("Não foi possível atualizar o contador de mensagens.", error);
      return 0;
    }
  }, [accessSession?.role, isAuthenticated]);

  useEffect(() => {
    if (!isHydrated || !isAuthenticated || !isPublicAppRole(accessSession?.role)) return undefined;
    const initialTimer = setTimeout(() => {
      refreshUnreadMessageCount().catch(() => undefined);
    }, 0);
    const timer = setInterval(() => {
      refreshUnreadMessageCount().catch(() => undefined);
    }, 60_000);
    return () => {
      clearTimeout(initialTimer);
      clearInterval(timer);
    };
  }, [accessSession?.role, isAuthenticated, isHydrated, refreshUnreadMessageCount]);

  async function login(email: string, password: string): Promise<LoginResult> {
    isDeletingAccountRef.current = false;
    const normalizedEmail = normalizeEmail(email);
    if (!normalizedEmail || password.length < 6) return { ok: false, reason: "empty" };

    try {
      const credential = await signInWithEmailAndPassword(auth, normalizedEmail, password);
      const destination = await resolveUserAccess(credential.user);
      return { ok: true, destination };
    } catch (error) {
      return mapLoginError(error);
    }
  }

  async function register(newProfile: UserProfile, password: string): Promise<AccessDestination> {
    isDeletingAccountRef.current = false;
    const normalizedEmail = normalizeEmail(newProfile.email);
    if (!normalizedEmail) throw new Error("Informe um e-mail válido.");
    if (password.length < 6) throw new Error("A senha deve ter pelo menos 6 caracteres.");
    const publicAddress = validatePublicAddress(newProfile.address, newProfile.role);

    try {
      const credential = await createUserWithEmailAndPassword(auth, normalizedEmail, password);
      clearPendingDeviceApprovalToken();
      const profileWithUid: UserProfile = {
        ...newProfile,
        id: credential.user.uid,
        email: credential.user.email || normalizedEmail,
        name: newProfile.name.trim(),
        city: newProfile.city.trim(),
        address: publicAddress,
        category: newProfile.role === "entrepreneur" ? newProfile.category.trim() : "Visitante LiberRotas",
        interests: newProfile.interests,
        createdAtMs: Date.now(),
      };

      // A escolha feita no cadastro é apenas um rascunho local. Ela não cria
      // perfil público nem concede função antes da aprovação do backend.
      await AsyncStorage.setItem(STORAGE_KEYS.profile, JSON.stringify(profileWithUid));
      try {
        await registerPublicAccount({
          role: profileWithUid.role,
          displayName: profileWithUid.name,
          establishmentName: profileWithUid.category,
        });
      } catch (error) {
        console.warn(
          "A conta Firebase foi criada, mas o cadastro público ainda não foi concluído no backend.",
          error,
        );
      }
      try {
        return await resolveUserAccess(credential.user);
      } catch {
        // A conta Firebase foi criada, mas nenhum painel pode ser aberto sem a
        // decisão autoritativa do backend. A tela pendente permite tentar novamente.
        return "/access-pending";
      }
    } catch (error) {
      throw new Error(getRegistrationMessage(error));
    }
  }

  async function refreshAccess(): Promise<AccessDestination> {
    const firebaseUser = auth.currentUser;
    if (!firebaseUser) {
      setHasFirebaseSession(false);
      setDeviceApprovalRequired(false);
      setAccessSession(null);
      setIsAuthenticated(false);
      return "/access-pending";
    }
    deviceEnrollmentRef.current = null;
    return resolveUserAccess(firebaseUser);
  }

  function hasPermission(permission: string) {
    return accessSession?.access_state === "AUTHORIZED" && accessSession.permissions.includes(permission);
  }

  async function deleteAccount(password: string) {
    const firebaseUser = auth.currentUser;
    if (!firebaseUser?.email) throw new Error("Entre novamente antes de excluir a conta.");
    if (password.length < 6) throw new Error("Digite sua senha atual para confirmar a exclusão.");

    const uid = firebaseUser.uid;
    isDeletingAccountRef.current = true;
    try {
      const credential = EmailAuthProvider.credential(firebaseUser.email, password);
      await reauthenticateWithCredential(firebaseUser, credential);
      await prepareAccountDeletion();
      await deleteUser(firebaseUser);
    } catch (error) {
      isDeletingAccountRef.current = false;
      throw new Error(getAccountDeletionMessage(error));
    }

    // A conta remota já foi excluída. Falhas de limpeza local não devem exibir
    // um falso aviso de que o login ainda existe.
    await removeDeviceIdentity(uid).catch((error) => {
      console.warn("Não foi possível remover a chave local do dispositivo.", error);
    });
    await AsyncStorage.multiRemove(Object.values(STORAGE_KEYS)).catch((error) => {
      console.warn("Não foi possível limpar todo o cache local da conta excluída.", error);
    });
    clearPendingDeviceApprovalToken();

    setProfile(defaultProfile);
    setFavorites([]);
    setUsedCoupons([]);
    setUserPosts([]);
    setUnreadMessageCount(0);
    setIsAuthenticated(false);
    setHasFirebaseSession(false);
    setIsResolvingAccess(false);
    setDeviceApprovalRequired(false);
    setAccessSession(null);
    setAccessError("");
  }

  async function logout() {
    isDeletingAccountRef.current = false;
    accessResolutionIdRef.current += 1;
    deviceEnrollmentRef.current = null;
    deviceNoticeKeyRef.current = "";
    clearPendingDeviceApprovalToken();
    await signOut(auth);
    await AsyncStorage.multiRemove([
      STORAGE_KEYS.session,
      STORAGE_KEYS.profile,
      STORAGE_KEYS.favorites,
      STORAGE_KEYS.usedCoupons,
    ]);
    setProfile(defaultProfile);
    setFavorites([]);
    setUsedCoupons([]);
    setUnreadMessageCount(0);
    setIsAuthenticated(false);
    setHasFirebaseSession(false);
    setIsResolvingAccess(false);
    setDeviceApprovalRequired(false);
    setAccessSession(null);
    setAccessError("");
  }

  async function updateProfile(newProfile: UserProfile) {
    const firebaseUser = auth.currentUser;
    if (!firebaseUser) throw new Error("Entre novamente para atualizar o perfil.");
    const authorizedRole = accessSession?.access_state === "AUTHORIZED" && isPublicAppRole(accessSession.role)
      ? accessSession.role
      : null;
    if (!authorizedRole) throw new Error("O backend não autorizou a edição deste perfil público.");
    const publicAddress = validatePublicAddress(newProfile.address, authorizedRole);

    const profileWithUid: UserProfile = {
      ...newProfile,
      id: firebaseUser.uid,
      role: authorizedRole,
      email: firebaseUser.email || newProfile.email,
      address: publicAddress,
      category: authorizedRole === "entrepreneur" ? newProfile.category : "Visitante LiberRotas",
    };

    await syncPublicDirectoryProfile({
      displayName: profileWithUid.name,
      city: profileWithUid.city,
      category: profileWithUid.category,
      interests: profileWithUid.interests,
      address: profileWithUid.address,
      avatarUri: profileWithUid.avatarUri,
    });
    await persistProfile(profileWithUid);
    setProfile(profileWithUid);
  }

  async function toggleFavorite(id: string) {
    const willEnable = !favorites.includes(id);
    const next = willEnable ? [...favorites, id] : favorites.filter((item) => item !== id);
    setFavorites(next);
    await AsyncStorage.setItem(STORAGE_KEYS.favorites, JSON.stringify(next));
    saveNetworkInteraction(profile, id, getInteractionKind(id), willEnable).catch((error) => {
      console.warn("Não foi possível sincronizar a interação no Firebase.", error);
    });
  }

  async function markCouponUsed(id: string) {
    if (usedCoupons.includes(id)) return;
    const next = [...usedCoupons, id];
    setUsedCoupons(next);
    await AsyncStorage.setItem(STORAGE_KEYS.usedCoupons, JSON.stringify(next));
    saveCouponValidation(profile, id).catch((error) => {
      console.warn("Não foi possível sincronizar a validação de cupom no Firebase.", error);
    });
  }

  async function createPost(text: string, media?: NewPostMedia) {
    const authorizedRole = accessSession?.access_state === "AUTHORIZED" && isPublicAppRole(accessSession.role)
      ? accessSession.role
      : null;
    if (!authorizedRole) throw new Error("O backend não autorizou esta publicação.");
    const cleanText = text.trim();
    const confirmedMedia = media?.mediaId.trim()
      ? { type: "image" as const, media_id: media.mediaId.trim() }
      : undefined;
    const documentId = await publishCommunityPost({ text: cleanText, media: confirmedMedia });
    const post: FeedPost = {
      id: documentId,
      authorId: profile.id,
      author: profile.name,
      authorRole: authorizedRole,
      authorAvatarUri: profile.avatarUri,
      authorCity: profile.city,
      authorCategory: profile.category,
      text: cleanText,
      createdAt: new Date().toISOString(),
      media: confirmedMedia ? { type: "image", mediaId: confirmedMedia.media_id } : undefined,
    };
    const next = mergePosts([post, ...userPosts]);
    setUserPosts(next);
    await AsyncStorage.setItem(STORAGE_KEYS.userPosts, JSON.stringify(next));
  }

  async function updatePost(postId: string, text: string) {
    const cleanText = text.trim();
    if (!cleanText) throw new Error("Escreva o texto da publicação.");
    const currentPost = userPosts.find((post) => post.id === postId);
    if (!currentPost || currentPost.authorId !== profile.id) {
      throw new Error("Somente o autor pode editar esta publicação.");
    }
    await updateCommunityPost(postId, cleanText);
    const next = userPosts.map((post) => (
      post.id === postId
        ? { ...post, text: cleanText, updatedAt: new Date().toISOString() }
        : post
    ));
    setUserPosts(next);
    await AsyncStorage.setItem(STORAGE_KEYS.userPosts, JSON.stringify(next));
  }

  async function deletePost(postId: string) {
    const currentPost = userPosts.find((post) => post.id === postId);
    if (!currentPost || currentPost.authorId !== profile.id) {
      throw new Error("Somente o autor pode excluir esta publicação.");
    }
    await deleteCommunityPost(postId);
    const next = userPosts.filter((post) => post.id !== postId);
    setUserPosts(next);
    await AsyncStorage.setItem(STORAGE_KEYS.userPosts, JSON.stringify(next));
  }

  const session = {
    isHydrated,
    isAuthenticated,
    hasFirebaseSession,
    isResolvingAccess,
    deviceApprovalRequired,
    accessSession,
    accessError,
    accessDestination,
    login,
    register,
    refreshAccess,
    hasPermission,
    deleteAccount,
    logout,
  };
  const profileState = {
    profile,
    updateProfile,
  };
  const preferences = {
    favorites,
    usedCoupons,
    toggleFavorite,
    markCouponUsed,
  };
  const publicCache = {
    userPosts,
    unreadMessageCount,
    createPost,
    updatePost,
    deletePost,
    refreshUnreadMessageCount,
  };

  return (
    <AppStateProviders
      preferences={preferences}
      profile={profileState}
      publicCache={publicCache}
      session={session}
    >
      {children}
    </AppStateProviders>
  );
}

export function useApp() {
  return {
    ...useSessionState(),
    ...useProfileState(),
    ...usePreferencesState(),
    ...usePublicCacheState(),
  };
}

export {
  usePreferencesState,
  useProfileState,
  usePublicCacheState,
  useSessionState,
} from "@/context/app-state-contexts";
