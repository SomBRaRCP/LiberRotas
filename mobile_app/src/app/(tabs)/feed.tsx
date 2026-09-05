import { Ionicons } from "@expo/vector-icons";
import { router, type Href, useFocusEffect } from "expo-router";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { useVideoPlayer, VideoView } from "expo-video";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { BrandHeader } from "@/components/brand-header";
import { PostComments } from "@/components/post-comments";
import { PostOwnerActions } from "@/components/post-owner-actions";
import { ProtectedMediaImage } from "@/components/protected-media-image";
import { showStaffAlert } from "@/components/staff-panel-ui";
import { colors, radius, shadow } from "@/constants/theme";
import { useApp, type FeedPost } from "@/context/app-context";
import { useTrustedClock } from "@/context/trusted-clock-context";
import {
  pinhaisCategoryLabels,
  resolveLiveFairStatus,
  type LiveFair,
  type PinhaisPlace,
} from "@/data/pinhais";
import type { CatalogOfferSummary, CatalogProductItem } from "@/security/trq-bec/contracts";
import {
  getStablePublicAvatarUrl,
  listPublicCatalogFeed,
  searchGlobalDirectory,
  type GlobalSearchResult,
} from "@/security/trq-bec/service";
import {
  subscribeToApprovedCuratedPlaces,
  subscribeToPublicEntrepreneurProfiles,
  subscribeToPublicLiveFairs,
  type PublicEntrepreneurProfileSummary,
} from "@/services/cloud-data";
import {
  prepareImageForUpload,
  uploadImage,
  type PreparedImageUpload,
} from "@/services/media-upload";
import { profileSharePath, shareLiberRotasItem, type LiberRotasShareKind } from "@/utils/share";
import { formatRemainingTime, hasTimeEnded } from "@/utils/time";

type PendingMedia = PreparedImageUpload & {
  mediaId?: string;
};

type PublicOfferCard = {
  offer: CatalogOfferSummary;
  product: CatalogProductItem;
};

type TimelineEntry =
  | { key: string; kind: "profile"; timestamp: number; item: PublicEntrepreneurProfileSummary }
  | { key: string; kind: "place"; timestamp: number; item: PinhaisPlace }
  | { key: string; kind: "fair"; timestamp: number; item: LiveFair }
  | { key: string; kind: "product"; timestamp: number; item: CatalogProductItem }
  | { key: string; kind: "offer"; timestamp: number; item: PublicOfferCard }
  | { key: string; kind: "post"; timestamp: number; item: FeedPost };

function formatMoney(amountMinor: number, currency: string) {
  try {
    return new Intl.NumberFormat("pt-BR", { currency, style: "currency" }).format(amountMinor / 100);
  } catch {
    return `${currency} ${(amountMinor / 100).toFixed(2)}`;
  }
}

function formatDate(timestamp: number) {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "Data não informada";
  return new Date(timestamp).toLocaleString("pt-BR");
}

function normalizeSearch(value: string) {
  return value.trim().toLocaleLowerCase("pt-BR");
}

function productStatusLabel(product: CatalogProductItem) {
  if (product.status === "ENDED") return "PRODUTO ENCERRADO";
  if (product.status === "PAUSED") return "PRODUTO PAUSADO";
  return "PRODUTO PÚBLICO";
}

function productStatusReason(product: CatalogProductItem) {
  if (product.status_reason === "OUT_OF_STOCK") return "Encerrado porque o estoque terminou.";
  if (product.status_reason === "PAUSED") return "Publicação pausada pelo empreendedor.";
  return "Disponível no catálogo público.";
}

function offerStatusLabel(offer: CatalogOfferSummary, referenceTimeMs: number) {
  if (offer.status === "ENDED" || hasTimeEnded(offer.expires_at * 1_000, referenceTimeMs)) return "CUPOM ENCERRADO";
  if (offer.status === "PAUSED") return "CUPOM PAUSADO";
  return "CUPOM ATIVO";
}

function offerStatusReason(offer: CatalogOfferSummary, referenceTimeMs: number) {
  const reasons: Record<Exclude<CatalogOfferSummary["status_reason"], null>, string> = {
    CANCELLED: "Encerrado antecipadamente pelo empreendedor.",
    EXHAUSTED: "Encerrado porque todos os cupons foram usados.",
    EXPIRED: "Encerrado no fim da validade.",
    OUT_OF_STOCK: "Encerrado porque o produto ficou sem estoque.",
    PAUSED: "Oferta pausada pelo empreendedor.",
    PRODUCT_PAUSED: "Oferta pausada junto com o produto.",
  };
  if (offer.status_reason) return reasons[offer.status_reason];
  if (hasTimeEnded(offer.expires_at * 1_000, referenceTimeMs)) return "Encerrado no fim da validade.";
  return `Disponível por mais ${formatRemainingTime(offer.expires_at * 1_000, referenceTimeMs)}.`;
}

function fairStatusLabel(fair: LiveFair, referenceTimeMs: number) {
  const status = resolveLiveFairStatus(fair, referenceTimeMs);
  if (status === "ended") return "FEIRA ENCERRADA";
  if (status === "scheduled") return "FEIRA PROGRAMADA";
  return "FEIRA AO VIVO";
}

function fairStatusReason(fair: LiveFair, referenceTimeMs: number) {
  const status = resolveLiveFairStatus(fair, referenceTimeMs);
  if (status === "ended") {
    return fair.endReason === "manual"
      ? "Encerrada antecipadamente pelo empreendedor."
      : "Encerrada automaticamente no horário final.";
  }
  if (status === "scheduled") return `Começa em ${formatRemainingTime(fair.startsAtMs, referenceTimeMs)} · ${formatDate(fair.startsAtMs)}.`;
  return `Termina em ${formatRemainingTime(fair.endsAtMs, referenceTimeMs)} · ${formatDate(fair.endsAtMs)}.`;
}

