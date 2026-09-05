import { Ionicons } from "@expo/vector-icons";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import {
  formatPanelDate,
  getPanelErrorMessage,
  showStaffAlert,
  StaffMessage,
  StaffRecordCard,
  StaffSection,
  StaffStatusBadge,
} from "@/components/staff-panel-ui";
import { AppButton } from "@/components/ui";
import { colors, radius } from "@/constants/theme";
import { useTrustedClock } from "@/context/trusted-clock-context";
import {
  listInstitutionGroups,
  loadInstitutionSalesReport,
  type InstitutionGroup,
  type InstitutionMembershipStatus,
  type InstitutionSalesCurrencyTotal,
  type InstitutionSalesReport,
} from "@/security/trq-bec/service";

type PeriodDays = 7 | 30 | 90;

const MEMBERSHIP_STATUS_LABELS: Record<InstitutionMembershipStatus, string> = {
  ACTIVE: "Filiado",
  DECLINED: "Convite recusado",
  LEFT: "Saiu do grupo",
  PENDING: "Convite pendente",
  REMOVED: "Removido",
};

function reportPeriod(days: PeriodDays, nowMs: number) {
  const periodTo = new Date(nowMs);
  const periodFrom = new Date(periodTo.getTime() - days * 24 * 60 * 60 * 1000);
  return { periodFrom: periodFrom.toISOString(), periodTo: periodTo.toISOString() };
}

function formatMoney(minor: number, currency: string) {
  try {
    return new Intl.NumberFormat("pt-BR", { currency, style: "currency" }).format(minor / 100);
  } catch {
    return `${currency} ${(minor / 100).toFixed(2).replace(".", ",")}`;
  }
}

