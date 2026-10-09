import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { Redirect, router, type Href, useLocalSearchParams } from "expo-router";
import { useVideoPlayer, VideoView } from "expo-video";
import { useEffect, useMemo, useState } from "react";
import { KeyboardAvoidingView, Linking, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import QRCode from "react-native-qrcode-svg";
import { SafeAreaView } from "react-native-safe-area-context";
import { ImageViewerModal } from "@/components/image-viewer-modal";
import { HeaderBackButton } from "@/components/header-back-button";
import { PostComments } from "@/components/post-comments";
import { ProtectedMediaImage } from "@/components/protected-media-image";
import { PublicEntityMediaImage } from "@/components/public-entity-media-image";
import { PostOwnerActions } from "@/components/post-owner-actions";
import { LoadingScreen } from "@/components/ui";
import { showStaffAlert } from "@/components/staff-panel-ui";
import { colors, radius, shadow } from "@/constants/theme";
import { AccountType, FeedPost, UserProfile, useApp } from "@/context/app-context";
import { useTrustedClock } from "@/context/trusted-clock-context";
import { demoProducts, demoProfiles, marketPosts, Product } from "@/data/demo";
import type { LiveFair } from "@/data/pinhais";
import type {
  CatalogMerchantResponse,
  CatalogOfferSummary,
  CatalogProductItem,
  CouponQrGroupResult,
  OfferPreview,
} from "@/security/trq-bec/contracts";
import {
  createCombinedCouponQr,
  createClientMessageId,
  deleteLiveFair,
  deleteOwnLiveOffer,
  getStablePublicAvatarUrl,
  getPublicMerchantCatalog,
  getOwnLiveOfferQr,
  listEntrepreneurFundedEvents,
  listOwnLiveOffers,
  loadEntrepreneurFundedEventReport,
  loadPublicDirectoryProfile,
  sendPrivateMessage,
  TrqBecServiceError,
  MAX_COMBINED_COUPONS,
  type EntrepreneurFundedEventReport,
  type PublicDirectoryProfile,
} from "@/security/trq-bec/service";
import { loadPublicProfile, subscribeToPublicLiveFairs } from "@/services/cloud-data";
import { auth } from "@/services/firebase";
import { profileSharePath, shareLiberRotasItem, type ProfileShareTab } from "@/utils/share";
import { getAuthenticatedHomeDestination } from "@/utils/account-navigation";
import { formatRemainingTime, hasTimeEnded } from "@/utils/time";

type ProfileTab = ProfileShareTab;
type DemoMarketPost = (typeof marketPosts)[number];
type ProfilePostItem =
  | { id: string; kind: "local"; post: FeedPost }
  | { id: string; kind: "demo"; post: DemoMarketPost };

type PublicProfile = {
  id: string;
  role: AccountType | "institution";
  name: string;
  city: string;
  address?: string;
  category: string;
  bio: string;
  initials: string;
  interests: string[];
  avatarUri?: string;
  avatarColor?: string;
};

type ProfileOfferItem = {
  offer: CatalogOfferSummary;
  product: CatalogProductItem;
};

type OwnerOfferMetrics = {
  amountDueMinor: number;
  fundedEventCount: number;
  offer: OfferPreview | null;
  stockQuantity: number;
};

type OwnerOfferLoadState = {
  profileId: string;
  offers: OfferPreview[];
  fundedReports: EntrepreneurFundedEventReport[];
  error: string;
};

type ProfileLoadState = {
  profileId: string;
  profile: PublicProfile | null;
  error: string;
};

type CatalogLoadState = {
  profileId: string;
  catalog: CatalogMerchantResponse | null;
  error: string;
  notFound: boolean;
};

type LiveFairsLoadState = {
  profileId: string;
  fairs: LiveFair[];
  error: string;
};

function firstRouteParam(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() || "";
}

function normalizeProfileTab(value: string): ProfileTab | null {
  return value === "posts" || value === "products" || value === "offers" || value === "fairs" ? value : null;
}

function prioritizeTarget<T>(items: T[], targetId: string, getId: (item: T) => string): T[] {
  if (!targetId) return items;
  const targetIndex = items.findIndex((item) => getId(item) === targetId);
  if (targetIndex <= 0) return items;
  return [items[targetIndex], ...items.slice(0, targetIndex), ...items.slice(targetIndex + 1)];
}

function formatFairDateTime(timestamp: number) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(timestamp));
}

function getFairStatusLabel(fair: LiveFair) {
  if (fair.status === "live") return "AO VIVO";
  if (fair.status === "scheduled") return "PROGRAMADA";
  return "ENCERRADA";
}

async function openFairInMaps(fair: LiveFair) {
  try {
    await Linking.openURL(fair.googleMapsUri);
  } catch (error) {
    console.warn("Não foi possível abrir a localização da feira.", error);
    showStaffAlert("Mapa indisponível", "Não foi possível abrir esta localização no Maps.");
  }
}

function publicProfileFromUser(profile: UserProfile): PublicProfile {
  return {
    id: profile.id,
    role: profile.role,
    name: profile.name,
    city: profile.city,
    address: profile.role === "entrepreneur" ? profile.address : undefined,
    category: profile.category,
    bio: profile.role === "entrepreneur"
      ? "Conheça as publicações, os produtos e as ofertas deste empreendedor."
      : "Perfil de visitante da comunidade LiberRotas.",
    initials: profile.name.slice(0, 2).toUpperCase() || "LR",
    interests: profile.interests,
    avatarUri: profile.avatarUri,
  };
}

function publicProfileFromDirectory(profile: PublicDirectoryProfile): PublicProfile {
  const isEntrepreneur = profile.role === "entrepreneur";
  const isInstitution = profile.role === "institution";
  return {
    id: profile.firebase_uid,
    role: profile.role,
    name: profile.display_name,
    city: profile.city,
    address: isEntrepreneur ? profile.address || undefined : undefined,
    category: profile.category || (isInstitution ? "Instituição LiberRotas" : "Visitante LiberRotas"),
    bio: isEntrepreneur
      ? "Conheça as publicações, os produtos e as ofertas deste empreendedor."
      : isInstitution
        ? "Perfil de uma instituição autorizada da comunidade LiberRotas."
        : "Perfil de visitante da comunidade LiberRotas.",
    initials: profile.display_name.slice(0, 2).toUpperCase() || "LR",
    interests: profile.interests,
    avatarUri: profile.avatar_uri || undefined,
  };
}

function formatMoney(valueMinor: number, currency: string) {
  try {
    return new Intl.NumberFormat("pt-BR", { currency, style: "currency" }).format(valueMinor / 100);
  } catch {
    return `${currency} ${(valueMinor / 100).toFixed(2)}`;
  }
}

