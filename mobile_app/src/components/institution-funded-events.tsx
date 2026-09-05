import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import {
  confirmStaffAction,
  formatPanelDate,
  getPanelErrorMessage,
  showStaffAlert,
  StaffMessage,
  StaffRecordCard,
  StaffSection,
  StaffStatusBadge,
} from "@/components/staff-panel-ui";
import { AppButton, FormField } from "@/components/ui";
import { colors, radius } from "@/constants/theme";
import { useTrustedClock } from "@/context/trusted-clock-context";
import {
  activateInstitutionFundedEvent,
  createInstitutionFundedEvent,
  endInstitutionFundedEvent,
  listInstitutionFundedEvents,
  listInstitutionGroups,
  loadInstitutionFundedEventReport,
  setInstitutionFundedEventSellerAllocations,
  type FundedEventEndMode,
  type InstitutionFundedEvent,
  type InstitutionFundedEventReport,
  type InstitutionGroup,
} from "@/security/trq-bec/service";

type FundingSource = InstitutionFundedEvent["funding_source"];

const FUNDING_SOURCE_LABELS: Record<FundingSource, string> = {
  DONATION: "Doação",
  INSTITUTION_BUDGET: "Verba da instituição",
  OTHER: "Outra origem",
};

const END_REASON_LABELS: Record<NonNullable<InstitutionFundedEvent["end_reason"]>, string> = {
  COUPONS: "cupons utilizados",
  MANUAL: "encerramento manual",
  TIME: "fim do prazo",
};

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function localDateTimeValue(valueMs: number) {
  const value = new Date(valueMs);
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())} ${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

function parseLocalDateTime(value: string) {
  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})$/);
  if (!match) return null;
  const [, year, month, day, hour, minute] = match;
  const parsed = new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
  if (
    Number.isNaN(parsed.getTime())
    || parsed.getFullYear() !== Number(year)
    || parsed.getMonth() !== Number(month) - 1
    || parsed.getDate() !== Number(day)
    || parsed.getHours() !== Number(hour)
    || parsed.getMinutes() !== Number(minute)
  ) {
    return null;
  }
  return parsed.toISOString();
}

function parseMoneyToMinor(value: string) {
  const raw = value.trim().replace(/^R\$\s*/i, "").replace(/\s/g, "");
  if (!raw) return null;
  const normalized = raw.includes(",")
    ? raw.replace(/\./g, "").replace(",", ".")
    : raw;
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null;
  const amount = Number(normalized);
  if (!Number.isFinite(amount) || amount < 0) return null;
  return Math.round(amount * 100);
}

function formatMoney(minor: number, currency = "BRL") {
  try {
    return new Intl.NumberFormat("pt-BR", { currency, style: "currency" }).format(minor / 100);
  } catch {
    return `${currency} ${(minor / 100).toFixed(2).replace(".", ",")}`;
  }
}

function OptionButton({
  label,
  onPress,
  selected,
}: {
  label: string;
  onPress: () => void;
  selected: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[styles.option, selected && styles.optionSelected]}
    >
      <Text style={[styles.optionText, selected && styles.optionTextSelected]}>{label}</Text>
    </Pressable>
  );
}

function FinancialMetric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

