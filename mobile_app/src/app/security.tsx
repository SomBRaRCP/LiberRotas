import { Ionicons } from "@expo/vector-icons";
import { router, type Href, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { AuthorizedPanel } from "@/components/authorized-panel";
import {
  ACCOUNT_ROLE_LABELS,
  ACCOUNT_STATUS_LABELS,
  confirmStaffAction,
  formatPanelDate,
  getAccountStatusTone,
  getPanelErrorMessage,
  showStaffAlert,
  StaffMessage,
  StaffRecordCard,
  StaffSection,
  StaffStatusBadge,
} from "@/components/staff-panel-ui";
import { AppButton, FormField } from "@/components/ui";
import { colors } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import {
  loadSecurityAccessOverview,
  loadSecurityMonitoringSummary,
  loadTrqBecSecurityStatus,
  type AccessAuditEvent,
  type ManagedAccountSummary,
  type SecurityMonitoringSummary,
  type TrqBecSecurityStatus,
  updateManagedAccountStatus,
} from "@/security/trq-bec/service";

const EVENT_LABELS: Record<string, string> = {
  ACCOUNT_STATUS_CHANGED: "Status de conta alterado",
  INSTITUTION_PROVISIONED: "Instituição provisionada",
  OFFICIAL_ACCOUNT_VALIDATED: "Conta oficial validada",
  STAFF_ACCOUNT_CREATED: "Conta de equipe criada como pendente",
  STAFF_ACCOUNT_VALIDATED: "Autoridade de equipe validada",
};

type TrqBecMetricKey =
  | "official_accounts_total"
  | "privileged_accounts_pending_validation"
  | "access_events_last_24h"
  | "audit_events_total"
  | "audit_checkpoints_total"
  | "devices_active"
  | "devices_pending"
  | "device_notifications_failed"
  | "email_verifications_pending"
  | "email_verifications_failed";

type TrqBecMetricDetail = {
  label: string;
  description: string;
  resolution: string;
  tool?: "audit" | "monitoring" | "pending";
  focus?: "privileged" | "devices" | "email";
};

const TRQ_BEC_METRIC_DETAILS: Record<TrqBecMetricKey, TrqBecMetricDetail> = {
  official_accounts_total: {
    label: "Contas oficiais",
    description: "Contas administrativas bootstrap confirmadas, aprovadas e protegidas como SYSTEM.",
    resolution: "Use a Auditoria para conferir quando cada autoridade oficial foi validada.",
    tool: "audit",
  },
  privileged_accounts_pending_validation: {
    label: "Privilegiadas pendentes",
    description: "Contas de Administrador, Suporte ou Segurança criadas sem acesso enquanto aguardam confirmação e validação.",
    resolution: "Confira a Central de pendências. A aprovação final continua exclusiva do Administrador e exige e-mail verificado.",
    tool: "pending",
    focus: "privileged",
  },
  access_events_last_24h: {
    label: "Eventos de acesso (24 h)",
    description: "Quantidade de decisões administrativas e alterações de acesso registradas nas últimas 24 horas.",
    resolution: "Abra a Auditoria para identificar responsável, alvo, transição e justificativa.",
    tool: "audit",
  },
  audit_events_total: {
    label: "Eventos no ledger",
    description: "Total de evidências persistidas no ledger autoritativo e append-only do TRQ-BEC.",
    resolution: "Uma variação inesperada deve ser comparada com os eventos de acesso e a operação realizada no mesmo período.",
    tool: "audit",
  },
  audit_checkpoints_total: {
    label: "Checkpoints",
    description: "Consolidações assinadas de faixas do ledger usadas para verificar integridade histórica.",
    resolution: "A criação é uma operação administrativa interna. A Segurança acompanha a contagem e comunica ausência ou regressão.",
    tool: "monitoring",
  },
  devices_active: {
    label: "Dispositivos ativos",
    description: "Dispositivos que concluíram o período de segurança e estão reconhecidos pelo backend.",
    resolution: "Revise a Central de pendências se o total crescer sem uma justificativa operacional conhecida.",
    tool: "pending",
    focus: "devices",
  },
  devices_pending: {
    label: "Dispositivos em cooldown",
    description: "Novos dispositivos ainda dentro do período automático de segurança antes da ativação.",
    resolution: "Confirme se a quantidade diminui após o prazo. O dono da conta pode revisar e revogar dispositivos na própria área.",
    tool: "pending",
    focus: "devices",
  },
  device_notifications_failed: {
    label: "Alertas de dispositivo",
    description: "Avisos de novo dispositivo que falharam ou foram criados quando o envio de e-mail não estava configurado.",
    resolution: "Abra a Central de pendências para conferir a configuração de e-mail e orientar o reenvio pelo dono da conta.",
    tool: "pending",
    focus: "devices",
  },
  email_verifications_pending: {
    label: "E-mails na fila",
    description: "Confirmações de e-mail aguardando a próxima tentativa do processador autoritativo.",
    resolution: "A fila possui tentativas automáticas. Analise se a contagem permanece parada além do próximo ciclo.",
    tool: "pending",
    focus: "email",
  },
  email_verifications_failed: {
    label: "E-mails com falha",
    description: "Confirmações que atingiram o limite de tentativas sem entrega bem-sucedida.",
    resolution: "Abra a Central de pendências, corrija SMTP/remetente quando necessário e solicite um novo envio pela conta afetada.",
    tool: "pending",
    focus: "email",
  },
};

function openSecurityTool(tool: "audit" | "monitoring" | "pending" | "trq-bec", focus?: string) {
  router.push({
    pathname: "/security",
    params: { tool, ...(focus ? { focus } : {}) },
  } as unknown as Href);
}

function AuditContent() {
  const { hasPermission } = useApp();
  const canReadAudit = hasPermission("security.audit.read");
  const [events, setEvents] = useState<AccessAuditEvent[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const loadAudit = useCallback(async () => {
    if (!canReadAudit) return;
    setIsLoading(true);
    setError("");
    try {
      const overview = await loadSecurityAccessOverview();
      setEvents(overview.recentEvents);
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar a auditoria.");
      setError(message);
      showStaffAlert("Auditoria indisponível", message);
    } finally {
      setIsLoading(false);
    }
  }, [canReadAudit]);

  useEffect(() => {
    const timer = setTimeout(() => void loadAudit(), 0);
    return () => clearTimeout(timer);
  }, [loadAudit]);

  const filteredEvents = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("pt-BR");
    if (!normalizedQuery) return events;
    return events.filter((event) => [
      event.event_id,
      event.actor_uid,
      event.target_uid,
      event.event_type,
      EVENT_LABELS[event.event_type] || "",
      event.reason || "",
    ].join(" ").toLocaleLowerCase("pt-BR").includes(normalizedQuery));
  }, [events, query]);

  if (!canReadAudit) {
    return <StaffMessage>Esta conta não recebeu permissão para consultar a auditoria.</StaffMessage>;
  }

  return (
    <StaffSection
      description="Eventos de provisionamento e alterações de acesso registrados pelo backend."
      title="Auditoria"
    >
      <FormField
        autoCapitalize="none"
        autoCorrect={false}
        label="Filtrar por responsável, alvo, evento ou motivo"
        onChangeText={setQuery}
        placeholder="Digite para filtrar"
        value={query}
      />
      <AppButton disabled={isLoading} onPress={loadAudit} variant="secondary">
        {isLoading ? "Atualizando auditoria..." : "Atualizar auditoria"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
      {!isLoading && filteredEvents.length === 0 ? <StaffMessage>Nenhum evento encontrado.</StaffMessage> : null}
      {filteredEvents.map((event) => (
        <StaffRecordCard key={event.event_id}>
          <Text style={styles.eventTitle}>{EVENT_LABELS[event.event_type] || event.event_type}</Text>
          <Text selectable style={styles.meta}>Evento: {event.event_id}</Text>
          <Text selectable style={styles.meta}>Alvo: {event.target_uid}</Text>
          <Text selectable style={styles.meta}>Responsável: {event.actor_uid}</Text>
          <Text style={styles.transition}>
            {event.previous_status ? ACCOUNT_STATUS_LABELS[event.previous_status] : "Sem status anterior"}
            {" → "}
            {event.new_status ? ACCOUNT_STATUS_LABELS[event.new_status] : "Sem status novo"}
          </Text>
          {event.reason ? <Text style={styles.reason}>Motivo: {event.reason}</Text> : null}
          <Text style={styles.meta}>{formatPanelDate(event.created_at)}</Text>
        </StaffRecordCard>
      ))}
    </StaffSection>
  );
}

type PendingStatusChange = {
  account: ManagedAccountSummary;
  status: "ACTIVE" | "SUSPENDED";
};

function IncidentsContent() {
  const { hasPermission } = useApp();
  const canReadAudit = hasPermission("security.audit.read");
  const canManageIncidents = hasPermission("security.incidents.manage");
  const [accounts, setAccounts] = useState<ManagedAccountSummary[]>([]);
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const [pendingChange, setPendingChange] = useState<PendingStatusChange | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [updatingUid, setUpdatingUid] = useState<string | null>(null);

  const loadAccounts = useCallback(async () => {
    if (!canReadAudit) return;
    setIsLoading(true);
    setError("");
    try {
      const overview = await loadSecurityAccessOverview();
      setAccounts(overview.accounts);
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar as contas para análise.");
      setError(message);
      showStaffAlert("Incidentes indisponíveis", message);
    } finally {
      setIsLoading(false);
    }
  }, [canReadAudit]);

  useEffect(() => {
    const timer = setTimeout(() => void loadAccounts(), 0);
    return () => clearTimeout(timer);
  }, [loadAccounts]);

  const filteredAccounts = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("pt-BR");
    if (!normalizedQuery) return accounts;
    return accounts.filter((account) => [
      account.firebase_uid,
      account.email || "",
      account.role,
      ACCOUNT_ROLE_LABELS[account.role],
      account.status,
      ACCOUNT_STATUS_LABELS[account.status],
    ].join(" ").toLocaleLowerCase("pt-BR").includes(normalizedQuery));
  }, [accounts, query]);

  function availableStatus(account: ManagedAccountSummary): "ACTIVE" | "SUSPENDED" | null {
    if (
      !canManageIncidents
      || account.role === "admin"
      || account.role === "security"
      || account.protection_level === "SYSTEM"
    ) return null;
    if (account.status === "ACTIVE") return "SUSPENDED";
    if (account.status === "SUSPENDED") return "ACTIVE";
    return null;
  }

  function prepareStatusChange(account: ManagedAccountSummary, status: "ACTIVE" | "SUSPENDED") {
    setPendingChange({ account, status });
    setReason("");
    setError("");
  }

  async function applyStatusChange() {
    if (!pendingChange) return;
    const normalizedReason = reason.trim();
    if (normalizedReason.length < 10) {
      const message = "Informe um motivo objetivo com pelo menos 10 caracteres.";
      setError(message);
      showStaffAlert("Motivo necessário", message);
      return;
    }

    const { account, status } = pendingChange;
    setUpdatingUid(account.firebase_uid);
    setError("");
    try {
      const updated = await updateManagedAccountStatus(account.firebase_uid, status, normalizedReason);
      setAccounts((current) => current.map((item) => item.firebase_uid === updated.firebase_uid ? updated : item));
      setPendingChange(null);
      setReason("");
      showStaffAlert(
        status === "SUSPENDED" ? "Conta suspensa" : "Conta reativada",
        `${account.email || account.firebase_uid} agora está ${status === "SUSPENDED" ? "suspensa" : "ativa"}.`,
      );
    } catch (updateError) {
      const message = getPanelErrorMessage(updateError, "Não foi possível alterar o status da conta.");
      setError(message);
      showStaffAlert("Status não alterado", message);
    } finally {
      setUpdatingUid(null);
    }
  }

  async function confirmStatusChange() {
    if (!pendingChange) return;
    if (reason.trim().length < 10) {
      const message = "Informe um motivo objetivo com pelo menos 10 caracteres.";
      setError(message);
      showStaffAlert("Motivo necessário", message);
      return;
    }
    const suspending = pendingChange.status === "SUSPENDED";
    const confirmed = await confirmStaffAction(
      suspending ? "Confirmar suspensão?" : "Confirmar reativação?",
      `A ação será registrada com o motivo informado e exige autenticação recente.`,
      suspending ? "Suspender" : "Reativar",
      suspending,
    );
    if (confirmed) await applyStatusChange();
  }

  if (!canReadAudit) {
    return <StaffMessage>Esta conta não recebeu permissão para consultar as contas.</StaffMessage>;
  }

  return (
    <StaffSection
      description="Contas administrativas e de segurança são protegidas. Toda alteração exige motivo e autenticação recente."
      title="Incidentes"
    >
      {pendingChange ? (
        <StaffRecordCard>
          <Text style={styles.eventTitle}>
            {pendingChange.status === "SUSPENDED" ? "Preparar suspensão" : "Preparar reativação"}
          </Text>
          <Text style={styles.recordTitle}>{pendingChange.account.email || pendingChange.account.firebase_uid}</Text>
          <FormField
            label="Motivo obrigatório"
            maxLength={500}
            multiline
            onChangeText={setReason}
            placeholder="Descreva o incidente e a razão desta alteração."
            style={styles.reasonField}
            textAlignVertical="top"
            value={reason}
          />
          <Text style={styles.characterCount}>{reason.trim().length}/500 caracteres</Text>
          <AppButton
            disabled={Boolean(updatingUid)}
            onPress={confirmStatusChange}
            variant={pendingChange.status === "SUSPENDED" ? "danger" : "secondary"}
          >
            {updatingUid ? "Registrando..." : pendingChange.status === "SUSPENDED" ? "Confirmar suspensão" : "Confirmar reativação"}
          </AppButton>
          <AppButton disabled={Boolean(updatingUid)} onPress={() => setPendingChange(null)} variant="secondary">
            Cancelar ação
          </AppButton>
        </StaffRecordCard>
      ) : null}
      <FormField
        autoCapitalize="none"
        autoCorrect={false}
        label="Filtrar por e-mail, UID, função ou status"
        onChangeText={setQuery}
        placeholder="Digite para filtrar"
        value={query}
      />
      <AppButton disabled={isLoading || Boolean(updatingUid)} onPress={loadAccounts} variant="secondary">
        {isLoading ? "Atualizando contas..." : "Atualizar contas"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
      {!isLoading && filteredAccounts.length === 0 ? <StaffMessage>Nenhuma conta encontrada.</StaffMessage> : null}
      {filteredAccounts.map((account) => {
        const nextStatus = availableStatus(account);
        const protectedAccount = (
          account.role === "admin"
          || account.role === "security"
          || account.protection_level === "SYSTEM"
        );
        return (
          <StaffRecordCard key={account.firebase_uid}>
            <View style={styles.recordHeader}>
              <Text style={styles.recordTitle}>{account.email || "E-mail não informado"}</Text>
              <StaffStatusBadge label={ACCOUNT_STATUS_LABELS[account.status]} tone={getAccountStatusTone(account.status)} />
            </View>
            <Text style={styles.role}>{ACCOUNT_ROLE_LABELS[account.role]}</Text>
            <Text selectable style={styles.uid}>UID: {account.firebase_uid}</Text>
            <Text style={styles.meta}>Atualizada em {formatPanelDate(account.updated_at)}</Text>
            {protectedAccount ? <Text style={styles.protectedText}>Conta protegida: nenhuma ação disponível.</Text> : null}
            {nextStatus ? (
              <AppButton
                disabled={Boolean(updatingUid)}
                onPress={() => prepareStatusChange(account, nextStatus)}
                variant={nextStatus === "SUSPENDED" ? "danger" : "secondary"}
              >
                {nextStatus === "SUSPENDED" ? "Analisar suspensão" : "Analisar reativação"}
              </AppButton>
            ) : null}
          </StaffRecordCard>
        );
      })}
      {!canManageIncidents ? (
        <StaffMessage>Leitura liberada, mas alterações de status não foram autorizadas para esta conta.</StaffMessage>
      ) : null}
    </StaffSection>
  );
}