function formatExpiration(expiresAt: number) {
  return new Date(expiresAt * 1000).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function formatOfferTime(expiresAt: number, nowMs: number) {
  return hasTimeEnded(expiresAt * 1000, nowMs)
    ? "Encerrada"
    : formatRemainingTime(expiresAt * 1000, nowMs);
}

function catalogProductToCard(product: CatalogProductItem): Product {
  const statusLabel = product.status === "ENDED"
    ? "Produto encerrado"
    : product.status === "PAUSED"
      ? "Produto pausado"
      : "Produto público";
  const reasonLabel = product.status_reason === "OUT_OF_STOCK" ? " · Estoque esgotado" : "";
  return {
    id: product.product_id,
    ownerId: product.merchant.firebase_uid,
    title: product.title,
    price: formatMoney(product.price_minor, product.currency),
    description: product.description.trim() || "Produto sem descrição.",
    category: `${statusLabel}${reasonLabel} · Estoque: ${product.stock_quantity}`,
  };
}

function profileOfferStatus(offer: CatalogOfferSummary) {
  if (offer.status === "ENDED") return "CUPOM ENCERRADO";
  if (offer.status === "PAUSED") return "CUPOM PAUSADO";
  return "CUPOM ATIVO";
}

function profileOfferReason(offer: CatalogOfferSummary) {
  const reasons: Record<Exclude<CatalogOfferSummary["status_reason"], null>, string> = {
    CANCELLED: "Encerrado antecipadamente pelo empreendedor.",
    EXHAUSTED: "Todos os cupons foram utilizados.",
    EXPIRED: "A validade terminou.",
    OUT_OF_STOCK: "O produto ficou sem estoque.",
    PAUSED: "Pausado pelo empreendedor.",
    PRODUCT_PAUSED: "Pausado junto com o produto.",
  };
  return offer.status_reason ? reasons[offer.status_reason] : "Disponível para resgate.";
}

function ProfileVideo({ uri }: { uri: string }) {
  const player = useVideoPlayer(uri);
  return <VideoView contentFit="cover" fullscreenOptions={{ enable: true }} nativeControls player={player} style={styles.postMedia} />;
}

function ShareButton({ accessibilityLabel, noMargin = false, onPress }: { accessibilityLabel: string; noMargin?: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityLabel={accessibilityLabel} accessibilityRole="button" onPress={onPress} style={[styles.shareButton, noMargin && styles.shareButtonNoMargin]}>
      <Ionicons color={colors.primary} name="share-social-outline" size={17} />
      <Text style={styles.shareButtonText}>Compartilhar</Text>
    </Pressable>
  );
}

function ProductCard({ highlighted, product }: { highlighted: boolean; product: Product }) {
  return (
    <View style={[styles.productCard, highlighted && styles.targetedCard]}>
      <PublicEntityMediaImage
        contentFit="cover"
        entityId={product.id}
        entityType="product"
        fallback={(
          <View style={styles.productIcon}>
            <Ionicons color={colors.accent} name="bag-handle-outline" size={26} />
          </View>
        )}
        mediaRole="product_image"
        style={styles.productImage}
        variant="thumbnail"
      />
      <View style={styles.productText}>
        <Text style={styles.productCategory}>{product.category}</Text>
        <Text style={styles.productTitle}>{product.title}</Text>
        <Text style={styles.productDescription}>{product.description}</Text>
      </View>
      <View style={styles.productTrailing}>
        <Text style={styles.productPrice}>{product.price}</Text>
        <ShareButton accessibilityLabel={`Compartilhar produto ${product.title}`} noMargin onPress={() => void shareLiberRotasItem({
          kind: "product",
          title: product.title,
          description: `${product.price} · ${product.description}`,
          path: profileSharePath(product.ownerId, { tab: "products", itemId: product.id }),
        })} />
      </View>
    </View>
  );
}

function OfferCard({
  busyAction,
  highlighted,
  item,
  metrics,
  nowMs,
  onDelete,
  onGenerateQr,
  onQuantityChange,
  onToggleBundle,
  quantityText,
  selectedForBundle,
}: {
  busyAction: string;
  highlighted: boolean;
  item: ProfileOfferItem;
  metrics: OwnerOfferMetrics | null;
  nowMs: number;
  onDelete: (() => void) | null;
  onGenerateQr: ((quantity: number) => void) | null;
  onQuantityChange: ((value: string) => void) | null;
  onToggleBundle: (() => void) | null;
  quantityText: string;
  selectedForBundle: boolean;
}) {
  const { offer, product } = item;
  const isBusy = Boolean(busyAction);
  const qrAvailable = metrics?.offer
    ? (metrics.offer.status === "ACTIVE" || metrics.offer.status === "PAUSED")
      && !hasTimeEnded(metrics.offer.expires_at * 1000, nowMs)
      && metrics.offer.remaining_redemptions > 0
      && metrics.stockQuantity > 0
    : false;
  const bundleAvailable = metrics?.offer
    ? metrics.offer.status === "ACTIVE"
      && !hasTimeEnded(metrics.offer.expires_at * 1000, nowMs)
      && metrics.offer.remaining_redemptions > 0
      && metrics.stockQuantity > 0
    : false;
  const bundleSelectionDisabled = isBusy || (!bundleAvailable && !selectedForBundle);
  const maximumQuantity = Math.max(
    1,
    Math.min(metrics?.offer?.remaining_redemptions ?? 1, metrics?.stockQuantity ?? 1),
  );
  const parsedQuantity = Number.parseInt(quantityText, 10);
  const quantity = Number.isInteger(parsedQuantity)
    ? Math.max(1, Math.min(parsedQuantity, maximumQuantity))
    : 1;
  function updateQuantity(next: number) {
    onQuantityChange?.(String(Math.max(1, Math.min(next, maximumQuantity))));
  }
  return (
    <View style={[styles.offerCard, highlighted && styles.targetedCard]}>
      <View style={styles.offerIcon}>
        <Ionicons color={colors.surface} name="pricetag" size={22} />
      </View>
      <View style={styles.offerText}>
        <Text style={[styles.offerStatus, offer.status === "ENDED" && styles.offerStatusInactive]}>{profileOfferStatus(offer)}</Text>
        <Text style={styles.offerTitle}>{product.title}</Text>
        <View style={styles.offerPriceRow}>
          <Text style={styles.offerOriginalPrice}>{formatMoney(offer.original_amount_minor, offer.currency)}</Text>
          <Text style={styles.offerFinalPrice}>{formatMoney(offer.final_amount_minor, offer.currency)}</Text>
        </View>
        <Text style={styles.offerMeta}>
          Economize {formatMoney(offer.discount_amount_minor, offer.currency)} · {offer.remaining_redemptions} disponível(is)
        </Text>
        <Text style={styles.offerMeta}>{profileOfferReason(offer)}</Text>
        <Text style={styles.offerMeta}>
          {offer.ended_at ? `Encerrada em ${formatExpiration(offer.ended_at)}` : `Válida até ${formatExpiration(offer.expires_at)}`}
        </Text>
        <ShareButton accessibilityLabel={`Compartilhar oferta ${product.title}`} onPress={() => void shareLiberRotasItem({
          kind: "offer",
          title: product.title,
          description: `${formatMoney(offer.final_amount_minor, offer.currency)} · ${profileOfferReason(offer)}`,
          path: profileSharePath(product.merchant.firebase_uid, { tab: "offers", itemId: offer.offer_id }),
        })} />
        {metrics ? (
          <>
            <Pressable
              accessibilityLabel={`${selectedForBundle ? "Remover" : "Incluir"} ${product.title} no QR único`}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: selectedForBundle, disabled: bundleSelectionDisabled }}
              disabled={bundleSelectionDisabled}
              onPress={onToggleBundle || undefined}
              style={[
                styles.offerBundleSelection,
                selectedForBundle && styles.offerBundleSelectionActive,
                bundleSelectionDisabled && styles.offerActionDisabled,
              ]}
            >
              <Ionicons
                color={selectedForBundle ? colors.surface : colors.primary}
                name={selectedForBundle ? "checkbox" : "square-outline"}
                size={20}
              />
              <View style={styles.offerBundleSelectionText}>
                <Text style={[
                  styles.offerBundleSelectionTitle,
                  selectedForBundle && styles.offerBundleSelectionTitleActive,
                ]}>
                  Selecionar para QR único
                </Text>
                {!bundleAvailable ? (
                  <Text style={styles.offerBundleSelectionHint}>Disponível somente para oferta ativa com estoque.</Text>
                ) : null}
              </View>
            </Pressable>
            <View style={styles.offerMetrics}>
              <View style={styles.offerMetric}>
                <Text style={styles.offerMetricValue}>{metrics.offer?.redeemed_count ?? 0}</Text>
                <Text style={styles.offerMetricLabel}>VENDIDOS</Text>
              </View>
              <View style={styles.offerMetric}>
                <Text style={styles.offerMetricValue}>{metrics.stockQuantity}</Text>
                <Text style={styles.offerMetricLabel}>ESTOQUE</Text>
              </View>
              <View style={styles.offerMetric}>
                <Text style={styles.offerMetricValue}>
                  {formatOfferTime(metrics.offer?.expires_at ?? offer.expires_at, nowMs)}
                </Text>
                <Text style={styles.offerMetricLabel}>TEMPO</Text>
              </View>
              <View style={styles.offerMetric}>
                <Text style={styles.offerMetricValue}>
                  {metrics.fundedEventCount > 0
                    ? formatMoney(metrics.amountDueMinor, offer.currency)
                    : "Sem verba"}
                </Text>
                <Text style={styles.offerMetricLabel}>INSTITUIÇÃO DEVE</Text>
              </View>
            </View>
            <Text style={styles.offerFinanceHint}>
              {metrics.fundedEventCount > 0
                ? `Repasse calculado para este produto em ${metrics.fundedEventCount} evento(s) institucional(is).`
                : "Este produto ainda não possui repasse em evento institucional."}
            </Text>
            <View style={styles.offerOwnerActions}>
              <View style={[styles.offerQuantityControl, (isBusy || !qrAvailable) && styles.offerActionDisabled]}>
                <Pressable
                  accessibilityLabel={`Diminuir quantidade de ${product.title}`}
                  disabled={isBusy || !qrAvailable || quantity <= 1}
                  onPress={() => updateQuantity(quantity - 1)}
                  style={styles.offerQuantityStep}
                >
                  <Ionicons color={colors.primary} name="chevron-down" size={17} />
                </Pressable>
                <TextInput
                  accessibilityLabel={`Quantidade de ${product.title}`}
                  editable={!isBusy && qrAvailable}
                  inputMode="numeric"
                  keyboardType="number-pad"
                  maxLength={4}
                  onBlur={() => updateQuantity(quantity)}
                  onChangeText={(value) => onQuantityChange?.(value.replace(/\D/g, ""))}
                  selectTextOnFocus
                  style={styles.offerQuantityInput}
                  value={quantityText}
                />
                <Pressable
                  accessibilityLabel={`Aumentar quantidade de ${product.title}`}
                  disabled={isBusy || !qrAvailable || quantity >= maximumQuantity}
                  onPress={() => updateQuantity(quantity + 1)}
                  style={styles.offerQuantityStep}
                >
                  <Ionicons color={colors.primary} name="chevron-up" size={17} />
                </Pressable>
              </View>
              <Pressable
                accessibilityLabel={`Gerar QR Code da oferta ${product.title}`}
                accessibilityRole="button"
                disabled={isBusy || !qrAvailable}
                onPress={onGenerateQr ? () => onGenerateQr(quantity) : undefined}
                style={[styles.offerQrButton, (isBusy || !qrAvailable) && styles.offerActionDisabled]}
              >
                <Ionicons color={colors.surface} name="qr-code-outline" size={17} />
                <Text style={styles.offerQrButtonText}>
                  {busyAction === "qr" ? "Gerando..." : qrAvailable ? "Gerar QR Code" : "QR indisponível"}
                </Text>
              </Pressable>
              <Pressable
                accessibilityLabel={`Excluir oferta ${product.title}`}
                accessibilityRole="button"
                disabled={isBusy}
                onPress={onDelete || undefined}
                style={[styles.offerDeleteButton, isBusy && styles.offerActionDisabled]}
              >
                <Ionicons color={colors.danger} name="trash-outline" size={17} />
                <Text style={styles.offerDeleteButtonText}>{busyAction === "delete" ? "Excluindo..." : "Excluir"}</Text>
              </Pressable>
            </View>
          </>
        ) : null}
      </View>
    </View>
  );
}

function LocalPostCard({ highlighted, post }: { highlighted: boolean; post: FeedPost }) {
  const [commentsOpen, setCommentsOpen] = useState(false);
  return (
    <View style={[styles.postCard, highlighted && styles.targetedCard]}>
      {post.media?.type === "image" ? (
        <ProtectedMediaImage
          contentFit="contain"
          expandable
          legacyUri={post.media.uri}
          mediaId={post.media.mediaId}
          publicVariant="display"
          style={styles.postMedia}
        />
      ) : null}
      {post.media?.type === "video" && post.media.uri ? <ProfileVideo uri={post.media.uri} /> : null}
      <View style={styles.postBody}>
        <Text style={styles.postDate}>{new Date(post.createdAt).toLocaleString("pt-BR")}</Text>
      <Text style={styles.postText}>{post.text}</Text>
      <PostOwnerActions post={post} />
        <Pressable onPress={() => setCommentsOpen((current) => !current)} style={styles.commentsToggle}>
          <Ionicons color={colors.primary} name={commentsOpen ? "chatbubble" : "chatbubble-outline"} size={16} />
          <Text style={styles.commentsToggleText}>{commentsOpen ? "Ocultar comentários" : "Ver comentários"}</Text>
        </Pressable>
        <ShareButton accessibilityLabel={`Compartilhar publicação de ${post.author}`} onPress={() => void shareLiberRotasItem({
          kind: "post",
          title: `Publicação de ${post.author}`,
          description: post.text,
          path: profileSharePath(post.authorId, { tab: "posts", itemId: post.id }),
        })} />
        <PostComments
          expanded={commentsOpen}
          onOpenProfile={(targetProfileId) => router.push(`/profile/${encodeURIComponent(targetProfileId)}` as Href)}
          postId={post.id}
        />
      </View>
    </View>
  );
}

function DemoPostCard({ highlighted, post }: { highlighted: boolean; post: DemoMarketPost }) {
  return (
    <View style={[styles.postCard, highlighted && styles.targetedCard]}>
      {post.imageKind === "photo" ? (
        <Image contentFit="cover" source={require("../../../assets/images/feed-feira.png")} style={styles.postMedia} />
      ) : (
        <View style={styles.placeholder}>
          <Ionicons color={colors.accent} name="color-palette-outline" size={56} />
        </View>
      )}
      <View style={styles.postBody}>
        <Text style={styles.postDate}>{post.date}</Text>
        <Text style={styles.postText}>{post.title}</Text>
        <Text style={styles.meta}>{post.city}</Text>
        <ShareButton accessibilityLabel={`Compartilhar publicação ${post.title}`} onPress={() => void shareLiberRotasItem({
          kind: "post",
          title: post.title,
          description: `${post.city} · ${post.date}`,
          path: profileSharePath(post.authorId, { tab: "posts", itemId: post.id }),
        })} />
      </View>
    </View>
  );
}

