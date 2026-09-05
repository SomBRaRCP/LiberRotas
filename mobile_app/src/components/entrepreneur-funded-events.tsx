import { Ionicons } from "@expo/vector-icons";
import { useCallback, useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import {
  formatPanelDate,
  getPanelErrorMessage,
  showStaffAlert,
} from "@/components/staff-panel-ui";
import { AppButton, FormField } from "@/components/ui";
import { colors, radius } from "@/constants/theme";
import {
  listEntrepreneurFundedEvents,
  listOwnMarketplaceProducts,
  setEntrepreneurFundedEventProductAllocations,
  type EntrepreneurFundedEvent,
} from "@/security/trq-bec/service";
import type { MarketplaceProduct } from "@/security/trq-bec/contracts";

function formatMoney(minor: number, currency = "BRL") {
  try {
    return new Intl.NumberFormat("pt-BR", { currency, style: "currency" }).format(minor / 100);
  } catch {
    return `${currency} ${(minor / 100).toFixed(2).replace(".", ",")}`;
  }
}

function parseMoneyToMinor(value: string) {
  const raw = value.trim().replace(/^R\$\s*/i, "").replace(/\s/g, "");
  if (!raw) return null;
  const normalized = raw.includes(",")
    ? raw.replace(/\./g, "").replace(",", ".")
    : raw;
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null;
  const amount = Number(normalized);
  return Number.isFinite(amount) && amount >= 0 ? Math.round(amount * 100) : null;
}

function equalAllocation(total: number, products: MarketplaceProduct[]) {
  const sorted = [...products].sort((left, right) => left.product_id.localeCompare(right.product_id));
  if (sorted.length === 0) return {};
  const base = Math.floor(total / sorted.length);
  const remainder = total % sorted.length;
  return Object.fromEntries(
    sorted.map((product, index) => [
      product.product_id,
      ((base + (index < remainder ? 1 : 0)) / 100).toFixed(2).replace(".", ","),
    ]),
  );
}

export function EntrepreneurFundedEvents() {
  const [events, setEvents] = useState<EntrepreneurFundedEvent[]>([]);
  const [products, setProducts] = useState<MarketplaceProduct[]>([]);
  const [inputs, setInputs] = useState<Record<string, Record<string, string>>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const loadData = useCallback(async () => {
    setBusy("load");
    setError("");
    try {
      const [loadedEvents, loadedProducts] = await Promise.all([
        listEntrepreneurFundedEvents(),
        listOwnMarketplaceProducts(),
      ]);
      const activeProducts = loadedProducts.filter((product) => product.status === "ACTIVE");
      setEvents(loadedEvents);
      setProducts(activeProducts);
      setInputs((current) => {
        const next = { ...current };
        for (const event of loadedEvents) {
          if (next[event.event_id]) continue;
          next[event.event_id] = event.product_allocations.length > 0
            ? Object.fromEntries(event.product_allocations.map((allocation) => [
              allocation.product_id,
              (allocation.allocated_amount_minor / 100).toFixed(2).replace(".", ","),
            ]))
            : equalAllocation(event.allocated_amount_minor, activeProducts);
        }
        return next;
      });
    } catch (loadError) {
      setError(getPanelErrorMessage(loadError, "Não foi possível carregar as verbas dos eventos."));
    } finally {
      setBusy("");
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void loadData(), 0);
    return () => clearTimeout(timer);
  }, [loadData]);

  async function saveAllocation(event: EntrepreneurFundedEvent) {
    const eventInputs = inputs[event.event_id] || {};
    const allocations = products.map((product) => ({
      productId: product.product_id,
      allocatedAmountMinor: parseMoneyToMinor(eventInputs[product.product_id] || ""),
    }));
    if (allocations.length === 0) {
      setError("Cadastre pelo menos um produto ativo antes de dividir a verba.");
      return;
    }
    if (allocations.some((allocation) => allocation.allocatedAmountMinor === null)) {
      setError("Revise os valores dos produtos. Use valores como 50,00.");
      return;
    }
    const total = allocations.reduce((sum, allocation) => sum + Number(allocation.allocatedAmountMinor), 0);
    if (total !== event.allocated_amount_minor) {
      setError(
        `A divisão deve somar ${formatMoney(event.allocated_amount_minor, event.currency)}. Agora soma ${formatMoney(total, event.currency)}.`,
      );
      return;
    }
    setBusy(event.event_id);
    setError("");
    try {
      const updated = await setEntrepreneurFundedEventProductAllocations(
        event.event_id,
        allocations.map((allocation) => ({
          allocatedAmountMinor: Number(allocation.allocatedAmountMinor),
          productId: allocation.productId,
        })),
      );
      setEvents((current) => current.map((item) => item.event_id === updated.event_id ? updated : item));
      showStaffAlert(
        "Divisão salva",
        "A instituição verá o uso consolidado da verba, e cada produto respeitará a cota definida.",
      );
    } catch (saveError) {
      const message = getPanelErrorMessage(saveError, "Não foi possível salvar a divisão entre produtos.");
      setError(message);
      showStaffAlert("Divisão não salva", message);
    } finally {
      setBusy("");
    }
  }

  const visibleEvents = events.filter((event) => event.status === "DRAFT" || event.status === "ACTIVE");

  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <View style={styles.sectionIcon}>
          <Ionicons color={colors.primary} name="cash-outline" size={21} />
        </View>
        <View style={styles.sectionTitleGroup}>
          <Text style={styles.sectionTitle}>Verbas promocionais</Text>
          <Text style={styles.sectionDescription}>
            Divida sua cota entre os produtos. Sem ajuste, o sistema divide igualmente ao ativar.
          </Text>
        </View>
        <Pressable
          accessibilityLabel="Atualizar verbas promocionais"
          accessibilityRole="button"
          disabled={Boolean(busy)}
          onPress={loadData}
          style={styles.refreshButton}
        >
          <Ionicons color={colors.primary} name="refresh" size={20} />
        </Pressable>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {busy === "load" && visibleEvents.length === 0 ? (
        <Text style={styles.emptyText}>Carregando verbas...</Text>
      ) : null}
      {!busy && visibleEvents.length === 0 ? (
        <Text style={styles.emptyText}>Nenhuma verba promocional ativa ou aguardando configuração.</Text>
      ) : null}
      {visibleEvents.map((event) => (
        <View key={event.event_id} style={styles.eventCard}>
          <View style={styles.eventHeader}>
            <View style={styles.eventTitleGroup}>
              <Text style={styles.eventTitle}>{event.name}</Text>
              <Text style={styles.groupName}>{event.institution_name} · {event.group_name}</Text>
            </View>
            <View style={[styles.badge, event.status === "ACTIVE" && styles.badgeActive]}>
              <Text style={[styles.badgeText, event.status === "ACTIVE" && styles.badgeTextActive]}>
                {event.status === "DRAFT" ? "Aguardando ativação" : "Ativo"}
              </Text>
            </View>
          </View>
          <Text style={styles.amount}>Sua cota: {formatMoney(event.allocated_amount_minor, event.currency)}</Text>
          <Text style={styles.meta}>
            Início: {formatPanelDate(event.starts_at)} ·{" "}
            {event.end_mode === "TIME"
              ? `término: ${formatPanelDate(event.ends_at)}`
              : `${event.current_coupon_redemptions} de ${event.coupon_limit} cupons`}
          </Text>
          {event.status === "DRAFT" ? (
            <>
              {products.map((product) => (
                <FormField
                  key={product.product_id}
                  keyboardType="decimal-pad"
                  label={`${product.title} (R$)`}
                  onChangeText={(value) => setInputs((current) => ({
                    ...current,
                    [event.event_id]: {
                      ...(current[event.event_id] || {}),
                      [product.product_id]: value,
                    },
                  }))}
                  value={inputs[event.event_id]?.[product.product_id] || ""}
                />
              ))}
              <AppButton disabled={Boolean(busy)} onPress={() => saveAllocation(event)}>
                {busy === event.event_id ? "Salvando..." : "Salvar divisão entre produtos"}
              </AppButton>
            </>
          ) : (
            <View style={styles.activeAllocations}>
              {event.product_allocations.map((allocation) => (
                <Text key={allocation.product_id} style={styles.meta}>
                  {allocation.product_title}: {formatMoney(allocation.allocated_amount_minor, event.currency)}
                </Text>
              ))}
            </View>
          )}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  activeAllocations: { gap: 4 },
  amount: { color: colors.success, fontSize: 13, fontWeight: "900" },
  badge: { backgroundColor: colors.cream, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5 },
  badgeActive: { backgroundColor: "#E8F6EF" },
  badgeText: { color: colors.primaryDark, fontSize: 9, fontWeight: "800" },
  badgeTextActive: { color: colors.success },
  emptyText: { color: colors.textMuted, fontSize: 11, lineHeight: 16, textAlign: "center" },
  error: { color: colors.danger, fontSize: 11, lineHeight: 16 },
  eventCard: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radius.small,
    borderWidth: 1,
    gap: 8,
    padding: 13,
  },
  eventHeader: { alignItems: "flex-start", flexDirection: "row", gap: 8, justifyContent: "space-between" },
  eventTitle: { color: colors.primaryDark, fontSize: 14, fontWeight: "900" },
  eventTitleGroup: { flex: 1 },
  groupName: { color: colors.primary, fontSize: 11, fontWeight: "700", marginTop: 2 },
  meta: { color: colors.textMuted, fontSize: 10, lineHeight: 15 },
  refreshButton: { alignItems: "center", justifyContent: "center", minHeight: 42, minWidth: 42 },
  section: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    gap: 12,
    marginHorizontal: 24,
    marginTop: 18,
    padding: 16,
  },
  sectionDescription: { color: colors.textMuted, fontSize: 11, lineHeight: 15, marginTop: 2 },
  sectionHeader: { alignItems: "center", flexDirection: "row", gap: 10 },
  sectionIcon: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderRadius: 20,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  sectionTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900" },
  sectionTitleGroup: { flex: 1 },
});