function timelineSearchText(entry: TimelineEntry, referenceTimeMs: number) {
  switch (entry.kind) {
    case "profile":
      return `${entry.item.name} ${entry.item.category} ${entry.item.city} ${entry.item.address ?? ""}`;
    case "place":
      return `${entry.item.nome} ${entry.item.endereco} ${entry.item.ownerName ?? ""} ${pinhaisCategoryLabels[entry.item.categoriaApp]}`;
    case "fair":
      return `${entry.item.name} ${entry.item.address} ${entry.item.ownerName} ${fairStatusLabel(entry.item, referenceTimeMs)}`;
    case "product":
      return `${entry.item.title} ${entry.item.description} ${entry.item.merchant.display_name} ${entry.item.merchant.establishment_name} ${productStatusLabel(entry.item)}`;
    case "offer":
      return `${entry.item.product.title} ${entry.item.product.merchant.display_name} ${entry.item.product.merchant.establishment_name} ${offerStatusLabel(entry.item.offer, referenceTimeMs)}`;
    case "post":
      return `${entry.item.author} ${entry.item.text} ${entry.item.authorCity ?? ""} ${entry.item.authorCategory ?? ""}`;
  }
}

function timelineFavoriteId(entry: TimelineEntry) {
  // Mantém compatibilidade com os favoritos que já existiam no mapa e nas publicações.
  if (entry.kind === "place" || entry.kind === "post") return entry.item.id;
  return entry.key;
}

const globalSearchKindLabels: Record<GlobalSearchResult["kind"], string> = {
  fair: "FEIRA",
  offer: "OFERTA",
  place: "PONTO",
  post: "PUBLICAÇÃO",
  product: "PRODUTO",
  profile: "PERFIL",
};

const globalSearchKindIcons: Record<GlobalSearchResult["kind"], keyof typeof Ionicons.glyphMap> = {
  fair: "calendar-outline",
  offer: "ticket-outline",
  place: "location-outline",
  post: "newspaper-outline",
  product: "bag-handle-outline",
  profile: "person-outline",
};

