import { useEffect } from "react";
import { Modal, ScrollView, StyleSheet, Text, View } from "react-native";
import QRCode from "react-native-qrcode-svg";
import { AppButton } from "@/components/ui";
import { showStaffAlert } from "@/components/staff-panel-ui";
import { colors, radius, shadow } from "@/constants/theme";
import type { CouponQrResult } from "@/security/trq-bec/contracts";
import { getOwnLiveOfferQr, listOwnLiveOffers } from "@/security/trq-bec/service";
import { formatRemainingTime, hasTimeEnded } from "@/utils/time";

export function SaleQrModal({ result, nowMs, onChange, onInventoryChanged }: {
  result: CouponQrResult | null;
  nowMs: number;
  onChange: (result: CouponQrResult | null) => void;
  onInventoryChanged?: () => void;
}) {
  const offerId = result?.offer.offer_id;
  const quantity = result?.offer.purchase_quantity || 1;
  const redeemedCount = result?.offer.redeemed_count;
  useEffect(() => {
    if (!offerId) return undefined;
    let isActive = true;
    let isChecking = false;
    const interval = setInterval(async () => {
      if (isChecking) return;
      isChecking = true;
      try {
        const currentOffer = (await listOwnLiveOffers()).find((offer) => offer.offer_id === offerId);
        if (!isActive) return;
        if (currentOffer && currentOffer.redeemed_count > (redeemedCount ?? 0)) {
          onChange(null);
          onInventoryChanged?.();
          return;
        }
        const currentQr = await getOwnLiveOfferQr(offerId, quantity);
        if (currentQr.offer.status !== "ACTIVE") {
          throw new Error("A oferta está pausada. Reative-a antes de gerar o QR para vender.");
        }
        if (isActive) {
          onChange(currentQr);
          if (currentQr.offer.redeemed_count !== redeemedCount) onInventoryChanged?.();
        }
      } catch (error) {
        if (isActive) {
          onChange(null);
          onInventoryChanged?.();
          showStaffAlert("QR indisponível", error instanceof Error ? error.message : "Atualize as ofertas e tente novamente.");
        }
      } finally {
        isChecking = false;
      }
    }, 5_000);
    return () => { isActive = false; clearInterval(interval); };
  }, [offerId, onChange, onInventoryChanged, quantity, redeemedCount]);

  function closeQr() {
    onChange(null);
    onInventoryChanged?.();
  }

  const total = result
    ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: result.offer.currency })
      .format(result.offer.final_amount_minor * quantity / 100)
    : "";
  return (
    <Modal animationType="fade" onRequestClose={closeQr} transparent visible={result !== null}>
      <View style={styles.overlay}>
        <View accessibilityViewIsModal style={styles.card}>
          <ScrollView contentContainerStyle={styles.content}>
            <Text style={styles.title}>QR para venda</Text>
            <Text style={styles.message}>{result?.offer.product_title}</Text>
            {result && result.offer.status === "ACTIVE" && !hasTimeEnded(result.expiresAt * 1_000, nowMs) ? (
              <View style={styles.qrSurface}>
                <QRCode value={result.qrValue} size={210} quietZone={12} ecl="M" color={colors.primaryDark} backgroundColor={colors.surface} />
              </View>
            ) : (
              <Text style={styles.error}>Este QR não está disponível. Atualize as ofertas para continuar vendendo.</Text>
            )}
            {result ? (
              <>
                <Text style={styles.message}>{quantity} unidade(s) · total {total}</Text>
                <Text style={styles.hint}>Válido por {formatRemainingTime(result.expiresAt * 1_000, nowMs)}</Text>
                <Text style={styles.message}>
                  O visitante deve abrir Cupons &gt; Abrir leitor de QR Code para confirmar a compra. O estoque só é baixado após essa confirmação. Este QR não realiza pagamento Pix.
                </Text>
              </>
            ) : null}
          </ScrollView>
          <AppButton onPress={closeQr}>Fechar QR Code</AppButton>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { alignItems: "center", backgroundColor: "rgba(2, 24, 68, 0.62)", flex: 1, justifyContent: "center", padding: 20 },
  card: { backgroundColor: colors.surface, borderRadius: radius.large, gap: 12, maxHeight: "90%", maxWidth: 460, padding: 20, width: "100%", ...shadow },
  content: { alignItems: "center", gap: 12 },
  title: { color: colors.primaryDark, fontSize: 19, fontWeight: "900", textAlign: "center" },
  message: { color: colors.textMuted, fontSize: 13, lineHeight: 20, textAlign: "center" },
  hint: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
  error: { color: colors.danger, fontSize: 12, lineHeight: 18 },
  qrSurface: { alignItems: "center", backgroundColor: colors.surface, padding: 8 },
});
