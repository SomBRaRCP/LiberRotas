import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import { router, type Href } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Alert, Linking, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import type { StyleProp, ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { BrandHeader } from "@/components/brand-header";
import { InteractivePlaceMap } from "@/components/interactive-place-map";
import { MediaImagePicker } from "@/components/media-image-picker";
import { PaginationControls } from "@/components/pagination-controls";
import { PublicEntityMediaImage } from "@/components/public-entity-media-image";
import { pinhaisCategoryIcons } from "@/constants/pinhais-icons";
import { colors, radius, shadow } from "@/constants/theme";
import { usePreferencesState, useProfileState, useSessionState } from "@/context/app-context";
import { useTrustedClock } from "@/context/trusted-clock-context";
import { marketPosts } from "@/data/demo";
import {
  PINHAIS_CENTER,
  resolveLiveFairStatus,
  pinhaisCategoryColors,
  pinhaisCategoryLabels,
  pinhaisPlaces,
  type LiveFair,
  type PinhaisCategory,
  type PinhaisPlace,
} from "@/data/pinhais";
import {
  subscribeToApprovedCuratedPlaces,
  subscribeToPublicLiveFairs,
} from "@/services/cloud-data";
import {
  deleteCuratedPlace,
  finishLiveFair as endLiveFairOnBackend,
  publishCuratedPlace,
  publishLiveFair as publishLiveFairOnBackend,
} from "@/security/trq-bec/service";
import { profileSharePath, shareLiberRotasItem } from "@/utils/share";
import { formatRemainingTime } from "@/utils/time";
import { uploadImage, type PreparedImageUpload } from "@/services/media-upload";
import { clampPage, HISTORY_PAGE_SIZE, paginateItems } from "@/utils/pagination";

const GOOGLE_MAPS_PINHAIS_URL = "https://www.google.com/maps/search/?api=1&query=Pinhais%20PR";

const manualCategoryOptions: PinhaisCategory[] = [
  "artesanato",
  "bordados",
  "feiras_livres",
  "gastronomia",
  "comercio_local",
];

function normalizeText(value: string) {
  return value
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

function matchesCategory(place: PinhaisPlace, category: PinhaisCategory | "todos") {
  if (category === "todos") return true;
  return place.categoriaApp === category || place.categoriasSecundarias?.includes(category);
}

function buildRouteUrl(place: PinhaisPlace) {
  return `https://www.google.com/maps/dir/?api=1&destination=${place.latitude},${place.longitude}&travelmode=driving`;
}

async function openExternalUrl(url: string) {
  try {
    await Linking.openURL(url);
  } catch {
    Alert.alert("Nao foi possivel abrir o mapa", "Tente novamente em alguns instantes.");
  }
}

function openOwnerProfile(profileId: string) {
  router.push({ pathname: "/profile/[profileId]", params: { profileId } } as unknown as Href);
}

function parseCoordinate(value: string) {
  const normalized = value.trim().replace(",", ".");
  return normalized ? Number(normalized) : Number.NaN;
}

function padDatePart(value: number) {
  return String(value).padStart(2, "0");
}

function formatDateTimeInput(timestamp: number) {
  const date = new Date(timestamp);
  return `${padDatePart(date.getDate())}/${padDatePart(date.getMonth() + 1)}/${date.getFullYear()} ${padDatePart(date.getHours())}:${padDatePart(date.getMinutes())}`;
}

function parseDateTimeInput(value: string) {
  const match = value.trim().match(/^(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})$/);
  if (!match) return Number.NaN;

  const [, dayText, monthText, yearText, hourText, minuteText] = match;
  const day = Number(dayText);
  const monthIndex = Number(monthText) - 1;
  const year = Number(yearText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const date = new Date(year, monthIndex, day, hour, minute, 0, 0);

  if (
    date.getFullYear() !== year ||
    date.getMonth() !== monthIndex ||
    date.getDate() !== day ||
    date.getHours() !== hour ||
    date.getMinutes() !== minute
  ) {
    return Number.NaN;
  }
  return date.getTime();
}

function formatFairTime(timestamp: number) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(timestamp));
}

function getLiveFairStatusLabel(fair: LiveFair) {
  if (fair.status === "live") return "AO VIVO AGORA";
  if (fair.status === "scheduled") return "AGENDADA";
  return fair.endReason === "manual" ? "ENCERRADA PELO EMPREENDEDOR" : "ENCERRADA PELO HORÁRIO";
}

function liveFairToPlace(fair: LiveFair): PinhaisPlace {
  const statusLabel = getLiveFairStatusLabel(fair).toLowerCase();
  return {
    id: `live-fair-${fair.id}`,
    ownerId: fair.ownerId,
    ownerName: fair.ownerName,
    createdAtMs: fair.createdAtMs,
    nome: fair.name,
    categoriaApp: "feiras_livres",
    endereco: fair.address,
    latitude: fair.latitude,
    longitude: fair.longitude,
    rating: null,
    totalAvaliacoes: 0,
    origem: "curadoria_manual",
    buscaOrigem: "feira ao vivo do empreendedor",
    ativo: fair.status !== "ended",
    curadoriaManual: true,
    potencialTuristico: fair.status === "live" ? 100 : fair.status === "scheduled" ? 75 : 35,
    tags: [statusLabel, `início ${formatFairTime(fair.startsAtMs)}`, `fim ${formatFairTime(fair.endsAtMs)}`],
    resumo:
      fair.status === "ended"
        ? `Feira de ${fair.ownerName} encerrada em ${formatFairTime(fair.endedAtMs ?? fair.endsAtMs)}.`
        : `Feira publicada por ${fair.ownerName}. ${formatFairTime(fair.startsAtMs)} até ${formatFairTime(fair.endsAtMs)}.`,
    googleMapsUri: fair.googleMapsUri,
    mapPosition: fair.mapPosition,
  };
}

function getCuratedPlaceErrorMessage(error: unknown) {
  const code = typeof error === "object" && error && "code" in error ? String(error.code) : "";
  if (code.includes("permission-denied")) {
    return "O Firebase recusou a publicacao. Confirme se sua conta possui a permissao de empreendedor.";
  }
  if (code.includes("unavailable") || code.includes("network")) {
    return "Nao foi possivel conectar ao Firebase. Verifique sua internet e tente novamente.";
  }
  return error instanceof Error ? error.message : "Nao foi possivel publicar o ponto agora.";
}

function RatingText({ place }: { place: PinhaisPlace }) {
  if (place.rating === null) return <Text style={styles.metricValue}>A consultar</Text>;
  return (
    <Text style={styles.metricValue}>
      {place.rating.toFixed(1)} ({place.totalAvaliacoes})
    </Text>
  );
}