function CurrencyTotals({ totals }: { totals: InstitutionSalesCurrencyTotal }) {
  return (
    <StaffRecordCard>
      <View style={styles.currencyHeader}>
        <Ionicons color={colors.primary} name="cash-outline" size={18} />
        <Text style={styles.currencyCode}>{totals.currency}</Text>
      </View>
      <Text style={styles.moneyPrimary}>
        Valor registrado: {formatMoney(totals.gross_final_amount_minor, totals.currency)}
      </Text>
      <Text style={styles.meta}>
        Valor original dos itens: {formatMoney(totals.gross_original_amount_minor, totals.currency)}
      </Text>
      <Text style={styles.meta}>
        Descontos registrados: {formatMoney(totals.total_discount_amount_minor, totals.currency)}
      </Text>
    </StaffRecordCard>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

export function InstitutionSalesReportContent() {
  const { nowMs } = useTrustedClock();
  const [groups, setGroups] = useState<InstitutionGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [periodDays, setPeriodDays] = useState<PeriodDays>(30);
  const [report, setReport] = useState<InstitutionSalesReport | null>(null);
  const [error, setError] = useState("");
  const [isLoadingGroups, setIsLoadingGroups] = useState(false);
  const [isLoadingReport, setIsLoadingReport] = useState(false);
  const reportRequestSequenceRef = useRef(0);
  const nowMsRef = useRef(nowMs);

  useEffect(() => {
    nowMsRef.current = nowMs;
  }, [nowMs]);

  const selectedGroup = useMemo(
    () => groups.find((group) => group.group_id === selectedGroupId) || null,
    [groups, selectedGroupId],
  );

  const loadGroups = useCallback(async () => {
    setIsLoadingGroups(true);
    try {
      setGroups(await listInstitutionGroups());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar os grupos para o filtro.");
      setError(message);
    } finally {
      setIsLoadingGroups(false);
    }
  }, []);

  const loadReport = useCallback(async (groupId: string, days: PeriodDays) => {
    const requestSequence = ++reportRequestSequenceRef.current;
    const period = reportPeriod(days, nowMsRef.current);
    setIsLoadingReport(true);
    setError("");
    try {
      const loaded = await loadInstitutionSalesReport({
        groupId: groupId || undefined,
        periodFrom: period.periodFrom,
        periodTo: period.periodTo,
      });
      if (requestSequence === reportRequestSequenceRef.current) setReport(loaded);
    } catch (loadError) {
      if (requestSequence !== reportRequestSequenceRef.current) return;
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar o relatório de resgates/vendas.");
      setError(message);
      showStaffAlert("Relatório indisponível", message);
    } finally {
      if (requestSequence === reportRequestSequenceRef.current) setIsLoadingReport(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadGroups();
      void loadReport("", 30);
    }, 0);
    return () => {
      clearTimeout(timer);
      reportRequestSequenceRef.current += 1;
    };
  }, [loadGroups, loadReport]);

  function selectGroup(groupId: string) {
    setSelectedGroupId(groupId);
    setReport(null);
    void loadReport(groupId, periodDays);
  }

  function selectPeriod(days: PeriodDays) {
    setPeriodDays(days);
    setReport(null);
    void loadReport(selectedGroupId, days);
  }

  return (
    <StaffSection
      description="Filtre os resgates/vendas registradas pelo grupo e pelo período. Os valores são separados por moeda."
      title="Relatório dos vendedores filiados"
    >
      <View style={styles.noticeCard}>
        <Ionicons color={colors.primary} name="information-circle-outline" size={22} />
        <Text style={styles.noticeText}>
          Este relatório contabiliza resgates/vendas registradas no LiberRotas. Ele não comprova pagamento,
          recebimento via Pix ou liquidação financeira.
        </Text>
      </View>

      <Text style={styles.filterLabel}>Grupo</Text>
      <View style={styles.filterOptions}>
        <Pressable
          accessibilityRole="radio"
          accessibilityState={{ checked: !selectedGroupId }}
          onPress={() => selectGroup("")}
          style={[styles.filterOption, !selectedGroupId && styles.filterOptionSelected]}
        >
          <Text style={[styles.filterOptionText, !selectedGroupId && styles.filterOptionTextSelected]}>Todos os grupos</Text>
        </Pressable>
        {groups.map((group) => {
          const selected = selectedGroupId === group.group_id;
          return (
            <Pressable
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
              key={group.group_id}
              onPress={() => selectGroup(group.group_id)}
              style={[styles.filterOption, selected && styles.filterOptionSelected]}
            >
              <Text numberOfLines={2} style={[styles.filterOptionText, selected && styles.filterOptionTextSelected]}>
                {group.name}
              </Text>
            </Pressable>
          );
        })}
      </View>
      {isLoadingGroups ? <Text style={styles.meta}>Atualizando grupos...</Text> : null}

      <Text style={styles.filterLabel}>Período</Text>
      <View style={styles.filterOptions}>
        {([7, 30, 90] as const).map((days) => {
          const selected = periodDays === days;
          return (
            <Pressable
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
              key={days}
              onPress={() => selectPeriod(days)}
              style={[styles.filterOption, selected && styles.filterOptionSelected]}
            >
              <Text style={[styles.filterOptionText, selected && styles.filterOptionTextSelected]}>
                Últimos {days} dias
              </Text>
            </Pressable>
          );
        })}
      </View>
      <AppButton
        disabled={isLoadingReport}
        onPress={() => loadReport(selectedGroupId, periodDays)}
        variant="secondary"
      >
        {isLoadingReport ? "Atualizando relatório..." : "Atualizar relatório"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}

      {report ? (
        <>
          <Text style={styles.periodText}>
            {selectedGroup ? selectedGroup.name : "Todos os grupos"} · {formatPanelDate(report.period_from)} até {formatPanelDate(report.period_to)}
          </Text>
          <View style={styles.metricGrid}>
            <Metric label="Resgates/vendas registradas" value={report.confirmed_redemptions} />
            <Metric label="Unidades registradas" value={report.units_sold} />
            <Metric label="Vendedores no relatório" value={report.sellers.length} />
          </View>

          {report.amounts_unavailable_count > 0 ? (
            <View style={styles.legacyWarning}>
              <Ionicons color={colors.danger} name="warning-outline" size={20} />
              <Text style={styles.legacyWarningText}>
                {report.amounts_unavailable_count} resgate(s) legado(s) não possuem um valor financeiro completo e
                foram excluídos dos totais em dinheiro. Nenhum valor foi estimado ou inventado.
              </Text>
            </View>
          ) : null}

          <Text style={styles.subsectionTitle}>Resumo por moeda</Text>
          {report.totals_by_currency.length === 0 ? (
            <StaffMessage>Nenhum valor financeiro registrado para este filtro.</StaffMessage>
          ) : report.totals_by_currency.map((totals) => (
            <CurrencyTotals key={totals.currency} totals={totals} />
          ))}

          <Text style={styles.subsectionTitle}>Linhas por vendedor</Text>
          {report.sellers.length === 0 ? (
            <StaffMessage>Nenhum vendedor com resgate/venda registrada neste período.</StaffMessage>
          ) : report.sellers.map((seller) => (
            <StaffRecordCard key={`${seller.group_name}:${seller.seller_name}:${seller.active_from}`}>
              <View style={styles.sellerHeader}>
                <View style={styles.sellerTitleGroup}>
                  <Text style={styles.sellerName}>{seller.seller_name}</Text>
                  <Text style={styles.groupName}>{seller.group_name}</Text>
                </View>
                <StaffStatusBadge
                  label={MEMBERSHIP_STATUS_LABELS[seller.membership_status]}
                  tone={seller.membership_status === "ACTIVE" ? "success" : "neutral"}
                />
              </View>
              <Text style={styles.meta}>
                {seller.confirmed_redemptions} resgate(s)/venda(s) registrada(s) · {seller.units_sold} unidade(s)
              </Text>
              <Text style={styles.meta}>Filiação desde {formatPanelDate(seller.active_from)}</Text>
              {seller.ended_at ? <Text style={styles.meta}>Filiação encerrada em {formatPanelDate(seller.ended_at)}</Text> : null}
              {seller.amounts_unavailable_count > 0 ? (
                <Text style={styles.sellerWarning}>
                  {seller.amounts_unavailable_count} registro(s) legado(s) sem valor, fora dos totais em dinheiro.
                </Text>
              ) : null}
              {seller.totals_by_currency.map((totals) => (
                <Text key={totals.currency} style={styles.sellerMoney}>
                  {totals.currency}: {formatMoney(totals.gross_final_amount_minor, totals.currency)} registrado · {formatMoney(totals.total_discount_amount_minor, totals.currency)} em descontos
                </Text>
              ))}
            </StaffRecordCard>
          ))}
          {report.has_more ? (
            <StaffMessage>O relatório possui mais vendedores. Reduza o período ou filtre um grupo para visualizar todas as linhas.</StaffMessage>
          ) : null}
          <Text style={styles.meta}>Relatório gerado em {formatPanelDate(report.generated_at)}</Text>
          <Text style={styles.financialNotice}>{report.financial_notice}</Text>
        </>
      ) : !isLoadingReport && !error ? (
        <StaffMessage>Escolha os filtros e atualize para consultar o relatório.</StaffMessage>
      ) : null}
    </StaffSection>
  );
}

const styles = StyleSheet.create({
  noticeCard: {
    alignItems: "flex-start",
    backgroundColor: "#F2F6FF",
    borderColor: colors.primary,
    borderRadius: radius.small,
    borderWidth: 1,
    flexDirection: "row",
    gap: 9,
    padding: 12,
  },
  noticeText: { color: colors.primaryDark, flex: 1, fontSize: 11, lineHeight: 17 },
  filterLabel: { color: colors.primaryDark, fontSize: 12, fontWeight: "900", marginTop: 2 },
  filterOptions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  filterOption: {
    backgroundColor: colors.cream,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 40,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  filterOptionSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  filterOptionText: { color: colors.primary, fontSize: 11, fontWeight: "800", maxWidth: 220 },
  filterOptionTextSelected: { color: colors.surface },
  periodText: { color: colors.primaryDark, fontSize: 12, fontWeight: "800", lineHeight: 17 },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: 9 },
  metricCard: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radius.small,
    borderWidth: 1,
    flexBasis: 145,
    flexGrow: 1,
    minWidth: 125,
    padding: 12,
  },
  metricValue: { color: colors.primaryDark, fontSize: 21, fontWeight: "900" },
  metricLabel: { color: colors.textMuted, fontSize: 10, lineHeight: 14, marginTop: 2 },
  legacyWarning: {
    alignItems: "flex-start",
    backgroundColor: "#FDECEC",
    borderRadius: radius.small,
    flexDirection: "row",
    gap: 8,
    padding: 12,
  },
  legacyWarningText: { color: colors.danger, flex: 1, fontSize: 11, fontWeight: "700", lineHeight: 16 },
  subsectionTitle: { color: colors.primaryDark, fontSize: 14, fontWeight: "900", marginTop: 4 },
  currencyHeader: { alignItems: "center", flexDirection: "row", gap: 7 },
  currencyCode: { color: colors.primaryDark, fontSize: 13, fontWeight: "900" },
  moneyPrimary: { color: colors.success, fontSize: 13, fontWeight: "900" },
  sellerHeader: { alignItems: "flex-start", flexDirection: "row", gap: 8, justifyContent: "space-between" },
  sellerTitleGroup: { flex: 1 },
  sellerName: { color: colors.primaryDark, fontSize: 14, fontWeight: "900" },
  groupName: { color: colors.primary, fontSize: 11, fontWeight: "700", marginTop: 2 },
  sellerMoney: { color: colors.text, fontSize: 11, lineHeight: 16 },
  sellerWarning: { color: colors.danger, fontSize: 10, fontWeight: "700", lineHeight: 15 },
  meta: { color: colors.textMuted, fontSize: 10, lineHeight: 15 },
  financialNotice: { color: colors.textMuted, fontSize: 10, fontStyle: "italic", lineHeight: 15 },
});
