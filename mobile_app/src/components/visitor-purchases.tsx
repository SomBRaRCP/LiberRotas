import { useFocusEffect } from "expo-router";
import { useCallback, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { AppButton } from "@/components/ui";
import { PurchaseReport } from "@/components/purchase-report";
import { colors } from "@/constants/theme";
import type { VisitorPurchasesReport } from "@/features/marketplace/purchases";
import { loadOwnPurchases } from "@/security/trq-bec/service";

export function VisitorPurchases() {
  const [report, setReport] = useState<VisitorPurchasesReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [nextOffset, setNextOffset] = useState(0);
  const requestId = useRef(0);

  const load = useCallback(async (offset = 0) => {
    const currentRequest = ++requestId.current;
    setIsLoading(true);
    setError("");
    if (!offset) setReport(null);
    try {
      const page = await loadOwnPurchases(offset);
      if (currentRequest !== requestId.current) return;
      setNextOffset(page.offset + page.items.length);
      setReport((previous) => {
        if (!offset || !previous) return page;
        const previousIds = new Set(previous.items.map((item) => item.redemption_id));
        return { ...page, items: [...previous.items, ...page.items.filter((item) => !previousIds.has(item.redemption_id))] };
      });
    } catch (failure) {
      if (currentRequest !== requestId.current) return;
      setError(failure instanceof Error ? failure.message : "Não foi possível carregar suas compras.");
    } finally {
      if (currentRequest === requestId.current) setIsLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    void load();
    return () => { requestId.current += 1; };
  }, [load]));

  return <View style={styles.section}>
    <Text style={styles.title}>Minhas compras</Text>
    <Text style={styles.description}>Acompanhe onde comprou, quanto gastou e quanto economizou nas ofertas do app.</Text>
    {isLoading ? <Text accessibilityLiveRegion="polite" style={styles.description}>Atualizando suas compras...</Text> : null}
    {error ? <Text accessibilityLiveRegion="polite" style={styles.error}>{error}</Text> : null}
    {report ? <PurchaseReport report={report} /> : null}
    {report?.has_more ? <AppButton disabled={isLoading} onPress={() => { void load(nextOffset); }} variant="secondary">Ver compras anteriores</AppButton> : null}
    <AppButton disabled={isLoading} onPress={() => { void load(); }} variant="secondary">{error && !report ? "Tentar novamente" : "Atualizar minhas compras"}</AppButton>
  </View>;
}

const styles = StyleSheet.create({
  section: { gap: 12, marginBottom: 24 },
  title: { color: colors.primaryDark, fontSize: 19, fontWeight: "900" },
  description: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  error: { color: colors.danger, fontSize: 12, lineHeight: 18 },
});