function PlaceCard({
  isSaved,
  onOpenOwner,
  onSave,
  place,
  selected,
  onSelect,
}: {
  isSaved: boolean;
  onOpenOwner: (ownerId: string) => void;
  onSave: () => void;
  place: PinhaisPlace;
  selected: boolean;
  onSelect: () => void;
}) {
  const categoryColor = pinhaisCategoryColors[place.categoriaApp];
  const ownerId = place.ownerId;

  return (
    <Pressable onPress={onSelect} style={[styles.placeCard, selected && styles.placeCardSelected]}>
      <View style={styles.placeHeader}>
        <View style={[styles.placeIcon, { backgroundColor: categoryColor }]}>
          <Ionicons color={colors.surface} name={pinhaisCategoryIcons[place.categoriaApp]} size={20} />
        </View>
        <View style={styles.placeTitleBox}>
          <Text style={styles.placeCategory}>{pinhaisCategoryLabels[place.categoriaApp]}</Text>
          <Text style={styles.placeTitle}>{place.nome}</Text>
        </View>
        <View style={styles.scoreBadge}>
          <Text style={styles.scoreValue}>{place.potencialTuristico}</Text>
          <Text style={styles.scoreLabel}>pts</Text>
        </View>
      </View>
      <Text style={styles.placeSummary}>{place.resumo}</Text>
      <Text style={styles.placeAddress}>{place.endereco}</Text>
      <View style={styles.metrics}>
        <View style={styles.metric}>
          <Text style={styles.metricLabel}>Google</Text>
          <RatingText place={place} />
        </View>
        <View style={styles.metric}>
          <Text style={styles.metricLabel}>Origem</Text>
          <Text style={styles.metricValue}>{place.curadoriaManual ? "Curadoria" : "Seed"}</Text>
        </View>
      </View>
      <View style={styles.tagRow}>
        {place.tags.slice(0, 3).map((tag) => (
          <View key={tag} style={styles.tagChip}>
            <Text adjustsFontSizeToFit minimumFontScale={0.82} numberOfLines={1} style={styles.tagText}>
              {tag}
            </Text>
          </View>
        ))}
      </View>
      <View style={styles.cardActions}>
        {ownerId ? (
          <Pressable onPress={() => onOpenOwner(ownerId)} style={styles.actionButton}>
            <Ionicons color={colors.primary} name="person-circle-outline" size={16} />
            <Text style={styles.actionText}>Ver perfil</Text>
          </Pressable>
        ) : null}
        {place.mapVerified !== false ? (
          <Pressable onPress={() => openExternalUrl(buildRouteUrl(place))} style={styles.actionButton}>
            <Ionicons color={colors.primary} name="navigate-outline" size={16} />
            <Text style={styles.actionText}>Abrir rota</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={() => openExternalUrl(place.googleMapsUri || buildRouteUrl(place))} style={styles.actionButton}>
          <Ionicons color={colors.primary} name="map-outline" size={16} />
          <Text style={styles.actionText}>Google Maps</Text>
        </Pressable>
        <Pressable
          accessibilityLabel={`Compartilhar ${place.categoriaApp === "eventos" ? "evento" : "local"} ${place.nome}`}
          accessibilityRole="button"
          onPress={(event) => {
            event.stopPropagation();
            void shareLiberRotasItem({
              kind: place.categoriaApp === "eventos" ? "event" : "place",
              title: place.nome,
              description: `${place.resumo} · ${place.endereco}`,
              path: ownerId ? profileSharePath(ownerId) : undefined,
            });
          }}
          style={styles.actionButton}
        >
          <Ionicons color={colors.primary} name="share-social-outline" size={16} />
          <Text style={styles.actionText}>Compartilhar</Text>
        </Pressable>
        <Pressable onPress={onSave} style={[styles.actionButton, isSaved && styles.actionButtonSaved]}>
          <Ionicons color={isSaved ? colors.danger : colors.primary} name={isSaved ? "bookmark" : "bookmark-outline"} size={16} />
          <Text style={[styles.actionText, isSaved && styles.actionTextSaved]}>
            {isSaved ? "Na rota" : "Adicionar"}
          </Text>
        </Pressable>
      </View>
    </Pressable>
  );
}

function LiveFairCard({
  currentProfileId,
  fair,
  isEnding,
  onEnd,
  referenceTimeMs,
}: {
  currentProfileId: string;
  fair: LiveFair;
  isEnding: boolean;
  onEnd: (fair: LiveFair) => void;
  referenceTimeMs: number;
}) {
  const isOwner = fair.ownerId === currentProfileId;
  const statusStyle =
    fair.status === "live" ? styles.liveFairStatusLive : fair.status === "scheduled" ? styles.liveFairStatusScheduled : styles.liveFairStatusEnded;

  return (
    <View style={styles.liveFairCard}>
      <PublicEntityMediaImage
        contentFit="cover"
        entityId={fair.id}
        entityType="fair"
        fallback={null}
        mediaRole="fair_cover"
        style={styles.liveFairCover}
        variant="display"
      />
      <View style={styles.liveFairCardHeader}>
        <View style={styles.liveFairCardTitleBox}>
          <Text style={[styles.liveFairStatus, statusStyle]}>{getLiveFairStatusLabel(fair)}</Text>
          <Text style={styles.liveFairName}>{fair.name}</Text>
          <Text style={styles.liveFairOwner}>por {fair.ownerName}</Text>
        </View>
        <Ionicons color={fair.status === "live" ? colors.accent : colors.primary} name="radio-outline" size={25} />
      </View>
      <Text style={styles.liveFairAddress}>{fair.address}</Text>
      {fair.status !== "ended" ? (
        <Text style={styles.liveFairCountdown}>
          {fair.status === "scheduled" ? "Começa em" : "Termina em"} {formatRemainingTime(
            fair.status === "scheduled" ? fair.startsAtMs : fair.endsAtMs,
            referenceTimeMs,
          )}
        </Text>
      ) : null}
      <View style={styles.liveFairSchedule}>
        <View style={styles.liveFairScheduleItem}>
          <Text style={styles.metricLabel}>INÍCIO</Text>
          <Text style={styles.liveFairScheduleValue}>{formatFairTime(fair.startsAtMs)}</Text>
        </View>
        <View style={styles.liveFairScheduleItem}>
          <Text style={styles.metricLabel}>{fair.status === "ended" ? "TÉRMINO" : "FIM PREVISTO"}</Text>
          <Text style={styles.liveFairScheduleValue}>{formatFairTime(fair.status === "ended" ? fair.endedAtMs ?? fair.endsAtMs : fair.endsAtMs)}</Text>
        </View>
      </View>
      <View style={styles.cardActions}>
        <Pressable onPress={() => openOwnerProfile(fair.ownerId)} style={styles.actionButton}>
          <Ionicons color={colors.primary} name="person-circle-outline" size={16} />
          <Text style={styles.actionText}>Ver perfil</Text>
        </Pressable>
        <Pressable onPress={() => openExternalUrl(fair.googleMapsUri)} style={styles.actionButton}>
          <Ionicons color={colors.primary} name="navigate-outline" size={16} />
          <Text style={styles.actionText}>Abrir mapa</Text>
        </Pressable>
        <Pressable
          accessibilityLabel={`Compartilhar feira ${fair.name}`}
          accessibilityRole="button"
          onPress={() => void shareLiberRotasItem({
            kind: "fair",
            title: fair.name,
            description: `${fair.address} · Início: ${formatFairTime(fair.startsAtMs)}`,
            path: profileSharePath(fair.ownerId, { tab: "fairs", itemId: fair.id }),
          })}
          style={styles.actionButton}
        >
          <Ionicons color={colors.primary} name="share-social-outline" size={16} />
          <Text style={styles.actionText}>Compartilhar</Text>
        </Pressable>
        {isOwner && fair.status !== "ended" ? (
          <Pressable
            accessibilityState={{ disabled: isEnding }}
            disabled={isEnding}
            onPress={() => onEnd(fair)}
            style={[styles.endLiveFairButton, isEnding && styles.saveManualButtonDisabled]}
          >
            <Ionicons color={colors.surface} name="stop-circle-outline" size={16} />
            <Text style={styles.endLiveFairButtonText}>{isEnding ? "Encerrando..." : "Encerrar agora"}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

function LockablePlaceMap({
  interactionEnabled,
  onEnableInteraction,
  onSelectPoint,
  points,
  selectedPointId,
  style,
}: {
  interactionEnabled: boolean;
  onEnableInteraction: () => void;
  onSelectPoint: (placeId: string) => void;
  points: PinhaisPlace[];
  selectedPointId?: string;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.lockableMap, style]}>
      <InteractivePlaceMap
        center={PINHAIS_CENTER}
        onSelectPoint={onSelectPoint}
        points={points}
        selectedPointId={selectedPointId}
        style={styles.interactiveMap}
      />
      {!interactionEnabled ? (
        <Pressable
          accessibilityHint="Depois de liberar, o mapa podera receber zoom e movimentos de arraste."
          accessibilityLabel="Clique ou toque para liberar o mapa"
          accessibilityRole="button"
          onPress={onEnableInteraction}
          style={styles.mapInteractionOverlay}
        >
          <View style={styles.mapInteractionPrompt}>
            <Ionicons color={colors.surface} name="hand-left-outline" size={24} />
            <Text style={styles.mapInteractionPromptTitle}>Clique ou toque para usar o mapa</Text>
            <Text style={styles.mapInteractionPromptText}>Enquanto bloqueado, arraste para continuar rolando a pagina.</Text>
          </View>
        </Pressable>
      ) : null}
    </View>
  );
}

function MapConfirmationModal({
  busy,
  confirmLabel,
  message,
  onCancel,
  onConfirm,
  title,
  visible,
}: {
  busy: boolean;
  confirmLabel: string;
  message: string;
  onCancel: () => void;
  onConfirm: () => void;
  title: string;
  visible: boolean;
}) {
  return (
    <Modal
      animationType="fade"
      onRequestClose={() => {
        if (!busy) onCancel();
      }}
      statusBarTranslucent
      transparent
      visible={visible}
    >
      <View style={styles.confirmModalBackdrop}>
        <View accessibilityViewIsModal style={styles.confirmModalCard}>
          <View style={styles.confirmModalIcon}>
            <Ionicons color={colors.surface} name="warning-outline" size={25} />
          </View>
          <Text style={styles.confirmModalTitle}>{title}</Text>
          <Text style={styles.confirmModalMessage}>{message}</Text>
          <View style={styles.confirmModalActions}>
            <Pressable
              disabled={busy}
              onPress={onCancel}
              style={[styles.confirmModalButton, styles.confirmModalSecondary, busy && styles.saveManualButtonDisabled]}
            >
              <Text style={styles.confirmModalSecondaryText}>Cancelar</Text>
            </Pressable>
            <Pressable
              disabled={busy}
              onPress={onConfirm}
              style={[styles.confirmModalButton, styles.confirmModalDanger, busy && styles.saveManualButtonDisabled]}
            >
              <Text style={styles.confirmModalDangerText}>{busy ? "Processando..." : confirmLabel}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

export default function FairsScreen() {
  const { accessSession, hasPermission } = useSessionState();
  const { profile } = useProfileState();
  const { favorites, toggleFavorite } = usePreferencesState();
  const { nowMs } = useTrustedClock();
  const canPublishLocations = accessSession?.role === "entrepreneur" && hasPermission("locations.publish");
  const [viewMode, setViewMode] = useState<"local" | "routes">("local");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<PinhaisCategory | "todos">("todos");
  const [curatedPlaces, setCuratedPlaces] = useState<PinhaisPlace[]>([]);
  const [isLoadingCuratedPlaces, setIsLoadingCuratedPlaces] = useState(true);
  const [curatedPlacesError, setCuratedPlacesError] = useState("");
  const [liveFairs, setLiveFairs] = useState<LiveFair[]>([]);
  const [isLoadingLiveFairs, setIsLoadingLiveFairs] = useState(true);
  const [liveFairsError, setLiveFairsError] = useState("");
  const [selectedPlaceId, setSelectedPlaceId] = useState(pinhaisPlaces[0]?.id || "");
  const [manualName, setManualName] = useState("");
  const [manualAddress, setManualAddress] = useState("");
  const [manualCategory, setManualCategory] = useState<PinhaisCategory>("artesanato");
  const [manualLatitude, setManualLatitude] = useState(String(PINHAIS_CENTER.latitude));
  const [manualLongitude, setManualLongitude] = useState(String(PINHAIS_CENTER.longitude));
  const [isSavingManualPlace, setIsSavingManualPlace] = useState(false);
  const [liveFairName, setLiveFairName] = useState("");
  const [liveFairAddress, setLiveFairAddress] = useState("");
  const [liveFairLatitude, setLiveFairLatitude] = useState("");
  const [liveFairLongitude, setLiveFairLongitude] = useState("");
  const [liveFairStartsAt, setLiveFairStartsAt] = useState(() => formatDateTimeInput(nowMs + 5 * 60 * 1000));
  const [liveFairEndsAt, setLiveFairEndsAt] = useState(() => formatDateTimeInput(nowMs + 2 * 60 * 60 * 1000));
  const [liveFairCover, setLiveFairCover] = useState<PreparedImageUpload | null>(null);
  const [isFindingLocation, setIsFindingLocation] = useState(false);
  const [isSavingLiveFair, setIsSavingLiveFair] = useState(false);
  const [endingLiveFairId, setEndingLiveFairId] = useState("");
  const [deletingPlaceId, setDeletingPlaceId] = useState("");
  const [pendingFairEnd, setPendingFairEnd] = useState<LiveFair | null>(null);
  const [pendingPlaceDelete, setPendingPlaceDelete] = useState<PinhaisPlace | null>(null);
  const [fairListMode, setFairListMode] = useState<"live" | "history">("live");
  const [fairHistoryPage, setFairHistoryPage] = useState(1);
  const [placesPage, setPlacesPage] = useState(1);
  const [isMapInteractionEnabled, setIsMapInteractionEnabled] = useState(false);
  const [isMapMaximized, setIsMapMaximized] = useState(false);

  useEffect(() => {
    return subscribeToApprovedCuratedPlaces(
      (places) => {
        setCuratedPlaces(places);
        setCuratedPlacesError("");
        setIsLoadingCuratedPlaces(false);
      },
      (error) => {
        console.warn("Nao foi possivel carregar os pontos publicos do Firestore.", error);
        setCuratedPlacesError(getCuratedPlaceErrorMessage(error));
        setIsLoadingCuratedPlaces(false);
      },
    );
  }, []);

  useEffect(() => {
    return subscribeToPublicLiveFairs(
      (fairs) => {
        setLiveFairs(fairs);
        setLiveFairsError("");
        setIsLoadingLiveFairs(false);
      },
      (error) => {
        console.warn("Nao foi possivel carregar as feiras ao vivo do Firestore.", error);
        setLiveFairsError(getCuratedPlaceErrorMessage(error));
        setIsLoadingLiveFairs(false);
      },
    );
  }, []);

  const effectiveLiveFairs = useMemo(
    () => liveFairs.map((fair) => ({ ...fair, status: resolveLiveFairStatus(fair, nowMs) })),
    [liveFairs, nowMs],
  );

  const liveFairPlaces = useMemo(
    () => effectiveLiveFairs.filter((fair) => fair.status !== "ended").map(liveFairToPlace),
    [effectiveLiveFairs],
  );

  const allPlaces = useMemo(
    () => [...pinhaisPlaces, ...curatedPlaces, ...liveFairPlaces].sort((left, right) => right.potencialTuristico - left.potencialTuristico),
    [curatedPlaces, liveFairPlaces],
  );

  const visiblePlaces = useMemo(() => {
    const normalizedQuery = normalizeText(query);
    return allPlaces.filter((place) => {
      const text = normalizeText(
        [place.nome, place.endereco, place.resumo, place.buscaOrigem, pinhaisCategoryLabels[place.categoriaApp], ...place.tags].join(" "),
      );
      return matchesCategory(place, category) && (!normalizedQuery || text.includes(normalizedQuery));
    });
  }, [allPlaces, category, query]);

  const visibleMapPlaces = useMemo(
    () => visiblePlaces.filter((place) => place.mapVerified !== false),
    [visiblePlaces],
  );
  const selectedPlace = visibleMapPlaces.find((place) => place.id === selectedPlaceId)
    || visibleMapPlaces[0]
    || visiblePlaces[0]
    || allPlaces[0];
  const visibleLiveFairs = useMemo(
    () => {
      if (category !== "todos" && category !== "feiras_livres") return [];
      const normalizedQuery = normalizeText(query);
      return effectiveLiveFairs.filter((fair) => {
        if (!normalizedQuery) return true;
        return normalizeText([fair.name, fair.address, fair.ownerName, getLiveFairStatusLabel(fair)].join(" ")).includes(normalizedQuery);
      });
    },
    [category, effectiveLiveFairs, query],
  );
  const visibleRegularPlaces = useMemo(() => visiblePlaces.filter((place) => !place.id.startsWith("live-fair-")), [visiblePlaces]);
  const activeVisibleFairs = useMemo(() => visibleLiveFairs.filter((fair) => fair.status !== "ended"), [visibleLiveFairs]);
  const historicalVisibleFairs = useMemo(() => visibleLiveFairs.filter((fair) => fair.status === "ended"), [visibleLiveFairs]);
  const safeFairHistoryPage = clampPage(fairHistoryPage, historicalVisibleFairs.length);
  const displayedFairs = fairListMode === "live"
    ? activeVisibleFairs
    : paginateItems(historicalVisibleFairs, safeFairHistoryPage);
  const safePlacesPage = clampPage(placesPage, visibleRegularPlaces.length);
  const paginatedRegularPlaces = paginateItems(visibleRegularPlaces, safePlacesPage);
  const ownCuratedPlaces = useMemo(
    () => curatedPlaces.filter((place) => place.ownerId === profile.id),
    [curatedPlaces, profile.id],
  );
  const savedPlaces = useMemo(() => allPlaces.filter((place) => favorites.includes(place.id)), [allPlaces, favorites]);
  const savedOffers = useMemo(() => marketPosts.filter((post) => favorites.includes(post.id)), [favorites]);
  const savedRouteCount = savedPlaces.length;
  const savedItemCount = savedPlaces.length + savedOffers.length;
  const activeCategoryLabel = category === "todos" ? "Pontos e rotas" : `Enderecos de ${pinhaisCategoryLabels[category]}`;

  function toggleCategory(nextCategory: PinhaisCategory) {
    setCategory((currentCategory) => (currentCategory === nextCategory ? "todos" : nextCategory));
    setFairHistoryPage(1);
    setPlacesPage(1);
  }

  function updateQuery(value: string) {
    setQuery(value);
    setFairHistoryPage(1);
    setPlacesPage(1);
  }

  async function saveManualPlace() {
    if (!canPublishLocations) {
      Alert.alert("Acao nao permitida", "Somente perfis de empreendedor podem publicar pontos no mapa.");
      return;
    }
    if (ownCuratedPlaces.length > 0) {
      Alert.alert(
        "Limite de um ponto",
        "Você já possui um ponto publicado. Exclua o ponto atual antes de publicar outro.",
      );
      return;
    }
    if (isSavingManualPlace) return;

    const latitude = parseCoordinate(manualLatitude);
    const longitude = parseCoordinate(manualLongitude);
    setIsSavingManualPlace(true);
    try {
      const documentId = await publishCuratedPlace({
        name: manualName,
        address: manualAddress,
        category: manualCategory,
        latitude,
        longitude,
      });
      setSelectedPlaceId(documentId);
      setManualName("");
      setManualAddress("");
      Alert.alert("Ponto publicado", "O ponto foi salvo no Firestore e ja esta disponivel no mapa publico.");
    } catch (error) {
      console.warn("Nao foi possivel publicar o ponto no Firestore.", error);
      Alert.alert("Falha ao publicar", getCuratedPlaceErrorMessage(error));
    } finally {
      setIsSavingManualPlace(false);
    }
  }

  async function removeCuratedPlace(place: PinhaisPlace) {
    if (deletingPlaceId) return;
    setDeletingPlaceId(place.id);
    try {
      await deleteCuratedPlace(place.id);
      setCuratedPlaces((current) => current.filter((item) => item.id !== place.id));
      setSelectedPlaceId((current) => (current === place.id ? "" : current));
      setPendingPlaceDelete(null);
      Alert.alert("Ponto excluído", "O ponto e o ícone foram removidos do mapa público.");
    } catch (error) {
      console.warn("Nao foi possivel excluir o ponto do mapa.", error);
      Alert.alert("Falha ao excluir", getCuratedPlaceErrorMessage(error));
    } finally {
      setDeletingPlaceId("");
    }
  }

  async function useCurrentLocation() {
    if (isFindingLocation) return;
    setIsFindingLocation(true);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== Location.PermissionStatus.GRANTED) {
        Alert.alert(
          "Localização não autorizada",
          "Permita o acesso à localização nas configurações do aparelho ou informe latitude e longitude manualmente.",
        );
        return;
      }

      const currentPosition = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const { latitude, longitude } = currentPosition.coords;
      setLiveFairLatitude(latitude.toFixed(6));
      setLiveFairLongitude(longitude.toFixed(6));

      if (!liveFairAddress.trim()) {
        try {
          const [geocodedAddress] = await Location.reverseGeocodeAsync({ latitude, longitude });
          if (geocodedAddress) {
            const address = [
              geocodedAddress.name,
              geocodedAddress.street,
              geocodedAddress.district,
              geocodedAddress.city,
              geocodedAddress.region,
            ]
              .filter((part, index, parts): part is string => Boolean(part) && parts.indexOf(part) === index)
              .join(", ");
            if (address) setLiveFairAddress(address);
          }
        } catch {
          // As coordenadas continuam validas mesmo quando o aparelho nao consegue obter o endereco textual.
        }
      }
    } catch (error) {
      console.warn("Nao foi possivel obter a localizacao atual.", error);
      Alert.alert(
        "Localização indisponível",
        "Não foi possível obter sua localização. Confira se o GPS está ativo ou informe as coordenadas manualmente.",
      );
    } finally {
      setIsFindingLocation(false);
    }
  }

  async function publishLiveFair() {
    if (!canPublishLocations) {
      Alert.alert("Ação não permitida", "Somente perfis de empreendedor podem publicar feiras ao vivo.");
      return;
    }
    if (isSavingLiveFair) return;

    setIsSavingLiveFair(true);
    try {
      const documentId = await publishLiveFairOnBackend({
        name: liveFairName,
        address: liveFairAddress,
        latitude: parseCoordinate(liveFairLatitude),
        longitude: parseCoordinate(liveFairLongitude),
        startsAtMs: parseDateTimeInput(liveFairStartsAt),
        endsAtMs: parseDateTimeInput(liveFairEndsAt),
      });
      let imageWarning = "";
      if (liveFairCover) {
        try {
          await uploadImage(liveFairCover, {
            entityType: "fair",
            entityId: documentId,
            mediaRole: "fair_cover",
          });
        } catch (error) {
          imageWarning = ` A feira foi publicada sem a capa: ${getCuratedPlaceErrorMessage(error)}`;
        }
      }
      setSelectedPlaceId(`live-fair-${documentId}`);
      setLiveFairName("");
      setLiveFairAddress("");
      setLiveFairLatitude("");
      setLiveFairLongitude("");
      setLiveFairStartsAt(formatDateTimeInput(nowMs + 5 * 60 * 1000));
      setLiveFairEndsAt(formatDateTimeInput(nowMs + 2 * 60 * 60 * 1000));
      setLiveFairCover(null);
      Alert.alert("Feira publicada", `Ela já está visível no mapa público e será encerrada automaticamente no horário final.${imageWarning}`);
    } catch (error) {
      console.warn("Nao foi possivel publicar a feira ao vivo.", error);
      Alert.alert("Falha ao publicar", getCuratedPlaceErrorMessage(error));
    } finally {
      setIsSavingLiveFair(false);
    }
  }

  async function finishLiveFair(fair: LiveFair) {
    if (endingLiveFairId) return;
    setEndingLiveFairId(fair.id);
    try {
      await endLiveFairOnBackend(fair.id);
      setLiveFairs((current) => current.map((item) => (
        item.id === fair.id
          ? { ...item, status: "ended", endedAtMs: nowMs, endReason: "manual" }
          : item
      )));
      setPendingFairEnd(null);
      setFairListMode("history");
      setFairHistoryPage(1);
      Alert.alert("Feira encerrada", "O ícone saiu do mapa e a feira foi movida para o histórico público.");
    } catch (error) {
      console.warn("Nao foi possivel encerrar a feira ao vivo.", error);
      Alert.alert("Falha ao encerrar", getCuratedPlaceErrorMessage(error));
    } finally {
      setEndingLiveFairId("");
    }
  }

  function confirmEndLiveFair(fair: LiveFair) {
    setPendingFairEnd(fair);
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <BrandHeader subtitle="turismo, feiras e comercio local" title="Mapa de Pinhais" />
      <ScrollView contentContainerStyle={styles.content}>
        <View accessibilityRole="tablist" style={styles.viewTabs}>
          <Pressable
            accessibilityRole="tab"
            accessibilityState={{ selected: viewMode === "local" }}
            onPress={() => setViewMode("local")}
            style={[styles.viewTab, viewMode === "local" && styles.viewTabActive]}
          >
            <Ionicons color={viewMode === "local" ? colors.surface : colors.primary} name="map-outline" size={19} />
            <Text style={[styles.viewTabText, viewMode === "local" && styles.viewTabTextActive]}>Local</Text>
          </Pressable>
          <Pressable
            accessibilityRole="tab"
            accessibilityState={{ selected: viewMode === "routes" }}
            onPress={() => setViewMode("routes")}
            style={[styles.viewTab, viewMode === "routes" && styles.viewTabActive]}
          >
            <Ionicons color={viewMode === "routes" ? colors.surface : colors.primary} name="navigate-outline" size={19} />
            <Text style={[styles.viewTabText, viewMode === "routes" && styles.viewTabTextActive]}>Rotas</Text>
            {savedItemCount > 0 ? (
              <View style={[styles.viewTabBadge, viewMode === "routes" && styles.viewTabBadgeActive]}>
                <Text style={[styles.viewTabBadgeText, viewMode === "routes" && styles.viewTabBadgeTextActive]}>{savedItemCount}</Text>
              </View>
            ) : null}
          </Pressable>
        </View>

        {viewMode === "local" ? (
          <>
        <View style={styles.hero}>
          <Text style={styles.heroLabel}>PINHAIS - PR</Text>
          <Text style={styles.heroTitle}>Rotas para turismo, feiras, bordados e gastronomia.</Text>
          <View style={styles.heroStats}>
            <View style={styles.heroStat}>
              <Text style={styles.heroStatValue}>{allPlaces.length}</Text>
              <Text style={styles.heroStatLabel}>pontos</Text>
            </View>
            <View style={styles.heroStat}>
              <Text style={styles.heroStatValue}>{savedRouteCount}</Text>
              <Text style={styles.heroStatLabel}>na rota</Text>
            </View>
            <View style={styles.heroStat}>
              <Text style={styles.heroStatValue}>9 km</Text>
              <Text style={styles.heroStatLabel}>raio</Text>
            </View>
          </View>
        </View>

        <View style={styles.searchBox}>
          <Ionicons color={colors.textMuted} name="search" size={18} />
          <TextInput
            onChangeText={updateQuery}
            placeholder="Buscar turismo, feira, artesanato ou gastronomia"
            placeholderTextColor={colors.textMuted}
            style={styles.input}
            value={query}
          />
        </View>

        <View style={styles.mapPanel}>
          <View style={styles.mapHeader}>
            <View>
              <Text style={styles.sectionEyebrow}>MAPA INTERATIVO</Text>
              <Text style={styles.sectionTitle}>Pinhais, PR</Text>
            </View>
            <View style={styles.mapHeaderActions}>
              <Pressable
                accessibilityLabel="Maximizar mapa"
                accessibilityRole="button"
                onPress={() => setIsMapMaximized(true)}
                style={styles.maximizeMapButton}
              >
                <Ionicons color={colors.primary} name="expand-outline" size={16} />
                <Text style={styles.maximizeMapButtonText}>MAXIMIZAR</Text>
              </Pressable>
              <View accessibilityLabel={`${visibleMapPlaces.length} pontos no mapa`} style={styles.mapCount}>
                <Text style={styles.mapCountText}>{visibleMapPlaces.length}</Text>
              </View>
            </View>
          </View>
          <View style={styles.mapCanvas}>
            <LockablePlaceMap
              interactionEnabled={isMapInteractionEnabled}
              onEnableInteraction={() => setIsMapInteractionEnabled(true)}
              onSelectPoint={setSelectedPlaceId}
              points={visibleMapPlaces}
              selectedPointId={selectedPlace?.id}
              style={styles.interactiveMap}
            />
            <Pressable onPress={() => openExternalUrl(GOOGLE_MAPS_PINHAIS_URL)} style={styles.openCityMapButton}>
              <Ionicons color={colors.primary} name="expand-outline" size={17} />
              <Text style={styles.openCityMapText}>Abrir no Google Maps</Text>
            </Pressable>
          </View>
          {selectedPlace ? (
            <View style={styles.selectedBar}>
              <View style={[styles.selectedDot, { backgroundColor: pinhaisCategoryColors[selectedPlace.categoriaApp] }]} />
              <View style={styles.selectedTextBox}>
                <Text style={styles.selectedCategory}>{pinhaisCategoryLabels[selectedPlace.categoriaApp]}</Text>
                <Text style={styles.selectedName}>{selectedPlace.nome}</Text>
              </View>
              <Pressable onPress={() => openExternalUrl(buildRouteUrl(selectedPlace))} style={styles.routeIconButton}>
                <Ionicons color={colors.surface} name="navigate-outline" size={18} />
              </Pressable>
            </View>
          ) : null}
        </View>

        <View style={styles.highlightButtons}>
          {(Object.keys(pinhaisCategoryLabels) as PinhaisCategory[]).map((item) => (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ selected: category === item }}
              key={item}
              onPress={() => toggleCategory(item)}
              style={[
                styles.highlightButton,
                category === item && {
                  backgroundColor: pinhaisCategoryColors[item],
                  borderColor: pinhaisCategoryColors[item],
                },
              ]}
            >
              <View style={[styles.highlightDot, { backgroundColor: category === item ? colors.surface : pinhaisCategoryColors[item] }]} />
              <Text style={[styles.highlightText, category === item && styles.highlightTextActive]}>
                {pinhaisCategoryLabels[item]}
              </Text>
            </Pressable>
          ))}
        </View>

        {category === "todos" || category === "feiras_livres" ? (
          <View style={styles.liveFairsPanel}>
            <View style={styles.liveFairsHeader}>
              <View>
                <Text style={styles.sectionEyebrow}>FEIRAS PUBLICADAS PELOS EMPREENDEDORES</Text>
                <View accessibilityRole="tablist" style={styles.fairListTabs}>
                  <Pressable
                    accessibilityRole="tab"
                    accessibilityState={{ selected: fairListMode === "live" }}
                    onPress={() => setFairListMode("live")}
                    style={[styles.fairListTab, fairListMode === "live" && styles.fairListTabActive]}
                  >
                    <Text style={[styles.fairListTabText, fairListMode === "live" && styles.fairListTabTextActive]}>
                      Ao vivo agora
                    </Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="tab"
                    accessibilityState={{ selected: fairListMode === "history" }}
                    onPress={() => setFairListMode("history")}
                    style={[styles.fairListTab, fairListMode === "history" && styles.fairListTabActive]}
                  >
                    <Text style={[styles.fairListTabText, fairListMode === "history" && styles.fairListTabTextActive]}>
                      Histórico
                    </Text>
                  </Pressable>
                </View>
              </View>
              <View style={styles.liveFairsCount}>
                <Text style={styles.liveFairsCountText}>
                  {fairListMode === "live" ? activeVisibleFairs.length : historicalVisibleFairs.length}
                </Text>
              </View>
            </View>
            <Text style={styles.liveFairsHint}>
              {fairListMode === "live"
                ? "Feiras ativas aparecem no mapa. Ao terminar ou serem encerradas, o ícone é removido automaticamente."
                : "Feiras encerradas ficam registradas aqui, em páginas de até 20 itens."}
            </Text>
            {isLoadingLiveFairs ? <Text style={styles.cloudStatus}>Carregando feiras públicas...</Text> : null}
            {liveFairsError ? <Text style={[styles.cloudStatus, styles.cloudStatusError]}>{liveFairsError}</Text> : null}
            <View style={styles.liveFairsList}>
              {displayedFairs.map((fair) => (
                <LiveFairCard
                  currentProfileId={profile.id}
                  fair={fair}
                  isEnding={endingLiveFairId === fair.id}
                  key={fair.id}
                  onEnd={confirmEndLiveFair}
                  referenceTimeMs={nowMs}
                />
              ))}
              {!isLoadingLiveFairs && !liveFairsError && displayedFairs.length === 0 ? (
                <Text style={styles.emptyLiveFairs}>
                  {fairListMode === "live" ? "Nenhuma feira ao vivo neste filtro." : "Nenhuma feira no histórico deste filtro."}
                </Text>
              ) : null}
            </View>
            {fairListMode === "history" ? (
              <PaginationControls
                label="histórico de feiras"
                onPageChange={setFairHistoryPage}
                page={safeFairHistoryPage}
                pageSize={HISTORY_PAGE_SIZE}
                totalItems={historicalVisibleFairs.length}
              />
            ) : null}
          </View>
        ) : null}

        {canPublishLocations ? (
          <View style={[styles.manualPanel, styles.liveFairForm]}>
            <Text style={styles.sectionEyebrow}>COMPARTILHAR LOCALIZAÇÃO TEMPORÁRIA</Text>
            <Text style={styles.manualTitle}>Publicar feira ao vivo</Text>
            <Text style={styles.manualHint}>
              Informe o endereço completo e o período. No horário final, a feira muda automaticamente para encerrada.
            </Text>
            <TextInput
              maxLength={120}
              onChangeText={setLiveFairName}
              placeholder="Nome da feira ou evento"
              placeholderTextColor={colors.textMuted}
              style={styles.manualInput}
              value={liveFairName}
            />
            <TextInput
              maxLength={240}
              onChangeText={setLiveFairAddress}
              placeholder="Endereço completo da feira"
              placeholderTextColor={colors.textMuted}
              style={styles.manualInput}
              value={liveFairAddress}
            />
            <Pressable
              accessibilityState={{ disabled: isFindingLocation }}
              disabled={isFindingLocation}
              onPress={useCurrentLocation}
              style={[styles.locationButton, isFindingLocation && styles.saveManualButtonDisabled]}
            >
              <Ionicons color={colors.primary} name="locate-outline" size={18} />
              <Text style={styles.locationButtonText}>{isFindingLocation ? "Obtendo localização..." : "Usar minha localização atual"}</Text>
            </Pressable>
            <View style={styles.manualCoordinates}>
              <TextInput
                keyboardType="decimal-pad"
                maxLength={16}
                onChangeText={setLiveFairLatitude}
                placeholder="Latitude"
                placeholderTextColor={colors.textMuted}
                style={[styles.manualInput, styles.manualCoordinateInput]}
                value={liveFairLatitude}
              />
              <TextInput
                keyboardType="decimal-pad"
                maxLength={16}
                onChangeText={setLiveFairLongitude}
                placeholder="Longitude"
                placeholderTextColor={colors.textMuted}
                style={[styles.manualInput, styles.manualCoordinateInput]}
                value={liveFairLongitude}
              />
            </View>
            <View style={styles.liveFairDateInputs}>
              <View style={styles.liveFairDateField}>
                <Text style={styles.liveFairInputLabel}>Início (DD/MM/AAAA HH:mm)</Text>
                <TextInput
                  maxLength={16}
                  onChangeText={setLiveFairStartsAt}
                  placeholder="14/07/2026 18:00"
                  placeholderTextColor={colors.textMuted}
                  style={styles.manualInput}
                  value={liveFairStartsAt}
                />
              </View>
              <View style={styles.liveFairDateField}>
                <Text style={styles.liveFairInputLabel}>Fim (DD/MM/AAAA HH:mm)</Text>
                <TextInput
                  maxLength={16}
                  onChangeText={setLiveFairEndsAt}
                  placeholder="14/07/2026 22:00"
                  placeholderTextColor={colors.textMuted}
                  style={styles.manualInput}
                  value={liveFairEndsAt}
                />
              </View>
            </View>
            <Text style={styles.liveFairFormNote}>Duração máxima: 24 horas. Latitude e longitude podem ser corrigidas manualmente.</Text>
            <MediaImagePicker
              disabled={isSavingLiveFair}
              hint="Opcional. A capa pública usa somente as variantes processadas pelo backend."
              label="Capa da feira"
              onChange={setLiveFairCover}
              value={liveFairCover}
            />
            <Pressable
              accessibilityState={{ disabled: isSavingLiveFair }}
              disabled={isSavingLiveFair}
              onPress={publishLiveFair}
              style={[styles.saveLiveFairButton, isSavingLiveFair && styles.saveManualButtonDisabled]}
            >
              <Ionicons color={colors.surface} name="radio-outline" size={18} />
              <Text style={styles.saveManualText}>{isSavingLiveFair ? "Publicando..." : "Publicar feira ao vivo"}</Text>
            </Pressable>
          </View>
        ) : null}

        {canPublishLocations ? (
          <View style={styles.manualPanel}>
            <Text style={styles.sectionEyebrow}>PONTO DO EMPREENDEDOR</Text>
            <Text style={styles.manualTitle}>
              {ownCuratedPlaces.length > 0 ? "Seu ponto publicado" : "Publicar ponto no mapa"}
            </Text>
            {ownCuratedPlaces.length > 0 ? (
              <>
                <Text style={styles.manualHint}>
                  Cada empreendedor pode manter somente um ponto no mapa. Para publicar outro local, exclua o atual primeiro.
                </Text>
                {ownCuratedPlaces.map((place) => (
                  <View key={place.id} style={styles.ownPlaceCard}>
                    <View style={[styles.placeIcon, { backgroundColor: pinhaisCategoryColors[place.categoriaApp] }]}>
                      <Ionicons color={colors.surface} name={pinhaisCategoryIcons[place.categoriaApp]} size={20} />
                    </View>
                    <View style={styles.ownPlaceCopy}>
                      <Text style={styles.ownPlaceName}>{place.nome}</Text>
                      <Text style={styles.ownPlaceAddress}>{place.endereco}</Text>
                      {ownCuratedPlaces.length > 1 ? (
                        <Text style={styles.legacyPlaceWarning}>
                          Cadastro antigo excedente: exclua até restar somente um ponto.
                        </Text>
                      ) : null}
                    </View>
                    <Pressable
                      accessibilityLabel={`Excluir ponto ${place.nome}`}
                      accessibilityRole="button"
                      disabled={Boolean(deletingPlaceId)}
                      onPress={() => setPendingPlaceDelete(place)}
                      style={[styles.deletePlaceButton, deletingPlaceId && styles.saveManualButtonDisabled]}
                    >
                      <Ionicons color={colors.surface} name="trash-outline" size={17} />
                      <Text style={styles.deletePlaceButtonText}>Excluir ponto</Text>
                    </Pressable>
                  </View>
                ))}
              </>
            ) : (
              <>
                <Text style={styles.manualHint}>
                  O ponto aparece para todos os usuários. O backend permite apenas um ponto ativo por empreendedor.
                </Text>
                <TextInput
                  maxLength={120}
                  onChangeText={setManualName}
                  placeholder="Nome do artesão, feira, loja ou evento"
                  placeholderTextColor={colors.textMuted}
                  style={styles.manualInput}
                  value={manualName}
                />
                <TextInput
                  maxLength={240}
                  onChangeText={setManualAddress}
                  placeholder="Endereço ou referência em Pinhais"
                  placeholderTextColor={colors.textMuted}
                  style={styles.manualInput}
                  value={manualAddress}
                />
                <View style={styles.manualCoordinates}>
                  <TextInput
                    keyboardType="decimal-pad"
                    maxLength={16}
                    onChangeText={setManualLatitude}
                    placeholder="Latitude"
                    placeholderTextColor={colors.textMuted}
                    style={[styles.manualInput, styles.manualCoordinateInput]}
                    value={manualLatitude}
                  />
                  <TextInput
                    keyboardType="decimal-pad"
                    maxLength={16}
                    onChangeText={setManualLongitude}
                    placeholder="Longitude"
                    placeholderTextColor={colors.textMuted}
                    style={[styles.manualInput, styles.manualCoordinateInput]}
                    value={manualLongitude}
                  />
                </View>
                <ScrollView contentContainerStyle={styles.manualCategories} horizontal showsHorizontalScrollIndicator={false}>
                  {manualCategoryOptions.map((item) => (
                    <Pressable
                      key={item}
                      onPress={() => setManualCategory(item)}
                      style={[
                        styles.manualCategory,
                        manualCategory === item && {
                          backgroundColor: pinhaisCategoryColors[item],
                          borderColor: pinhaisCategoryColors[item],
                        },
                      ]}
                    >
                      <Text style={[styles.manualCategoryText, manualCategory === item && styles.manualCategoryTextActive]}>
                        {pinhaisCategoryLabels[item]}
                      </Text>
                    </Pressable>
                  ))}
                </ScrollView>
                <Pressable
                  accessibilityState={{ disabled: isSavingManualPlace }}
                  disabled={isSavingManualPlace}
                  onPress={saveManualPlace}
                  style={[styles.saveManualButton, isSavingManualPlace && styles.saveManualButtonDisabled]}
                >
                  <Ionicons color={colors.surface} name="add-circle-outline" size={18} />
                  <Text style={styles.saveManualText}>{isSavingManualPlace ? "Publicando..." : "Publicar ponto"}</Text>
                </Pressable>
              </>
            )}
          </View>
        ) : null}

        <View style={styles.listHeader}>
          <Text style={styles.sectionTitle}>{activeCategoryLabel}</Text>
          <Text style={styles.listCount}>{visibleRegularPlaces.length} resultados</Text>
        </View>
        {isLoadingCuratedPlaces ? <Text style={styles.cloudStatus}>Carregando pontos publicados...</Text> : null}
        {curatedPlacesError ? <Text style={[styles.cloudStatus, styles.cloudStatusError]}>{curatedPlacesError}</Text> : null}
        <View style={styles.list}>
          {paginatedRegularPlaces.map((place) => (
            <PlaceCard
              isSaved={favorites.includes(place.id)}
              key={place.id}
              onOpenOwner={openOwnerProfile}
              onSave={() => toggleFavorite(place.id)}
              onSelect={() => setSelectedPlaceId(place.id)}
              place={place}
              selected={selectedPlace?.id === place.id}
            />
          ))}
          {visibleRegularPlaces.length === 0 ? <Text style={styles.empty}>Nenhum ponto encontrado para esse filtro.</Text> : null}
        </View>
        <PaginationControls
          label="pontos do mapa"
          onPageChange={setPlacesPage}
          page={safePlacesPage}
          pageSize={HISTORY_PAGE_SIZE}
          totalItems={visibleRegularPlaces.length}
        />

          </>
        ) : (
          <View style={styles.routesContent}>
            <View style={styles.routesIntro}>
              <View style={styles.routesIntroIcon}>
                <Ionicons color={colors.surface} name="bookmark" size={24} />
              </View>
              <View style={styles.routesIntroText}>
                <Text style={styles.routesTitle}>Minha rota</Text>
                <Text style={styles.routesDescription}>Locais para visitar e ofertas que você salvou ficam guardados neste aparelho.</Text>
              </View>
            </View>

            {profile.interests.length > 0 ? (
              <View style={styles.interestsPanel}>
                <Text style={styles.sectionEyebrow}>SEUS INTERESSES</Text>
                <View style={styles.interestChips}>
                  {profile.interests.map((interest) => (
                    <View key={interest} style={styles.interestChip}>
                      <Text style={styles.interestChipText}>{interest}</Text>
                    </View>
                  ))}
                </View>
              </View>
            ) : null}

            {savedPlaces.length > 0 ? (
              <>
                <View style={styles.listHeader}>
                  <Text style={styles.sectionTitle}>Para visitar</Text>
                  <Text style={styles.listCount}>{savedPlaces.length} locais</Text>
                </View>
                <View style={styles.list}>
                  {savedPlaces.map((place) => (
                    <PlaceCard
                      isSaved
                      key={place.id}
                      onOpenOwner={openOwnerProfile}
                      onSave={() => toggleFavorite(place.id)}
                      onSelect={() => setSelectedPlaceId(place.id)}
                      place={place}
                      selected={selectedPlaceId === place.id}
                    />
                  ))}
                </View>
              </>
            ) : null}

            {savedOffers.length > 0 ? (
              <>
                <View style={styles.listHeader}>
                  <Text style={styles.sectionTitle}>Para comprar</Text>
                  <Text style={styles.listCount}>{savedOffers.length} ofertas</Text>
                </View>
                <View style={styles.list}>
                  {savedOffers.map((offer) => (
                    <View key={offer.id} style={styles.savedOfferCard}>
                      <View style={styles.savedOfferIcon}>
                        <Ionicons color={colors.accent} name="bag-handle-outline" size={23} />
                      </View>
                      <View style={styles.savedOfferText}>
                        <Text style={styles.savedOfferCategory}>{offer.category}</Text>
                        <Text style={styles.savedOfferTitle}>{offer.title}</Text>
                        <Text style={styles.savedOfferMeta}>{offer.seller} · {offer.city}</Text>
                      </View>
                      <Pressable accessibilityLabel={`Remover ${offer.title} da rota`} onPress={() => toggleFavorite(offer.id)} style={styles.removeOfferButton}>
                        <Ionicons color={colors.danger} name="trash-outline" size={18} />
                      </Pressable>
                    </View>
                  ))}
                </View>
              </>
            ) : null}

            {savedItemCount === 0 ? (
              <View style={styles.emptyRoutes}>
                <Ionicons color={colors.textMuted} name="bookmark-outline" size={38} />
                <Text style={styles.emptyRoutesTitle}>Sua rota ainda está vazia</Text>
                <Text style={styles.emptyRoutesText}>Abra “Local” e toque em “Adicionar” para guardar um lugar para visitar. Ofertas salvas no Feed também aparecem aqui.</Text>
                <Pressable onPress={() => setViewMode("local")} style={styles.emptyRoutesButton}>
                  <Text style={styles.emptyRoutesButtonText}>Explorar locais</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        )}
      </ScrollView>
      <Modal
        animationType="fade"
        onRequestClose={() => setIsMapMaximized(false)}
        presentationStyle="fullScreen"
        statusBarTranslucent
        visible={isMapMaximized}
      >
        <SafeAreaView accessibilityViewIsModal edges={["top", "bottom"]} style={styles.maximizedMapSafeArea}>
          <View style={styles.maximizedMapHeader}>
            <View style={styles.maximizedMapTitleBox}>
              <Text style={styles.sectionEyebrow}>MAPA AMPLIADO</Text>
              <Text style={styles.sectionTitle}>Pinhais, PR</Text>
            </View>
            <View style={styles.maximizedMapHeaderActions}>
              <View accessibilityLabel={`${visibleMapPlaces.length} pontos no mapa`} style={styles.mapCount}>
                <Text style={styles.mapCountText}>{visibleMapPlaces.length}</Text>
              </View>
              <Pressable
                accessibilityLabel="Fechar mapa maximizado"
                accessibilityRole="button"
                onPress={() => setIsMapMaximized(false)}
                style={styles.closeMaximizedMapButton}
              >
                <Ionicons color={colors.surface} name="contract-outline" size={17} />
                <Text style={styles.closeMaximizedMapButtonText}>FECHAR</Text>
              </Pressable>
            </View>
          </View>
          <View style={styles.maximizedMapCanvas}>
            <LockablePlaceMap
              interactionEnabled={isMapInteractionEnabled}
              onEnableInteraction={() => setIsMapInteractionEnabled(true)}
              onSelectPoint={setSelectedPlaceId}
              points={visibleMapPlaces}
              selectedPointId={selectedPlace?.id}
              style={styles.interactiveMap}
            />
          </View>
        </SafeAreaView>
      </Modal>
      <MapConfirmationModal
        busy={Boolean(endingLiveFairId)}
        confirmLabel="Encerrar feira"
        message={pendingFairEnd
          ? `${pendingFairEnd.name} sairá imediatamente do mapa e continuará disponível no Histórico.`
          : ""}
        onCancel={() => setPendingFairEnd(null)}
        onConfirm={() => {
          if (pendingFairEnd) void finishLiveFair(pendingFairEnd);
        }}
        title="Encerrar feira agora?"
        visible={pendingFairEnd !== null}
      />
      <MapConfirmationModal
        busy={Boolean(deletingPlaceId)}
        confirmLabel="Excluir ponto"
        message={pendingPlaceDelete
          ? `${pendingPlaceDelete.nome} e seu ícone serão removidos do mapa público. Depois você poderá publicar outro ponto.`
          : ""}
        onCancel={() => setPendingPlaceDelete(null)}
        onConfirm={() => {
          if (pendingPlaceDelete) void removeCuratedPlace(pendingPlaceDelete);
        }}
        title="Excluir ponto do mapa?"
        visible={pendingPlaceDelete !== null}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  content: { backgroundColor: colors.background, flexGrow: 1, padding: 16, paddingBottom: 34 },
  viewTabs: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 8, marginBottom: 14, padding: 5 },
  viewTab: { alignItems: "center", borderRadius: radius.small, flex: 1, flexDirection: "row", gap: 7, justifyContent: "center", minHeight: 48, paddingHorizontal: 12 },
  viewTabActive: { backgroundColor: colors.primary },
  viewTabText: { color: colors.primary, fontSize: 14, fontWeight: "900" },
  viewTabTextActive: { color: colors.surface },
  viewTabBadge: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 10, justifyContent: "center", minHeight: 20, minWidth: 20, paddingHorizontal: 5 },
  viewTabBadgeActive: { backgroundColor: colors.accent },
  viewTabBadgeText: { color: colors.primary, fontSize: 10, fontWeight: "900" },
  viewTabBadgeTextActive: { color: colors.surface },
  routesContent: { flex: 1 },
  routesIntro: { alignItems: "center", backgroundColor: colors.primaryDark, borderRadius: radius.medium, flexDirection: "row", gap: 13, padding: 17 },
  routesIntroIcon: { alignItems: "center", backgroundColor: colors.accent, borderRadius: 26, height: 52, justifyContent: "center", width: 52 },
  routesIntroText: { flex: 1 },
  routesTitle: { color: colors.surface, fontSize: 21, fontWeight: "900" },
  routesDescription: { color: "#D9E2FF", fontSize: 12, lineHeight: 18, marginTop: 3 },
  interestsPanel: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, marginTop: 14, padding: 14 },
  interestChips: { flexDirection: "row", flexWrap: "wrap", gap: 7, marginTop: 9 },
  interestChip: { backgroundColor: colors.cream, borderRadius: radius.pill, paddingHorizontal: 11, paddingVertical: 7 },
  interestChipText: { color: colors.primary, fontSize: 11, fontWeight: "800" },
  savedOfferCard: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 11, padding: 14 },
  savedOfferIcon: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 22, height: 44, justifyContent: "center", width: 44 },
  savedOfferText: { flex: 1 },
  savedOfferCategory: { color: colors.textMuted, fontSize: 10, fontWeight: "900" },
  savedOfferTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900", marginTop: 2 },
  savedOfferMeta: { color: colors.textMuted, fontSize: 11, marginTop: 4 },
  removeOfferButton: { alignItems: "center", backgroundColor: "#FFF0EE", borderRadius: 19, height: 38, justifyContent: "center", width: 38 },
  emptyRoutes: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, marginTop: 14, padding: 26 },
  emptyRoutesTitle: { color: colors.primaryDark, fontSize: 17, fontWeight: "900", marginTop: 9 },
  emptyRoutesText: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6, textAlign: "center" },
  emptyRoutesButton: { backgroundColor: colors.accent, borderRadius: radius.pill, marginTop: 16, paddingHorizontal: 18, paddingVertical: 11 },
  emptyRoutesButtonText: { color: colors.surface, fontSize: 12, fontWeight: "900" },
  hero: {
    backgroundColor: colors.primaryDark,
    borderRadius: radius.medium,
    marginBottom: 14,
    minHeight: 190,
    overflow: "hidden",
    padding: 18,
  },
  heroLabel: { color: colors.accentSoft, fontSize: 11, fontWeight: "900", letterSpacing: 1.2 },
  heroTitle: { color: colors.surface, fontSize: 26, fontWeight: "900", lineHeight: 31, marginTop: 8, maxWidth: 330 },
  heroStats: { flexDirection: "row", gap: 8, marginTop: 20 },
  heroStat: { backgroundColor: "rgba(255,255,255,0.12)", borderRadius: radius.small, flex: 1, minHeight: 64, padding: 10 },
  heroStatValue: { color: colors.surface, fontSize: 20, fontWeight: "900" },
  heroStatLabel: { color: "#D9E2FF", fontSize: 11, fontWeight: "700", marginTop: 2 },
  searchBox: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    minHeight: 54,
    paddingHorizontal: 16,
  },
  input: { color: colors.text, flex: 1, fontSize: 14 },
  mapPanel: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, padding: 14, ...shadow },
  mapHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  mapHeaderActions: { alignItems: "center", flexDirection: "row", gap: 8 },
  sectionEyebrow: { color: colors.textMuted, fontSize: 10, fontWeight: "900", letterSpacing: 1 },
  sectionTitle: { color: colors.primaryDark, fontSize: 18, fontWeight: "900" },
  mapCount: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 18, height: 36, justifyContent: "center", width: 36 },
  mapCountText: { color: colors.primary, fontSize: 13, fontWeight: "900" },
  maximizeMapButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.primary,
    borderRadius: radius.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 5,
    minHeight: 36,
    paddingHorizontal: 11,
  },
  maximizeMapButtonText: { color: colors.primary, fontSize: 10, fontWeight: "900", letterSpacing: 0.4 },
  mapCanvas: { backgroundColor: "#E8F2EF", borderRadius: radius.small, height: 280, marginTop: 12, overflow: "hidden", position: "relative" },
  lockableMap: { backgroundColor: "#E8F2EF", overflow: "hidden", position: "relative" },
  interactiveMap: { bottom: 0, left: 0, position: "absolute", right: 0, top: 0 },
  mapInteractionOverlay: {
    alignItems: "center",
    backgroundColor: "rgba(15, 46, 110, 0.18)",
    bottom: 0,
    justifyContent: "center",
    left: 0,
    padding: 18,
    position: "absolute",
    right: 0,
    top: 0,
    zIndex: 4,
  },
  mapInteractionPrompt: {
    alignItems: "center",
    backgroundColor: "rgba(15, 46, 110, 0.92)",
    borderColor: "rgba(255, 255, 255, 0.72)",
    borderRadius: radius.medium,
    borderWidth: 1,
    maxWidth: 350,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  mapInteractionPromptTitle: { color: colors.surface, fontSize: 14, fontWeight: "900", marginTop: 7, textAlign: "center" },
  mapInteractionPromptText: { color: "#D9E2FF", fontSize: 11, lineHeight: 16, marginTop: 4, textAlign: "center" },
  openCityMapButton: {
    alignItems: "center",
    backgroundColor: "rgba(255, 255, 255, 0.94)",
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 5,
    minHeight: 34,
    paddingHorizontal: 10,
    position: "absolute",
    right: 10,
    top: 10,
    zIndex: 5,
  },
  openCityMapText: { color: colors.primary, fontSize: 11, fontWeight: "900" },
  maximizedMapSafeArea: { backgroundColor: colors.surface, flex: 1 },
  maximizedMapHeader: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 72,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  maximizedMapTitleBox: { flex: 1, marginRight: 12 },
  maximizedMapHeaderActions: { alignItems: "center", flexDirection: "row", gap: 8 },
  closeMaximizedMapButton: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: radius.pill,
    flexDirection: "row",
    gap: 6,
    minHeight: 38,
    paddingHorizontal: 13,
  },
  closeMaximizedMapButtonText: { color: colors.surface, fontSize: 10, fontWeight: "900", letterSpacing: 0.4 },
  maximizedMapCanvas: { backgroundColor: "#E8F2EF", flex: 1, overflow: "hidden", position: "relative" },
  selectedBar: {
    alignItems: "center",
    backgroundColor: colors.background,
    borderRadius: radius.small,
    flexDirection: "row",
    gap: 10,
    marginTop: 12,
    minHeight: 64,
    padding: 10,
  },
  selectedDot: { borderRadius: 7, height: 14, width: 14 },
  selectedTextBox: { flex: 1 },
  selectedCategory: { color: colors.textMuted, fontSize: 10, fontWeight: "900" },
  selectedName: { color: colors.primaryDark, fontSize: 14, fontWeight: "900", marginTop: 2 },
  routeIconButton: { alignItems: "center", backgroundColor: colors.accent, borderRadius: 20, height: 40, justifyContent: "center", width: 40 },
  highlightButtons: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 14 },
  highlightButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 7,
    height: 40,
    paddingHorizontal: 13,
  },
  highlightDot: { borderRadius: 6, height: 12, width: 12 },
  highlightText: { color: colors.text, fontSize: 12, fontWeight: "900" },
  highlightTextActive: { color: colors.surface },
  listHeader: { alignItems: "center", flexDirection: "row", justifyContent: "space-between", marginTop: 18 },
  listCount: { color: colors.textMuted, fontSize: 12, fontWeight: "700" },
  list: { gap: 12, marginTop: 12 },
  placeCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, padding: 14 },
  placeCardSelected: { borderColor: colors.accent, borderWidth: 2 },
  placeHeader: { alignItems: "center", flexDirection: "row", gap: 10 },
  placeIcon: { alignItems: "center", borderRadius: 22, height: 44, justifyContent: "center", width: 44 },
  placeTitleBox: { flex: 1 },
  placeCategory: { color: colors.textMuted, fontSize: 10, fontWeight: "900", letterSpacing: 0.6 },
  placeTitle: { color: colors.primaryDark, fontSize: 16, fontWeight: "900", marginTop: 2 },
  scoreBadge: { alignItems: "center", backgroundColor: colors.cream, borderRadius: radius.small, minWidth: 48, paddingHorizontal: 8, paddingVertical: 6 },
  scoreValue: { color: colors.accent, fontSize: 16, fontWeight: "900" },
  scoreLabel: { color: colors.textMuted, fontSize: 9, fontWeight: "700" },
  placeSummary: { color: colors.text, fontSize: 13, lineHeight: 18, marginTop: 12 },
  placeAddress: { color: colors.textMuted, fontSize: 12, lineHeight: 17, marginTop: 8 },
  metrics: { flexDirection: "row", gap: 8, marginTop: 12 },
  metric: { backgroundColor: colors.background, borderRadius: radius.small, flex: 1, padding: 10 },
  metricLabel: { color: colors.textMuted, fontSize: 10, fontWeight: "800" },
  metricValue: { color: colors.primaryDark, fontSize: 12, fontWeight: "900", marginTop: 3 },
  tagRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 12 },
  tagChip: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderRadius: radius.pill,
    height: 30,
    justifyContent: "center",
    maxWidth: 172,
    paddingHorizontal: 10,
  },
  tagText: { color: colors.primary, fontSize: 10, fontWeight: "800", lineHeight: 13 },
  cardActions: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 14 },
  actionButton: {
    alignItems: "center",
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 5,
    paddingHorizontal: 11,
    paddingVertical: 9,
  },
  actionButtonSaved: { backgroundColor: "#FFF0EE", borderColor: "#F2B8B5" },
  actionText: { color: colors.primary, fontSize: 11, fontWeight: "800" },
  actionTextSaved: { color: colors.danger },
  cloudStatus: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 10 },
  cloudStatusError: { color: colors.danger },
  empty: { color: colors.textMuted, paddingVertical: 36, textAlign: "center" },
  liveFairsPanel: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    marginTop: 18,
    padding: 14,
  },
  liveFairsHeader: { alignItems: "flex-start", flexDirection: "row", gap: 12, justifyContent: "space-between" },
  liveFairsCount: { alignItems: "center", backgroundColor: "#FFF0E6", borderRadius: 20, height: 40, justifyContent: "center", width: 40 },
  liveFairsCountText: { color: colors.accent, fontSize: 14, fontWeight: "900" },
  fairListTabs: { flexDirection: "row", gap: 8, marginTop: 10 },
  fairListTab: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    minHeight: 38,
    paddingHorizontal: 14,
    justifyContent: "center",
  },
  fairListTabActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  fairListTabText: { color: colors.primary, fontSize: 11, fontWeight: "900" },
  fairListTabTextActive: { color: colors.surface },
  liveFairsHint: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 8 },
  liveFairsList: { gap: 10, marginTop: 12 },
  emptyLiveFairs: { color: colors.textMuted, paddingVertical: 18, textAlign: "center" },
  liveFairCard: { backgroundColor: colors.background, borderColor: colors.border, borderRadius: radius.small, borderWidth: 1, padding: 13 },
  liveFairCover: { backgroundColor: colors.cream, borderRadius: radius.small, height: 180, marginBottom: 12, width: "100%" },
  liveFairCardHeader: { alignItems: "flex-start", flexDirection: "row", gap: 10, justifyContent: "space-between" },
  liveFairCardTitleBox: { flex: 1 },
  liveFairStatus: { alignSelf: "flex-start", borderRadius: radius.pill, fontSize: 9, fontWeight: "900", overflow: "hidden", paddingHorizontal: 9, paddingVertical: 5 },
  liveFairStatusLive: { backgroundColor: "#DDF7E8", color: "#116B43" },
  liveFairStatusScheduled: { backgroundColor: "#E7EEFF", color: colors.primary },
  liveFairStatusEnded: { backgroundColor: "#ECECEC", color: "#5C5C5C" },
  liveFairName: { color: colors.primaryDark, fontSize: 16, fontWeight: "900", marginTop: 7 },
  liveFairOwner: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  liveFairAddress: { color: colors.text, fontSize: 12, lineHeight: 18, marginTop: 10 },
  liveFairCountdown: { color: colors.accent, fontSize: 12, fontWeight: "900", marginTop: 8 },
  liveFairSchedule: { flexDirection: "row", gap: 8, marginTop: 10 },
  liveFairScheduleItem: { backgroundColor: colors.surface, borderRadius: radius.small, flex: 1, padding: 9 },
  liveFairScheduleValue: { color: colors.primaryDark, fontSize: 11, fontWeight: "800", lineHeight: 16, marginTop: 3 },
  endLiveFairButton: { alignItems: "center", backgroundColor: colors.danger, borderRadius: radius.pill, flexDirection: "row", gap: 5, paddingHorizontal: 11, paddingVertical: 9 },
  endLiveFairButtonText: { color: colors.surface, fontSize: 11, fontWeight: "900" },
  manualPanel: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    gap: 10,
    marginTop: 20,
    padding: 14,
  },
  manualTitle: { color: colors.primaryDark, fontSize: 17, fontWeight: "900" },
  manualHint: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  ownPlaceCard: {
    alignItems: "center",
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radius.small,
    borderWidth: 1,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
    padding: 13,
  },
  ownPlaceCopy: { flex: 1, minWidth: 200 },
  ownPlaceName: { color: colors.primaryDark, fontSize: 14, fontWeight: "900" },
  ownPlaceAddress: { color: colors.textMuted, fontSize: 11, lineHeight: 17, marginTop: 3 },
  legacyPlaceWarning: { color: colors.danger, fontSize: 10, fontWeight: "800", marginTop: 5 },
  deletePlaceButton: {
    alignItems: "center",
    backgroundColor: colors.danger,
    borderRadius: radius.pill,
    flexDirection: "row",
    gap: 6,
    minHeight: 40,
    paddingHorizontal: 14,
  },
  deletePlaceButtonText: { color: colors.surface, fontSize: 11, fontWeight: "900" },
  manualInput: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radius.small,
    borderWidth: 1,
    color: colors.text,
    minHeight: 48,
    paddingHorizontal: 12,
  },
  manualCoordinates: { flexDirection: "row", gap: 10 },
  manualCoordinateInput: { flex: 1 },
  liveFairForm: { borderColor: "#F3B487" },
  locationButton: { alignItems: "center", backgroundColor: "#EAF0FF", borderColor: "#B9C9F3", borderRadius: radius.pill, borderWidth: 1, flexDirection: "row", gap: 7, justifyContent: "center", minHeight: 44 },
  locationButtonText: { color: colors.primary, fontSize: 12, fontWeight: "900" },
  liveFairDateInputs: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  liveFairDateField: { flex: 1, minWidth: 220 },
  liveFairInputLabel: { color: colors.textMuted, fontSize: 10, fontWeight: "800", marginBottom: 5 },
  liveFairFormNote: { color: colors.textMuted, fontSize: 10, lineHeight: 15 },
  saveLiveFairButton: { alignItems: "center", backgroundColor: "#D94F04", borderRadius: radius.pill, flexDirection: "row", gap: 7, justifyContent: "center", minHeight: 46 },
  manualCategories: { gap: 8, paddingVertical: 2 },
  manualCategory: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  manualCategoryText: { color: colors.primaryDark, fontSize: 10, fontWeight: "900" },
  manualCategoryTextActive: { color: colors.surface },
  saveManualButton: {
    alignItems: "center",
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
    flexDirection: "row",
    gap: 7,
    justifyContent: "center",
    minHeight: 46,
  },
  saveManualButtonDisabled: { opacity: 0.55 },
  saveManualText: { color: colors.surface, fontSize: 13, fontWeight: "900" },
  confirmModalBackdrop: {
    alignItems: "center",
    backgroundColor: "rgba(2, 24, 68, 0.68)",
    flex: 1,
    justifyContent: "center",
    padding: 20,
  },
  confirmModalCard: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.large,
    gap: 12,
    maxWidth: 520,
    padding: 22,
    width: "100%",
    ...shadow,
  },
  confirmModalIcon: {
    alignItems: "center",
    backgroundColor: colors.danger,
    borderRadius: 28,
    height: 56,
    justifyContent: "center",
    width: 56,
  },
  confirmModalTitle: { color: colors.primaryDark, fontSize: 19, fontWeight: "900", textAlign: "center" },
  confirmModalMessage: { color: colors.textMuted, fontSize: 13, lineHeight: 20, textAlign: "center" },
  confirmModalActions: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 4, width: "100%" },
  confirmModalButton: { alignItems: "center", borderRadius: radius.pill, flex: 1, justifyContent: "center", minHeight: 46, minWidth: 150 },
  confirmModalSecondary: { backgroundColor: colors.surfaceMuted, borderColor: colors.border, borderWidth: 1 },
  confirmModalDanger: { backgroundColor: colors.danger },
  confirmModalSecondaryText: { color: colors.primaryDark, fontSize: 12, fontWeight: "900" },
  confirmModalDangerText: { color: colors.surface, fontSize: 12, fontWeight: "900" },
});
