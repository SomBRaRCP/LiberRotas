import { Ionicons } from "@expo/vector-icons";
import { router, type Href, useFocusEffect } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { BrandHeader } from "@/components/brand-header";
import { AppButton } from "@/components/ui";
import { colors, radius } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import { useTrustedClock } from "@/context/trusted-clock-context";
import type { CatalogOfferSummary, CatalogProductItem } from "@/security/trq-bec/contracts";
import { listPublicCatalogFeed } from "@/security/trq-bec/service";
import { profileSharePath, shareLiberRotasItem } from "@/utils/share";
import { formatRemainingTime, hasTimeEnded } from "@/utils/time";

type PublicOfferItem = {
  offer: CatalogOfferSummary;
  product: CatalogProductItem;
};

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

function offerStatusLabel(offer: CatalogOfferSummary, referenceTimeMs: number) {
  if (offer.status === "ACTIVE" && hasTimeEnded(offer.expires_at * 1_000, referenceTimeMs)) {
    return "OFERTA ENCERRADA · validade atingida";
  }
  if (offer.status === "ACTIVE") return "OFERTA ATIVA";
  if (offer.status === "PAUSED") return "OFERTA PAUSADA";
  const reasons: Record<Exclude<CatalogOfferSummary["status_reason"], null>, string> = {
    PAUSED: "pausada pelo empreendedor",
    PRODUCT_PAUSED: "produto pausado",
    CANCELLED: "encerrada pelo empreendedor",
    EXHAUSTED: "limite de resgates atingido",
    EXPIRED: "validade encerrada",
    OUT_OF_STOCK: "estoque encerrado",
  };
  return `OFERTA ENCERRADA · ${offer.status_reason ? reasons[offer.status_reason] : "finalizada"}`;
}

/**
 * Catálogo público de ofertas e pontos de entrada para emissão e resgate.
 *
 * As condições comerciais vêm exclusivamente do PostgreSQL por meio do
 * backend TRQ-BEC. O catálogo não recebe QR, token ou material criptográfico;
 * o resgate continua sendo iniciado pelo leitor de QR Code.
 */
