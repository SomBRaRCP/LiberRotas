import { Ionicons } from "@expo/vector-icons";
import { CameraView, useCameraPermissions } from "expo-camera";
import { Redirect, router, type Href } from "expo-router";
import { useRef, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { LocalClock } from "@/components/local-clock";
import { HeaderBackButton } from "@/components/header-back-button";
import { AppButton, LoadingScreen } from "@/components/ui";
import { colors, radius } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import { useTrustedClock } from "@/context/trusted-clock-context";
import type { CouponRedemptionResult, OfferPreview } from "@/security/trq-bec/contracts";
import {
  previewCouponQrGroup,
  redeemCouponQrGroup,
  TrqBecServiceError,
} from "@/security/trq-bec/service";
import { getAuthenticatedHomeDestination } from "@/utils/account-navigation";
import { formatRemainingTime, hasTimeEnded } from "@/utils/time";

function formatMoney(valueMinor: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(valueMinor / 100);
}

function formatDate(unixSeconds: number) {
  return new Date(unixSeconds * 1000).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

function errorMessage(error: unknown) {
  return error instanceof TrqBecServiceError ? error.userMessage : "Não foi possível consultar o backend TRQ-BEC.";
}

type RedemptionPhase = "READY" | "AUTHORIZING" | "COMPLETED";
type CompletedRedemptionState = {
  completed: CouponRedemptionResult[];
  failureMessages: string[];
};

/**
 * Leitor da oferta presencial da Fase 1.
 *
 * A consulta não produz efeito comercial. O resgate só ocorre depois da
 * confirmação do visitante e da sequência begin + prova do dispositivo +
 * authorize no backend. Não existe autorização final offline.
 */
export default function ScannerScreen() {
  const { nowMs } = useTrustedClock();
  const [permission, requestPermission] = useCameraPermissions();
  const [scannedData, setScannedData] = useState<string | null>(null);
  const [previewOffers, setPreviewOffers] = useState<OfferPreview[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [redemptionPhase, setRedemptionPhase] = useState<RedemptionPhase>("READY");
  const [completedRedemption, setCompletedRedemption] = useState<CompletedRedemptionState | null>(null);
  const redemptionInFlight = useRef(false);
  const {
    accessDestination,
    accessSession,
    deviceApprovalRequired,
    hasFirebaseSession,
    hasPermission,
    isAuthenticated,
    isHydrated,
    isResolvingAccess,
    markCouponUsed,
  } = useApp();
  const canRedeemCoupons = accessSession?.role === "visitor" && hasPermission("coupons.redeem");
  const profileDestination = getAuthenticatedHomeDestination(accessSession?.role, accessDestination);

  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (!hasFirebaseSession) return <Redirect href={"/login" as Href} />;
  if (!isAuthenticated || accessSession?.access_state !== "AUTHORIZED") {
    return <Redirect href={"/access-pending" as Href} />;
  }
  if (accessSession.role !== "visitor") return <Redirect href={accessDestination as Href} />;
  if (deviceApprovalRequired) return <Redirect href={"/account/devices" as Href} />;
  if (!canRedeemCoupons) return <Redirect href={"/access-pending" as Href} />;

  if (!permission) {
    return <View style={styles.center}><Text style={styles.message}>Verificando permissão da câmera...</Text></View>;
  }

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.permissionScreen}>
        <View style={styles.permissionIcon}><Ionicons color={colors.surface} name="camera" size={42} /></View>
        <Text style={styles.permissionTitle}>A câmera é necessária</Text>
        <Text style={styles.message}>Permita o acesso para ler o QR Code das ofertas LiberRotas.</Text>
        <AppButton onPress={requestPermission} style={styles.permissionButton}>Permitir acesso</AppButton>
        <View style={styles.navigationButtons}>
          <HeaderBackButton fallbackHref={profileDestination} />
          <AppButton onPress={() => router.replace(profileDestination)} variant="secondary">Perfil</AppButton>
        </View>
      </SafeAreaView>
    );
  }

  async function inspectOffer() {
    if (!scannedData || isLoading) return;
    setIsLoading(true);
    try {
      setPreviewOffers(await previewCouponQrGroup(scannedData));
    } catch (error) {
      setPreviewOffers([]);
      Alert.alert("Oferta não reconhecida", errorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }

  async function confirmRedemption() {
    if (!scannedData || previewOffers.length === 0 || isLoading || redemptionInFlight.current) return;
    if (previewOffers.some((offer) => hasTimeEnded(offer.expires_at * 1_000, nowMs))) {
      Alert.alert(
        "Oferta expirada",
        "Ao menos uma oferta deste QR terminou. Peça ao vendedor para gerar um novo código somente com ofertas ativas.",
      );
      return;
    }
    redemptionInFlight.current = true;
    setRedemptionPhase("AUTHORIZING");
    try {
      const result = await redeemCouponQrGroup(scannedData);
      if (result.completed.length === 0) {
        setRedemptionPhase("READY");
        Alert.alert(
          "Resgate não autorizado",
          result.failures.map((failure) => failure.message).join("\n") || "Nenhum cupom foi autorizado.",
        );
        return;
      }

      setCompletedRedemption({
        completed: result.completed,
        failureMessages: result.failures.map((failure) => failure.message),
      });
      setRedemptionPhase("COMPLETED");

      // Firebase/AsyncStorage recebem somente um reflexo para a interface. O
      // efeito comercial de cada cupom já foi confirmado no backend.
      result.completed.forEach((completed, position) => {
        const offerId = completed.offerId || previewOffers[position]?.offer_id;
        if (!offerId) return;
        void markCouponUsed(offerId).catch((cacheError) => {
          console.warn("O resgate foi autorizado, mas o reflexo local não pôde ser salvo.", cacheError);
        });
      });
    } catch (error) {
      setRedemptionPhase("READY");
      Alert.alert("Falha no resgate", errorMessage(error));
    } finally {
      redemptionInFlight.current = false;
    }
  }

  function scanAgain() {
    redemptionInFlight.current = false;
    setRedemptionPhase("READY");
    setCompletedRedemption(null);
    setScannedData(null);
    setPreviewOffers([]);
  }

  const previewExpired = previewOffers.some((offer) => hasTimeEnded(offer.expires_at * 1_000, nowMs));
  const previewFinalTotal = previewOffers.reduce(
    (total, offer) => total + offer.final_amount_minor * (offer.purchase_quantity || 1),
    0,
  );
  const previewSavingsTotal = previewOffers.reduce(
    (total, offer) => total + offer.discount_amount_minor * (offer.purchase_quantity || 1),
    0,
  );
  const completedFinalTotal = completedRedemption?.completed.reduce((total, result) => {
    const offer = previewOffers.find((item) => item.offer_id === result.offerId);
    return total + (
      result.finalAmountMinor
      ?? (offer?.final_amount_minor ?? 0) * (offer?.purchase_quantity || 1)
    );
  }, 0) ?? 0;
  const completedSavingsTotal = completedRedemption?.completed.reduce((total, result) => {
    const offer = previewOffers.find((item) => item.offer_id === result.offerId);
    return total + (
      result.amountSavedMinor
      ?? (offer?.discount_amount_minor ?? 0) * (offer?.purchase_quantity || 1)
    );
  }, 0) ?? 0;
  const completedUnits = completedRedemption?.completed.reduce(
    (total, result) => total + (
      result.quantity
      ?? previewOffers.find((offer) => offer.offer_id === result.offerId)?.purchase_quantity
      ?? 1
    ),
    0,
  ) ?? 0;

  return (
    <View style={styles.container}>
      <CameraView
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onBarcodeScanned={scannedData || redemptionPhase !== "READY" ? undefined : ({ data }) => {
          setScannedData(data);
          setPreviewOffers([]);
        }}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView style={styles.overlay}>
        <View style={styles.topBar}>
          <HeaderBackButton disabled={redemptionPhase === "AUTHORIZING"} fallbackHref={profileDestination} />
          <Pressable
            accessibilityLabel="Abrir meu perfil"
            disabled={redemptionPhase === "AUTHORIZING"}
            onPress={() => router.replace(profileDestination)}
            style={[styles.closeButton, redemptionPhase === "AUTHORIZING" && styles.disabledControl]}
          >
            <Ionicons color={colors.primaryDark} name="person-circle-outline" size={21} />
            <Text style={styles.closeButtonText}>Perfil</Text>
          </Pressable>
          <Text style={styles.title}>Oferta TRQ-BEC</Text>
          <LocalClock />
        </View>
        {redemptionPhase === "READY" ? (
          <View style={styles.guideArea}>
            <Text style={styles.guideText}>Posicione o código dentro da moldura</Text>
            <View style={styles.frame} />
          </View>
        ) : <View />}
        <ScrollView contentContainerStyle={styles.resultContent} style={styles.resultPanel}>
          {redemptionPhase === "AUTHORIZING" ? (
            <View accessibilityLiveRegion="assertive" style={styles.statusCard}>
              <View style={styles.authorizingIcon}>
                <Ionicons color={colors.surface} name="shield-checkmark" size={38} />
              </View>
              <Text style={styles.statusTitle}>Autorizando resgate...</Text>
              <Text style={styles.statusMessage}>Aguarde a confirmação segura do LiberRotas.</Text>
            </View>
          ) : redemptionPhase === "COMPLETED" && completedRedemption ? (
            <View accessibilityLiveRegion="assertive" style={styles.statusCard}>
              <Ionicons color={colors.success} name="checkmark-circle" size={68} />
              <Text style={styles.completedTitle}>
                {completedRedemption.failureMessages.length > 0
                  ? "Resgate parcialmente concluído"
                  : "Resgate concluído"}
              </Text>
              <Text style={styles.completedProduct}>
                {completedRedemption.completed.length === 1
                  ? `${previewOffers.find((offer) => offer.offer_id === completedRedemption.completed[0].offerId)
                    ?.product_title || "Produto"} · ${completedUnits} unidade(s)`
                  : `${completedRedemption.completed.length} cupons e ${completedUnits} unidade(s) validados para o vendedor`}
              </Text>
              <Text style={styles.statusMessage}>
                Preço final total: {formatMoney(completedFinalTotal)}
                {"\n"}Economia total: {formatMoney(completedSavingsTotal)}
              </Text>
              {completedRedemption.failureMessages.length > 0 ? (
                <View style={styles.partialWarning}>
                  <Text style={styles.partialWarningTitle}>Alguns cupons não foram concluídos</Text>
                  <Text style={styles.partialWarningText}>
                    {completedRedemption.failureMessages.join("\n")}
                  </Text>
                </View>
              ) : null}
              <View style={styles.navigationButtons}>
                <HeaderBackButton fallbackHref={profileDestination} />
                <AppButton onPress={() => router.replace(profileDestination)}>Perfil</AppButton>
              </View>
            </View>
          ) : scannedData ? (
            <>
              {previewOffers.length > 0 ? (
                <View style={styles.previewList}>
                  {previewOffers.length > 1 ? (
                    <View style={styles.bundleSummary}>
                      <Text style={styles.bundleSummaryTitle}>{previewOffers.length} cupons neste QR</Text>
                      <Text style={styles.bundleSummaryValue}>
                        Total: {formatMoney(previewFinalTotal)} · economia {formatMoney(previewSavingsTotal)}
                      </Text>
                    </View>
                  ) : null}
                  {previewOffers.map((preview, index) => (
                    <View key={preview.offer_id} style={styles.previewCard}>
                      <Text style={styles.resultTitle}>
                        {previewOffers.length > 1 ? `${index + 1}. ` : ""}{preview.product_title}
                      </Text>
                      <Text style={styles.merchant}>{preview.establishment_name} · {preview.merchant_name}</Text>
                      <View style={styles.priceRow}>
                        <Text style={styles.oldPrice}>
                          {formatMoney(preview.original_amount_minor * (preview.purchase_quantity || 1))}
                        </Text>
                        <Text style={styles.newPrice}>
                          {formatMoney(preview.final_amount_minor * (preview.purchase_quantity || 1))}
                        </Text>
                      </View>
                      <Text style={styles.purchaseQuantity}>
                        Compra: {preview.purchase_quantity || 1} unidade(s) · preço unitário {formatMoney(preview.final_amount_minor)}
                      </Text>
                      <Text style={styles.savings}>
                        Você economiza {formatMoney(preview.discount_amount_minor * (preview.purchase_quantity || 1))}
                      </Text>
                      <Text style={styles.details}>
                        {preview.remaining_redemptions} unidade(s) disponível(is) · {hasTimeEnded(preview.expires_at * 1_000, nowMs)
                          ? `expirou em ${formatDate(preview.expires_at)}`
                          : `restam ${formatRemainingTime(preview.expires_at * 1_000, nowMs)} · expira ${formatDate(preview.expires_at)}`}
                      </Text>
                    </View>
                  ))}
                  {previewOffers.length > 1 ? (
                    <Text style={styles.bundleNotice}>
                      Uma confirmação valida cada oferta separadamente. O vendedor recebe {previewOffers.length} vendas.
                    </Text>
                  ) : null}
                </View>
              ) : (
                <>
                  <Text style={styles.resultTitle}>Código encontrado</Text>
                  <Text numberOfLines={2} style={styles.resultData}>{scannedData}</Text>
                </>
              )}

              {previewOffers.length > 0 ? (
                <AppButton disabled={isLoading || previewExpired} onPress={confirmRedemption}>
                  {previewExpired
                    ? "Há uma oferta expirada"
                    : previewOffers.length > 1
                      ? `Confirmar ${previewOffers.length} cupons`
                      : "Confirmar resgate"}
                </AppButton>
              ) : (
                <AppButton disabled={isLoading} onPress={inspectOffer}>
                  {isLoading ? "Consultando o backend..." : "Consultar oferta"}
                </AppButton>
              )}
              <AppButton disabled={isLoading} onPress={scanAgain} variant="secondary">Ler outro código</AppButton>
            </>
          ) : (
            <Text style={styles.waiting}>Aguardando leitura...</Text>
          )}
        </ScrollView>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: "#000", flex: 1 },
  center: { alignItems: "center", backgroundColor: colors.background, flex: 1, justifyContent: "center", padding: 24 },
  permissionScreen: { alignItems: "center", backgroundColor: colors.background, flex: 1, justifyContent: "center", padding: 28 },
  permissionIcon: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 40, height: 80, justifyContent: "center", width: 80 },
  permissionTitle: { color: colors.primaryDark, fontSize: 24, fontWeight: "900", marginTop: 22 },
  message: { color: colors.textMuted, fontSize: 14, lineHeight: 20, marginTop: 10, textAlign: "center" },
  permissionButton: { marginTop: 24, width: "100%" },
  overlay: { flex: 1, justifyContent: "space-between" },
  topBar: { alignItems: "center", flexDirection: "row", gap: 8, padding: 18 },
  closeButton: { alignItems: "center", backgroundColor: colors.surface, borderRadius: 22, flexDirection: "row", gap: 5, minHeight: 44, paddingHorizontal: 10 },
  closeButtonText: { color: colors.primaryDark, fontSize: 11, fontWeight: "900" },
  disabledControl: { opacity: 0.45 },
  title: { color: colors.surface, flex: 1, fontSize: 18, fontWeight: "800" },
  guideArea: { alignItems: "center" },
  guideText: { color: colors.surface, fontSize: 14, fontWeight: "700", marginBottom: 18 },
  frame: { borderColor: colors.accent, borderRadius: radius.large, borderWidth: 4, height: 220, width: 220 },
  resultPanel: { backgroundColor: colors.background, borderTopLeftRadius: 28, borderTopRightRadius: 28, maxHeight: "58%" },
  resultContent: { gap: 10, minHeight: 190, padding: 24 },
  previewList: { gap: 10 },
  previewCard: { backgroundColor: colors.surface, borderRadius: radius.medium, gap: 5, padding: 14 },
  bundleSummary: { backgroundColor: "#E8F1FF", borderRadius: radius.medium, gap: 3, padding: 12 },
  bundleSummaryTitle: { color: colors.primaryDark, fontSize: 17, fontWeight: "900" },
  bundleSummaryValue: { color: colors.primary, fontSize: 13, fontWeight: "800" },
  bundleNotice: { color: colors.textMuted, fontSize: 11, lineHeight: 16, textAlign: "center" },
  resultTitle: { color: colors.primaryDark, fontSize: 18, fontWeight: "800" },
  resultData: { color: colors.textMuted, fontSize: 12, marginBottom: 4 },
  merchant: { color: colors.textMuted, fontSize: 11 },
  priceRow: { alignItems: "baseline", flexDirection: "row", gap: 10, marginTop: 4 },
  oldPrice: { color: colors.textMuted, fontSize: 12, textDecorationLine: "line-through" },
  newPrice: { color: colors.accent, fontSize: 24, fontWeight: "900" },
  purchaseQuantity: { color: colors.primaryDark, fontSize: 11, fontWeight: "800" },
  savings: { color: colors.success, fontSize: 12, fontWeight: "800" },
  details: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
  statusCard: { alignItems: "center", gap: 8, justifyContent: "center", minHeight: 220, paddingVertical: 12 },
  authorizingIcon: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 34, height: 68, justifyContent: "center", width: 68 },
  statusTitle: { color: colors.primaryDark, fontSize: 22, fontWeight: "900", marginTop: 6 },
  completedTitle: { color: colors.success, fontSize: 24, fontWeight: "900", textAlign: "center" },
  completedProduct: { color: colors.primaryDark, fontSize: 16, fontWeight: "800", textAlign: "center" },
  statusMessage: { color: colors.textMuted, fontSize: 13, lineHeight: 19, textAlign: "center" },
  partialWarning: { backgroundColor: "#FFF4DC", borderColor: colors.accent, borderRadius: radius.medium, borderWidth: 1, padding: 12, width: "100%" },
  partialWarningTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: "900" },
  partialWarningText: { color: colors.textMuted, fontSize: 12, lineHeight: 17, marginTop: 4 },
  navigationButtons: { alignItems: "center", flexDirection: "row", gap: 10, marginTop: 8 },
  waiting: { color: colors.textMuted, fontSize: 14, textAlign: "center" },
});
