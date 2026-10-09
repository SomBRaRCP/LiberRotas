import { useFocusEffect } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SaleQrModal } from "@/components/sale-qr-modal";
import { showStaffAlert } from "@/components/staff-panel-ui";
import { AppButton, FormField } from "@/components/ui";
import { colors, radius } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import { useTrustedClock } from "@/context/trusted-clock-context";
import { canGenerateSaleQr, fundedEventsForOffer, fundedProductTotals } from "@/features/marketplace/seller-coupons";
import type { CouponQrResult, MarketplaceProduct, OfferPreview } from "@/security/trq-bec/contracts";
import {
  getOwnLiveOfferQr, listOwnLiveOffers, listOwnMarketplaceProducts,
  listEntrepreneurFundedEvents, listEntrepreneurInstitutionMemberships,
  loadEntrepreneurFundedEventReport,
  type EntrepreneurFundedEvent, type EntrepreneurFundedEventReport, type InstitutionMembership,
} from "@/security/trq-bec/service";
import { auth } from "@/services/firebase";
import { formatRemainingTime } from "@/utils/time";

export function EntrepreneurCoupons() {
  const { hasPermission } = useApp();
  const { nowMs } = useTrustedClock();
  const canReadFunding = hasPermission("institution.event_allocations.manage");
  const canReadMemberships = hasPermission("institution.memberships.respond");
  const [offers, setOffers] = useState<OfferPreview[]>([]);
  const [products, setProducts] = useState<MarketplaceProduct[]>([]);
  const [events, setEvents] = useState<EntrepreneurFundedEvent[]>([]);
  const [memberships, setMemberships] = useState<InstitutionMembership[]>([]);
  const [reports, setReports] = useState<EntrepreneurFundedEventReport[]>([]);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [qrResult, setQrResult] = useState<CouponQrResult | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [fundingError, setFundingError] = useState("");
  const [busyOfferId, setBusyOfferId] = useState("");
  const requestId = useRef(0);
  const generationId = useRef(0);
  const isFocused = useRef(false);

  const loadOffers = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setIsLoading(true);
    setError("");
    setFundingError("");
    const results = await Promise.allSettled([
      listOwnLiveOffers(), listOwnMarketplaceProducts(),
      canReadFunding && canReadMemberships ? listEntrepreneurFundedEvents() : Promise.resolve([]),
      canReadFunding && canReadMemberships ? listEntrepreneurInstitutionMemberships() : Promise.resolve([]),
    ]);
    if (currentRequest !== requestId.current) return;
    const reportResults = results[2].status === "fulfilled"
      ? await Promise.allSettled(results[2].value.map((event) => loadEntrepreneurFundedEventReport(event.event_id)))
      : [];
    if (currentRequest !== requestId.current) return;
    setOffers(results[0].status === "fulfilled" ? results[0].value : []);
    setProducts(results[1].status === "fulfilled" ? results[1].value : []);
    setEvents(results[2].status === "fulfilled" ? results[2].value : []);
    setMemberships(results[3].status === "fulfilled" ? results[3].value : []);
    setReports(reportResults.flatMap((report) => report.status === "fulfilled" ? [report.value] : []));
    const failure = results.slice(0, 2).find((result) => result.status === "rejected");
    if (failure?.status === "rejected") {
      setError(failure.reason instanceof Error ? failure.reason.message : "Não foi possível carregar suas ofertas.");
    }
    if (results[2].status === "rejected" || results[3].status === "rejected" || reportResults.some((report) => report.status === "rejected")) {
      setFundingError("Não foi possível conferir todo o apoio institucional. Atualize para consultar o saldo a receber.");
    }
    setIsLoading(false);
  }, [canReadFunding, canReadMemberships]);

  useFocusEffect(useCallback(() => {
    isFocused.current = true;
    void loadOffers();
    return () => { isFocused.current = false; requestId.current += 1; generationId.current += 1; setQrResult(null); setBusyOfferId(""); };
  }, [loadOffers]));

  async function generateQr(offer: OfferPreview, maximum: number) {
    if (busyOfferId || isLoading) return;
    const quantity = Number(quantities[offer.offer_id] ?? "1");
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > maximum) {
      showStaffAlert("Revise a quantidade", `Informe entre 1 e ${maximum} unidade(s) para esta venda.`);
      return;
    }
    setBusyOfferId(offer.offer_id);
    const currentGeneration = ++generationId.current;
    try {
      const result = await getOwnLiveOfferQr(offer.offer_id, quantity);
      if (result.offer.status !== "ACTIVE") throw new Error("Reative a oferta antes de gerar o QR.");
      if (isFocused.current && currentGeneration === generationId.current) setQrResult(result);
    } catch (qrError) {
      if (isFocused.current && currentGeneration === generationId.current) {
        showStaffAlert("QR não gerado", qrError instanceof Error ? qrError.message : "Atualize as ofertas e tente novamente.");
        void loadOffers();
      }
    } finally {
      if (isFocused.current && currentGeneration === generationId.current) setBusyOfferId("");
    }
  }

  return (
    <View style={styles.list}>
      <AppButton disabled={isLoading || Boolean(busyOfferId)} onPress={() => void loadOffers()} variant="secondary">Atualizar minhas ofertas</AppButton>
      {isLoading ? <Text style={styles.meta}>Atualizando suas ofertas...</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {fundingError ? <Text style={styles.error}>{fundingError}</Text> : null}
      {!isLoading && !error && offers.length === 0 ? <Text style={styles.meta}>Você ainda não emitiu ofertas. Cadastre um produto e emita uma oferta para gerar o QR.</Text> : null}
      {offers.map((offer) => {
        const product = products.find((item) => item.product_id === offer.product_id);
        const available = !error && canGenerateSaleQr(offer, product, nowMs);
        const maximum = Math.min(offer.remaining_redemptions, product?.stock_quantity ?? 0, 1_000);
        const funding = fundedEventsForOffer(offer, events, memberships, auth.currentUser?.uid || "", nowMs);
        const totals = fundedProductTotals(offer.product_id, offer.currency, reports);
        const price = new Intl.NumberFormat("pt-BR", { style: "currency", currency: offer.currency }).format(offer.final_amount_minor / 100);
        return (
          <View key={offer.offer_id} style={styles.card}>
            <Pressable
              accessibilityLabel={`Abrir QR da oferta ${offer.product_title}`}
              accessibilityRole="button"
              disabled={!available || isLoading || Boolean(busyOfferId)}
              onPress={() => void generateQr(offer, maximum)}
              style={styles.offerSummary}
            >
            <Text style={styles.title}>{offer.product_title}</Text>
            <Text style={styles.meta}>{price} · {offer.remaining_redemptions} unidade(s) disponível(is)</Text>
            <Text style={styles.origin}>{funding.length > 0 ? "Oferta própria com apoio institucional" : "Oferta criada por você"}</Text>
            {funding.map((event) => (
              <Text key={event.event_id} style={styles.meta}>Verba parceira: {event.institution_name} · {event.name}</Text>
            ))}
            {funding.length > 0 ? <Text style={styles.meta}>O repasse depende do saldo e das regras do evento na confirmação da compra.</Text> : null}
            <Text style={styles.meta}>{available ? `Termina em ${formatRemainingTime(offer.expires_at * 1_000, nowMs)}` : offer.status === "PAUSED" ? "Oferta pausada. Reative-a no gerenciador." : "QR indisponível: confira validade, estoque e situação da oferta."}</Text>
            <Text style={styles.origin}>Estoque: {product?.stock_quantity ?? "indisponível"} · vendidos nesta oferta: {offer.redeemed_count} unidade(s)</Text>
            {available ? <Text style={styles.meta}>Toque nesta oferta para abrir o QR.</Text> : null}
            </Pressable>
            {totals.hasFunding || funding.length > 0 ? (
              <View style={styles.fundingSummary}>
                <Text style={styles.origin}>Benefício institucional deste produto</Text>
                <Text style={styles.meta}>
                  {fundingError
                    ? "Saldo e vendas institucionais indisponíveis nesta atualização."
                    : `Saldo a receber: ${new Intl.NumberFormat("pt-BR", { style: "currency", currency: offer.currency }).format(totals.amountDueMinor / 100)} · vendidos com benefício: ${totals.unitsSold} unidade(s)`}
                </Text>
              </View>
            ) : null}
            {available ? (
              <>
                <FormField
                  accessibilityLabel={`Quantidade para vender ${offer.product_title}`}
                  editable={!isLoading && !busyOfferId}
                  keyboardType="number-pad"
                  label={`Quantidade para esta venda (até ${maximum})`}
                  maxLength={4}
                  onChangeText={(value) => setQuantities((current) => ({ ...current, [offer.offer_id]: value.replace(/\D/g, "") }))}
                  value={quantities[offer.offer_id] ?? "1"}
                />
                <AppButton accessibilityLabel={`Gerar QR para vender ${offer.product_title}`} disabled={isLoading || Boolean(busyOfferId)} onPress={() => void generateQr(offer, maximum)}>
                  {busyOfferId === offer.offer_id ? "Gerando QR..." : "Gerar QR para venda"}
                </AppButton>
              </>
            ) : null}
          </View>
        );
      })}
      <SaleQrModal result={qrResult} nowMs={nowMs} onChange={setQrResult} onInventoryChanged={loadOffers} />
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: 12 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, gap: 8, padding: 16 },
  offerSummary: { gap: 8 },
  fundingSummary: { backgroundColor: colors.cream, borderRadius: radius.small, gap: 6, padding: 12 },
  title: { color: colors.primaryDark, fontSize: 16, fontWeight: "900" },
  origin: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  meta: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, fontSize: 12, lineHeight: 18 },
});