function EventReport({ report }: { report: InstitutionFundedEventReport }) {
  return (
    <View style={styles.reportContainer}>
      <Text style={styles.subsectionTitle}>Relatório do evento</Text>
      <View style={styles.metricGrid}>
        <FinancialMetric label="Valor a pagar" value={formatMoney(report.amount_due_minor, report.event.currency)} />
        <FinancialMetric label="Saldo da verba" value={formatMoney(report.remaining_budget_minor, report.event.currency)} />
        <FinancialMetric label="Cupons usados" value={String(report.confirmed_redemptions)} />
        <FinancialMetric label="Unidades vendidas" value={String(report.units_sold)} />
      </View>
      <Text style={styles.reportLine}>
        Vendas antes do desconto: {formatMoney(report.gross_original_amount_minor, report.event.currency)}
      </Text>
      <Text style={styles.reportLine}>
        Vendas após o desconto: {formatMoney(report.gross_final_amount_minor, report.event.currency)}
      </Text>
      <Text style={styles.reportLine}>
        Descontos usados: {formatMoney(report.discount_used_minor, report.event.currency)}
      </Text>
      {report.unfunded_discount_minor > 0 ? (
        <StaffMessage tone="danger">
          Há {formatMoney(report.unfunded_discount_minor, report.event.currency)} em descontos acima da verba
          reservada. Esse excedente não foi incluído no valor a pagar.
        </StaffMessage>
      ) : null}
      <Text style={styles.subsectionTitle}>Quanto a instituição deve por afiliado</Text>
      {report.sellers.map((seller) => (
        <StaffRecordCard key={seller.seller_uid}>
          <View style={styles.recordHeader}>
            <Text style={styles.recordTitle}>{seller.seller_name}</Text>
            <Text style={styles.dueValue}>{formatMoney(seller.amount_due_minor, report.event.currency)}</Text>
          </View>
          <Text style={styles.meta}>
            Cota: {formatMoney(seller.allocated_amount_minor, report.event.currency)} · saldo:{" "}
            {formatMoney(seller.remaining_budget_minor, report.event.currency)}
          </Text>
          <Text style={styles.meta}>
            {seller.confirmed_redemptions} cupom(ns) · {seller.units_sold} unidade(s)
          </Text>
          {seller.products.map((product) => (
            <View key={product.product_id} style={styles.productReport}>
              <Text style={styles.productTitle}>{product.product_title}</Text>
              <Text style={styles.meta}>
                A pagar: {formatMoney(product.amount_due_minor, report.event.currency)} · cota:{" "}
                {formatMoney(product.allocated_amount_minor, report.event.currency)}
              </Text>
              <Text style={styles.meta}>
                {product.confirmed_redemptions} cupom(ns) · saldo{" "}
                {formatMoney(product.remaining_budget_minor, report.event.currency)}
              </Text>
            </View>
          ))}
        </StaffRecordCard>
      ))}
      <Text style={styles.notice}>{report.financial_notice}</Text>
      <Text style={styles.meta}>Gerado em {formatPanelDate(report.generated_at)}</Text>
    </View>
  );
}