function MonitoringMetric({
  label,
  onPress,
  value,
}: {
  label: string;
  onPress?: () => void;
  value: number | string;
}) {
  const content = (
    <>
      <View style={styles.metricHeading}>
        <Text style={styles.metricValue}>{value}</Text>
        {onPress ? <Ionicons color={colors.primary} name="chevron-forward-outline" size={18} /> : null}
      </View>
      <Text style={styles.metricLabel}>{label}</Text>
      {onPress ? <Text style={styles.metricAction}>Ver detalhes</Text> : null}
    </>
  );
  if (!onPress) return <View style={styles.metricCard}>{content}</View>;
  return (
    <Pressable
      accessibilityHint={`Abre a explicação do indicador ${label}`}
      accessibilityLabel={`${label}: ${value}. Ver detalhes`}
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [styles.metricCard, styles.metricButton, pressed && styles.metricPressed]}
    >
      {content}
    </Pressable>
  );
}

function MonitoringContent() {
  const { hasPermission } = useApp();
  const canReadMonitoring = hasPermission("security.audit.read");
  const [summary, setSummary] = useState<SecurityMonitoringSummary | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const loadSummary = useCallback(async () => {
    if (!canReadMonitoring) return;
    setIsLoading(true);
    setError("");
    try {
      setSummary(await loadSecurityMonitoringSummary());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar o monitoramento.");
      setError(message);
      showStaffAlert("Monitoramento indisponível", message);
    } finally {
      setIsLoading(false);
    }
  }, [canReadMonitoring]);

  useEffect(() => {
    const timer = setTimeout(() => void loadSummary(), 0);
    return () => clearTimeout(timer);
  }, [loadSummary]);

  if (!canReadMonitoring) {
    return <StaffMessage>Esta conta não recebeu permissão para consultar o monitoramento.</StaffMessage>;
  }

  return (
    <StaffSection
      description="Indicadores consolidados pelo backend. O relógio local é apenas visual; decisões de validade continuam no servidor."
      title="Monitoramento"
    >
      <AppButton disabled={isLoading} onPress={loadSummary} variant="secondary">
        {isLoading ? "Atualizando monitoramento..." : "Atualizar monitoramento"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
      {summary ? (
        <>
          <View style={styles.metricGrid}>
            <MonitoringMetric label="Contas" value={summary.accounts_total} />
            <MonitoringMetric label="Ativas" value={summary.active_accounts} />
            <MonitoringMetric label="Suspensas" value={summary.suspended_accounts} />
            <MonitoringMetric label="Pendentes" value={summary.pending_accounts} />
            <MonitoringMetric label="Desativadas" value={summary.disabled_accounts} />
            <MonitoringMetric label="Eventos de acesso" value={summary.recent_events_total} />
          </View>
          <StaffRecordCard>
            <Text style={styles.eventTitle}>Saúde dos serviços</Text>
            <View style={styles.statusRow}>
              <StaffStatusBadge label={`API: ${summary.health_status}`} tone={summary.health_status === "ok" ? "success" : "danger"} />
              <StaffStatusBadge label={`Banco: ${summary.database_ok ? "online" : "indisponível"}`} tone={summary.database_ok ? "success" : "danger"} />
              <StaffStatusBadge label={`Redis: ${summary.redis_ok ? "online" : "indisponível"}`} tone={summary.redis_ok ? "success" : "danger"} />
              <StaffStatusBadge label={`PQC: ${summary.pqc_ready ? "disponível" : "não aprovada"}`} tone={summary.pqc_ready ? "success" : "warning"} />
            </View>
            <Text style={styles.meta}>Hora do servidor: {formatPanelDate(summary.server_time_iso)}</Text>
            <Text style={styles.meta}>Último evento: {formatPanelDate(summary.last_event_at)}</Text>
          </StaffRecordCard>
          {summary.recent_events.map((event) => (
            <StaffRecordCard key={event.event_id}>
              <Text style={styles.eventTitle}>{EVENT_LABELS[event.event_type] || event.event_type}</Text>
              <Text style={styles.meta}>Alvo: {event.target_uid}</Text>
              {event.reason ? <Text style={styles.reason}>Motivo: {event.reason}</Text> : null}
              <Text style={styles.meta}>{formatPanelDate(event.created_at)}</Text>
            </StaffRecordCard>
          ))}
        </>
      ) : !isLoading && !error ? <StaffMessage>Atualize para consultar os indicadores.</StaffMessage> : null}
    </StaffSection>
  );
}

function TrqBecMonitoringContent() {
  const { hasPermission } = useApp();
  const canMonitorTrqBec = hasPermission("security.trq_bec.monitor");
  const [status, setStatus] = useState<TrqBecSecurityStatus | null>(null);
  const [selectedMetric, setSelectedMetric] = useState<TrqBecMetricKey | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const loadStatus = useCallback(async () => {
    if (!canMonitorTrqBec) return;
    setIsLoading(true);
    setError("");
    try {
      setStatus(await loadTrqBecSecurityStatus());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível consultar os controles do TRQ-BEC.");
      setError(message);
      showStaffAlert("TRQ-BEC indisponível", message);
    } finally {
      setIsLoading(false);
    }
  }, [canMonitorTrqBec]);

  useEffect(() => {
    const timer = setTimeout(() => void loadStatus(), 0);
    return () => clearTimeout(timer);
  }, [loadStatus]);

  if (!canMonitorTrqBec) {
    return <StaffMessage>Esta conta não recebeu permissão específica para monitorar o TRQ-BEC.</StaffMessage>;
  }

  return (
    <StaffSection
      description="Visão sanitizada dos controles técnicos. Este painel não mostra tokens, assinaturas, chaves, senhas, conteúdo de mensagens ou dados PIX."
      title="Estado do TRQ-BEC"
    >
      <AppButton disabled={isLoading} onPress={loadStatus} variant="secondary">
        {isLoading ? "Consultando controles..." : "Atualizar TRQ-BEC"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
      {status ? (
        <>
          {(status.privileged_accounts_pending_validation > 0
            || status.device_notifications_failed > 0
            || status.email_verifications_failed > 0) ? (
              <Pressable
                accessibilityHint="Abre a central com as providências para cada pendência"
                accessibilityLabel="Há itens que exigem análise. Abrir central de pendências"
                accessibilityRole="link"
                onPress={() => openSecurityTool("pending")}
                style={({ pressed }) => [styles.pendingBanner, pressed && styles.metricPressed]}
              >
                <Ionicons color={colors.danger} name="warning-outline" size={21} />
                <View style={styles.pendingBannerText}>
                  <Text style={styles.pendingBannerTitle}>Há itens que exigem análise</Text>
                  <Text style={styles.pendingBannerDescription}>
                    Confira contas privilegiadas pendentes, alertas de dispositivos e falhas de verificação de e-mail.
                  </Text>
                  <Text style={styles.pendingBannerLink}>Abrir Central de pendências</Text>
                </View>
                <Ionicons color={colors.danger} name="chevron-forward-outline" size={20} />
              </Pressable>
            ) : (
              <StaffMessage>Nenhuma pendência crítica foi encontrada nos indicadores disponíveis.</StaffMessage>
            )}

          <View style={styles.metricGrid}>
            {(Object.keys(TRQ_BEC_METRIC_DETAILS) as TrqBecMetricKey[]).map((metricKey) => (
              <MonitoringMetric
                key={metricKey}
                label={TRQ_BEC_METRIC_DETAILS[metricKey].label}
                onPress={() => setSelectedMetric(metricKey)}
                value={status[metricKey]}
              />
            ))}
          </View>

          {selectedMetric ? (
            <StaffRecordCard>
              <View style={styles.metricDetailHeading}>
                <View style={styles.metricDetailIcon}>
                  <Ionicons color={colors.primary} name="information-circle-outline" size={23} />
                </View>
                <View style={styles.pendingBannerText}>
                  <Text style={styles.eventTitle}>{TRQ_BEC_METRIC_DETAILS[selectedMetric].label}</Text>
                  <Text style={styles.metricDetailValue}>{status[selectedMetric]}</Text>
                </View>
              </View>
              <Text style={styles.reason}>{TRQ_BEC_METRIC_DETAILS[selectedMetric].description}</Text>
              <Text style={styles.meta}>Providência: {TRQ_BEC_METRIC_DETAILS[selectedMetric].resolution}</Text>
              {TRQ_BEC_METRIC_DETAILS[selectedMetric].tool ? (
                <AppButton
                  onPress={() => openSecurityTool(
                    TRQ_BEC_METRIC_DETAILS[selectedMetric].tool!,
                    TRQ_BEC_METRIC_DETAILS[selectedMetric].focus,
                  )}
                  variant="secondary"
                >
                  Abrir análise deste indicador
                </AppButton>
              ) : null}
              <AppButton onPress={() => setSelectedMetric(null)} variant="secondary">
                Fechar detalhes
              </AppButton>
            </StaffRecordCard>
          ) : null}

          <StaffRecordCard>
            <Text style={styles.eventTitle}>Controles obrigatórios</Text>
            <View style={styles.statusRow}>
              <StaffStatusBadge
                label={`Validação de autoridade: ${status.access_validation_enforced ? "ativa" : "inativa"}`}
                tone={status.access_validation_enforced ? "success" : "danger"}
              />
              <StaffStatusBadge
                label={`Tokens revogados: ${status.token_revocation_checks_enabled ? "verificados" : "não verificados"}`}
                tone={status.token_revocation_checks_enabled ? "success" : "danger"}
              />
              <StaffStatusBadge
                label={`Ledger: ${status.audit_ledger_append_only ? "append-only" : "sem proteção"}`}
                tone={status.audit_ledger_append_only ? "success" : "danger"}
              />
            </View>
            <Text style={styles.meta}>Política: {status.policy_version}</Text>
            <Text style={styles.meta}>Ambiente: {status.environment}</Text>
            <Text style={styles.meta}>Migração mais recente: {status.latest_schema_migration || "não informada"}</Text>
          </StaffRecordCard>

          <StaffRecordCard>
            <Text style={styles.eventTitle}>Infraestrutura e criptografia</Text>
            <View style={styles.statusRow}>
              <StaffStatusBadge label={`PostgreSQL: ${status.database_ok ? "online" : "indisponível"}`} tone={status.database_ok ? "success" : "danger"} />
              <StaffStatusBadge label={`Redis: ${status.redis_ok ? "online" : "indisponível"}`} tone={status.redis_ok ? "success" : "danger"} />
              <StaffStatusBadge label={`PQC: ${status.pqc_ready ? "disponível" : "não aprovada"}`} tone={status.pqc_ready ? "success" : "warning"} />
              <StaffStatusBadge label={`Suíte de laboratório: ${status.lab_suite_enabled ? "habilitada" : "desabilitada"}`} tone={status.lab_suite_enabled ? "warning" : "success"} />
            </View>
            <Text style={styles.meta}>Provedor PQC: {status.pqc_provider_name} {status.pqc_provider_version}</Text>
            <Text style={styles.meta}>Hora autoritativa do servidor: {formatPanelDate(status.server_time_iso)}</Text>
          </StaffRecordCard>

          <StaffRecordCard>
            <Text style={styles.eventTitle}>Como interpretar</Text>
            <Text style={styles.meta}>• Pendente privilegiada: não recebeu acesso aos painéis e precisa de validação administrativa.</Text>
            <Text style={styles.meta}>• Alerta de dispositivo: envio de aviso falhou ou o SMTP ainda não estava configurado.</Text>
            <Text style={styles.meta}>• Checkpoint: consolida e assina uma faixa do ledger append-only; não é criado automaticamente por esta tela.</Text>
            <Text style={styles.meta}>• PQC “não aprovada” não significa que todo o sistema está sem criptografia; indica apenas que o adaptador pós-quântico auditado não está disponível.</Text>
          </StaffRecordCard>
        </>
      ) : !isLoading && !error ? <StaffMessage>Atualize para carregar a telemetria sanitizada.</StaffMessage> : null}
    </StaffSection>
  );
}

function PendingResolutionCard({
  actionLabel,
  count,
  description,
  highlighted,
  onAction,
  resolution,
  title,
}: {
  actionLabel: string;
  count: number;
  description: string;
  highlighted: boolean;
  onAction: () => void;
  resolution: string;
  title: string;
}) {
  return (
    <StaffRecordCard>
      <View style={[styles.pendingCard, highlighted && styles.pendingCardHighlighted]}>
        <View style={styles.pendingCount}>
          <Text style={styles.pendingCountValue}>{count}</Text>
        </View>
        <View style={styles.pendingBannerText}>
          <Text style={styles.eventTitle}>{title}</Text>
          <Text style={styles.reason}>{description}</Text>
          <Text style={styles.meta}>Como resolver: {resolution}</Text>
        </View>
      </View>
      <AppButton onPress={onAction} variant="secondary">{actionLabel}</AppButton>
    </StaffRecordCard>
  );
}

function SecurityPendingContent() {
  const { focus } = useLocalSearchParams<{ focus?: string | string[] }>();
  const focusedIssue = Array.isArray(focus) ? focus[0] : focus;
  const { hasPermission } = useApp();
  const canMonitorTrqBec = hasPermission("security.trq_bec.monitor");
  const [status, setStatus] = useState<TrqBecSecurityStatus | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const loadPendingStatus = useCallback(async () => {
    if (!canMonitorTrqBec) return;
    setIsLoading(true);
    setError("");
    try {
      setStatus(await loadTrqBecSecurityStatus());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível atualizar a Central de pendências.");
      setError(message);
      showStaffAlert("Pendências indisponíveis", message);
    } finally {
      setIsLoading(false);
    }
  }, [canMonitorTrqBec]);

  useEffect(() => {
    const timer = setTimeout(() => void loadPendingStatus(), 0);
    return () => clearTimeout(timer);
  }, [loadPendingStatus]);

  if (!canMonitorTrqBec) {
    return <StaffMessage>Esta conta não recebeu permissão para analisar as pendências do TRQ-BEC.</StaffMessage>;
  }

  return (
    <StaffSection
      description="Mostra a providência correta para cada alerta sem misturar responsabilidades de Administrador, Segurança e titular da conta."
      title="Central de pendências"
    >
      <AppButton disabled={isLoading} onPress={loadPendingStatus} variant="secondary">
        {isLoading ? "Atualizando pendências..." : "Atualizar Central de pendências"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
      {status ? (
        <>
          <PendingResolutionCard
            actionLabel="Revisar trilha de auditoria"
            count={status.privileged_accounts_pending_validation}
            description="Convites de equipe ainda não receberam autoridade administrativa. A Segurança acompanha a trilha, mas não pode escolher função ou aprovar o próprio acesso."
            highlighted={focusedIssue === "privileged"}
            onAction={() => openSecurityTool("audit")}
            resolution="a pessoa confirma o e-mail e um Administrador autenticado recentemente conclui a validação em Equipe autorizada."
            title="Contas privilegiadas pendentes"
          />
          <PendingResolutionCard
            actionLabel="Abrir monitoramento de contas"
            count={status.device_notifications_failed}
            description={`${status.devices_pending} dispositivo(s) ainda estão em cooldown e ${status.device_notifications_failed} alerta(s) não foram entregues.`}
            highlighted={focusedIssue === "devices"}
            onAction={() => openSecurityTool("monitoring")}
            resolution="confira SMTP e o remetente; depois o titular reenvia o aviso em Segurança da minha conta. Um dispositivo desconhecido deve ser revogado pelo titular."
            title="Dispositivos e alertas"
          />
          <PendingResolutionCard
            actionLabel="Voltar ao estado do TRQ-BEC"
            count={status.email_verifications_failed}
            description={`${status.email_verifications_pending} confirmação(ões) aguardam tentativa e ${status.email_verifications_failed} atingiram o limite de falhas.`}
            highlighted={focusedIssue === "email"}
            onAction={() => openSecurityTool("trq-bec")}
            resolution="corrija SMTP/DNS quando houver erro de entrega e solicite um novo envio pela conta afetada; a fila pendente continua com retentativas automáticas."
            title="Verificação de e-mail"
          />
          {(status.privileged_accounts_pending_validation === 0
            && status.device_notifications_failed === 0
            && status.email_verifications_failed === 0) ? (
              <StaffMessage>Nenhuma pendência crítica permanece nos indicadores atuais.</StaffMessage>
            ) : null}
          <StaffMessage>
            Separação obrigatória: a Segurança investiga e acompanha. Aprovação de nova equipe pertence ao Administrador; revogação de dispositivo pertence ao titular da conta.
          </StaffMessage>
        </>
      ) : !isLoading && !error ? <StaffMessage>Atualize para consultar as pendências atuais.</StaffMessage> : null}
    </StaffSection>
  );
}

export default function SecurityScreen() {
  return (
    <AuthorizedPanel
      guide={{
        purpose: "A Segurança audita decisões de acesso, contém incidentes em contas não protegidas e acompanha os controles do TRQ-BEC. Ela observa e contém riscos, mas não cria funções nem escolhe permissões.",
        boundaries: [
          "Contas oficiais, Administrador e outras contas de Segurança são protegidas contra suspensão comum.",
          "Toda suspensão ou reativação exige motivo, confirmação e autenticação recente validada pelo backend.",
          "A telemetria é sanitizada: não exibe chaves, tokens, assinaturas privadas, senhas, mensagens ou dados financeiros.",
          "Criação de equipe e instituições pertence ao Administrador ou ao Suporte; a Segurança acompanha a trilha de auditoria.",
        ],
      }}
      role="security"
      sections={[
        {
          id: "audit",
          title: "Auditoria",
          description: "Consulte eventos autorizados e as justificativas registradas.",
          icon: "document-text-outline",
          permission: "security.audit.read",
          renderContent: () => <AuditContent />,
        },
        {
          id: "incidents",
          title: "Incidentes",
          description: "Analise, justifique e altere somente contas que o backend permite gerenciar.",
          icon: "warning-outline",
          permission: "security.incidents.manage",
          additionalPermissions: ["security.audit.read"],
          renderContent: () => <IncidentsContent />,
        },
        {
          id: "monitoring",
          title: "Monitoramento",
          description: "Veja contas, eventos recentes e saúde geral dos serviços com permissão explícita de auditoria.",
          icon: "shield-checkmark-outline",
          permission: "security.audit.read",
          renderContent: () => <MonitoringContent />,
        },
        {
          id: "trq-bec",
          title: "TRQ-BEC",
          description: "Acompanhe política, ledger, validação privilegiada, dispositivos, filas, PostgreSQL, Redis e disponibilidade PQC sem expor segredos.",
          icon: "pulse-outline",
          permission: "security.trq_bec.monitor",
          renderContent: () => <TrqBecMonitoringContent />,
        },
        {
          id: "pending",
          title: "Central de pendências",
          description: "Analise alertas de contas privilegiadas, dispositivos e verificação de e-mail e veja a providência correta.",
          icon: "alert-circle-outline",
          permission: "security.trq_bec.monitor",
          renderContent: () => <SecurityPendingContent />,
        },
      ]}
      subtitle="Área restrita para auditoria, incidentes e monitoramento."
      title="Painel da Segurança"
    />
  );
}

const styles = StyleSheet.create({
  recordHeader: { alignItems: "flex-start", flexDirection: "row", gap: 10, justifyContent: "space-between" },
  recordTitle: { color: colors.primaryDark, flex: 1, fontSize: 14, fontWeight: "900" },
  role: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  uid: { color: colors.text, fontSize: 11, lineHeight: 16 },
  meta: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
  protectedText: { color: colors.danger, fontSize: 11, fontWeight: "700", lineHeight: 16 },
  eventTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: "900" },
  transition: { color: colors.text, fontSize: 12, fontWeight: "700" },
  reason: { color: colors.text, fontSize: 12, lineHeight: 18 },
  reasonField: { minHeight: 90 },
  characterCount: { color: colors.textMuted, fontSize: 10, textAlign: "right" },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  metricCard: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    flexBasis: 145,
    flexGrow: 1,
    minWidth: 125,
    padding: 13,
  },
  metricButton: { minHeight: 98 },
  metricPressed: { opacity: 0.65 },
  metricHeading: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  metricValue: { color: colors.primaryDark, fontSize: 22, fontWeight: "900" },
  metricLabel: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 2 },
  metricAction: { color: colors.primary, fontSize: 10, fontWeight: "800", marginTop: 7 },
  metricDetailHeading: { alignItems: "center", flexDirection: "row", gap: 10 },
  metricDetailIcon: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderRadius: 20,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  metricDetailValue: { color: colors.primary, fontSize: 20, fontWeight: "900", marginTop: 2 },
  pendingBanner: {
    alignItems: "center",
    backgroundColor: "#FDECEC",
    borderColor: colors.danger,
    borderRadius: 12,
    borderWidth: 1,
    flexDirection: "row",
    gap: 10,
    padding: 13,
  },
  pendingBannerText: { flex: 1 },
  pendingBannerTitle: { color: colors.danger, fontSize: 13, fontWeight: "900" },
  pendingBannerDescription: { color: colors.text, fontSize: 11, lineHeight: 16, marginTop: 3 },
  pendingBannerLink: { color: colors.primary, fontSize: 11, fontWeight: "900", marginTop: 7 },
  pendingCard: { alignItems: "flex-start", flexDirection: "row", gap: 12 },
  pendingCardHighlighted: {
    backgroundColor: "#FFF8E8",
    borderColor: colors.accent,
    borderRadius: 10,
    borderWidth: 1,
    padding: 10,
  },
  pendingCount: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderRadius: 22,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  pendingCountValue: { color: colors.primaryDark, fontSize: 19, fontWeight: "900" },
  statusRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
});