export default function CouponsScreen() {
  const { accessSession, hasPermission } = useApp();
  const { nowMs } = useTrustedClock();
  const isEntrepreneur = accessSession?.role === "entrepreneur" && hasPermission("marketplace.manage");
  const canRedeemCoupons = accessSession?.role === "visitor" && hasPermission("coupons.redeem");
  const [catalogItems, setCatalogItems] = useState<CatalogProductItem[] | null>(null);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState(false);
  const [catalogError, setCatalogError] = useState("");

  useFocusEffect(
    useCallback(() => {
      let isActive = true;
      setIsLoadingCatalog(true);
      setCatalogError("");

      listPublicCatalogFeed()
        .then((items) => {
          if (isActive) setCatalogItems(items);
        })
        .catch((error) => {
          if (!isActive) return;
          setCatalogError(error instanceof Error ? error.message : "Não foi possível carregar as ofertas ao vivo.");
        })
        .finally(() => {
          if (isActive) setIsLoadingCatalog(false);
        });

      return () => {
        isActive = false;
      };
    }, []),
  );

  const publicOffers = useMemo<PublicOfferItem[]>(
    () => (catalogItems || [])
      .flatMap((product) => product.offers.map((offer) => ({ offer, product })))
      .sort((left, right) => (
        (right.offer.ended_at || right.offer.created_at)
        - (left.offer.ended_at || left.offer.created_at)
      )),
    [catalogItems],
  );

  function openMerchantProfile(firebaseUid: string) {
    router.push({ pathname: "/profile/[profileId]", params: { profileId: firebaseUid } } as unknown as Href);
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <BrandHeader subtitle="benefícios locais" title="Cupons" />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.heading}>{isEntrepreneur ? "Gestão e ofertas ao vivo" : "Ofertas ao vivo"}</Text>
        <Text style={styles.lead}>
          Consulte ofertas ativas, pausadas e encerradas. Somente ofertas ativas podem ser resgatadas pelo leitor de QR.
        </Text>

        <Text style={styles.sectionTitle}>Ofertas publicadas</Text>
        {isLoadingCatalog ? <Text style={styles.statusText}>Atualizando catálogo...</Text> : null}
        {catalogError ? <Text style={styles.errorText}>{catalogError}</Text> : null}
        <View style={styles.list}>
          {publicOffers.map(({ offer, product }) => {
            const timeEnded = hasTimeEnded(offer.expires_at * 1_000, nowMs);
            const isEffectivelyEnded = offer.status === "ENDED" || timeEnded;
            return (
              <Pressable
              accessibilityHint="Abre o perfil público do empreendedor"
              accessibilityRole="link"
              key={offer.offer_id}
              onPress={() => openMerchantProfile(product.merchant.firebase_uid)}
              style={({ pressed }) => [
                styles.offerCard,
                isEffectivelyEnded && styles.offerCardEnded,
                pressed && styles.offerCardPressed,
              ]}
            >
              <View style={[styles.offerIcon, (offer.status !== "ACTIVE" || timeEnded) && styles.offerIconInactive]}>
                <Ionicons color={colors.surface} name="pricetag" size={22} />
              </View>
              <View style={styles.offerText}>
                <Text style={[styles.offerStatus, isEffectivelyEnded && styles.offerStatusEnded]}>
                  {offerStatusLabel(offer, nowMs)}
                </Text>
                <Text style={styles.offerTitle}>{product.title}</Text>
                <Text style={styles.offerMerchant}>
                  {product.merchant.display_name} · {product.merchant.establishment_name}
                </Text>
                <View style={styles.priceRow}>
                  <Text style={styles.originalPrice}>{formatMoney(offer.original_amount_minor, offer.currency)}</Text>
                  <Text style={styles.finalPrice}>{formatMoney(offer.final_amount_minor, offer.currency)}</Text>
                </View>
                <Text style={styles.offerMeta}>
                  Economize {formatMoney(offer.discount_amount_minor, offer.currency)} · {offer.remaining_redemptions} disponível(is)
                </Text>
                <Text style={styles.offerMeta}>
                  {offer.status === "ENDED" && offer.ended_at
                    ? `Encerrada em ${formatExpiration(offer.ended_at)}`
                    : timeEnded
                      ? `Validade encerrada em ${formatExpiration(offer.expires_at)}`
                      : `Termina em ${formatRemainingTime(offer.expires_at * 1_000, nowMs)} · ${formatExpiration(offer.expires_at)}`}
                </Text>
                <Pressable
                  accessibilityLabel={`Compartilhar oferta ${product.title}`}
                  accessibilityRole="button"
                  onPress={(event) => {
                    event.stopPropagation();
                    void shareLiberRotasItem({
                      kind: "offer",
                      title: product.title,
                      description: `${formatMoney(offer.final_amount_minor, offer.currency)} · ${offer.remaining_redemptions} disponível(is) · ${product.merchant.display_name}`,
                      path: profileSharePath(product.merchant.firebase_uid, { tab: "offers", itemId: offer.offer_id }),
                    });
                  }}
                  style={styles.shareButton}
                >
                  <Ionicons color={colors.primary} name="share-social-outline" size={15} />
                  <Text style={styles.shareButtonText}>Compartilhar</Text>
                </Pressable>
              </View>
              <Ionicons color={colors.primary} name="chevron-forward" size={20} />
              </Pressable>
            );
          })}
        </View>
        {catalogItems !== null && publicOffers.length === 0 && !isLoadingCatalog ? (
          <Text style={styles.emptyText}>Nenhuma oferta pública foi encontrada.</Text>
        ) : null}

        {isEntrepreneur ? (
          <>
            <View style={styles.generateCard}>
              <View style={styles.generateIcon}><Ionicons color={colors.surface} name="qr-code-outline" size={28} /></View>
              <View style={styles.scanText}>
                <Text style={styles.scanTitle}>Produtos e ofertas</Text>
                <Text style={styles.scanDescription}>Cadastre preço e estoque, emita ofertas ao vivo e acompanhe o saldo.</Text>
              </View>
            </View>
            <AppButton onPress={() => router.push("/generate-qr")}>Gerenciar produtos e ofertas</AppButton>
          </>
        ) : null}
        {canRedeemCoupons ? (
          <>
            <View style={[styles.scanCard, isEntrepreneur && styles.scanCardAfterGenerator]}>
              <View style={styles.scanIcon}><Ionicons color={colors.surface} name="qr-code" size={28} /></View>
              <View style={styles.scanText}>
                <Text style={styles.scanTitle}>Resgatar oferta</Text>
                <Text style={styles.scanDescription}>
                  Leia o QR, confira preço e desconto e confirme o resgate no backend.
                </Text>
              </View>
            </View>
            <AppButton onPress={() => router.push("/scanner")}>Abrir leitor de QR Code</AppButton>
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  content: { backgroundColor: colors.surfaceMuted, flexGrow: 1, padding: 16, paddingBottom: 32 },
  heading: { color: colors.primaryDark, fontSize: 28, fontWeight: "900" },
  lead: { color: colors.textMuted, fontSize: 13, lineHeight: 18, marginTop: 4 },
  sectionTitle: { color: colors.primaryDark, fontSize: 18, fontWeight: "900", marginBottom: 10, marginTop: 22 },
  statusText: { color: colors.textMuted, fontSize: 12, marginBottom: 10 },
  errorText: { color: colors.danger, fontSize: 12, marginBottom: 10 },
  emptyText: { color: colors.textMuted, paddingVertical: 24, textAlign: "center" },
  list: { gap: 12 },
  offerCard: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 12, padding: 14 },
  offerCardEnded: { opacity: 0.82 },
  offerCardPressed: { opacity: 0.72 },
  offerIcon: { alignItems: "center", backgroundColor: colors.accent, borderRadius: 22, height: 44, justifyContent: "center", width: 44 },
  offerIconInactive: { backgroundColor: colors.textMuted },
  offerText: { flex: 1 },
  offerStatus: { color: colors.success, fontSize: 9, fontWeight: "900", letterSpacing: 0.7, marginBottom: 3 },
  offerStatusEnded: { color: colors.textMuted },
  offerTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900" },
  offerMerchant: { color: colors.textMuted, fontSize: 11, marginTop: 3 },
  priceRow: { alignItems: "baseline", flexDirection: "row", gap: 8, marginTop: 8 },
  originalPrice: { color: colors.textMuted, fontSize: 11, textDecorationLine: "line-through" },
  finalPrice: { color: colors.primary, fontSize: 16, fontWeight: "900" },
  offerMeta: { color: colors.textMuted, fontSize: 11, marginTop: 3 },
  shareButton: { alignItems: "center", alignSelf: "flex-start", backgroundColor: colors.cream, borderColor: colors.border, borderRadius: radius.pill, borderWidth: 1, flexDirection: "row", gap: 5, marginTop: 9, minHeight: 36, paddingHorizontal: 11 },
  shareButtonText: { color: colors.primary, fontSize: 10, fontWeight: "900" },
  generateCard: { alignItems: "center", backgroundColor: "#EAF0FF", borderColor: "#BED0F8", borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 12, marginBottom: 12, marginTop: 28, padding: 14 },
  generateIcon: { alignItems: "center", backgroundColor: colors.accent, borderRadius: 24, height: 48, justifyContent: "center", width: 48 },
  scanCard: { alignItems: "center", backgroundColor: colors.cream, borderRadius: radius.medium, flexDirection: "row", gap: 12, marginBottom: 12, marginTop: 28, padding: 14 },
  scanCardAfterGenerator: { marginTop: 14 },
  scanIcon: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 24, height: 48, justifyContent: "center", width: 48 },
  scanText: { flex: 1 },
  scanTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "800" },
  scanDescription: { color: colors.textMuted, fontSize: 12, lineHeight: 16, marginTop: 3 },
});