export function InstitutionFundedEventsContent() {
  const { nowMs } = useTrustedClock();
  const [groups, setGroups] = useState<InstitutionGroup[]>([]);
  const [events, setEvents] = useState<InstitutionFundedEvent[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [budget, setBudget] = useState("");
  const [fundingSource, setFundingSource] = useState<FundingSource>("DONATION");
  const [endMode, setEndMode] = useState<FundedEventEndMode>("TIME");
  const [startsAt, setStartsAt] = useState(() => localDateTimeValue(nowMs));
  const [endsAt, setEndsAt] = useState(() => localDateTimeValue(nowMs + 7 * 24 * 60 * 60 * 1000));
  const [couponLimit, setCouponLimit] = useState("100");
  const [allocationInputs, setAllocationInputs] = useState<Record<string, Record<string, string>>>({});
  const [reports, setReports] = useState<Record<string, InstitutionFundedEventReport>>({});
  const [busyAction, setBusyAction] = useState("");
  const [error, setError] = useState("");

  const activeGroups = useMemo(
    () => groups.filter((group) => group.status === "ACTIVE"),
    [groups],
  );

  const loadData = useCallback(async () => {
    setBusyAction("load");
    setError("");
    try {
      const [loadedGroups, loadedEvents] = await Promise.all([
        listInstitutionGroups(),
        listInstitutionFundedEvents(),
      ]);
      setGroups(loadedGroups);
      setEvents(loadedEvents);
      setSelectedGroupId((current) => current || loadedGroups.find((group) => group.status === "ACTIVE")?.group_id || "");
      setAllocationInputs((current) => {
        const next = { ...current };
        for (const event of loadedEvents) {
          if (!next[event.event_id]) {
            next[event.event_id] = Object.fromEntries(
              event.seller_allocations.map((seller) => [
                seller.seller_uid,
                (seller.allocated_amount_minor / 100).toFixed(2).replace(".", ","),
              ]),
            );
          }
        }
        return next;
      });
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar os eventos promocionais.");
      setError(message);
      showStaffAlert("Eventos indisponíveis", message);
    } finally {
      setBusyAction("");
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void loadData(), 0);
    return () => clearTimeout(timer);
  }, [loadData]);

  function replaceEvent(updated: InstitutionFundedEvent) {
    setEvents((current) => [
      updated,
      ...current.filter((event) => event.event_id !== updated.event_id),
    ].sort((left, right) => right.created_at.localeCompare(left.created_at)));
    setAllocationInputs((current) => ({
      ...current,
      [updated.event_id]: Object.fromEntries(
        updated.seller_allocations.map((seller) => [
          seller.seller_uid,
          (seller.allocated_amount_minor / 100).toFixed(2).replace(".", ","),
        ]),
      ),
    }));
  }

  async function handleCreate() {
    const budgetMinor = parseMoneyToMinor(budget);
    const startsAtIso = parseLocalDateTime(startsAt);
    const endsAtIso = endMode === "TIME" ? parseLocalDateTime(endsAt) : undefined;
    const parsedCouponLimit = Number(couponLimit);
    if (!selectedGroupId || name.trim().length < 3 || budgetMinor === null || budgetMinor < 1) {
      setError("Escolha o grupo, informe um nome e uma verba maior que zero.");
      return;
    }
    if (!startsAtIso || (endMode === "TIME" && !endsAtIso)) {
      setError("Use a data no formato AAAA-MM-DD HH:MM.");
      return;
    }
    if (endMode === "TIME" && new Date(endsAtIso!).getTime() <= new Date(startsAtIso).getTime()) {
      setError("O término precisa acontecer depois do início.");
      return;
    }
    if (endMode === "COUPONS" && (!Number.isInteger(parsedCouponLimit) || parsedCouponLimit < 1)) {
      setError("Informe uma quantidade válida de cupons.");
      return;
    }
    setBusyAction("create");
    setError("");
    try {
      const created = await createInstitutionFundedEvent({
        budgetAmountMinor: budgetMinor,
        couponLimit: endMode === "COUPONS" ? parsedCouponLimit : undefined,
        description: description.trim() || undefined,
        endMode,
        endsAt: endsAtIso || undefined,
        fundingSource,
        groupId: selectedGroupId,
        name: name.trim(),
        startsAt: startsAtIso,
      });
      replaceEvent(created);
      setName("");
      setDescription("");
      setBudget("");
      showStaffAlert(
        "Rascunho criado",
        "A verba foi dividida igualmente. Revise as cotas e ative o evento quando estiver pronto.",
      );
    } catch (saveError) {
      const message = getPanelErrorMessage(saveError, "Não foi possível criar o evento.");
      setError(message);
      showStaffAlert("Evento não criado", message);
    } finally {
      setBusyAction("");
    }
  }

  async function saveAllocations(event: InstitutionFundedEvent) {
    const values = allocationInputs[event.event_id] || {};
    const allocations = event.seller_allocations.map((seller) => ({
      sellerUid: seller.seller_uid,
      allocatedAmountMinor: parseMoneyToMinor(values[seller.seller_uid] || ""),
    }));
    if (allocations.some((allocation) => allocation.allocatedAmountMinor === null)) {
      setError("Revise as cotas dos afiliados. Use valores como 150,00.");
      return;
    }
    const total = allocations.reduce((sum, allocation) => sum + Number(allocation.allocatedAmountMinor), 0);
    if (total !== event.budget_amount_minor) {
      setError(
        `A soma das cotas precisa ser exatamente ${formatMoney(event.budget_amount_minor, event.currency)}. Agora ela está em ${formatMoney(total, event.currency)}.`,
      );
      return;
    }
    setBusyAction(`allocation:${event.event_id}`);
    setError("");
    try {
      replaceEvent(await setInstitutionFundedEventSellerAllocations(
        event.event_id,
        allocations.map((allocation) => ({
          allocatedAmountMinor: Number(allocation.allocatedAmountMinor),
          sellerUid: allocation.sellerUid,
        })),
      ));
      showStaffAlert("Divisão salva", "As cotas dos afiliados foram atualizadas.");
    } catch (saveError) {
      const message = getPanelErrorMessage(saveError, "Não foi possível salvar a divisão.");
      setError(message);
      showStaffAlert("Divisão não salva", message);
    } finally {
      setBusyAction("");
    }
  }

  async function activateEvent(event: InstitutionFundedEvent) {
    const confirmed = await confirmStaffAction(
      "Ativar este evento?",
      "Depois da ativação, as cotas ficam congeladas. Afiliados sem ajuste próprio terão a verba dividida igualmente entre seus produtos ativos.",
      "Ativar",
    );
    if (!confirmed) return;
    setBusyAction(`activate:${event.event_id}`);
    setError("");
    try {
      replaceEvent(await activateInstitutionFundedEvent(event.event_id));
      showStaffAlert("Evento ativado", "Os cupons confirmados já podem consumir a verba promocional.");
    } catch (activateError) {
      const message = getPanelErrorMessage(activateError, "Não foi possível ativar o evento.");
      setError(message);
      showStaffAlert("Evento não ativado", message);
    } finally {
      setBusyAction("");
    }
  }

  async function finishEvent(event: InstitutionFundedEvent) {
    const confirmed = await confirmStaffAction(
      "Encerrar o evento agora?",
      "O relatório ficará preservado, mas novos cupons não serão atribuídos à verba deste evento.",
      "Encerrar",
      true,
    );
    if (!confirmed) return;
    setBusyAction(`end:${event.event_id}`);
    setError("");
    try {
      replaceEvent(await endInstitutionFundedEvent(event.event_id));
      showStaffAlert("Evento encerrado", "O relatório final já pode ser consultado.");
    } catch (finishError) {
      const message = getPanelErrorMessage(finishError, "Não foi possível encerrar o evento.");
      setError(message);
      showStaffAlert("Evento não encerrado", message);
    } finally {
      setBusyAction("");
    }
  }

  async function loadReport(eventId: string) {
    setBusyAction(`report:${eventId}`);
    setError("");
    try {
      const report = await loadInstitutionFundedEventReport(eventId);
      setReports((current) => ({ ...current, [eventId]: report }));
      replaceEvent(report.event);
    } catch (reportError) {
      const message = getPanelErrorMessage(reportError, "Não foi possível gerar o relatório do evento.");
      setError(message);
      showStaffAlert("Relatório indisponível", message);
    } finally {
      setBusyAction("");
    }
  }

  return (
    <>
      <StaffSection
        description="A verba é dividida igualmente entre os afiliados ativos por padrão. Você pode ajustar as cotas antes de ativar."
        title="Criar evento com verba promocional"
      >
        <Text style={styles.fieldLabel}>Grupo que receberá a verba</Text>
        <View style={styles.options}>
          {activeGroups.map((group) => (
            <OptionButton
              key={group.group_id}
              label={group.name}
              onPress={() => setSelectedGroupId(group.group_id)}
              selected={selectedGroupId === group.group_id}
            />
          ))}
        </View>
        {activeGroups.length === 0 ? (
          <StaffMessage>Crie um grupo e tenha pelo menos um afiliado ativo antes de criar o evento.</StaffMessage>
        ) : null}
        <FormField label="Nome do evento" maxLength={160} onChangeText={setName} value={name} />
        <FormField
          label="Descrição (opcional)"
          maxLength={1000}
          multiline
          onChangeText={setDescription}
          style={styles.multiline}
          value={description}
        />
        <FormField
          keyboardType="decimal-pad"
          label="Verba total (R$)"
          onChangeText={setBudget}
          placeholder="Ex.: 1.500,00"
          value={budget}
        />
        <Text style={styles.fieldLabel}>Origem da verba</Text>
        <View style={styles.options}>
          {(Object.keys(FUNDING_SOURCE_LABELS) as FundingSource[]).map((source) => (
            <OptionButton
              key={source}
              label={FUNDING_SOURCE_LABELS[source]}
              onPress={() => setFundingSource(source)}
              selected={fundingSource === source}
            />
          ))}
        </View>
        <Text style={styles.fieldLabel}>O evento termina por</Text>
        <View style={styles.options}>
          <OptionButton label="Data e hora" onPress={() => setEndMode("TIME")} selected={endMode === "TIME"} />
          <OptionButton label="Quantidade de cupons" onPress={() => setEndMode("COUPONS")} selected={endMode === "COUPONS"} />
        </View>
        <FormField
          autoCapitalize="none"
          label="Início (AAAA-MM-DD HH:MM)"
          onChangeText={setStartsAt}
          value={startsAt}
        />
        {endMode === "TIME" ? (
          <FormField
            autoCapitalize="none"
            label="Término (AAAA-MM-DD HH:MM)"
            onChangeText={setEndsAt}
            value={endsAt}
          />
        ) : (
          <FormField
            keyboardType="number-pad"
            label="Total de cupons do evento"
            onChangeText={setCouponLimit}
            value={couponLimit}
          />
        )}
        {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
        <AppButton disabled={Boolean(busyAction) || activeGroups.length === 0} onPress={handleCreate}>
          {busyAction === "create" ? "Criando..." : "Criar rascunho e dividir igualmente"}
        </AppButton>
      </StaffSection>

      <StaffSection
        description="Revise a divisão, ative o evento e acompanhe o valor devido a cada afiliado."
        title="Eventos e relatórios"
      >
        <AppButton disabled={Boolean(busyAction)} onPress={loadData} variant="secondary">
          {busyAction === "load" ? "Atualizando..." : "Atualizar eventos"}
        </AppButton>
        {events.length === 0 && busyAction !== "load" ? <StaffMessage>Nenhum evento criado.</StaffMessage> : null}
        {events.map((event) => (
          <StaffRecordCard key={event.event_id}>
            <View style={styles.recordHeader}>
              <View style={styles.recordTitleGroup}>
                <Text style={styles.recordTitle}>{event.name}</Text>
                <Text style={styles.groupName}>{event.group_name}</Text>
              </View>
              <StaffStatusBadge
                label={event.status === "DRAFT" ? "Rascunho" : event.status === "ACTIVE" ? "Ativo" : "Encerrado"}
                tone={event.status === "ACTIVE" ? "success" : event.status === "DRAFT" ? "warning" : "neutral"}
              />
            </View>
            {event.description ? <Text style={styles.description}>{event.description}</Text> : null}
            <Text style={styles.moneyPrimary}>
              Verba total: {formatMoney(event.budget_amount_minor, event.currency)}
            </Text>
            <Text style={styles.meta}>
              Origem: {FUNDING_SOURCE_LABELS[event.funding_source]} · início: {formatPanelDate(event.starts_at)}
            </Text>
            <Text style={styles.meta}>
              {event.end_mode === "TIME"
                ? `Término: ${formatPanelDate(event.ends_at)}`
                : `Cupons: ${event.current_coupon_redemptions} de ${event.coupon_limit}`}
            </Text>
            {event.end_reason ? (
              <Text style={styles.meta}>Encerrado por {END_REASON_LABELS[event.end_reason]} em {formatPanelDate(event.ended_at)}</Text>
            ) : null}

            <Text style={styles.subsectionTitle}>Divisão entre afiliados</Text>
            {event.seller_allocations.map((seller) => (
              <View key={seller.seller_uid} style={styles.allocationRow}>
                <View style={styles.allocationText}>
                  <Text style={styles.productTitle}>{seller.seller_name}</Text>
                  <Text style={styles.meta}>
                    {seller.product_allocation_configured
                      ? "Produtos configurados"
                      : "Aguardando divisão entre produtos"}
                  </Text>
                </View>
                {event.status === "DRAFT" ? (
                  <FormField
                    containerStyle={styles.allocationField}
                    keyboardType="decimal-pad"
                    label="Cota (R$)"
                    onChangeText={(value) => setAllocationInputs((current) => ({
                      ...current,
                      [event.event_id]: {
                        ...(current[event.event_id] || {}),
                        [seller.seller_uid]: value,
                      },
                    }))}
                    value={allocationInputs[event.event_id]?.[seller.seller_uid] || ""}
                  />
                ) : (
                  <Text style={styles.allocationValue}>
                    {formatMoney(seller.allocated_amount_minor, event.currency)}
                  </Text>
                )}
              </View>
            ))}
            {event.status === "DRAFT" ? (
              <>
                <AppButton
                  disabled={Boolean(busyAction)}
                  onPress={() => saveAllocations(event)}
                  variant="secondary"
                >
                  {busyAction === `allocation:${event.event_id}` ? "Salvando divisão..." : "Salvar divisão personalizada"}
                </AppButton>
                <AppButton disabled={Boolean(busyAction)} onPress={() => activateEvent(event)}>
                  {busyAction === `activate:${event.event_id}` ? "Ativando..." : "Ativar evento"}
                </AppButton>
              </>
            ) : null}
            {event.status === "ACTIVE" ? (
              <AppButton disabled={Boolean(busyAction)} onPress={() => finishEvent(event)} variant="danger">
                {busyAction === `end:${event.event_id}` ? "Encerrando..." : "Encerrar evento agora"}
              </AppButton>
            ) : null}
            {event.status !== "DRAFT" ? (
              <AppButton disabled={Boolean(busyAction)} onPress={() => loadReport(event.event_id)} variant="secondary">
                {busyAction === `report:${event.event_id}` ? "Gerando relatório..." : "Ver relatório do evento"}
              </AppButton>
            ) : null}
            {reports[event.event_id] ? <EventReport report={reports[event.event_id]} /> : null}
          </StaffRecordCard>
        ))}
      </StaffSection>
    </>
  );
}

const styles = StyleSheet.create({
  allocationField: { flexBasis: 150, flexGrow: 1, marginBottom: 0 },
  allocationRow: {
    alignItems: "center",
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    paddingBottom: 10,
  },
  allocationText: { flexBasis: 190, flexGrow: 2 },
  allocationValue: { color: colors.success, fontSize: 13, fontWeight: "900" },
  description: { color: colors.text, fontSize: 12, lineHeight: 18 },
  dueValue: { color: colors.success, fontSize: 15, fontWeight: "900" },
  fieldLabel: { color: colors.primaryDark, fontSize: 12, fontWeight: "900" },
  groupName: { color: colors.primary, fontSize: 11, fontWeight: "800", marginTop: 2 },
  meta: { color: colors.textMuted, fontSize: 10, lineHeight: 15 },
  metric: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radius.small,
    borderWidth: 1,
    flexBasis: 140,
    flexGrow: 1,
    padding: 11,
  },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  metricLabel: { color: colors.textMuted, fontSize: 10, lineHeight: 14, marginTop: 2 },
  metricValue: { color: colors.primaryDark, fontSize: 16, fontWeight: "900" },
  moneyPrimary: { color: colors.success, fontSize: 13, fontWeight: "900" },
  multiline: { minHeight: 74, textAlignVertical: "top" },
  notice: { color: colors.textMuted, fontSize: 10, fontStyle: "italic", lineHeight: 15 },
  option: {
    backgroundColor: colors.cream,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 40,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  optionSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  optionText: { color: colors.primary, fontSize: 11, fontWeight: "800" },
  optionTextSelected: { color: colors.surface },
  options: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  productReport: {
    backgroundColor: colors.background,
    borderRadius: radius.small,
    marginTop: 5,
    padding: 9,
  },
  productTitle: { color: colors.primaryDark, fontSize: 12, fontWeight: "900" },
  recordHeader: { alignItems: "flex-start", flexDirection: "row", gap: 8, justifyContent: "space-between" },
  recordTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900" },
  recordTitleGroup: { flex: 1 },
  reportContainer: {
    borderColor: colors.primary,
    borderRadius: radius.small,
    borderWidth: 1,
    gap: 8,
    marginTop: 6,
    padding: 11,
  },
  reportLine: { color: colors.text, fontSize: 11, lineHeight: 16 },
  subsectionTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: "900", marginTop: 4 },
});