function GlobalSearchCard({ item, onOpenProfile }: { item: GlobalSearchResult; onOpenProfile: () => void }) {
  const routeProfileMatch = item.target_url?.match(/^\/profile\/([^/?#]+)/);
  const profileId = item.profile_id || (routeProfileMatch?.[1] ? decodeURIComponent(routeProfileMatch[1]) : "");
  const targetTab = item.kind === "post"
    ? "posts"
    : item.kind === "product"
      ? "products"
      : item.kind === "offer"
        ? "offers"
        : item.kind === "fair"
          ? "fairs"
          : null;
  const profilePath = profileId
    ? targetTab
      ? profileSharePath(profileId, { tab: targetTab, itemId: item.id })
      : profileSharePath(profileId)
    : undefined;
  return (
    <View style={styles.globalResultCard}>
      <View style={styles.globalResultIcon}>
        <Ionicons color={colors.primary} name={globalSearchKindIcons[item.kind]} size={21} />
      </View>
      <View style={styles.globalResultText}>
        <Text style={styles.globalResultKind}>{globalSearchKindLabels[item.kind]}</Text>
        <Text numberOfLines={2} style={styles.globalResultTitle}>{item.title}</Text>
        {item.subtitle ? <Text numberOfLines={2} style={styles.globalResultSubtitle}>{item.subtitle}</Text> : null}
      </View>
      <View style={styles.globalResultActions}>
        {profilePath ? (
          <Pressable accessibilityRole="button" onPress={onOpenProfile} style={styles.globalResultAction}>
            <Text style={styles.globalResultActionText}>Ver perfil</Text>
          </Pressable>
        ) : null}
        <Pressable
          accessibilityLabel={`Compartilhar ${item.title}`}
          accessibilityRole="button"
          onPress={() => void shareLiberRotasItem({
            kind: item.kind as LiberRotasShareKind,
            title: item.title,
            description: item.subtitle,
            path: profilePath,
          })}
          style={styles.globalResultAction}
        >
          <Text style={styles.globalResultActionText}>Compartilhar</Text>
        </Pressable>
      </View>
    </View>
  );
}

function VideoPreview({ uri, compact = false }: { uri: string; compact?: boolean }) {
  const player = useVideoPlayer(uri);
  return (
    <VideoView
      contentFit="cover"
      fullscreenOptions={{ enable: true }}
      nativeControls
      player={player}
      style={compact ? styles.composerMedia : styles.userPostMedia}
    />
  );
}

function FeedActions({
  commentsOpen,
  liked,
  onOpenProfile,
  onShare,
  onToggleComments,
  onToggleFavorite,
  shareAccessibilityLabel,
}: {
  commentsOpen?: boolean;
  liked: boolean;
  onOpenProfile: () => void;
  onShare: () => void;
  onToggleComments?: () => void;
  onToggleFavorite: () => void;
  shareAccessibilityLabel: string;
}) {
  return (
    <View style={styles.postActions}>
      <Pressable onPress={onToggleFavorite} style={[styles.actionButton, liked && styles.actionButtonLiked]}>
        <Ionicons color={liked ? colors.danger : colors.primary} name={liked ? "heart" : "heart-outline"} size={16} />
        <Text style={[styles.actionText, liked && styles.actionTextLiked]}>{liked ? "Curtido" : "Curtir"}</Text>
      </Pressable>
      {onToggleComments ? (
        <Pressable onPress={onToggleComments} style={[styles.actionButton, commentsOpen && styles.actionButtonActive]}>
          <Ionicons color={colors.primary} name={commentsOpen ? "chatbubble" : "chatbubble-outline"} size={16} />
          <Text style={styles.actionText}>{commentsOpen ? "Fechar comentários" : "Comentar"}</Text>
        </Pressable>
      ) : null}
      <Pressable onPress={onOpenProfile} style={styles.actionButton}>
        <Ionicons color={colors.primary} name="person-circle-outline" size={16} />
        <Text style={styles.actionText}>Ver perfil</Text>
      </Pressable>
      <Pressable accessibilityLabel={shareAccessibilityLabel} accessibilityRole="button" onPress={onShare} style={styles.actionButton}>
        <Ionicons color={colors.primary} name="share-social-outline" size={16} />
        <Text style={styles.actionText}>Compartilhar</Text>
      </Pressable>
    </View>
  );
}

function ProfileCard({
  item,
  liked,
  onOpenProfile,
  onToggleFavorite,
}: {
  item: PublicEntrepreneurProfileSummary;
  liked: boolean;
  onOpenProfile: () => void;
  onToggleFavorite: () => void;
}) {
  return (
    <View style={styles.timelineCard}>
      <View style={styles.summaryRow}>
        <View style={styles.avatar}>
          {item.avatarUri ? (
            <Image contentFit="cover" source={{ uri: item.avatarUri }} style={styles.avatarImage} />
          ) : (
            <Text style={styles.avatarText}>{item.name.slice(0, 2).toUpperCase() || "LR"}</Text>
          )}
        </View>
        <View style={styles.summaryText}>
          <Text style={styles.eyebrow}>NOVO EMPREENDEDOR</Text>
          <Text style={styles.summaryTitle}>{item.name}</Text>
          <Text style={styles.summaryMeta}>{item.category} · {item.city}</Text>
        </View>
        <Text style={styles.timelineDate}>{formatDate(item.createdAtMs)}</Text>
      </View>
      {item.address ? <Text style={styles.description}>Endereço público: {item.address}</Text> : null}
      <FeedActions
        liked={liked}
        onOpenProfile={onOpenProfile}
        onShare={() => void shareLiberRotasItem({
          kind: "profile",
          title: item.name,
          description: `${item.category} · ${item.city}`,
          path: profileSharePath(item.id),
        })}
        onToggleFavorite={onToggleFavorite}
        shareAccessibilityLabel={`Compartilhar perfil ${item.name}`}
      />
    </View>
  );
}

function PlaceCard({
  place,
  liked,
  onOpenProfile,
  onToggleFavorite,
}: {
  place: PinhaisPlace;
  liked: boolean;
  onOpenProfile: () => void;
  onToggleFavorite: () => void;
}) {
  return (
    <View style={styles.timelineCard}>
      <View style={styles.summaryRow}>
        <View style={[styles.squareIcon, styles.placeIcon]}>
          <Ionicons color={colors.primary} name="location-outline" size={24} />
        </View>
        <View style={styles.summaryText}>
          <Text style={styles.eyebrow}>PONTO PÚBLICO</Text>
          <Text style={styles.summaryTitle}>{place.nome}</Text>
          <Text style={styles.summaryMeta}>{pinhaisCategoryLabels[place.categoriaApp]} · {place.endereco}</Text>
          <Text style={styles.ownerLink}>Publicado por {place.ownerName}</Text>
        </View>
        <Text style={styles.timelineDate}>{formatDate(place.createdAtMs ?? 0)}</Text>
      </View>
      <FeedActions
        liked={liked}
        onOpenProfile={onOpenProfile}
        onShare={() => void shareLiberRotasItem({
          kind: place.categoriaApp === "eventos" ? "event" : "place",
          title: place.nome,
          description: `${place.resumo} · ${place.endereco}`,
          path: place.ownerId ? profileSharePath(place.ownerId) : undefined,
        })}
        onToggleFavorite={onToggleFavorite}
        shareAccessibilityLabel={`Compartilhar ${place.categoriaApp === "eventos" ? "evento" : "local"} ${place.nome}`}
      />
    </View>
  );
}

function LiveFairCard({
  fair,
  liked,
  onOpenProfile,
  onToggleFavorite,
  referenceTimeMs,
}: {
  fair: LiveFair;
  liked: boolean;
  onOpenProfile: () => void;
  onToggleFavorite: () => void;
  referenceTimeMs: number;
}) {
  const status = resolveLiveFairStatus(fair, referenceTimeMs);
  const eventTimestamp = status === "ended" ? fair.endedAtMs ?? fair.endsAtMs : fair.createdAtMs;

  function openMap() {
    Linking.openURL(fair.googleMapsUri).catch(() => {
      showStaffAlert("Não foi possível abrir o mapa", "Confira se o aparelho possui um aplicativo de mapas disponível.");
    });
  }

  return (
    <View style={[styles.timelineCard, status === "live" && styles.liveCard]}>
      <View style={styles.summaryRow}>
        <View style={[styles.squareIcon, status === "live" ? styles.liveIcon : styles.placeIcon]}>
          <Ionicons color={status === "live" ? colors.surface : colors.primary} name="radio-outline" size={24} />
        </View>
        <View style={styles.summaryText}>
          <Text style={[styles.eyebrow, status === "ended" && styles.eyebrowInactive]}>{fairStatusLabel(fair, referenceTimeMs)}</Text>
          <Text style={styles.summaryTitle}>{fair.name}</Text>
          <Text style={styles.ownerLink}>Publicada por {fair.ownerName}</Text>
        </View>
        <Text style={styles.timelineDate}>{formatDate(eventTimestamp)}</Text>
      </View>
      <Text style={styles.description}>{fair.address}</Text>
      <Text style={styles.statusNote}>{fairStatusReason(fair, referenceTimeMs)}</Text>
      <Pressable onPress={openMap} style={styles.mapButton}>
        <Ionicons color={colors.primary} name="navigate-outline" size={16} />
        <Text style={styles.actionText}>Abrir localização no Maps</Text>
      </Pressable>
      <FeedActions
        liked={liked}
        onOpenProfile={onOpenProfile}
        onShare={() => void shareLiberRotasItem({
          kind: "fair",
          title: fair.name,
          description: `${fair.address} · ${fairStatusReason(fair, referenceTimeMs)}`,
          path: profileSharePath(fair.ownerId, { tab: "fairs", itemId: fair.id }),
        })}
        onToggleFavorite={onToggleFavorite}
        shareAccessibilityLabel={`Compartilhar feira ${fair.name}`}
      />
    </View>
  );
}

function ProductCard({
  product,
  liked,
  onOpenProfile,
  onToggleFavorite,
}: {
  product: CatalogProductItem;
  liked: boolean;
  onOpenProfile: () => void;
  onToggleFavorite: () => void;
}) {
  const eventTimestamp = (product.ended_at ?? (product.status === "ACTIVE" ? product.created_at : product.updated_at)) * 1000;
  return (
    <View style={[styles.timelineCard, product.status === "ENDED" && styles.endedCard]}>
      <View style={styles.summaryRow}>
        <View style={styles.squareIcon}>
          <Ionicons color={colors.accent} name="bag-handle-outline" size={24} />
        </View>
        <View style={styles.summaryText}>
          <Text style={[styles.eyebrow, product.status === "ENDED" && styles.eyebrowInactive]}>{productStatusLabel(product)}</Text>
          <Text style={styles.summaryTitle}>{product.title}</Text>
          <Text style={styles.ownerLink}>{product.merchant.display_name}</Text>
        </View>
        <View style={styles.trailingColumn}>
          <Text style={styles.price}>{formatMoney(product.price_minor, product.currency)}</Text>
          <Text style={styles.timelineDate}>{formatDate(eventTimestamp)}</Text>
        </View>
      </View>
      {product.description ? <Text style={styles.description}>{product.description}</Text> : null}
      <Text style={styles.statusNote}>{productStatusReason(product)} Estoque: {product.stock_quantity}.</Text>
      <FeedActions
        liked={liked}
        onOpenProfile={onOpenProfile}
        onShare={() => void shareLiberRotasItem({
          kind: "product",
          title: product.title,
          description: `${formatMoney(product.price_minor, product.currency)} · ${product.description || productStatusReason(product)}`,
          path: profileSharePath(product.merchant.firebase_uid, { tab: "products", itemId: product.product_id }),
        })}
        onToggleFavorite={onToggleFavorite}
        shareAccessibilityLabel={`Compartilhar produto ${product.title}`}
      />
    </View>
  );
}

function OfferCard({
  item,
  liked,
  onOpenProfile,
  onToggleFavorite,
  referenceTimeMs,
}: {
  item: PublicOfferCard;
  liked: boolean;
  onOpenProfile: () => void;
  onToggleFavorite: () => void;
  referenceTimeMs: number;
}) {
  const { offer, product } = item;
  const timeEnded = hasTimeEnded(offer.expires_at * 1_000, referenceTimeMs);
  const eventTimestamp = (offer.ended_at ?? (offer.status === "ACTIVE" ? offer.created_at : offer.updated_at)) * 1000;
  return (
    <View style={[styles.offerCard, (offer.status === "ENDED" || timeEnded) && styles.endedCard]}>
      <View style={styles.offerMain}>
        <View style={[styles.offerBadge, (offer.status === "ENDED" || timeEnded) && styles.offerBadgeEnded]}>
          <Ionicons color={colors.surface} name="pricetag" size={18} />
          <Text style={styles.offerBadgeText}>CUPOM</Text>
        </View>
        <View style={styles.offerBody}>
          <View style={styles.offerTitleRow}>
            <View style={styles.summaryText}>
              <Text style={[styles.eyebrow, (offer.status === "ENDED" || timeEnded) && styles.eyebrowInactive]}>{offerStatusLabel(offer, referenceTimeMs)}</Text>
              <Text style={styles.summaryTitle}>{product.title}</Text>
              <Text style={styles.ownerLink}>Emitido por {product.merchant.display_name}</Text>
            </View>
            <Text style={styles.timelineDate}>{formatDate(eventTimestamp)}</Text>
          </View>
          <View style={styles.offerPrices}>
            <Text style={styles.oldPrice}>{formatMoney(offer.original_amount_minor, offer.currency)}</Text>
            <Text style={styles.offerPrice}>{formatMoney(offer.final_amount_minor, offer.currency)}</Text>
          </View>
          <Text style={styles.summaryMeta}>
            {offer.remaining_redemptions} resgate(s) disponível(is) · {timeEnded
              ? `validade encerrada: ${formatDate(offer.expires_at * 1_000)}`
              : `restam ${formatRemainingTime(offer.expires_at * 1_000, referenceTimeMs)} · validade: ${formatDate(offer.expires_at * 1_000)}`}
          </Text>
          <Text style={styles.statusNote}>{offerStatusReason(offer, referenceTimeMs)}</Text>
        </View>
      </View>
      <View style={styles.offerActions}>
        <FeedActions
          liked={liked}
          onOpenProfile={onOpenProfile}
          onShare={() => void shareLiberRotasItem({
            kind: "offer",
            title: product.title,
            description: `${formatMoney(offer.final_amount_minor, offer.currency)} · ${offerStatusReason(offer, referenceTimeMs)}`,
            path: profileSharePath(product.merchant.firebase_uid, { tab: "offers", itemId: offer.offer_id }),
          })}
          onToggleFavorite={onToggleFavorite}
          shareAccessibilityLabel={`Compartilhar oferta ${product.title}`}
        />
      </View>
    </View>
  );
}

function UserPostCard({
  post,
  liked,
  onOpenProfile,
  onToggleFavorite,
}: {
  post: FeedPost;
  liked: boolean;
  onOpenProfile: (profileId?: string) => void;
  onToggleFavorite: () => void;
}) {
  const roleLabel = post.authorRole === "entrepreneur" ? "Empreendedor" : "Visitante";
  const stableAuthorAvatarUri = getStablePublicAvatarUrl(post.authorId, post.authorAvatarUri);
  const [commentsOpen, setCommentsOpen] = useState(false);
  return (
    <View style={styles.postCard}>
      {post.media?.type === "image" ? (
        <ProtectedMediaImage
          contentFit="contain"
          expandable
          legacyUri={post.media.uri}
          mediaId={post.media.mediaId}
          publicVariant="display"
          style={styles.userPostMedia}
          viewerLabel={`Imagem da publicação de ${post.author}`}
        />
      ) : null}
      {post.media?.type === "video" && post.media.uri ? <VideoPreview uri={post.media.uri} /> : null}
      <View style={styles.postBody}>
        <Text style={styles.eyebrow}>PUBLICAÇÃO</Text>
        <View style={styles.postHeader}>
          <Pressable onPress={() => onOpenProfile(post.authorId)} style={styles.authorRow}>
            <View style={styles.avatar}>
              {stableAuthorAvatarUri ? (
                <Image cachePolicy="memory-disk" contentFit="cover" source={{ uri: stableAuthorAvatarUri }} style={styles.avatarImage} />
              ) : (
                <Text style={styles.avatarText}>{post.author.slice(0, 2).toUpperCase() || "LR"}</Text>
              )}
            </View>
            <View style={styles.summaryText}>
              <Text style={styles.summaryTitle}>{post.author}</Text>
              <Text style={styles.summaryMeta}>{roleLabel}</Text>
            </View>
          </Pressable>
          <Text style={styles.timelineDate}>{formatDate(Date.parse(post.createdAt))}</Text>
        </View>
        <Text style={styles.postText}>{post.text}</Text>
        <PostOwnerActions post={post} />
        <FeedActions
          commentsOpen={commentsOpen}
          liked={liked}
          onOpenProfile={() => onOpenProfile(post.authorId)}
          onShare={() => void shareLiberRotasItem({
            kind: "post",
            title: `Publicação de ${post.author}`,
            description: post.text,
            path: profileSharePath(post.authorId, { tab: "posts", itemId: post.id }),
          })}
          onToggleComments={() => setCommentsOpen((current) => !current)}
          onToggleFavorite={onToggleFavorite}
          shareAccessibilityLabel={`Compartilhar publicação de ${post.author}`}
        />
        <PostComments
          expanded={commentsOpen}
          onOpenProfile={(profileId) => onOpenProfile(profileId)}
          postId={post.id}
        />
      </View>
    </View>
  );
}

export default function FeedScreen() {
  const { nowMs } = useTrustedClock();
  const { createPost, favorites, profile, toggleFavorite, userPosts } = useApp();
  const [search, setSearch] = useState("");
  const [postText, setPostText] = useState("");
  const [pendingMedia, setPendingMedia] = useState<PendingMedia | null>(null);
  const [isPublishing, setIsPublishing] = useState(false);
  const [profiles, setProfiles] = useState<PublicEntrepreneurProfileSummary[]>([]);
  const [places, setPlaces] = useState<PinhaisPlace[]>([]);
  const [liveFairs, setLiveFairs] = useState<LiveFair[]>([]);
  const [catalog, setCatalog] = useState<CatalogProductItem[]>([]);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState(true);
  const [profilesError, setProfilesError] = useState("");
  const [placesError, setPlacesError] = useState("");
  const [fairsError, setFairsError] = useState("");
  const [catalogError, setCatalogError] = useState("");
  const [globalResults, setGlobalResults] = useState<GlobalSearchResult[]>([]);
  const [isGlobalSearching, setIsGlobalSearching] = useState(false);
  const [globalSearchError, setGlobalSearchError] = useState("");

  useEffect(() => {
    const unsubscribeProfiles = subscribeToPublicEntrepreneurProfiles(
      (items) => {
        setProfiles(items);
        setProfilesError("");
      },
      () => setProfilesError("Não foi possível sincronizar os perfis públicos."),
    );
    const unsubscribePlaces = subscribeToApprovedCuratedPlaces(
      (items) => {
        setPlaces(items);
        setPlacesError("");
      },
      () => setPlacesError("Não foi possível sincronizar os pontos públicos."),
    );
    const unsubscribeFairs = subscribeToPublicLiveFairs(
      (items) => {
        setLiveFairs(items);
        setFairsError("");
      },
      () => setFairsError("Não foi possível sincronizar as feiras ao vivo."),
    );

    return () => {
      unsubscribeProfiles();
      unsubscribePlaces();
      unsubscribeFairs();
    };
  }, []);

  useEffect(() => {
    const query = search.trim();
    if (query.length < 2) return undefined;

    let active = true;
    const timer = setTimeout(() => {
      searchGlobalDirectory(query)
        .then((items) => {
          if (active) setGlobalResults(items);
        })
        .catch((error) => {
          if (!active) return;
          setGlobalResults([]);
          setGlobalSearchError(error instanceof Error ? error.message : "Não foi possível concluir a busca global.");
        })
        .finally(() => {
          if (active) setIsGlobalSearching(false);
        });
    }, 350);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [search]);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      function refreshCatalog(showLoading = false) {
        if (showLoading) setIsLoadingCatalog(true);
        return listPublicCatalogFeed()
          .then((items) => {
            if (!active) return;
            setCatalog(items);
            setCatalogError("");
          })
          .catch((error) => {
            if (!active) return;
            setCatalogError(error instanceof Error ? error.message : "Não foi possível carregar produtos e ofertas.");
          })
          .finally(() => {
            if (active && showLoading) setIsLoadingCatalog(false);
          });
      }

      refreshCatalog(true);
      const refreshInterval = setInterval(() => refreshCatalog(), 30_000);

      return () => {
        active = false;
        clearInterval(refreshInterval);
      };
    }, []),
  );

  const term = normalizeSearch(search);
  const timeline = useMemo(() => {
    const entries: TimelineEntry[] = [
      ...profiles.map((item): TimelineEntry => ({
        key: `profile:${item.id}`,
        kind: "profile",
        timestamp: item.createdAtMs || item.updatedAtMs,
        item,
      })),
      ...places
        .filter((item) => Boolean(item.ownerId))
        .map((item): TimelineEntry => ({
          key: `place:${item.id}`,
          kind: "place",
          timestamp: item.createdAtMs ?? 0,
          item,
        })),
      ...liveFairs.map((item): TimelineEntry => {
        const status = resolveLiveFairStatus(item, nowMs);
        return {
          key: `fair:${item.id}`,
          kind: "fair",
          timestamp: status === "ended" ? item.endedAtMs ?? item.endsAtMs : item.createdAtMs,
          item,
        };
      }),
      ...catalog.map((item): TimelineEntry => ({
        key: `product:${item.product_id}`,
        kind: "product",
        timestamp: (item.ended_at ?? (item.status === "ACTIVE" ? item.created_at : item.updated_at)) * 1000,
        item,
      })),
      ...catalog.flatMap((product) => product.offers.map((offer): TimelineEntry => ({
        key: `offer:${offer.offer_id}`,
        kind: "offer",
        timestamp: (offer.ended_at ?? (offer.status === "ACTIVE" ? offer.created_at : offer.updated_at)) * 1000,
        item: { offer, product },
      }))),
      ...userPosts.map((item): TimelineEntry => ({
        key: `post:${item.id}`,
        kind: "post",
        timestamp: Date.parse(item.createdAt) || 0,
        item,
      })),
    ];

    return entries
      .filter((entry) => normalizeSearch(timelineSearchText(entry, nowMs)).includes(term))
      .sort((left, right) => right.timestamp - left.timestamp || left.key.localeCompare(right.key));
  }, [catalog, liveFairs, nowMs, places, profiles, term, userPosts]);

  function openProfile(profileId?: string) {
    if (!profileId) return;
    router.push({ pathname: "/profile/[profileId]", params: { profileId } } as unknown as Href);
  }

  function openGlobalResult(item: GlobalSearchResult) {
    if (item.profile_id) {
      openProfile(item.profile_id);
      return;
    }
    const routeMatch = item.target_url?.match(/^\/profile\/([^/?#]+)/);
    if (routeMatch?.[1]) openProfile(decodeURIComponent(routeMatch[1]));
  }

  function updateSearch(value: string) {
    setSearch(value);
    setGlobalSearchError("");
    if (value.trim().length < 2) {
      setGlobalResults([]);
      setIsGlobalSearching(false);
    } else {
      setGlobalResults([]);
      setIsGlobalSearching(true);
    }
  }

  async function setSelectedAsset(asset: ImagePicker.ImagePickerAsset) {
    try {
      setPendingMedia(await prepareImageForUpload(asset));
    } catch (error) {
      showStaffAlert(
        "Imagem não permitida",
        error instanceof Error ? error.message : "Escolha uma imagem JPEG, PNG ou WebP de até 5 MB.",
      );
    }
  }

  async function pickImageFromLibrary() {
    if (Platform.OS !== "web") {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        showStaffAlert("Permissão necessária", "Permita o acesso à galeria para escolher uma imagem.");
        return;
      }
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.85,
    });
    if (!result.canceled) await setSelectedAsset(result.assets[0]);
  }

  async function captureImage() {
    if (Platform.OS !== "web") {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        showStaffAlert("Permissão necessária", "Permita o acesso à câmera para registrar uma foto.");
        return;
      }
    }

    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ["images"],
      quality: 0.85,
    });
    if (result.canceled) return;
    await setSelectedAsset(result.assets[0]);
  }

  async function publishPost() {
    if (!postText.trim()) {
      showStaffAlert("Escreva uma mensagem", "A publicação precisa ter um texto.");
      return;
    }

    try {
      setIsPublishing(true);
      let mediaId = pendingMedia?.mediaId;
      if (pendingMedia && !mediaId) {
        const confirmedAsset = await uploadImage(pendingMedia, {
          entityId: null,
          entityType: "post",
          mediaRole: "post_image",
        });
        if (["deleted", "orphaned", "quarantined", "rejected"].includes(confirmedAsset.status)) {
          throw new Error("O backend recusou a imagem selecionada.");
        }
        mediaId = confirmedAsset.media_id;
        setPendingMedia((current) => current?.clientRequestId === pendingMedia.clientRequestId
          ? { ...current, mediaId: confirmedAsset.media_id }
          : current);
      }

      await createPost(postText, mediaId ? { type: "image", mediaId } : undefined);
      setPostText("");
      setPendingMedia(null);
      setSearch("");
    } catch (error) {
      console.warn("Não foi possível publicar.", error);
      showStaffAlert(
        "Falha ao publicar",
        error instanceof Error
          ? error.message
          : "Não foi possível publicar no Feed compartilhado. Confira sua conexão e tente novamente.",
      );
    } finally {
      setIsPublishing(false);
    }
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <BrandHeader subtitle="rede de turismo solidário" title="Feed" />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.searchBox}>
          <Ionicons color={colors.textMuted} name="search" size={18} />
          <TextInput
            accessibilityLabel="Pesquisar em todo o LiberRotas"
            autoCapitalize="none"
            onChangeText={updateSearch}
            placeholder="Pesquisar perfis, publicações, produtos, ofertas e feiras..."
            placeholderTextColor={colors.textMuted}
            returnKeyType="search"
            style={styles.searchInput}
            value={search}
          />
          {search ? (
            <Pressable accessibilityLabel="Limpar pesquisa" onPress={() => updateSearch("")} style={styles.clearSearchButton}>
              <Ionicons color={colors.textMuted} name="close-circle" size={20} />
            </Pressable>
          ) : null}
        </View>
        {term.length === 1 ? <Text style={styles.searchHint}>Digite mais um caractere para pesquisar em toda a plataforma.</Text> : null}
        {isGlobalSearching ? <Text style={styles.loadingText}>Pesquisando em toda a plataforma...</Text> : null}
        {globalSearchError ? (
          <Text style={styles.errorText}>A busca global falhou, mas os conteúdos já carregados continuam disponíveis: {globalSearchError}</Text>
        ) : null}
        {term.length >= 2 && globalResults.length > 0 ? (
          <View style={styles.globalResults}>
            <Text style={styles.globalResultsTitle}>Resultados em toda a plataforma</Text>
            {globalResults.map((item) => (
              <GlobalSearchCard item={item} key={`${item.kind}:${item.id}`} onOpenProfile={() => openGlobalResult(item)} />
            ))}
          </View>
        ) : null}

        <View style={styles.composer}>
          <View style={styles.composerHeader}>
            <View style={styles.avatar}>
              {profile.avatarUri ? (
                <Image contentFit="cover" source={{ uri: profile.avatarUri }} style={styles.avatarImage} />
              ) : (
                <Text style={styles.avatarText}>{profile.name.slice(0, 2).toUpperCase() || "LR"}</Text>
              )}
            </View>
            <View style={styles.summaryText}>
              <Text style={styles.summaryTitle}>{profile.name}</Text>
              <Text style={styles.summaryMeta}>{profile.role === "entrepreneur" ? "Empreendedor" : "Visitante"}</Text>
            </View>
          </View>
          <TextInput
            maxLength={500}
            multiline
            onChangeText={setPostText}
            placeholder="Compartilhe uma novidade ou experiência..."
            placeholderTextColor={colors.textMuted}
            style={styles.composerInput}
            textAlignVertical="top"
            value={postText}
          />
          {pendingMedia ? (
            <View style={styles.composerPreview}>
              <Image contentFit="contain" source={{ uri: pendingMedia.asset.uri }} style={styles.composerMedia} />
              <Pressable
                accessibilityLabel="Remover imagem"
                disabled={isPublishing}
                onPress={() => setPendingMedia(null)}
                style={styles.removeMedia}
              >
                <Ionicons color={colors.surface} name="close" size={20} />
              </Pressable>
            </View>
          ) : null}
          <View style={styles.composerActions}>
            <View style={styles.mediaActions}>
              <Pressable
                disabled={isPublishing}
                onPress={captureImage}
                style={[styles.mediaButton, isPublishing && styles.mediaButtonDisabled]}
              >
                <Ionicons color={colors.primary} name="camera-outline" size={19} />
                <Text style={styles.mediaButtonText}>Foto</Text>
              </Pressable>
              <Pressable
                disabled={isPublishing}
                onPress={pickImageFromLibrary}
                style={[styles.mediaButton, isPublishing && styles.mediaButtonDisabled]}
              >
                <Ionicons color={colors.primary} name="image-outline" size={19} />
                <Text style={styles.mediaButtonText}>Galeria</Text>
              </Pressable>
            </View>
            <Pressable
              disabled={isPublishing || !postText.trim()}
              onPress={publishPost}
              style={[styles.publishButton, (isPublishing || !postText.trim()) && styles.publishButtonDisabled]}
            >
              <Text style={styles.publishButtonText}>{isPublishing ? "Publicando..." : "Publicar"}</Text>
            </Pressable>
          </View>
        </View>

        {profilesError ? <Text style={styles.errorText}>{profilesError}</Text> : null}
        {placesError ? <Text style={styles.errorText}>{placesError}</Text> : null}
        {fairsError ? <Text style={styles.errorText}>{fairsError}</Text> : null}
        {catalogError ? <Text style={styles.errorText}>{catalogError}</Text> : null}
        {isLoadingCatalog ? <Text style={styles.loadingText}>Atualizando o Feed...</Text> : null}

        <View style={styles.timeline}>
          {term.length >= 2 && timeline.length > 0 ? <Text style={styles.localResultsTitle}>Resultados no Feed carregado</Text> : null}
          {timeline.map((entry) => {
            const favoriteId = timelineFavoriteId(entry);
            const liked = favorites.includes(favoriteId);
            const onToggleFavorite = () => void toggleFavorite(favoriteId);

            switch (entry.kind) {
              case "profile":
                return (
                  <ProfileCard
                    item={entry.item}
                    key={entry.key}
                    liked={liked}
                    onOpenProfile={() => openProfile(entry.item.id)}
                    onToggleFavorite={onToggleFavorite}
                  />
                );
              case "place":
                return (
                  <PlaceCard
                    key={entry.key}
                    liked={liked}
                    onOpenProfile={() => openProfile(entry.item.ownerId)}
                    onToggleFavorite={onToggleFavorite}
                    place={entry.item}
                  />
                );
              case "fair":
                return (
                  <LiveFairCard
                    fair={entry.item}
                    key={entry.key}
                    liked={liked}
                    onOpenProfile={() => openProfile(entry.item.ownerId)}
                    onToggleFavorite={onToggleFavorite}
                    referenceTimeMs={nowMs}
                  />
                );
              case "product":
                return (
                  <ProductCard
                    key={entry.key}
                    liked={liked}
                    onOpenProfile={() => openProfile(entry.item.merchant.firebase_uid)}
                    onToggleFavorite={onToggleFavorite}
                    product={entry.item}
                  />
                );
              case "offer":
                return (
                  <OfferCard
                    item={entry.item}
                    key={entry.key}
                    liked={liked}
                    onOpenProfile={() => openProfile(entry.item.product.merchant.firebase_uid)}
                    onToggleFavorite={onToggleFavorite}
                    referenceTimeMs={nowMs}
                  />
                );
              case "post":
                return (
                  <UserPostCard
                    key={entry.key}
                    liked={liked}
                    onOpenProfile={openProfile}
                    onToggleFavorite={onToggleFavorite}
                    post={entry.item}
                  />
                );
            }
          })}
        </View>

        {timeline.length === 0 && globalResults.length === 0 && !isLoadingCatalog && !isGlobalSearching ? (
          <Text style={styles.empty}>
            {term.length >= 2 ? `Nenhum resultado encontrado para “${search.trim()}”.` : "Nenhum conteúdo compartilhado foi encontrado."}
          </Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  content: { alignSelf: "center", backgroundColor: colors.surfaceMuted, maxWidth: 1100, padding: 16, paddingBottom: 32, width: "100%" },
  composer: { backgroundColor: colors.surface, borderRadius: radius.medium, marginBottom: 14, padding: 14, ...shadow },
  composerHeader: { alignItems: "center", flexDirection: "row", gap: 10 },
  avatar: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 20, height: 40, justifyContent: "center", overflow: "hidden", width: 40 },
  avatarImage: { height: "100%", width: "100%" },
  avatarText: { color: colors.accent, fontSize: 12, fontWeight: "900" },
  composerInput: { borderBottomColor: colors.border, borderBottomWidth: 1, color: colors.text, fontSize: 14, lineHeight: 20, minHeight: 84, paddingVertical: 12 },
  composerPreview: { borderRadius: radius.small, marginTop: 12, overflow: "hidden", position: "relative" },
  composerMedia: { backgroundColor: colors.surfaceMuted, height: 190, width: "100%" },
  removeMedia: { alignItems: "center", backgroundColor: "rgba(15, 46, 110, 0.85)", borderRadius: 18, height: 36, justifyContent: "center", position: "absolute", right: 10, top: 10, width: 36 },
  composerActions: { alignItems: "flex-start", flexDirection: "row", gap: 10, justifyContent: "space-between", marginTop: 12 },
  mediaActions: { flex: 1, flexDirection: "row", flexWrap: "wrap", gap: 4 },
  mediaButton: { alignItems: "center", borderRadius: radius.pill, flexDirection: "row", gap: 4, paddingHorizontal: 8, paddingVertical: 8 },
  mediaButtonDisabled: { opacity: 0.45 },
  mediaButtonText: { color: colors.primary, fontSize: 12, fontWeight: "700" },
  publishButton: { backgroundColor: colors.accent, borderRadius: radius.pill, paddingHorizontal: 18, paddingVertical: 10 },
  publishButtonDisabled: { opacity: 0.4 },
  publishButtonText: { color: colors.surface, fontSize: 12, fontWeight: "800" },
  searchBox: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.primary, borderRadius: radius.small, borderWidth: 1, flexDirection: "row", gap: 8, marginBottom: 14, minHeight: 50, paddingHorizontal: 14, ...shadow },
  searchInput: { color: colors.text, flex: 1, fontSize: 13, paddingVertical: 12 },
  clearSearchButton: { alignItems: "center", height: 36, justifyContent: "center", width: 36 },
  searchHint: { color: colors.textMuted, fontSize: 11, marginBottom: 12, marginTop: -5 },
  globalResults: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, gap: 8, marginBottom: 14, padding: 12 },
  globalResultsTitle: { color: colors.primaryDark, fontSize: 14, fontWeight: "900", marginBottom: 2 },
  globalResultCard: { alignItems: "center", backgroundColor: colors.surfaceMuted, borderRadius: radius.small, flexDirection: "row", gap: 10, padding: 11 },
  globalResultIcon: { alignItems: "center", backgroundColor: colors.surface, borderRadius: 20, height: 40, justifyContent: "center", width: 40 },
  globalResultText: { flex: 1, minWidth: 0 },
  globalResultKind: { color: colors.accent, fontSize: 8, fontWeight: "900", letterSpacing: 0.7 },
  globalResultTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: "900", marginTop: 2 },
  globalResultSubtitle: { color: colors.textMuted, fontSize: 10, lineHeight: 14, marginTop: 2 },
  globalResultActions: { alignItems: "stretch", gap: 6 },
  globalResultAction: { borderColor: colors.primary, borderRadius: radius.pill, borderWidth: 1, paddingHorizontal: 11, paddingVertical: 8 },
  globalResultActionText: { color: colors.primary, fontSize: 10, fontWeight: "900" },
  localResultsTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: "900", marginBottom: 10 },
  timeline: { marginTop: 16 },
  timelineCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, marginBottom: 12, padding: 14, ...shadow },
  liveCard: { borderColor: colors.success, borderWidth: 2 },
  endedCard: { opacity: 0.86 },
  summaryRow: { alignItems: "flex-start", flexDirection: "row", gap: 12 },
  summaryText: { flex: 1 },
  summaryTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900" },
  summaryMeta: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 3 },
  eyebrow: { color: colors.accent, fontSize: 9, fontWeight: "900", letterSpacing: 0.8, marginBottom: 3 },
  eyebrowInactive: { color: colors.textMuted },
  ownerLink: { color: colors.primary, fontSize: 12, fontWeight: "800", marginTop: 4 },
  squareIcon: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 14, height: 46, justifyContent: "center", width: 46 },
  placeIcon: { backgroundColor: "#EAF2FF" },
  liveIcon: { backgroundColor: colors.success },
  trailingColumn: { alignItems: "flex-end", maxWidth: 120 },
  timelineDate: { color: colors.textMuted, fontSize: 9, maxWidth: 105, textAlign: "right" },
  description: { color: colors.text, fontSize: 12, lineHeight: 18, marginTop: 10 },
  statusNote: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 8 },
  price: { color: colors.primary, fontSize: 14, fontWeight: "900", marginBottom: 4 },
  mapButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: "#EAF2FF", borderRadius: radius.pill, flexDirection: "row", gap: 5, marginTop: 10, paddingHorizontal: 12, paddingVertical: 9 },
  offerCard: { backgroundColor: colors.surface, borderColor: colors.accent, borderRadius: radius.medium, borderWidth: 1, marginBottom: 12, overflow: "hidden", ...shadow },
  offerMain: { flexDirection: "row" },
  offerBadge: { alignItems: "center", backgroundColor: colors.accent, gap: 6, justifyContent: "center", paddingHorizontal: 10, width: 68 },
  offerBadgeEnded: { backgroundColor: colors.textMuted },
  offerBadgeText: { color: colors.surface, fontSize: 9, fontWeight: "900", letterSpacing: 0.7 },
  offerBody: { flex: 1, padding: 14 },
  offerTitleRow: { alignItems: "flex-start", flexDirection: "row", gap: 8 },
  offerPrices: { alignItems: "baseline", flexDirection: "row", gap: 8, marginTop: 8 },
  oldPrice: { color: colors.textMuted, fontSize: 12, textDecorationLine: "line-through" },
  offerPrice: { color: colors.accent, fontSize: 18, fontWeight: "900" },
  offerActions: { borderTopColor: colors.border, borderTopWidth: 1, paddingHorizontal: 14, paddingBottom: 12 },
  postCard: { backgroundColor: colors.background, borderColor: colors.border, borderRadius: radius.large, borderWidth: 1, marginBottom: 12, overflow: "hidden", ...shadow },
  userPostMedia: { backgroundColor: colors.surfaceMuted, height: 260, width: "100%" },
  postBody: { padding: 16 },
  postHeader: { alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" },
  authorRow: { alignItems: "center", flex: 1, flexDirection: "row", gap: 10 },
  postText: { color: colors.text, fontSize: 15, lineHeight: 21, marginTop: 14 },
  postActions: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 14 },
  actionButton: { alignItems: "center", backgroundColor: colors.cream, borderColor: colors.border, borderRadius: radius.pill, borderWidth: 1, flexDirection: "row", gap: 5, paddingHorizontal: 12, paddingVertical: 9 },
  actionButtonActive: { backgroundColor: "#EAF2FF", borderColor: colors.primary },
  actionButtonLiked: { backgroundColor: "#FFF0EE", borderColor: "#F2B8B5" },
  actionText: { color: colors.primary, fontSize: 12, fontWeight: "700" },
  actionTextLiked: { color: colors.danger },
  loadingText: { color: colors.textMuted, fontSize: 12, marginTop: 12 },
  errorText: { color: colors.danger, fontSize: 12, marginTop: 10 },
  empty: { color: colors.textMuted, paddingVertical: 44, textAlign: "center" },
});