function ProfileLiveFairCard({
  fair,
  highlighted,
  isDeleting,
  onDelete,
}: {
  fair: LiveFair;
  highlighted: boolean;
  isDeleting: boolean;
  onDelete: (() => void) | null;
}) {
  const statusStyle = fair.status === "live"
    ? styles.fairStatusLive
    : fair.status === "scheduled"
      ? styles.fairStatusScheduled
      : styles.fairStatusEnded;
  const finalTimestamp = fair.endedAtMs ?? fair.endsAtMs;

  return (
    <View style={[styles.fairCard, highlighted && styles.targetedCard]}>
      <PublicEntityMediaImage
        contentFit="cover"
        entityId={fair.id}
        entityType="fair"
        fallback={null}
        mediaRole="fair_cover"
        style={styles.fairCover}
        variant="display"
      />
      <View style={styles.fairHeader}>
        <View style={styles.fairHeaderText}>
          <Text style={[styles.fairStatus, statusStyle]}>{getFairStatusLabel(fair)}</Text>
          <Text style={styles.fairName}>{fair.name}</Text>
        </View>
        <Ionicons color={fair.status === "live" ? colors.accent : colors.primary} name="radio-outline" size={25} />
      </View>

      <View style={styles.fairInfoRow}>
        <Ionicons color={colors.primary} name="location-outline" size={17} />
        <Text style={styles.fairInfoText}>{fair.address}</Text>
      </View>
      <View style={styles.fairInfoRow}>
        <Ionicons color={colors.primary} name="calendar-outline" size={17} />
        <Text style={styles.fairInfoText}>Início: {formatFairDateTime(fair.startsAtMs)}</Text>
      </View>
      <View style={styles.fairInfoRow}>
        <Ionicons color={colors.primary} name="time-outline" size={17} />
        <Text style={styles.fairInfoText}>
          {fair.status === "ended" ? "Encerrada" : "Término previsto"}: {formatFairDateTime(finalTimestamp)}
        </Text>
      </View>

      {fair.status === "ended" ? (
        <View style={styles.fairEndBox}>
          <Ionicons color={colors.textMuted} name="checkmark-circle-outline" size={18} />
          <Text style={styles.fairEndText}>
            {fair.endReason === "manual"
              ? "Encerrada antecipadamente pelo empreendedor."
              : "Encerrada automaticamente ao atingir o horário final."}
          </Text>
        </View>
      ) : null}

      <View style={styles.fairActions}>
        <Pressable accessibilityRole="button" onPress={() => openFairInMaps(fair)} style={styles.fairMapButton}>
          <Ionicons color={colors.surface} name="navigate-outline" size={17} />
          <Text style={styles.fairMapButtonText}>Abrir no Maps</Text>
        </Pressable>
        <ShareButton accessibilityLabel={`Compartilhar feira ${fair.name}`} noMargin onPress={() => void shareLiberRotasItem({
          kind: "fair",
          title: fair.name,
          description: `${fair.address} · Início: ${formatFairDateTime(fair.startsAtMs)}`,
          path: profileSharePath(fair.ownerId, { tab: "fairs", itemId: fair.id }),
        })} />
        {onDelete ? (
          <Pressable
            accessibilityLabel={`Excluir feira ${fair.name}`}
            accessibilityRole="button"
            disabled={isDeleting}
            onPress={onDelete}
            style={[styles.fairDeleteButton, isDeleting && styles.offerActionDisabled]}
          >
            <Ionicons color={colors.danger} name="trash-outline" size={17} />
            <Text style={styles.fairDeleteButtonText}>{isDeleting ? "Excluindo..." : "Excluir feira"}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

/**
 * Perfil público composto por fontes independentes.
 *
 * O Firebase fornece identidade social, publicações e feiras. O backend
 * TRQ-BEC fornece exclusivamente o catálogo comercial autoritativo. Uma falha
 * em uma fonte não apaga os dados válidos recebidos da outra.
 */
export default function PublicProfileScreen() {
  const {
    accessDestination,
    accessSession,
    deviceApprovalRequired,
    hasFirebaseSession,
    hasPermission,
    isAuthenticated,
    isHydrated,
    isResolvingAccess,
    profile,
    refreshUnreadMessageCount,
    userPosts,
  } = useApp();
  const { nowMs } = useTrustedClock();
  const routeParams = useLocalSearchParams<{
    fair?: string | string[];
    item?: string | string[];
    offer?: string | string[];
    post?: string | string[];
    product?: string | string[];
    profileId: string | string[];
    tab?: string | string[];
  }>();
  const [tabSelection, setTabSelection] = useState<{ routeTargetKey: string; tab: ProfileTab } | null>(null);
  const [profileLoad, setProfileLoad] = useState<ProfileLoadState | null>(null);
  const [catalogLoad, setCatalogLoad] = useState<CatalogLoadState | null>(null);
  const [liveFairsLoad, setLiveFairsLoad] = useState<LiveFairsLoadState | null>(null);
  const [ownerOfferLoad, setOwnerOfferLoad] = useState<OwnerOfferLoadState | null>(null);
  const [fairPendingDelete, setFairPendingDelete] = useState<LiveFair | null>(null);
  const [deletingFairId, setDeletingFairId] = useState("");
  const [offerAction, setOfferAction] = useState<{ kind: "delete" | "qr" | "qr-bundle"; offerId: string } | null>(null);
  const [offerPendingDelete, setOfferPendingDelete] = useState<ProfileOfferItem | null>(null);
  const [selectedBundleOfferIds, setSelectedBundleOfferIds] = useState<string[]>([]);
  const [offerQuantityTexts, setOfferQuantityTexts] = useState<Record<string, string>>({});
  const [qrResult, setQrResult] = useState<CouponQrGroupResult | null>(null);
  const [isOfferReportVisible, setIsOfferReportVisible] = useState(false);
  const [isMessageModalVisible, setIsMessageModalVisible] = useState(false);
  const [messageText, setMessageText] = useState("");
  const [messageError, setMessageError] = useState("");
  const [messageConversationId, setMessageConversationId] = useState("");
  const [messageClientId, setMessageClientId] = useState("");
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [isAvatarViewerVisible, setIsAvatarViewerVisible] = useState(false);
  const profileId = firstRouteParam(routeParams.profileId);
  const currentUid = auth.currentUser?.uid || "";
  const explicitTab = normalizeProfileTab(firstRouteParam(routeParams.tab));
  const legacyTarget = explicitTab
    ? null
    : firstRouteParam(routeParams.product)
      ? { itemId: firstRouteParam(routeParams.product), tab: "products" as const }
      : firstRouteParam(routeParams.offer)
        ? { itemId: firstRouteParam(routeParams.offer), tab: "offers" as const }
        : firstRouteParam(routeParams.post)
          ? { itemId: firstRouteParam(routeParams.post), tab: "posts" as const }
          : firstRouteParam(routeParams.fair)
            ? { itemId: firstRouteParam(routeParams.fair), tab: "fairs" as const }
            : null;
  const requestedTab = explicitTab || legacyTarget?.tab || "posts";
  const rawTargetItemId = explicitTab ? firstRouteParam(routeParams.item) : legacyTarget?.itemId || "";
  const targetItemId = rawTargetItemId.length <= 256 && !/[\u0000-\u001f\u007f]/.test(rawTargetItemId) ? rawTargetItemId : "";
  const routeTargetKey = `${profileId}|${requestedTab}|${targetItemId}`;
  const activeTab = tabSelection?.routeTargetKey === routeTargetKey ? tabSelection.tab : requestedTab;
  const isPublicAccess = isAuthenticated
    && (
      accessSession?.role === "entrepreneur"
      || accessSession?.role === "visitor"
      || accessSession?.role === "institution"
    )
    && (accessSession.role === "visitor" || !deviceApprovalRequired)
    && hasPermission(`${accessSession.role}.panel.access`);
  const canSendPrivateMessage = hasPermission("messaging.use");
  const canManageOwnOffers = isPublicAccess
    && accessSession?.role === "entrepreneur"
    && profileId === currentUid
    && hasPermission("marketplace.manage");
  const canDeleteOwnFairs = isPublicAccess
    && (accessSession?.role === "entrepreneur" || accessSession?.role === "institution")
    && profileId === currentUid
    && hasPermission("locations.publish");
  const canReadFundedReports = canManageOwnOffers
    && hasPermission("institution.event_allocations.manage");
  const profileDestination = getAuthenticatedHomeDestination(accessSession?.role, accessDestination);

  useEffect(() => {
    if (!isHydrated || !isPublicAccess || !profileId) return undefined;

    let isActive = true;
    void (async () => {
      try {
        const directoryProfile = await loadPublicDirectoryProfile(profileId);
        if (isActive) {
          setProfileLoad({ profileId, profile: publicProfileFromDirectory(directoryProfile), error: "" });
        }
      } catch (directoryError) {
        try {
          const legacyProfile = await loadPublicProfile(profileId);
          if (isActive) {
            setProfileLoad({
              profileId,
              profile: legacyProfile ? publicProfileFromUser(legacyProfile) : null,
              error: legacyProfile ? "" : "Este perfil ainda não foi publicado no diretório.",
            });
          }
        } catch {
          if (!isActive) return;
          setProfileLoad({
            profileId,
            profile: null,
            error: directoryError instanceof Error ? directoryError.message : "Não foi possível carregar o perfil público.",
          });
        }
      }
    })();

    return () => {
      isActive = false;
    };
  }, [isHydrated, isPublicAccess, profileId]);

  useEffect(() => {
    if (!isHydrated || !canManageOwnOffers || !profileId) return undefined;

    let isActive = true;
    void (async () => {
      const offersResult = await Promise.allSettled([
        listOwnLiveOffers(),
        canReadFundedReports ? listEntrepreneurFundedEvents() : Promise.resolve([]),
      ]);
      const errors: string[] = [];
      const ownOffers = offersResult[0].status === "fulfilled" ? offersResult[0].value : [];
      if (offersResult[0].status === "rejected") {
        errors.push(
          offersResult[0].reason instanceof Error
            ? offersResult[0].reason.message
            : "Não foi possível carregar os dados privados das ofertas.",
        );
      }

      let fundedReports: EntrepreneurFundedEventReport[] = [];
      if (offersResult[1].status === "fulfilled" && offersResult[1].value.length > 0) {
        const reportResults = await Promise.allSettled(
          offersResult[1].value.map((event) => loadEntrepreneurFundedEventReport(event.event_id)),
        );
        fundedReports = reportResults.flatMap((result) => (
          result.status === "fulfilled" ? [result.value] : []
        ));
        if (reportResults.some((result) => result.status === "rejected")) {
          errors.push("Alguns repasses institucionais não puderam ser atualizados.");
        }
      } else if (offersResult[1].status === "rejected") {
        errors.push(
          offersResult[1].reason instanceof Error
            ? offersResult[1].reason.message
            : "Não foi possível carregar os repasses institucionais.",
        );
      }
      if (isActive) {
        setOwnerOfferLoad({
          profileId,
          offers: ownOffers,
          fundedReports,
          error: errors.join("\n"),
        });
      }
    })();

    return () => {
      isActive = false;
    };
  }, [canManageOwnOffers, canReadFundedReports, isHydrated, profileId]);

  useEffect(() => {
    if (!isHydrated || !isPublicAccess || !profileId) return undefined;

    let isActive = true;

    getPublicMerchantCatalog(profileId)
      .then((nextCatalog) => {
        if (isActive) setCatalogLoad({ profileId, catalog: nextCatalog, error: "", notFound: false });
      })
      .catch((error) => {
        if (!isActive) return;
        if (error instanceof TrqBecServiceError && error.code === "MERCHANT_PUBLIC_PROFILE_NOT_FOUND") {
          setCatalogLoad({ profileId, catalog: null, error: "", notFound: true });
          return;
        }
        setCatalogLoad({
          profileId,
          catalog: null,
          error: error instanceof Error ? error.message : "Não foi possível carregar o catálogo comercial.",
          notFound: false,
        });
      });

    return () => {
      isActive = false;
    };
  }, [isHydrated, isPublicAccess, profileId]);

  useEffect(() => {
    if (!isHydrated || !isPublicAccess || !profileId) return undefined;

    return subscribeToPublicLiveFairs(
      (fairs) => {
        setLiveFairsLoad({
          profileId,
          fairs: fairs.filter((fair) => fair.ownerId === profileId),
          error: "",
        });
      },
      (error) => {
        console.warn("Não foi possível carregar as feiras deste perfil.", error);
        setLiveFairsLoad({
          profileId,
          fairs: [],
          error: "Não foi possível carregar as feiras públicas deste perfil.",
        });
      },
    );
  }, [isHydrated, isPublicAccess, profileId]);

  useEffect(() => {
    if (!canManageOwnOffers || !profileId || !qrResult) return undefined;
    let isActive = true;
    let isChecking = false;
    const baseline = new Map(
      qrResult.offers.map((offer) => [offer.offer_id, offer.redeemed_count]),
    );

    const checkRedemption = async () => {
      if (!isActive || isChecking) return;
      isChecking = true;
      try {
        const currentOffers = await listOwnLiveOffers();
        if (!isActive) return;
        setOwnerOfferLoad((current) => (
          current?.profileId === profileId
            ? { ...current, offers: currentOffers }
            : current
        ));
        const wasUsed = currentOffers.some((offer) => {
          const previousCount = baseline.get(offer.offer_id);
          return previousCount !== undefined && offer.redeemed_count > previousCount;
        });
        if (!wasUsed) return;

        setQrResult((current) => current === qrResult ? null : current);
        setOfferQuantityTexts((current) => {
          const next = { ...current };
          qrResult.offers.forEach((offer) => {
            next[offer.offer_id] = "1";
          });
          return next;
        });
        getPublicMerchantCatalog(profileId)
          .then((catalog) => {
            setCatalogLoad({ profileId, catalog, error: "", notFound: false });
          })
          .catch(() => undefined);
      } catch {
        // Uma falha transitória não fecha o QR nem interrompe a próxima consulta.
      } finally {
        isChecking = false;
      }
    };

    void checkRedemption();
    const interval = setInterval(() => void checkRedemption(), 1_500);
    return () => {
      isActive = false;
      clearInterval(interval);
    };
  }, [canManageOwnOffers, profileId, qrResult]);

  const currentProfileLoad = profileLoad?.profileId === profileId ? profileLoad : null;
  const currentCatalogLoad = catalogLoad?.profileId === profileId ? catalogLoad : null;
  const currentLiveFairsLoad = liveFairsLoad?.profileId === profileId ? liveFairsLoad : null;
  const currentOwnerOfferLoad = ownerOfferLoad?.profileId === profileId ? ownerOfferLoad : null;
  const cloudProfile = currentProfileLoad?.profile || null;
  const merchantCatalog = currentCatalogLoad?.catalog || null;
  const isProfileLoading = currentProfileLoad === null;
  const isCatalogLoading = currentCatalogLoad === null;
  const profileError = currentProfileLoad?.error || "";
  const catalogError = currentCatalogLoad?.error || "";
  const catalogNotFound = currentCatalogLoad?.notFound || false;
  const liveFairs = prioritizeTarget(currentLiveFairsLoad?.fairs || [], targetItemId, (fair) => fair.id);
  const liveFairsError = currentLiveFairsLoad?.error || "";
  const isLiveFairsLoading = currentLiveFairsLoad === null;
  const isOwnerOfferLoading = canManageOwnOffers && currentOwnerOfferLoad === null;
  const ownerOfferError = currentOwnerOfferLoad?.error || "";
  const ownerOfferById = useMemo(
    () => new Map((currentOwnerOfferLoad?.offers || []).map((offer) => [offer.offer_id, offer])),
    [currentOwnerOfferLoad?.offers],
  );
  const institutionDueByProduct = useMemo(() => {
    const totals = new Map<string, { amountDueMinor: number; fundedEventCount: number }>();
    for (const report of currentOwnerOfferLoad?.fundedReports || []) {
      for (const product of report.products) {
        const current = totals.get(product.product_id) || { amountDueMinor: 0, fundedEventCount: 0 };
        totals.set(product.product_id, {
          amountDueMinor: current.amountDueMinor + product.amount_due_minor,
          fundedEventCount: current.fundedEventCount + 1,
        });
      }
    }
    return totals;
  }, [currentOwnerOfferLoad?.fundedReports]);

  function selectTab(tab: ProfileTab) {
    if (profileId) setTabSelection({ routeTargetKey, tab });
  }

  async function confirmFairDeletion() {
    if (!canDeleteOwnFairs || !fairPendingDelete || deletingFairId) return;
    const fairId = fairPendingDelete.id;
    setDeletingFairId(fairId);
    try {
      await deleteLiveFair(fairId);
      setLiveFairsLoad((current) => (
        current?.profileId === profileId
          ? { ...current, fairs: current.fairs.filter((fair) => fair.id !== fairId) }
          : current
      ));
      setFairPendingDelete(null);
      showStaffAlert(
        "Feira excluída",
        "A feira saiu do perfil e deixou de aparecer no mapa público.",
      );
    } catch (error) {
      showStaffAlert(
        "Feira não excluída",
        error instanceof Error ? error.message : "Não foi possível excluir esta feira.",
      );
    } finally {
      setDeletingFairId("");
    }
  }

  function openMessageComposer() {
    setMessageText("");
    setMessageError("");
    setMessageConversationId("");
    setMessageClientId("");
    setIsMessageModalVisible(true);
  }

  function closeMessageComposer() {
    if (isSendingMessage) return;
    setIsMessageModalVisible(false);
  }

  async function submitPrivateMessage() {
    if (!profileId || profileId === currentUid || isSendingMessage || !messageText.trim()) return;
    const clientId = messageClientId || createClientMessageId();
    setMessageClientId(clientId);
    setMessageError("");
    setIsSendingMessage(true);
    try {
      const result = await sendPrivateMessage({
        recipientUid: profileId,
        content: messageText,
        clientMessageId: clientId,
      });
      setMessageConversationId(result.conversation.conversation_id || result.message.conversation_id);
      setMessageText("");
      await refreshUnreadMessageCount();
    } catch (error) {
      setMessageError(error instanceof Error ? error.message : "Não foi possível enviar a mensagem.");
    } finally {
      setIsSendingMessage(false);
    }
  }

  function openSentConversation() {
    if (!messageConversationId) return;
    setIsMessageModalVisible(false);
    router.push(`/messages/${encodeURIComponent(messageConversationId)}` as Href);
  }

  async function refreshOwnOfferInventory() {
    const [offersResult, catalogResult] = await Promise.allSettled([
      listOwnLiveOffers(),
      getPublicMerchantCatalog(profileId),
    ]);
    if (offersResult.status === "fulfilled") {
      setOwnerOfferLoad((current) => (
        current?.profileId === profileId
          ? { ...current, offers: offersResult.value }
          : current
      ));
    }
    if (catalogResult.status === "fulfilled") {
      setCatalogLoad({
        profileId,
        catalog: catalogResult.value,
        error: "",
        notFound: false,
      });
    }
  }

  function setOfferQuantityText(offerId: string, value: string) {
    setOfferQuantityTexts((current) => ({ ...current, [offerId]: value }));
  }

  function normalizedOfferQuantity(item: ProfileOfferItem, requested?: number) {
    const privateOffer = ownerOfferById.get(item.offer.offer_id);
    const maximum = Math.max(
      1,
      Math.min(
        privateOffer?.remaining_redemptions ?? item.offer.remaining_redemptions,
        item.product.stock_quantity,
      ),
    );
    const raw = requested ?? Number.parseInt(offerQuantityTexts[item.offer.offer_id] || "1", 10);
    return Number.isInteger(raw) ? Math.max(1, Math.min(raw, maximum)) : 1;
  }

  async function generateOfferQr(item: ProfileOfferItem, requestedQuantity: number) {
    if (!canManageOwnOffers || offerAction) return;
    setOfferAction({ kind: "qr", offerId: item.offer.offer_id });
    try {
      const quantity = normalizedOfferQuantity(item, requestedQuantity);
      setOfferQuantityText(item.offer.offer_id, String(quantity));
      const result = await getOwnLiveOfferQr(item.offer.offer_id, quantity);
      setQrResult({
        qrValue: result.qrValue,
        expiresAt: result.expiresAt,
        offers: [result.offer],
      });
      await refreshOwnOfferInventory();
    } catch (error) {
      showStaffAlert(
        "QR não gerado",
        error instanceof Error ? error.message : "Não foi possível gerar o QR desta oferta.",
      );
    } finally {
      setOfferAction(null);
    }
  }

  function toggleBundleOffer(offerId: string) {
    if (offerAction) return;
    setSelectedBundleOfferIds((current) => {
      if (current.includes(offerId)) return current.filter((id) => id !== offerId);
      if (current.length >= MAX_COMBINED_COUPONS) {
        showStaffAlert(
          "Limite do QR único",
          `Selecione no máximo ${MAX_COMBINED_COUPONS} ofertas por QR para manter a leitura rápida e segura.`,
        );
        return current;
      }
      return [...current, offerId];
    });
  }

  async function generateCombinedOfferQr() {
    if (!canManageOwnOffers || offerAction) return;
    const offerIds = [...new Set(selectedBundleOfferIds)];
    if (offerIds.length < 2 || offerIds.length > MAX_COMBINED_COUPONS) {
      showStaffAlert(
        "Seleção incompleta",
        `Selecione entre 2 e ${MAX_COMBINED_COUPONS} ofertas ativas para gerar um QR único.`,
      );
      return;
    }
    setOfferAction({ kind: "qr-bundle", offerId: "bundle" });
    try {
      const results = await Promise.all(offerIds.map((offerId) => {
        const item = offers.find((candidate) => candidate.offer.offer_id === offerId);
        if (!item) throw new Error("Uma das ofertas selecionadas não está mais disponível.");
        return getOwnLiveOfferQr(offerId, normalizedOfferQuantity(item));
      }));
      setQrResult(createCombinedCouponQr(results));
      setSelectedBundleOfferIds([]);
      await refreshOwnOfferInventory();
    } catch (error) {
      showStaffAlert(
        "QR único não gerado",
        error instanceof Error ? error.message : "Não foi possível reunir as ofertas em um único QR.",
      );
    } finally {
      setOfferAction(null);
    }
  }

  async function confirmOfferDeletion() {
    if (!canManageOwnOffers || !offerPendingDelete || offerAction) return;
    const offerId = offerPendingDelete.offer.offer_id;
    setOfferAction({ kind: "delete", offerId });
    try {
      await deleteOwnLiveOffer(offerId);
      setCatalogLoad((current) => {
        if (current?.profileId !== profileId || !current.catalog) return current;
        return {
          ...current,
          catalog: {
            ...current.catalog,
            products: current.catalog.products.map((product) => ({
              ...product,
              offers: product.offers.filter((offer) => offer.offer_id !== offerId),
            })),
          },
        };
      });
      setOwnerOfferLoad((current) => (
        current?.profileId === profileId
          ? { ...current, offers: current.offers.filter((offer) => offer.offer_id !== offerId) }
          : current
      ));
      setSelectedBundleOfferIds((current) => current.filter((id) => id !== offerId));
      setOfferPendingDelete(null);
      setQrResult((current) => current?.offers.some((offer) => offer.offer_id === offerId) ? null : current);
      showStaffAlert(
        "Oferta excluída",
        "A oferta saiu da vitrine e do Feed, e o QR correspondente foi revogado.",
      );
    } catch (error) {
      showStaffAlert(
        "Oferta não excluída",
        error instanceof Error ? error.message : "Não foi possível excluir esta oferta.",
      );
    } finally {
      setOfferAction(null);
    }
  }

  const publicProfile = useMemo<PublicProfile | null>(() => {
    if (!profileId) return null;
    if (cloudProfile?.id === profileId) return cloudProfile;
    if (profile.id === profileId) return publicProfileFromUser(profile);

    const demoProfile = demoProfiles.find((item) => item.id === profileId);
    if (demoProfile) return demoProfile;

    if (merchantCatalog?.merchant.firebase_uid === profileId) {
      const merchant = merchantCatalog.merchant;
      return {
        id: merchant.firebase_uid,
        role: "entrepreneur",
        name: merchant.display_name,
        city: "Localidade não informada",
        category: merchant.establishment_name,
        bio: "Catálogo comercial ativo no LiberRotas.",
        initials: merchant.display_name.slice(0, 2).toUpperCase() || "LR",
        interests: [],
      };
    }

    const postAuthor = userPosts.find((post) => post.authorId === profileId);
    if (!postAuthor) return null;
    return {
      id: postAuthor.authorId,
      role: postAuthor.authorRole,
      name: postAuthor.author,
      city: postAuthor.authorCity || "Cidade não informada",
      category: postAuthor.authorCategory || (postAuthor.authorRole === "entrepreneur" ? "Empreendedor LiberRotas" : "Visitante LiberRotas"),
      bio: "Perfil identificado pelas publicações desta comunidade.",
      initials: postAuthor.author.slice(0, 2).toUpperCase() || "LR",
      interests: [],
      avatarUri: getStablePublicAvatarUrl(postAuthor.authorId, postAuthor.authorAvatarUri),
    };
  }, [cloudProfile, merchantCatalog, profile, profileId, userPosts]);

  const localPosts = useMemo(() => userPosts.filter((post) => post.authorId === profileId), [profileId, userPosts]);
  const demoPosts = useMemo(() => marketPosts.filter((post) => post.authorId === profileId), [profileId]);
  const profilePosts: ProfilePostItem[] = prioritizeTarget(
    [
      ...localPosts.map((post) => ({ id: post.id, kind: "local" as const, post })),
      ...demoPosts.map((post) => ({ id: post.id, kind: "demo" as const, post })),
    ],
    targetItemId,
    (item) => item.id,
  );
  const isDemoProfile = useMemo(() => demoProfiles.some((item) => item.id === profileId), [profileId]);
  const productItems = merchantCatalog
    ? merchantCatalog.products.map(catalogProductToCard)
    : !isCatalogLoading && isDemoProfile
      ? demoProducts.filter((product) => product.ownerId === profileId)
      : [];
  const products = prioritizeTarget(productItems, targetItemId, (product) => product.id);
  const offers: ProfileOfferItem[] = prioritizeTarget(
    (merchantCatalog?.products || [])
      .flatMap((product) => product.offers.map((offer) => ({ offer, product })))
      .sort(
        (left, right) =>
          (right.offer.ended_at ?? right.offer.created_at) - (left.offer.ended_at ?? left.offer.created_at),
      ),
    targetItemId,
    (item) => item.offer.offer_id,
  );
  const fundedReports = currentOwnerOfferLoad?.fundedReports || [];
  const fundedReportTotals = fundedReports.reduce(
    (totals, report) => ({
      amountDueMinor: totals.amountDueMinor + report.amount_due_minor,
      confirmedRedemptions: totals.confirmedRedemptions + report.confirmed_redemptions,
    }),
    { amountDueMinor: 0, confirmedRedemptions: 0 },
  );
  function ownerMetricsFor(item: ProfileOfferItem): OwnerOfferMetrics | null {
    if (!canManageOwnOffers) return null;
    const institutional = institutionDueByProduct.get(item.product.product_id);
    return {
      amountDueMinor: institutional?.amountDueMinor || 0,
      fundedEventCount: institutional?.fundedEventCount || 0,
      offer: ownerOfferById.get(item.offer.offer_id) || null,
      stockQuantity: item.product.stock_quantity,
    };
  }
  const profileReturnTo = profileId
    ? profileSharePath(profileId, targetItemId ? { tab: requestedTab, itemId: targetItemId } : null)
    : null;
  const loginHref: Href = profileReturnTo
    ? ({ pathname: "/login", params: { returnTo: profileReturnTo } } as unknown as Href)
    : ("/login" as Href);

  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (!hasFirebaseSession) return <Redirect href={loginHref} />;
  if (!isAuthenticated || accessSession?.access_state !== "AUTHORIZED") {
    return <Redirect href={"/access-pending" as Href} />;
  }
  if (deviceApprovalRequired && accessSession.role !== "visitor") {
    return <Redirect href={"/account/devices" as Href} />;
  }
  if (!isPublicAccess) return <Redirect href={accessDestination as Href} />;
  if (!profileId) return <ProfileNotFound message="O identificador do perfil não foi informado." />;
  if (!publicProfile && (isProfileLoading || isCatalogLoading)) return <LoadingScreen />;
  if (!publicProfile) {
    return <ProfileNotFound message={profileError || catalogError || "Não foi possível localizar este perfil."} />;
  }

  const isEntrepreneur = publicProfile.role === "entrepreneur" || Boolean(merchantCatalog);
  const isInstitution = publicProfile.role === "institution";
  const visibleTab: ProfileTab = isInstitution ? "fairs" : activeTab;

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <View style={styles.header}>
        <HeaderBackButton fallbackHref={profileDestination} />
        <Pressable
          accessibilityLabel="Abrir meu perfil"
          onPress={() => router.replace(profileDestination)}
          style={styles.backButton}
        >
          <Ionicons color={colors.primaryDark} name="person-circle-outline" size={21} />
          <Text style={styles.backButtonText}>Perfil</Text>
        </Pressable>
        <View style={styles.headerText}>
          <Text style={styles.headerTitle}>Vitrine</Text>
          <Text style={styles.headerSubtitle}>{isEntrepreneur ? "empreendedor" : isInstitution ? "instituição" : "visitante"}</Text>
        </View>
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={[styles.cover, !isEntrepreneur && styles.visitorCover]}>
          <Pressable
            accessibilityHint="Abre a foto em tamanho maior com controles de zoom"
            accessibilityLabel={`Ampliar foto de perfil de ${publicProfile.name}`}
            accessibilityRole="imagebutton"
            disabled={!publicProfile.avatarUri}
            onPress={() => setIsAvatarViewerVisible(true)}
            style={[styles.avatar, { backgroundColor: publicProfile.avatarColor || colors.cream }]}
          >
            {isInstitution ? (
              <PublicEntityMediaImage
                contentFit="cover"
                entityId={publicProfile.id}
                entityType="institution"
                fallback={<Text style={styles.avatarText}>{publicProfile.initials}</Text>}
                mediaRole="institution_logo"
                style={styles.avatarImage}
                variant="thumbnail"
              />
            ) : publicProfile.avatarUri ? (
              <Image contentFit="cover" source={{ uri: publicProfile.avatarUri }} style={styles.avatarImage} />
            ) : (
              <Text style={styles.avatarText}>{publicProfile.initials}</Text>
            )}
          </Pressable>
        </View>

        <View style={styles.profileCard}>
          <Text style={styles.roleLabel}>{isEntrepreneur ? "EMPREENDEDOR" : isInstitution ? "INSTITUIÇÃO" : "VISITANTE"}</Text>
          <Text style={styles.name}>{publicProfile.name}</Text>
          <Text style={styles.meta}>{publicProfile.category} · {publicProfile.city}</Text>
          {isEntrepreneur && publicProfile.address ? (
            <View style={styles.addressRow}>
              <Ionicons color={colors.primary} name="location-outline" size={17} />
              <View style={styles.addressTextGroup}>
                <Text style={styles.addressLabel}>ENDEREÇO PÚBLICO</Text>
                <Text style={styles.addressText}>{publicProfile.address}</Text>
              </View>
            </View>
          ) : null}
          <Text style={styles.bio}>{publicProfile.bio}</Text>
          <View style={styles.interests}>
            {publicProfile.interests.map((interest) => (
              <View key={interest} style={styles.interestPill}>
                <Text style={styles.interestText}>{interest}</Text>
              </View>
            ))}
          </View>
          <View style={styles.profileActions}>
            {canSendPrivateMessage && profileId !== currentUid && !isDemoProfile ? (
              <Pressable accessibilityRole="button" onPress={openMessageComposer} style={styles.messageButton}>
                <Ionicons color={colors.surface} name="chatbubble-ellipses-outline" size={19} />
                <Text style={styles.messageButtonText}>Enviar mensagem</Text>
              </Pressable>
            ) : null}
            <ShareButton accessibilityLabel={`Compartilhar perfil ${publicProfile.name}`} noMargin onPress={() => void shareLiberRotasItem({
              kind: "profile",
              title: publicProfile.name,
              description: `${publicProfile.category} · ${publicProfile.city}`,
              path: profileSharePath(publicProfile.id),
            })} />
          </View>
        </View>

        {profileError ? <Text style={styles.inlineError}>O perfil social não pôde ser atualizado: {profileError}</Text> : null}

        {isEntrepreneur || isInstitution ? (
          <View style={styles.tabs}>
            {isEntrepreneur ? (
              <>
                <Pressable onPress={() => selectTab("posts")} style={[styles.tabButton, visibleTab === "posts" && styles.tabButtonActive]}>
                  <Text style={[styles.tabText, visibleTab === "posts" && styles.tabTextActive]}>Postagens</Text>
                </Pressable>
                <Pressable onPress={() => selectTab("products")} style={[styles.tabButton, visibleTab === "products" && styles.tabButtonActive]}>
                  <Text style={[styles.tabText, visibleTab === "products" && styles.tabTextActive]}>Produtos</Text>
                </Pressable>
                <Pressable onPress={() => selectTab("offers")} style={[styles.tabButton, visibleTab === "offers" && styles.tabButtonActive]}>
                  <Text style={[styles.tabText, visibleTab === "offers" && styles.tabTextActive]}>Ofertas</Text>
                </Pressable>
              </>
            ) : null}
            <Pressable onPress={() => selectTab("fairs")} style={[styles.tabButton, visibleTab === "fairs" && styles.tabButtonActive]}>
              <Text style={[styles.tabText, visibleTab === "fairs" && styles.tabTextActive]}>Feiras</Text>
            </Pressable>
          </View>
        ) : null}

        {visibleTab === "fairs" && (isEntrepreneur || isInstitution) ? (
          <View>
            <Text style={styles.sectionTitle}>Feiras deste perfil</Text>
            {isLiveFairsLoading ? <Text style={styles.statusText}>Carregando feiras...</Text> : null}
            {liveFairsError ? <Text style={styles.inlineError}>{liveFairsError}</Text> : null}
            {liveFairs.map((fair) => (
              <ProfileLiveFairCard
                fair={fair}
                highlighted={targetItemId === fair.id}
                isDeleting={deletingFairId === fair.id}
                key={fair.id}
                onDelete={canDeleteOwnFairs ? () => setFairPendingDelete(fair) : null}
              />
            ))}
            {!isLiveFairsLoading && !liveFairsError && liveFairs.length === 0 ? (
              <Text style={styles.empty}>Este perfil ainda não publicou feiras.</Text>
            ) : null}
          </View>
        ) : visibleTab === "products" && isEntrepreneur ? (
          <View>
            <Text style={styles.sectionTitle}>Produtos do comerciante</Text>
            {isCatalogLoading ? <Text style={styles.statusText}>Carregando catálogo comercial...</Text> : null}
            {catalogError ? <Text style={styles.inlineError}>{catalogError}</Text> : null}
            {products.map((product) => <ProductCard highlighted={targetItemId === product.id} key={product.id} product={product} />)}
            {!isCatalogLoading && products.length === 0 ? (
              <Text style={styles.empty}>{catalogNotFound ? "Este perfil não possui catálogo comercial ativo." : "Este empreendedor ainda não possui produtos públicos."}</Text>
            ) : null}
          </View>
        ) : visibleTab === "offers" && isEntrepreneur ? (
          <View>
            <View style={styles.offerSectionHeader}>
              <Text style={[styles.sectionTitle, styles.offerSectionTitle]}>Ofertas publicadas</Text>
              {canManageOwnOffers ? (
                <View style={styles.offerSectionActions}>
                  <Pressable
                    accessibilityLabel={`Gerar um QR Code com ${selectedBundleOfferIds.length} ofertas selecionadas`}
                    accessibilityRole="button"
                    disabled={selectedBundleOfferIds.length < 2 || Boolean(offerAction)}
                    onPress={() => void generateCombinedOfferQr()}
                    style={[
                      styles.offerBundleButton,
                      (selectedBundleOfferIds.length < 2 || offerAction) && styles.offerActionDisabled,
                    ]}
                  >
                    <Ionicons color={colors.surface} name="qr-code-outline" size={17} />
                    <Text style={styles.offerReportButtonText}>
                      {offerAction?.kind === "qr-bundle"
                        ? "Gerando..."
                        : `QR único (${selectedBundleOfferIds.length})`}
                    </Text>
                  </Pressable>
                  <Pressable
                    accessibilityLabel="Emitir relatório das ofertas"
                    accessibilityRole="button"
                    disabled={isOwnerOfferLoading}
                    onPress={() => setIsOfferReportVisible(true)}
                    style={[styles.offerReportButton, isOwnerOfferLoading && styles.offerActionDisabled]}
                  >
                    <Ionicons color={colors.surface} name="document-text-outline" size={17} />
                    <Text style={styles.offerReportButtonText}>
                      {isOwnerOfferLoading ? "Atualizando..." : "Emitir relatório"}
                    </Text>
                  </Pressable>
                </View>
              ) : null}
            </View>
            {isCatalogLoading ? <Text style={styles.statusText}>Carregando ofertas...</Text> : null}
            {isOwnerOfferLoading ? <Text style={styles.statusText}>Carregando vendas e repasses...</Text> : null}
            {catalogError ? <Text style={styles.inlineError}>{catalogError}</Text> : null}
            {ownerOfferError ? <Text style={styles.inlineError}>{ownerOfferError}</Text> : null}
            {offers.map((item) => (
              <OfferCard
                busyAction={offerAction?.kind === "qr-bundle"
                  ? offerAction.kind
                  : offerAction?.offerId === item.offer.offer_id
                    ? offerAction.kind
                    : ""}
                highlighted={targetItemId === item.offer.offer_id}
                item={item}
                key={item.offer.offer_id}
                metrics={ownerMetricsFor(item)}
                nowMs={nowMs}
                onDelete={canManageOwnOffers ? () => setOfferPendingDelete(item) : null}
                onGenerateQr={canManageOwnOffers ? (quantity) => void generateOfferQr(item, quantity) : null}
                onQuantityChange={canManageOwnOffers
                  ? (value) => setOfferQuantityText(item.offer.offer_id, value)
                  : null}
                onToggleBundle={canManageOwnOffers ? () => toggleBundleOffer(item.offer.offer_id) : null}
                quantityText={offerQuantityTexts[item.offer.offer_id] ?? "1"}
                selectedForBundle={selectedBundleOfferIds.includes(item.offer.offer_id)}
              />
            ))}
            {!isCatalogLoading && offers.length === 0 ? <Text style={styles.empty}>Este empreendedor ainda não emitiu ofertas públicas.</Text> : null}
          </View>
        ) : (
          <View>
            <Text style={styles.sectionTitle}>Postagens deste perfil</Text>
            {profilePosts.map((item) => item.kind === "local"
              ? <LocalPostCard highlighted={targetItemId === item.id} key={`local:${item.id}`} post={item.post} />
              : <DemoPostCard highlighted={targetItemId === item.id} key={`demo:${item.id}`} post={item.post} />)}
            {profilePosts.length === 0 ? <Text style={styles.empty}>Nenhuma postagem encontrada para este perfil.</Text> : null}
          </View>
        )}
      </ScrollView>
      <Modal
        animationType="fade"
        onRequestClose={() => {
          if (!deletingFairId) setFairPendingDelete(null);
        }}
        statusBarTranslucent
        transparent
        visible={fairPendingDelete !== null}
      >
        <View style={styles.offerModalBackdrop}>
          <View accessibilityViewIsModal style={styles.offerModalCard}>
            <View style={styles.offerModalIconDanger}>
              <Ionicons color={colors.surface} name="trash-outline" size={25} />
            </View>
            <Text style={styles.offerModalTitle}>Excluir esta feira?</Text>
            <Text style={styles.offerModalDescription}>
              {fairPendingDelete
                ? `${fairPendingDelete.name} será removida definitivamente do perfil e do mapa público.`
                : ""}
            </Text>
            <View style={styles.offerModalActions}>
              <Pressable
                disabled={Boolean(deletingFairId)}
                onPress={() => setFairPendingDelete(null)}
                style={styles.offerModalSecondaryButton}
              >
                <Text style={styles.offerModalSecondaryText}>Cancelar</Text>
              </Pressable>
              <Pressable
                disabled={Boolean(deletingFairId)}
                onPress={() => void confirmFairDeletion()}
                style={[styles.offerModalDangerButton, deletingFairId && styles.offerActionDisabled]}
              >
                <Text style={styles.offerModalPrimaryText}>
                  {deletingFairId ? "Excluindo..." : "Excluir feira"}
                </Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
      <Modal
        animationType="fade"
        onRequestClose={() => {
          if (!offerAction) setOfferPendingDelete(null);
        }}
        statusBarTranslucent
        transparent
        visible={offerPendingDelete !== null}
      >
        <View style={styles.offerModalBackdrop}>
          <View accessibilityViewIsModal style={styles.offerModalCard}>
            <View style={styles.offerModalIconDanger}>
              <Ionicons color={colors.surface} name="trash-outline" size={25} />
            </View>
            <Text style={styles.offerModalTitle}>Excluir esta oferta?</Text>
            <Text style={styles.offerModalDescription}>
              {offerPendingDelete
                ? `${offerPendingDelete.product.title} sairá da sua vitrine e do Feed. O QR será revogado, mas o histórico de auditoria continuará protegido.`
                : ""}
            </Text>
            <View style={styles.offerModalActions}>
              <Pressable
                disabled={Boolean(offerAction)}
                onPress={() => setOfferPendingDelete(null)}
                style={styles.offerModalSecondaryButton}
              >
                <Text style={styles.offerModalSecondaryText}>Cancelar</Text>
              </Pressable>
              <Pressable
                disabled={Boolean(offerAction)}
                onPress={() => void confirmOfferDeletion()}
                style={[styles.offerModalDangerButton, offerAction && styles.offerActionDisabled]}
              >
                <Text style={styles.offerModalPrimaryText}>
                  {offerAction?.kind === "delete" ? "Excluindo..." : "Excluir oferta"}
                </Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
      <Modal
        animationType="fade"
        onRequestClose={() => setQrResult(null)}
        statusBarTranslucent
        transparent
        visible={qrResult !== null}
      >
        <View style={styles.offerModalBackdrop}>
          <View accessibilityViewIsModal style={styles.qrModalCard}>
            <Text style={styles.qrModalEyebrow}>QR AUTORITATIVO TRQ-BEC</Text>
            <Text style={styles.offerModalTitle}>
              {qrResult?.offers.length === 1
                ? qrResult.offers[0].product_title
                : `${qrResult?.offers.length || 0} ofertas no mesmo QR`}
            </Text>
            {qrResult && !hasTimeEnded(qrResult.expiresAt * 1000, nowMs) ? (
              <View style={styles.qrSurface}>
                <QRCode
                  backgroundColor={colors.surface}
                  color={colors.primaryDark}
                  ecl="M"
                  quietZone={14}
                  size={230}
                  value={qrResult.qrValue}
                />
              </View>
            ) : (
              <Text style={styles.inlineError}>Este QR expirou. Emita uma nova oferta para gerar outro.</Text>
            )}
            {qrResult ? (
              <>
                <Text style={styles.qrModalCode}>
                  {qrResult.offers.length === 1
                    ? qrResult.offers[0].offer_id
                    : "UMA LEITURA · CUPONS VALIDADOS SEPARADAMENTE"}
                </Text>
                <Text style={styles.qrModalMeta}>
                  {formatOfferTime(qrResult.expiresAt, nowMs)}
                </Text>
                <View style={styles.qrOfferList}>
                  {qrResult.offers.map((offer, index) => (
                    <Text key={offer.offer_id} style={styles.qrOfferLine}>
                      {index + 1}. {offer.product_title} · compra de {offer.purchase_quantity || 1} unidade(s)
                    </Text>
                  ))}
                </View>
                <Text style={styles.qrModalMeta}>
                  O estoque será baixado somente depois da confirmação do visitante.
                </Text>
                {qrResult.offers.some((offer) => offer.status === "PAUSED") ? (
                  <Text style={styles.qrPausedWarning}>
                    Existe uma oferta pausada neste código. Reative-a antes da leitura para evitar resgate parcial.
                  </Text>
                ) : null}
              </>
            ) : null}
            <Pressable onPress={() => setQrResult(null)} style={styles.offerModalPrimaryButton}>
              <Text style={styles.offerModalPrimaryText}>Fechar QR Code</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
      <Modal
        animationType="fade"
        onRequestClose={() => setIsOfferReportVisible(false)}
        statusBarTranslucent
        transparent
        visible={isOfferReportVisible}
      >
        <View style={styles.offerModalBackdrop}>
          <View accessibilityViewIsModal style={styles.reportModalCard}>
            <View style={styles.reportModalHeader}>
              <View style={styles.offerModalIcon}>
                <Ionicons color={colors.surface} name="document-text-outline" size={25} />
              </View>
              <View style={styles.reportModalHeaderText}>
                <Text style={styles.offerModalTitle}>Relatório da vitrine</Text>
                <Text style={styles.offerModalDescription}>
                  Vendas, estoque, validade e repasses institucionais dos produtos ofertados.
                </Text>
              </View>
            </View>
            <ScrollView contentContainerStyle={styles.reportModalContent}>
              <View style={styles.reportSummary}>
                <View style={styles.reportSummaryItem}>
                  <Text style={styles.reportSummaryValue}>
                    {currentOwnerOfferLoad?.offers.reduce((sum, offer) => sum + offer.redeemed_count, 0) || 0}
                  </Text>
                  <Text style={styles.reportSummaryLabel}>VENDAS NAS OFERTAS</Text>
                </View>
                <View style={styles.reportSummaryItem}>
                  <Text style={styles.reportSummaryValue}>{fundedReportTotals.confirmedRedemptions}</Text>
                  <Text style={styles.reportSummaryLabel}>CUPONS INSTITUCIONAIS</Text>
                </View>
                <View style={styles.reportSummaryItem}>
                  <Text style={styles.reportSummaryValue}>
                    {formatMoney(fundedReportTotals.amountDueMinor, fundedReports[0]?.event.currency || "BRL")}
                  </Text>
                  <Text style={styles.reportSummaryLabel}>TOTAL A RECEBER</Text>
                </View>
              </View>
              {offers.map((item) => {
                const metrics = ownerMetricsFor(item);
                return (
                  <View key={`report-offer:${item.offer.offer_id}`} style={styles.reportRow}>
                    <Text style={styles.reportRowTitle}>{item.product.title}</Text>
                    <Text style={styles.reportRowMeta}>
                      Vendidos: {metrics?.offer?.redeemed_count ?? 0} · estoque: {item.product.stock_quantity} ·{" "}
                      tempo: {formatOfferTime(metrics?.offer?.expires_at ?? item.offer.expires_at, nowMs)}
                    </Text>
                    <Text style={styles.reportRowDue}>
                      Instituição deve pelo produto:{" "}
                      {metrics && metrics.fundedEventCount > 0
                        ? formatMoney(metrics.amountDueMinor, item.offer.currency)
                        : "sem verba institucional"}
                    </Text>
                  </View>
                );
              })}
              <Text style={styles.reportSectionTitle}>Eventos institucionais</Text>
              {fundedReports.length === 0 ? (
                <Text style={styles.reportEmpty}>Nenhum evento institucional foi vinculado a estes produtos.</Text>
              ) : fundedReports.map((report) => (
                <View key={report.event.event_id} style={styles.reportEventCard}>
                  <Text style={styles.reportRowTitle}>{report.event.name}</Text>
                  <Text style={styles.reportRowMeta}>
                    {report.event.institution_name} · {report.event.group_name}
                  </Text>
                  <Text style={styles.reportRowDue}>
                    A receber: {formatMoney(report.amount_due_minor, report.event.currency)}
                  </Text>
                  {report.products.map((product) => (
                    <Text key={product.product_id} style={styles.reportProductLine}>
                      {product.product_title}: {product.units_sold} vendido(s) ·{" "}
                      {formatMoney(product.amount_due_minor, report.event.currency)}
                    </Text>
                  ))}
                </View>
              ))}
              <Text style={styles.reportGeneratedAt}>
                Emitido em {new Date(nowMs).toLocaleString("pt-BR")}
              </Text>
              <Text style={styles.reportNotice}>
                O relatório informa valores calculados pelo backend e não executa nem comprova pagamentos.
              </Text>
            </ScrollView>
            <Pressable onPress={() => setIsOfferReportVisible(false)} style={styles.offerModalPrimaryButton}>
              <Text style={styles.offerModalPrimaryText}>Fechar relatório</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
      <Modal
        animationType="fade"
        onRequestClose={closeMessageComposer}
        statusBarTranslucent
        transparent
        visible={isMessageModalVisible}
      >
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.messageModalBackdrop}>
          <View accessibilityViewIsModal style={styles.messageModalCard}>
            <View style={styles.messageModalIcon}>
              <Ionicons color={colors.surface} name="chatbubbles-outline" size={25} />
            </View>
            <Text style={styles.messageModalTitle}>
              {messageConversationId ? "Mensagem enviada" : `Mensagem para ${publicProfile.name}`}
            </Text>
            {messageConversationId ? (
              <>
                <Text style={styles.messageModalDescription}>
                  A conversa foi criada na sua caixa de entrada. Somente os participantes podem acessar o conteúdo.
                </Text>
                <View style={styles.messageModalActions}>
                  <Pressable onPress={closeMessageComposer} style={styles.messageSecondaryButton}>
                    <Text style={styles.messageSecondaryText}>Fechar</Text>
                  </Pressable>
                  <Pressable onPress={openSentConversation} style={styles.messagePrimaryButton}>
                    <Text style={styles.messagePrimaryText}>Abrir conversa</Text>
                  </Pressable>
                </View>
              </>
            ) : (
              <>
                <Text style={styles.messageModalDescription}>
                  Seja respeitoso e não compartilhe senhas, códigos ou dados financeiros.
                </Text>
                <TextInput
                  editable={!isSendingMessage}
                  maxLength={2_000}
                  multiline
                  onChangeText={(value) => {
                    setMessageText(value);
                    setMessageError("");
                    setMessageClientId("");
                  }}
                  placeholder="Escreva sua mensagem..."
                  placeholderTextColor={colors.textMuted}
                  style={styles.messageInput}
                  textAlignVertical="top"
                  value={messageText}
                />
                <Text style={styles.messageCounter}>{messageText.length}/2000</Text>
                {messageError ? <Text style={styles.messageError}>{messageError}</Text> : null}
                <View style={styles.messageModalActions}>
                  <Pressable disabled={isSendingMessage} onPress={closeMessageComposer} style={styles.messageSecondaryButton}>
                    <Text style={styles.messageSecondaryText}>Cancelar</Text>
                  </Pressable>
                  <Pressable
                    disabled={isSendingMessage || !messageText.trim()}
                    onPress={submitPrivateMessage}
                    style={[styles.messagePrimaryButton, (isSendingMessage || !messageText.trim()) && styles.messageButtonDisabled]}
                  >
                    <Text style={styles.messagePrimaryText}>{isSendingMessage ? "Enviando..." : "Enviar"}</Text>
                  </Pressable>
                </View>
              </>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>
      <ImageViewerModal
        accessibilityLabel={`Foto de perfil de ${publicProfile.name}`}
        onClose={() => setIsAvatarViewerVisible(false)}
        uri={publicProfile.avatarUri}
        visible={isAvatarViewerVisible}
      />
    </SafeAreaView>
  );
}

function ProfileNotFound({ message }: { message: string }) {
  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <View style={styles.header}>
        <HeaderBackButton fallbackHref={"/(tabs)/perfil" as Href} />
        <Pressable
          accessibilityLabel="Abrir meu perfil"
          onPress={() => router.replace("/(tabs)/perfil" as Href)}
          style={styles.backButton}
        >
          <Ionicons color={colors.primaryDark} name="person-circle-outline" size={21} />
          <Text style={styles.backButtonText}>Perfil</Text>
        </Pressable>
        <Text style={[styles.headerTitle, styles.headerText]}>Perfil não encontrado</Text>
      </View>
      <Text style={styles.empty}>{message}</Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  header: { alignItems: "center", backgroundColor: colors.cream, flexDirection: "row", gap: 12, minHeight: 70, paddingHorizontal: 18 },
  backButton: { alignItems: "center", backgroundColor: colors.surface, borderRadius: 22, flexDirection: "row", gap: 5, minHeight: 44, paddingHorizontal: 10 },
  backButtonText: { color: colors.primaryDark, fontSize: 11, fontWeight: "900" },
  headerText: { flex: 1 },
  headerTitle: { color: colors.primary, fontSize: 18, fontWeight: "900" },
  headerSubtitle: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  content: { backgroundColor: colors.surfaceMuted, paddingBottom: 36 },
  cover: { alignItems: "center", backgroundColor: colors.accentSoft, height: 132, justifyContent: "flex-end" },
  visitorCover: { backgroundColor: colors.primary },
  avatar: { alignItems: "center", borderColor: colors.surface, borderRadius: 56, borderWidth: 8, bottom: -42, height: 112, justifyContent: "center", overflow: "hidden", position: "relative", width: 112 },
  avatarImage: { height: "100%", width: "100%" },
  avatarText: { color: colors.primaryDark, fontSize: 24, fontWeight: "900" },
  profileCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.large, borderWidth: 1, margin: 16, marginTop: 58, padding: 18, ...shadow },
  roleLabel: { color: colors.accent, fontSize: 11, fontWeight: "900", letterSpacing: 1 },
  name: { color: colors.primaryDark, fontSize: 26, fontWeight: "900", marginTop: 4 },
  meta: { color: colors.textMuted, fontSize: 12, marginTop: 5 },
  addressRow: { alignItems: "flex-start", backgroundColor: colors.cream, borderRadius: radius.medium, flexDirection: "row", gap: 8, marginTop: 12, padding: 11 },
  addressTextGroup: { flex: 1 },
  addressLabel: { color: colors.primary, fontSize: 9, fontWeight: "900", letterSpacing: 0.7 },
  addressText: { color: colors.text, fontSize: 12, lineHeight: 17, marginTop: 2 },
  bio: { color: colors.text, fontSize: 14, lineHeight: 20, marginTop: 12 },
  interests: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 14 },
  interestPill: { backgroundColor: colors.cream, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 7 },
  interestText: { color: colors.primary, fontSize: 11, fontWeight: "800" },
  messageButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.primary, borderRadius: radius.pill, flexDirection: "row", gap: 8, minHeight: 44, paddingHorizontal: 17 },
  messageButtonText: { color: colors.surface, fontSize: 12, fontWeight: "900" },
  profileActions: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 9, marginTop: 16 },
  shareButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.cream, borderColor: colors.border, borderRadius: radius.pill, borderWidth: 1, flexDirection: "row", gap: 6, marginTop: 10, minHeight: 40, paddingHorizontal: 13 },
  shareButtonNoMargin: { marginTop: 0 },
  shareButtonText: { color: colors.primary, fontSize: 11, fontWeight: "900" },
  targetedCard: { borderColor: colors.accent, borderWidth: 2 },
  tabs: { backgroundColor: colors.surface, borderRadius: radius.pill, flexDirection: "row", gap: 6, marginHorizontal: 16, marginBottom: 14, padding: 4 },
  tabButton: { alignItems: "center", borderRadius: radius.pill, flex: 1, paddingVertical: 10 },
  tabButtonActive: { backgroundColor: colors.primary },
  tabText: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  tabTextActive: { color: colors.surface },
  sectionTitle: { color: colors.primaryDark, fontSize: 18, fontWeight: "900", marginHorizontal: 16, marginBottom: 10 },
  statusText: { color: colors.textMuted, fontSize: 12, marginHorizontal: 16, marginBottom: 10 },
  inlineError: { color: colors.danger, fontSize: 12, lineHeight: 17, marginHorizontal: 16, marginBottom: 12 },
  fairCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.large, borderWidth: 1, gap: 9, marginHorizontal: 16, marginBottom: 14, padding: 16, ...shadow },
  fairCover: { backgroundColor: colors.cream, borderRadius: radius.medium, height: 180, width: "100%" },
  fairHeader: { alignItems: "flex-start", flexDirection: "row", gap: 12, justifyContent: "space-between" },
  fairHeaderText: { flex: 1 },
  fairStatus: { alignSelf: "flex-start", borderRadius: radius.pill, color: colors.surface, fontSize: 9, fontWeight: "900", letterSpacing: 0.8, overflow: "hidden", paddingHorizontal: 9, paddingVertical: 5 },
  fairStatusLive: { backgroundColor: colors.accent },
  fairStatusScheduled: { backgroundColor: colors.primary },
  fairStatusEnded: { backgroundColor: colors.textMuted },
  fairName: { color: colors.primaryDark, fontSize: 17, fontWeight: "900", marginTop: 7 },
  fairInfoRow: { alignItems: "flex-start", flexDirection: "row", gap: 8 },
  fairInfoText: { color: colors.text, flex: 1, fontSize: 12, lineHeight: 17 },
  fairEndBox: { alignItems: "flex-start", backgroundColor: colors.surfaceMuted, borderRadius: radius.medium, flexDirection: "row", gap: 8, marginTop: 3, padding: 10 },
  fairEndText: { color: colors.textMuted, flex: 1, fontSize: 11, lineHeight: 16 },
  fairMapButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.primary, borderRadius: radius.pill, flexDirection: "row", gap: 7, marginTop: 4, minHeight: 40, paddingHorizontal: 14 },
  fairMapButtonText: { color: colors.surface, fontSize: 12, fontWeight: "900" },
  fairActions: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 8 },
  fairDeleteButton: { alignItems: "center", borderColor: colors.danger, borderRadius: radius.pill, borderWidth: 1, flexDirection: "row", gap: 7, minHeight: 40, paddingHorizontal: 14 },
  fairDeleteButtonText: { color: colors.danger, fontSize: 12, fontWeight: "900" },
  postCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.large, borderWidth: 1, marginHorizontal: 16, marginBottom: 14, overflow: "hidden", ...shadow },
  postMedia: { backgroundColor: colors.text, height: 230, width: "100%" },
  placeholder: { alignItems: "center", backgroundColor: colors.cream, height: 190, justifyContent: "center" },
  postBody: { padding: 14 },
  postDate: { color: colors.textMuted, fontSize: 11 },
  postText: { color: colors.text, fontSize: 15, fontWeight: "700", lineHeight: 21, marginTop: 6 },
  commentsToggle: { alignItems: "center", alignSelf: "flex-start", flexDirection: "row", gap: 6, marginTop: 10, minHeight: 34, paddingHorizontal: 4 },
  commentsToggleText: { color: colors.primary, fontSize: 10, fontWeight: "900" },
  productCard: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 12, marginHorizontal: 16, marginBottom: 12, padding: 14 },
  productImage: { backgroundColor: colors.cream, borderRadius: 26, height: 52, width: 52 },
  productIcon: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 22, height: 44, justifyContent: "center", width: 44 },
  productText: { flex: 1 },
  productCategory: { color: colors.accent, fontSize: 10, fontWeight: "900", letterSpacing: 0.8 },
  productTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900", marginTop: 3 },
  productDescription: { color: colors.textMuted, fontSize: 12, lineHeight: 16, marginTop: 4 },
  productPrice: { color: colors.primary, fontSize: 13, fontWeight: "900" },
  productTrailing: { alignItems: "flex-end", gap: 2 },
  offerCard: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 12, marginHorizontal: 16, marginBottom: 12, padding: 14 },
  offerIcon: { alignItems: "center", backgroundColor: colors.accent, borderRadius: 22, height: 44, justifyContent: "center", width: 44 },
  offerText: { flex: 1 },
  offerStatus: { color: colors.success, fontSize: 9, fontWeight: "900", letterSpacing: 0.7, marginBottom: 3 },
  offerStatusInactive: { color: colors.textMuted },
  offerTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900" },
  offerPriceRow: { alignItems: "baseline", flexDirection: "row", gap: 8, marginTop: 8 },
  offerOriginalPrice: { color: colors.textMuted, fontSize: 11, textDecorationLine: "line-through" },
  offerFinalPrice: { color: colors.primary, fontSize: 16, fontWeight: "900" },
  offerMeta: { color: colors.textMuted, fontSize: 11, marginTop: 3 },
  offerMetrics: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 13 },
  offerMetric: { backgroundColor: colors.surfaceMuted, borderRadius: radius.small, flexGrow: 1, minWidth: 108, padding: 10 },
  offerMetricValue: { color: colors.primaryDark, fontSize: 12, fontWeight: "900" },
  offerMetricLabel: { color: colors.textMuted, fontSize: 8, fontWeight: "900", letterSpacing: 0.5, marginTop: 3 },
  offerFinanceHint: { color: colors.textMuted, fontSize: 9, lineHeight: 14, marginTop: 7 },
  offerBundleSelection: { alignItems: "center", backgroundColor: colors.surfaceMuted, borderColor: colors.border, borderRadius: radius.small, borderWidth: 1, flexDirection: "row", gap: 9, marginTop: 11, minHeight: 46, paddingHorizontal: 11, paddingVertical: 8 },
  offerBundleSelectionActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  offerBundleSelectionText: { flex: 1 },
  offerBundleSelectionTitle: { color: colors.primary, fontSize: 11, fontWeight: "900" },
  offerBundleSelectionTitleActive: { color: colors.surface },
  offerBundleSelectionHint: { color: colors.textMuted, fontSize: 9, lineHeight: 13, marginTop: 2 },
  offerOwnerActions: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 11 },
  offerQuantityControl: { alignItems: "center", backgroundColor: colors.surfaceMuted, borderColor: colors.border, borderRadius: radius.pill, borderWidth: 1, flexDirection: "row", minHeight: 42, overflow: "hidden" },
  offerQuantityStep: { alignItems: "center", height: 40, justifyContent: "center", width: 38 },
  offerQuantityInput: { color: colors.primaryDark, fontSize: 13, fontWeight: "900", minWidth: 44, paddingHorizontal: 4, paddingVertical: 0, textAlign: "center" },
  offerQrButton: { alignItems: "center", backgroundColor: colors.primary, borderRadius: radius.pill, flexDirection: "row", gap: 7, minHeight: 42, paddingHorizontal: 15 },
  offerQrButtonText: { color: colors.surface, fontSize: 11, fontWeight: "900" },
  offerDeleteButton: { alignItems: "center", borderColor: colors.danger, borderRadius: radius.pill, borderWidth: 1, flexDirection: "row", gap: 7, minHeight: 42, paddingHorizontal: 15 },
  offerDeleteButtonText: { color: colors.danger, fontSize: 11, fontWeight: "900" },
  offerActionDisabled: { opacity: 0.45 },
  offerSectionHeader: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "space-between", marginBottom: 10, paddingHorizontal: 16 },
  offerSectionActions: { alignItems: "center", flexDirection: "row", flexWrap: "wrap", gap: 8 },
  offerSectionTitle: { marginBottom: 0, marginHorizontal: 0 },
  offerBundleButton: { alignItems: "center", backgroundColor: colors.primary, borderRadius: radius.pill, flexDirection: "row", gap: 7, minHeight: 42, paddingHorizontal: 15 },
  offerReportButton: { alignItems: "center", backgroundColor: colors.success, borderRadius: radius.pill, flexDirection: "row", gap: 7, minHeight: 42, paddingHorizontal: 15 },
  offerReportButtonText: { color: colors.surface, fontSize: 11, fontWeight: "900" },
  offerModalBackdrop: { alignItems: "center", backgroundColor: "rgba(15, 46, 110, 0.55)", flex: 1, justifyContent: "center", padding: 20 },
  offerModalCard: { backgroundColor: colors.surface, borderRadius: radius.large, maxWidth: 520, padding: 22, width: "100%", ...shadow },
  offerModalIcon: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 25, height: 50, justifyContent: "center", width: 50 },
  offerModalIconDanger: { alignItems: "center", backgroundColor: colors.danger, borderRadius: 25, height: 50, justifyContent: "center", width: 50 },
  offerModalTitle: { color: colors.primaryDark, fontSize: 20, fontWeight: "900", marginTop: 12 },
  offerModalDescription: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 },
  offerModalActions: { flexDirection: "row", gap: 10, marginTop: 20 },
  offerModalSecondaryButton: { alignItems: "center", borderColor: colors.border, borderRadius: radius.pill, borderWidth: 1, flex: 1, padding: 12 },
  offerModalSecondaryText: { color: colors.primaryDark, fontSize: 12, fontWeight: "800" },
  offerModalPrimaryButton: { alignItems: "center", backgroundColor: colors.primary, borderRadius: radius.pill, marginTop: 18, padding: 13 },
  offerModalDangerButton: { alignItems: "center", backgroundColor: colors.danger, borderRadius: radius.pill, flex: 1, padding: 12 },
  offerModalPrimaryText: { color: colors.surface, fontSize: 12, fontWeight: "900" },
  qrModalCard: { alignItems: "center", backgroundColor: colors.surface, borderRadius: radius.large, maxWidth: 460, padding: 22, width: "100%", ...shadow },
  qrModalEyebrow: { color: colors.accent, fontSize: 9, fontWeight: "900", letterSpacing: 0.8 },
  qrSurface: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, marginTop: 16, padding: 8 },
  qrModalCode: { color: colors.primaryDark, fontSize: 10, fontWeight: "800", marginTop: 12 },
  qrModalMeta: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 5, textAlign: "center" },
  qrOfferList: { alignSelf: "stretch", backgroundColor: colors.surfaceMuted, borderRadius: radius.small, gap: 4, marginTop: 10, padding: 10 },
  qrOfferLine: { color: colors.primaryDark, fontSize: 10, fontWeight: "800", lineHeight: 15 },
  qrPausedWarning: { backgroundColor: colors.cream, borderRadius: radius.small, color: colors.primaryDark, fontSize: 10, lineHeight: 15, marginTop: 10, padding: 10, textAlign: "center" },
  reportModalCard: { backgroundColor: colors.surface, borderRadius: radius.large, maxHeight: "92%", maxWidth: 760, padding: 20, width: "100%", ...shadow },
  reportModalHeader: { alignItems: "center", flexDirection: "row", gap: 12 },
  reportModalHeaderText: { flex: 1 },
  reportModalContent: { gap: 10, paddingVertical: 16 },
  reportSummary: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  reportSummaryItem: { backgroundColor: colors.surfaceMuted, borderRadius: radius.small, flexGrow: 1, minWidth: 150, padding: 12 },
  reportSummaryValue: { color: colors.primaryDark, fontSize: 16, fontWeight: "900" },
  reportSummaryLabel: { color: colors.textMuted, fontSize: 8, fontWeight: "900", letterSpacing: 0.5, marginTop: 3 },
  reportRow: { borderBottomColor: colors.border, borderBottomWidth: 1, paddingVertical: 10 },
  reportRowTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: "900" },
  reportRowMeta: { color: colors.textMuted, fontSize: 10, lineHeight: 15, marginTop: 3 },
  reportRowDue: { color: colors.success, fontSize: 11, fontWeight: "900", marginTop: 5 },
  reportSectionTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900", marginTop: 8 },
  reportEmpty: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
  reportEventCard: { backgroundColor: colors.cream, borderRadius: radius.small, gap: 3, padding: 12 },
  reportProductLine: { color: colors.text, fontSize: 10, lineHeight: 15, marginTop: 3 },
  reportGeneratedAt: { color: colors.textMuted, fontSize: 9, marginTop: 8 },
  reportNotice: { color: colors.textMuted, fontSize: 9, fontStyle: "italic", lineHeight: 14 },
  empty: { color: colors.textMuted, padding: 24, textAlign: "center" },
  messageModalBackdrop: { alignItems: "center", backgroundColor: "rgba(15, 46, 110, 0.5)", flex: 1, justifyContent: "center", padding: 22 },
  messageModalCard: { backgroundColor: colors.surface, borderRadius: radius.large, maxWidth: 520, padding: 22, width: "100%", ...shadow },
  messageModalIcon: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 25, height: 50, justifyContent: "center", width: 50 },
  messageModalTitle: { color: colors.primaryDark, fontSize: 20, fontWeight: "900", marginTop: 14 },
  messageModalDescription: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 7 },
  messageInput: { backgroundColor: colors.surfaceMuted, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, color: colors.text, fontSize: 14, marginTop: 16, minHeight: 128, padding: 13 },
  messageCounter: { color: colors.textMuted, fontSize: 9, marginTop: 5, textAlign: "right" },
  messageError: { color: colors.danger, fontSize: 11, lineHeight: 16, marginTop: 8 },
  messageModalActions: { flexDirection: "row", gap: 10, marginTop: 18 },
  messageSecondaryButton: { alignItems: "center", borderColor: colors.border, borderRadius: radius.pill, borderWidth: 1, flex: 1, padding: 12 },
  messageSecondaryText: { color: colors.primaryDark, fontSize: 12, fontWeight: "800" },
  messagePrimaryButton: { alignItems: "center", backgroundColor: colors.accent, borderRadius: radius.pill, flex: 1, padding: 12 },
  messagePrimaryText: { color: colors.surface, fontSize: 12, fontWeight: "900" },
  messageButtonDisabled: { opacity: 0.45 },
});
