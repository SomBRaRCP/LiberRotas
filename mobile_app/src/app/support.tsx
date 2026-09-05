import { sendPasswordResetEmail } from "firebase/auth";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { useTrustedClock } from "@/context/trusted-clock-context";
import {
  createSupportInstitution,
  createClientMessageId,
  getSupportRequest,
  listInstitutionApplications,
  listSupportRequests,
  listSupportAccounts,
  replySupportRequest,
  resolveSupportRequest,
  updateInstitutionApplicationStatus,
  type InstitutionApplication,
  type InstitutionApplicationStatus,
  type ManagedAccountSummary,
  type SupportRequestDetail,
  type SupportRequestStatus,
  type SupportRequestSummary,
} from "@/security/trq-bec/service";
import { auth } from "@/services/firebase";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function SupportToolsContent({ mode }: { mode: "accounts" | "institutions" }) {
  const { hasPermission } = useApp();
  const canReadAccounts = hasPermission("support.accounts.read");
  const canCreateInstitutions = hasPermission("support.institutions.create");
  const [accounts, setAccounts] = useState<ManagedAccountSummary[]>([]);
  const [query, setQuery] = useState("");
  const [institutionEmail, setInstitutionEmail] = useState("");
  const [institutionName, setInstitutionName] = useState("");
  const [institutionDescription, setInstitutionDescription] = useState("");
  const [institutionCity, setInstitutionCity] = useState("");
  const [accountsError, setAccountsError] = useState("");
  const [creationError, setCreationError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [resendingUid, setResendingUid] = useState<string | null>(null);

  const loadAccounts = useCallback(async () => {
    if (!canReadAccounts) return;
    setIsLoading(true);
    setAccountsError("");
    try {
      setAccounts(await listSupportAccounts());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível consultar as contas.");
      setAccountsError(message);
      showStaffAlert("Consulta indisponível", message);
    } finally {
      setIsLoading(false);
    }
  }, [canReadAccounts]);

  useEffect(() => {
    const timer = setTimeout(() => void loadAccounts(), 0);
    return () => clearTimeout(timer);
  }, [loadAccounts]);

  const filteredAccounts = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("pt-BR");
    if (!normalizedQuery) return accounts;
    return accounts.filter((account) => {
      const searchable = [
        account.firebase_uid,
        account.email || "",
        account.role,
        ACCOUNT_ROLE_LABELS[account.role],
        account.status,
        ACCOUNT_STATUS_LABELS[account.status],
      ].join(" ").toLocaleLowerCase("pt-BR");
      return searchable.includes(normalizedQuery);
    });
  }, [accounts, query]);

  async function handleCreateInstitution() {
    const normalizedEmail = institutionEmail.trim().toLowerCase();
    const normalizedName = institutionName.trim();
    const normalizedCity = institutionCity.trim();

    if (!EMAIL_PATTERN.test(normalizedEmail) || normalizedName.length < 2) {
      const message = "Informe o nome da instituição e um e-mail válido para a conta responsável.";
      setCreationError(message);
      showStaffAlert("Revise os dados", message);
      return;
    }
    if (normalizedCity.length === 1) {
      const message = "A cidade deve ter pelo menos 2 caracteres ou ficar em branco.";
      setCreationError(message);
      showStaffAlert("Revise a cidade", message);
      return;
    }

    setIsSaving(true);
    setCreationError("");
    try {
      const created = await createSupportInstitution({
        city: normalizedCity || undefined,
        description: institutionDescription.trim() || undefined,
        email: normalizedEmail,
        name: normalizedName,
      });
      setInstitutionEmail("");
      setInstitutionName("");
      setInstitutionDescription("");
      setInstitutionCity("");
      void loadAccounts();
      showStaffAlert(
        "Instituição criada",
        `O cadastro de ${created.name} foi concluído e o backend enviou a ${created.email} o link de primeiro acesso.`,
      );
    } catch (saveError) {
      const message = getPanelErrorMessage(saveError, "Não foi possível criar a instituição.");
      setCreationError(message);
      showStaffAlert("Instituição não criada", message);
    } finally {
      setIsSaving(false);
    }
  }

  async function resendPasswordSetup(account: ManagedAccountSummary) {
    if (!account.email) return;
    setResendingUid(account.firebase_uid);
    setCreationError("");
    try {
      await sendPasswordResetEmail(auth, account.email);
      showStaffAlert("E-mail reenviado", `Um novo link de definição de senha foi enviado para ${account.email}.`);
    } catch (resetError) {
      console.warn("Não foi possível reenviar o e-mail de definição de senha.", resetError);
      const message = "O e-mail não pôde ser reenviado agora. Aguarde alguns minutos e tente novamente.";
      setCreationError(message);
      showStaffAlert("E-mail não enviado", message);
    } finally {
      setResendingUid(null);
    }
  }

  async function confirmPasswordSetupResend(account: ManagedAccountSummary) {
    if (!account.email) return;
    const confirmed = await confirmStaffAction(
      "Reenviar definição de senha?",
      `Um novo link será enviado somente para ${account.email}.`,
      "Reenviar",
    );
    if (confirmed) await resendPasswordSetup(account);
  }

  if (mode === "accounts") {
    if (!canReadAccounts) {
      return <StaffMessage>Esta conta não recebeu permissão para consultar usuários.</StaffMessage>;
    }

    return (
      <StaffSection
        description="Consulta somente leitura. Nenhuma função, permissão ou status pode ser alterado pelo Suporte."
        title="Consultar contas"
      >
        <FormField
          autoCapitalize="none"
          autoCorrect={false}
          label="Filtrar por e-mail, UID, função ou status"
          onChangeText={setQuery}
          placeholder="Digite para filtrar a lista"
          value={query}
        />
        <AppButton disabled={isLoading} onPress={loadAccounts} variant="secondary">
          {isLoading ? "Consultando..." : "Atualizar consulta"}
        </AppButton>
        {accountsError ? <StaffMessage tone="danger">{accountsError}</StaffMessage> : null}
        {!isLoading ? <Text style={styles.resultCount}>{filteredAccounts.length} de {accounts.length} conta(s)</Text> : null}
        {!isLoading && filteredAccounts.length === 0 ? <StaffMessage>Nenhuma conta encontrada.</StaffMessage> : null}
        {filteredAccounts.map((account) => (
          <StaffRecordCard key={account.firebase_uid}>
            <View style={styles.recordHeader}>
              <Text style={styles.recordTitle}>{account.email || "E-mail não informado"}</Text>
              <StaffStatusBadge label={ACCOUNT_STATUS_LABELS[account.status]} tone={getAccountStatusTone(account.status)} />
            </View>
            <Text style={styles.role}>{ACCOUNT_ROLE_LABELS[account.role]}</Text>
            <Text selectable style={styles.uid}>UID: {account.firebase_uid}</Text>
            <Text style={styles.meta}>Criada em {formatPanelDate(account.created_at)}</Text>
            <Text style={styles.meta}>Atualizada em {formatPanelDate(account.updated_at)}</Text>
          </StaffRecordCard>
        ))}
      </StaffSection>
    );
  }

  return (
    <StaffSection
          description="Crie somente contas institucionais. A função e as permissões são definidas pelo backend e não podem ser escolhidas aqui."
          title="Instituições"
        >
          {!canCreateInstitutions ? (
            <StaffMessage>Esta conta não recebeu permissão para criar instituições.</StaffMessage>
          ) : (
            <>
          <FormField
            autoCapitalize="words"
            label="Nome da instituição"
            maxLength={160}
            onChangeText={setInstitutionName}
            placeholder="Ex.: Associação de Turismo Local"
            value={institutionName}
          />
          <FormField
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            label="E-mail da conta responsável"
            maxLength={254}
            onChangeText={setInstitutionEmail}
            placeholder="contato@instituicao.org.br"
            value={institutionEmail}
          />
          <FormField
            label="Cidade (opcional)"
            maxLength={120}
            onChangeText={setInstitutionCity}
            placeholder="Cidade - UF"
            value={institutionCity}
          />
          <FormField
            label="Descrição (opcional)"
            maxLength={1000}
            multiline
            onChangeText={setInstitutionDescription}
            placeholder="Explique brevemente a atuação da instituição."
            style={styles.multilineField}
            textAlignVertical="top"
            value={institutionDescription}
          />
          {creationError ? <StaffMessage tone="danger">{creationError}</StaffMessage> : null}
          <AppButton disabled={isSaving || isLoading || Boolean(resendingUid)} onPress={handleCreateInstitution}>
            {isSaving ? "Criando instituição..." : "Criar instituição"}
          </AppButton>
            </>
          )}
          {canReadAccounts ? (
            <>
              <Text style={styles.subheading}>Contas institucionais</Text>
              <AppButton disabled={isLoading || isSaving || Boolean(resendingUid)} onPress={loadAccounts} variant="secondary">
                {isLoading ? "Atualizando..." : "Atualizar instituições"}
              </AppButton>
              {accountsError ? <StaffMessage tone="danger">{accountsError}</StaffMessage> : null}
              {accounts.filter((account) => account.role === "institution").map((account) => (
            <StaffRecordCard key={account.firebase_uid}>
              <View style={styles.recordHeader}>
                <Text style={styles.recordTitle}>{account.email || "E-mail não informado"}</Text>
                <StaffStatusBadge
                  label={ACCOUNT_STATUS_LABELS[account.status]}
                  tone={getAccountStatusTone(account.status)}
                />
              </View>
              <Text selectable style={styles.uid}>UID: {account.firebase_uid}</Text>
              <Text style={styles.meta}>Atualizada em {formatPanelDate(account.updated_at)}</Text>
              {account.email && (account.status === "ACTIVE" || account.status === "PENDING") ? (
                <AppButton
                  disabled={isSaving || Boolean(resendingUid)}
                  onPress={() => confirmPasswordSetupResend(account)}
                  variant="secondary"
                >
                  {resendingUid === account.firebase_uid ? "Reenviando..." : "Reenviar definição de senha"}
                </AppButton>
              ) : account.email ? (
                <Text style={styles.meta}>Reenvio indisponível enquanto a conta estiver suspensa ou desativada.</Text>
              ) : null}
            </StaffRecordCard>
              ))}
              {!isLoading && accounts.every((account) => account.role !== "institution") ? (
                <StaffMessage>Nenhuma instituição encontrada.</StaffMessage>
              ) : null}
            </>
          ) : null}
        </StaffSection>
  );
}

const SUPPORT_STATUS_LABELS: Record<SupportRequestStatus, string> = {
  CLOSED: "Encerrado",
  IN_PROGRESS: "Em atendimento",
  OPEN: "Aberto",
  RESOLVED: "Resolvido",
  WAITING_USER: "Aguardando usuário",
};

function supportStatusTone(status: SupportRequestStatus): "neutral" | "success" | "warning" {
  if (status === "RESOLVED" || status === "CLOSED") return "success";
  if (status === "OPEN" || status === "WAITING_USER") return "warning";
  return "neutral";
}

type SupportFilter = "ACTIVE" | "RESOLVED" | "ALL";

function SupportInboxContent() {
  const { hasPermission } = useApp();
  const canManageRequests = hasPermission("support.requests.manage");
  const [requests, setRequests] = useState<SupportRequestSummary[]>([]);
  const [selected, setSelected] = useState<SupportRequestDetail | null>(null);
  const [filter, setFilter] = useState<SupportFilter>("ACTIVE");
  const [query, setQuery] = useState("");
  const [reply, setReply] = useState("");
  const [replyClientId, setReplyClientId] = useState("");
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isReplying, setIsReplying] = useState(false);
  const [isResolving, setIsResolving] = useState(false);
  const selectedRequestIdRef = useRef<string | null>(null);
  const detailRequestIdRef = useRef(0);
  const replyRequestIdRef = useRef(0);
  const resolveRequestIdRef = useRef(0);

  useEffect(() => () => {
    selectedRequestIdRef.current = null;
    detailRequestIdRef.current += 1;
    replyRequestIdRef.current += 1;
    resolveRequestIdRef.current += 1;
  }, []);

  const loadRequests = useCallback(async () => {
    if (!canManageRequests) return;
    setIsLoading(true);
    setError("");
    try {
      const items = await listSupportRequests();
      setRequests(items);
      setSelected((current) => current && items.some((item) => item.request_id === current.request.request_id)
        ? current
        : null);
    } catch (loadError) {
      setError(getPanelErrorMessage(loadError, "Não foi possível carregar os atendimentos."));
    } finally {
      setIsLoading(false);
    }
  }, [canManageRequests]);

  useEffect(() => {
    const timer = setTimeout(() => void loadRequests(), 0);
    return () => clearTimeout(timer);
  }, [loadRequests]);

  const filteredRequests = useMemo(() => requests.filter((request) => {
    const normalizedQuery = query.trim().toLocaleLowerCase("pt-BR");
    if (normalizedQuery && ![
      request.subject,
      request.requester_name,
      request.requester_email || "",
      request.requester_uid,
      request.last_message_preview,
    ].join(" ").toLocaleLowerCase("pt-BR").includes(normalizedQuery)) return false;
    if (filter === "ALL") return true;
    const isFinal = request.status === "RESOLVED" || request.status === "CLOSED";
    return filter === "RESOLVED" ? isFinal : !isFinal;
  }), [filter, query, requests]);

  async function selectRequest(requestId: string) {
    const detailRequestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = detailRequestId;
    selectedRequestIdRef.current = requestId;
    replyRequestIdRef.current += 1;
    resolveRequestIdRef.current += 1;
    setSelected(null);
    setIsLoadingDetail(true);
    setIsReplying(false);
    setIsResolving(false);
    setDetailError("");
    setReply("");
    setReplyClientId("");
    try {
      const detail = await getSupportRequest(requestId);
      if (selectedRequestIdRef.current !== requestId || detailRequestIdRef.current !== detailRequestId) return;
      setSelected(detail);
      setRequests((current) => current.map((item) => (
        item.request_id === requestId
          ? { ...detail.request, unread_count: 0 }
          : item
      )));
    } catch (loadError) {
      if (selectedRequestIdRef.current !== requestId || detailRequestIdRef.current !== detailRequestId) return;
      setDetailError(getPanelErrorMessage(loadError, "Não foi possível abrir este atendimento."));
    } finally {
      if (selectedRequestIdRef.current === requestId && detailRequestIdRef.current === detailRequestId) {
        setIsLoadingDetail(false);
      }
    }
  }

  async function sendReply() {
    if (!selected || !reply.trim() || isReplying || isLoadingDetail) return;
    const requestId = selected.request.request_id;
    const detailRequestId = detailRequestIdRef.current;
    if (selectedRequestIdRef.current !== requestId) return;
    const replyRequestId = replyRequestIdRef.current + 1;
    replyRequestIdRef.current = replyRequestId;
    const clientId = replyClientId || createClientMessageId("support");
    setReplyClientId(clientId);
    setIsReplying(true);
    setDetailError("");
    try {
      await replySupportRequest(requestId, reply, clientId);
      if (
        selectedRequestIdRef.current !== requestId
        || detailRequestIdRef.current !== detailRequestId
        || replyRequestIdRef.current !== replyRequestId
      ) return;
      setReply("");
      setReplyClientId("");
      const refreshed = await getSupportRequest(requestId);
      if (
        selectedRequestIdRef.current !== requestId
        || detailRequestIdRef.current !== detailRequestId
        || replyRequestIdRef.current !== replyRequestId
      ) return;
      setSelected(refreshed);
      await loadRequests();
    } catch (replyError) {
      if (
        selectedRequestIdRef.current !== requestId
        || detailRequestIdRef.current !== detailRequestId
        || replyRequestIdRef.current !== replyRequestId
      ) return;
      setDetailError(getPanelErrorMessage(replyError, "Não foi possível enviar a resposta."));
    } finally {
      if (
        selectedRequestIdRef.current === requestId
        && detailRequestIdRef.current === detailRequestId
        && replyRequestIdRef.current === replyRequestId
      ) {
        setIsReplying(false);
      }
    }
  }

  async function resolveSelectedRequest() {
    if (!selected || isResolving) return;
    const requestId = selected.request.request_id;
    const detailRequestId = detailRequestIdRef.current;
    if (selectedRequestIdRef.current !== requestId) return;
    const confirmed = await confirmStaffAction(
      "Resolver atendimento?",
      "O usuário continuará vendo o histórico, mas não poderá enviar novas mensagens neste atendimento.",
      "Resolver",
    );
    if (
      !confirmed
      || selectedRequestIdRef.current !== requestId
      || detailRequestIdRef.current !== detailRequestId
    ) return;
    const resolveRequestId = resolveRequestIdRef.current + 1;
    resolveRequestIdRef.current = resolveRequestId;
    setIsResolving(true);
    setDetailError("");
    try {
      const request = await resolveSupportRequest(requestId);
      if (
        selectedRequestIdRef.current !== requestId
        || detailRequestIdRef.current !== detailRequestId
        || resolveRequestIdRef.current !== resolveRequestId
      ) return;
      setSelected((current) => current?.request.request_id === requestId ? { ...current, request } : current);
      await loadRequests();
      showStaffAlert("Atendimento resolvido", "O atendimento foi encerrado e preservado no histórico.");
    } catch (resolveError) {
      if (
        selectedRequestIdRef.current !== requestId
        || detailRequestIdRef.current !== detailRequestId
        || resolveRequestIdRef.current !== resolveRequestId
      ) return;
      setDetailError(getPanelErrorMessage(resolveError, "Não foi possível resolver o atendimento."));
    } finally {
      if (
        selectedRequestIdRef.current === requestId
        && detailRequestIdRef.current === detailRequestId
        && resolveRequestIdRef.current === resolveRequestId
      ) {
        setIsResolving(false);
      }
    }
  }

  if (!canManageRequests) {
    return <StaffMessage>Esta conta não recebeu permissão para gerenciar atendimentos.</StaffMessage>;
  }

  const selectedIsFinal = selected?.request.status === "RESOLVED" || selected?.request.status === "CLOSED";

  return (
    <>
      <StaffSection
        description="Somente solicitações abertas pelo botão Contatar Suporte aparecem aqui. Conversas privadas entre usuários não são exibidas."
        title="Caixa de atendimentos"
      >
        <FormField
          autoCapitalize="none"
          autoCorrect={false}
          label="Pesquisar por nome, e-mail, UID, assunto ou mensagem"
          onChangeText={setQuery}
          placeholder="Digite para localizar um atendimento"
          value={query}
        />
        <View style={styles.supportFilters}>
          {(["ACTIVE", "RESOLVED", "ALL"] as SupportFilter[]).map((item) => (
            <Pressable key={item} onPress={() => setFilter(item)} style={[styles.supportFilter, filter === item && styles.supportFilterActive]}>
              <Text style={[styles.supportFilterText, filter === item && styles.supportFilterTextActive]}>
                {item === "ACTIVE" ? "Pendentes" : item === "RESOLVED" ? "Resolvidos" : "Todos"}
              </Text>
            </Pressable>
          ))}
        </View>
        <AppButton disabled={isLoading} onPress={loadRequests} variant="secondary">
          {isLoading ? "Atualizando atendimentos..." : "Atualizar atendimentos"}
        </AppButton>
        {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
        {!isLoading && !error && filteredRequests.length === 0 ? (
          <StaffMessage>Nenhum atendimento encontrado neste filtro.</StaffMessage>
        ) : null}

        <View style={styles.supportWorkspace}>
          <View style={styles.supportList}>
            {filteredRequests.map((request) => (
              <Pressable key={request.request_id} onPress={() => selectRequest(request.request_id)}>
                <StaffRecordCard>
                  <View style={styles.recordHeader}>
                    <Text numberOfLines={2} style={styles.recordTitle}>{request.subject}</Text>
                    <StaffStatusBadge label={SUPPORT_STATUS_LABELS[request.status]} tone={supportStatusTone(request.status)} />
                  </View>
                  <Text style={styles.role}>{request.requester_name}</Text>
                  {request.requester_email ? <Text style={styles.meta}>{request.requester_email}</Text> : null}
                  <Text numberOfLines={2} style={styles.meta}>{request.last_message_preview || "Sem prévia disponível"}</Text>
                  <Text style={styles.meta}>Atualizado em {formatPanelDate(request.updated_at)}</Text>
                  {request.unread_count > 0 ? <Text style={styles.supportUnread}>{request.unread_count} nova(s) mensagem(ns)</Text> : null}
                </StaffRecordCard>
              </Pressable>
            ))}
          </View>

          <View style={styles.supportDetail}>
            {isLoadingDetail ? <StaffMessage>Carregando conversa...</StaffMessage> : null}
            {detailError ? <StaffMessage tone="danger">{detailError}</StaffMessage> : null}
            {!isLoadingDetail && !selected ? (
              <StaffMessage>Selecione um atendimento para ler e responder.</StaffMessage>
            ) : null}
            {selected ? (
              <StaffRecordCard>
                <View style={styles.recordHeader}>
                  <Text style={styles.recordTitle}>{selected.request.subject}</Text>
                  <StaffStatusBadge label={SUPPORT_STATUS_LABELS[selected.request.status]} tone={supportStatusTone(selected.request.status)} />
                </View>
                <Text style={styles.meta}>Solicitante: {selected.request.requester_name}</Text>
                <Text selectable style={styles.uid}>UID: {selected.request.requester_uid}</Text>
                <View style={styles.supportMessages}>
                  {selected.messages.length === 0 ? <Text style={styles.meta}>Nenhuma mensagem neste atendimento.</Text> : null}
                  {selected.messages.map((message) => (
                    <View key={message.message_id} style={[styles.supportMessage, message.sender_role === "support" && styles.supportMessageStaff]}>
                      <Text style={styles.supportMessageAuthor}>
                        {message.sender_role === "support" ? "Equipe de suporte" : message.sender_name}
                      </Text>
                      <Text style={styles.supportMessageText}>{message.content}</Text>
                      <Text style={styles.supportMessageDate}>{formatPanelDate(message.created_at)}</Text>
                    </View>
                  ))}
                </View>
                {!selectedIsFinal ? (
                  <>
                    <FormField
                      editable={!isReplying && !isResolving}
                      label="Resposta"
                      maxLength={2_000}
                      multiline
                      onChangeText={(value) => {
                        setReply(value);
                        setReplyClientId("");
                        setDetailError("");
                      }}
                      placeholder="Escreva uma orientação objetiva, sem solicitar senha ou códigos."
                      style={styles.supportReplyField}
                      textAlignVertical="top"
                      value={reply}
                    />
                    <Text style={styles.resultCount}>{reply.length}/2000</Text>
                    <View style={styles.supportActions}>
                      <AppButton disabled={isReplying || isResolving || !reply.trim()} onPress={sendReply} style={styles.supportActionButton}>
                        {isReplying ? "Enviando..." : "Enviar resposta"}
                      </AppButton>
                      <AppButton disabled={isReplying || isResolving} onPress={resolveSelectedRequest} style={styles.supportActionButton} variant="secondary">
                        {isResolving ? "Resolvendo..." : "Marcar resolvido"}
                      </AppButton>
                    </View>
                  </>
                ) : <StaffMessage>Este atendimento está encerrado e permanece disponível somente para consulta.</StaffMessage>}
              </StaffRecordCard>
            ) : null}
          </View>
        </View>
      </StaffSection>
    </>
  );
}

const INSTITUTION_APPLICATION_STATUS_LABELS: Record<InstitutionApplicationStatus, string> = {
  NEW: "Recebida",
  IN_REVIEW: "Em análise",
  CONTACTED: "Contato realizado",
  APPROVED: "Aprovada",
  REJECTED: "Recusada",
};

function institutionApplicationTone(status: InstitutionApplicationStatus): "neutral" | "success" | "warning" {
  if (status === "APPROVED") return "success";
  if (status === "NEW" || status === "IN_REVIEW") return "warning";
  return "neutral";
}

function InstitutionApplicationsContent() {
  const { hasPermission } = useApp();
  const canManage = hasPermission("support.requests.manage");
  const [applications, setApplications] = useState<InstitutionApplication[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState("");

  const selected = applications.find((item) => item.application_id === selectedId) || null;

  const loadApplications = useCallback(async () => {
    if (!canManage) return;
    setIsLoading(true);
    setError("");
    try {
      const items = await listInstitutionApplications();
      setApplications(items);
      setSelectedId((current) => current && items.some((item) => item.application_id === current) ? current : null);
    } catch (loadError) {
      setError(getPanelErrorMessage(loadError, "Não foi possível carregar as solicitações institucionais."));
    } finally {
      setIsLoading(false);
    }
  }, [canManage]);

  useEffect(() => {
    const timer = setTimeout(() => void loadApplications(), 0);
    return () => clearTimeout(timer);
  }, [loadApplications]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("pt-BR");
    if (!normalized) return applications;
    return applications.filter((item) => [
      item.organization_name,
      item.contact_name,
      item.email,
      item.city,
      item.state,
      item.organization_type,
    ].join(" ").toLocaleLowerCase("pt-BR").includes(normalized));
  }, [applications, query]);

  function selectApplication(application: InstitutionApplication) {
    setSelectedId(application.application_id);
    setNotes(application.support_notes || "");
    setError("");
  }

  async function changeStatus(status: Exclude<InstitutionApplicationStatus, "NEW">) {
    if (!selected || isUpdating) return;
    if (status === "APPROVED") {
      const confirmed = await confirmStaffAction(
        "Aprovar e criar a conta?",
        `O LiberRotas criará a conta institucional de ${selected.organization_name} para ${selected.email} e enviará o link de primeiro acesso. Confira o e-mail antes de continuar.`,
        "Aprovar e criar",
      );
      if (!confirmed) return;
    }
    setIsUpdating(true);
    setError("");
    try {
      const updated = await updateInstitutionApplicationStatus(selected.application_id, status, notes);
      setApplications((current) => current.map((item) => item.application_id === updated.application_id ? updated : item));
      setNotes(updated.support_notes || "");
      showStaffAlert(
        "Solicitação atualizada",
        status === "APPROVED"
          ? "A análise foi aprovada, a conta institucional foi criada e o link de primeiro acesso foi enviado ao solicitante."
          : `Novo estado: ${INSTITUTION_APPLICATION_STATUS_LABELS[status]}.`,
      );
    } catch (updateError) {
      setError(getPanelErrorMessage(updateError, "Não foi possível atualizar esta solicitação."));
    } finally {
      setIsUpdating(false);
    }
  }

  if (!canManage) {
    return <StaffMessage>Esta conta não recebeu permissão para analisar solicitações institucionais.</StaffMessage>;
  }

  return (
    <StaffSection
      description="Pedidos enviados pelo formulário público. Ao aprovar, o backend cria a conta institucional e envia o link de primeiro acesso ao e-mail conferido."
      title="Fila de solicitações institucionais"
    >
      <FormField
        autoCapitalize="none"
        autoCorrect={false}
        label="Pesquisar por organização, responsável, e-mail ou cidade"
        onChangeText={setQuery}
        placeholder="Digite para localizar uma solicitação"
        value={query}
      />
      <AppButton disabled={isLoading} onPress={loadApplications} variant="secondary">
        {isLoading ? "Atualizando solicitações..." : "Atualizar solicitações"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
      {!isLoading && !error && filtered.length === 0 ? (
        <StaffMessage>Nenhuma solicitação institucional encontrada.</StaffMessage>
      ) : null}

      <View style={styles.supportWorkspace}>
        <View style={styles.supportList}>
          {filtered.map((application) => (
            <Pressable key={application.application_id} onPress={() => selectApplication(application)}>
              <StaffRecordCard>
                <View style={styles.recordHeader}>
                  <Text numberOfLines={2} style={styles.recordTitle}>{application.organization_name}</Text>
                  <StaffStatusBadge
                    label={INSTITUTION_APPLICATION_STATUS_LABELS[application.status]}
                    tone={institutionApplicationTone(application.status)}
                  />
                </View>
                <Text style={styles.role}>{application.organization_type === "NGO" ? "ONG" : "Empresa"}</Text>
                <Text style={styles.meta}>{application.contact_name} · {application.email}</Text>
                <Text style={styles.meta}>{application.city}/{application.state}</Text>
                <Text style={styles.meta}>Recebida em {formatPanelDate(application.created_at)}</Text>
              </StaffRecordCard>
            </Pressable>
          ))}
        </View>

        <View style={styles.supportDetail}>
          {!selected ? <StaffMessage>Selecione uma solicitação para conferir os dados e registrar a análise.</StaffMessage> : (
            <StaffRecordCard>
              <View style={styles.recordHeader}>
                <Text style={styles.recordTitle}>{selected.organization_name}</Text>
                <StaffStatusBadge
                  label={INSTITUTION_APPLICATION_STATUS_LABELS[selected.status]}
                  tone={institutionApplicationTone(selected.status)}
                />
              </View>
              <Text style={styles.meta}>Tipo: {selected.organization_type === "NGO" ? "ONG" : "Empresa"}</Text>
              <Text style={styles.meta}>Responsável: {selected.contact_name}</Text>
              <Text selectable style={styles.meta}>E-mail: {selected.email}</Text>
              <Text selectable style={styles.meta}>Telefone: {selected.phone || "não informado"}</Text>
              <Text style={styles.meta}>CNPJ/registro: {selected.registration_number || "não informado"}</Text>
              <Text style={styles.meta}>Localidade: {selected.city}/{selected.state}</Text>
              <Text selectable style={styles.meta}>Site/rede social: {selected.website_or_social || "não informado"}</Text>
              <Text style={styles.subheading}>Apresentação</Text>
              <Text style={styles.applicationDescription}>{selected.description}</Text>
              <FormField
                editable={!isUpdating && selected.status !== "APPROVED"}
                label="Observações internas do Suporte"
                maxLength={1_000}
                multiline
                onChangeText={setNotes}
                placeholder="Registre somente informações necessárias para a análise."
                style={styles.supportReplyField}
                textAlignVertical="top"
                value={notes}
              />
              {selected.status === "APPROVED" ? (
                <StaffMessage>Conta institucional criada. Esta aprovação fica preservada no histórico.</StaffMessage>
              ) : (
                <View style={styles.applicationActions}>
                  <AppButton disabled={isUpdating} onPress={() => changeStatus("IN_REVIEW")} style={styles.applicationAction} variant="secondary">Em análise</AppButton>
                  <AppButton disabled={isUpdating} onPress={() => changeStatus("CONTACTED")} style={styles.applicationAction} variant="secondary">Contato feito</AppButton>
                  <AppButton disabled={isUpdating} onPress={() => changeStatus("APPROVED")} style={styles.applicationAction}>Aprovar e criar conta</AppButton>
                  <AppButton disabled={isUpdating} onPress={() => changeStatus("REJECTED")} style={styles.applicationAction} variant="danger">Recusar</AppButton>
                </View>
              )}
            </StaffRecordCard>
          )}
        </View>
      </View>
    </StaffSection>
  );
}

function SupportGuidanceContent() {
  const { accessSession, hasPermission } = useApp();
  const { lastSynchronizedAtMs, status, synchronize } = useTrustedClock();
  const [isSynchronizing, setIsSynchronizing] = useState(false);

  async function handleSynchronize() {
    setIsSynchronizing(true);
    try {
      await synchronize();
    } finally {
      setIsSynchronizing(false);
    }
  }

  return (
    <StaffSection
      description="Diagnóstico simples para orientar o atendimento sem alterar contas, funções ou dados de segurança."
      title="Orientações e diagnóstico"
    >
      <StaffRecordCard>
        <Text style={styles.recordTitle}>Estado desta sessão</Text>
        <Text style={styles.meta}>Acesso: {accessSession?.access_state || "não resolvido"}</Text>
        <Text style={styles.meta}>Consulta de contas: {hasPermission("support.accounts.read") ? "liberada" : "não liberada"}</Text>
        <Text style={styles.meta}>Criação de instituição: {hasPermission("support.institutions.create") ? "liberada" : "não liberada"}</Text>
        <Text style={styles.meta}>Relógio: {status === "synchronized" ? "sincronizado com o servidor" : "sem sincronização"}</Text>
        <Text style={styles.meta}>
          Última sincronização: {lastSynchronizedAtMs ? formatPanelDate(new Date(lastSynchronizedAtMs).toISOString()) : "não registrada"}
        </Text>
      </StaffRecordCard>
      <AppButton disabled={isSynchronizing} onPress={handleSynchronize} variant="secondary">
        {isSynchronizing ? "Sincronizando..." : "Sincronizar relógio agora"}
      </AppButton>
      <StaffRecordCard>
        <Text style={styles.recordTitle}>Procedimento de atendimento</Text>
        <Text style={styles.meta}>1. Localize a conta pelo e-mail informado pela pessoa.</Text>
        <Text style={styles.meta}>2. Confira função e status sem solicitar ou visualizar senha.</Text>
        <Text style={styles.meta}>3. Para instituições, reenvie o link somente após confirmar o e-mail.</Text>
        <Text style={styles.meta}>4. Encaminhe suspeitas de fraude ou suspensão para a Segurança.</Text>
        <Text style={styles.meta}>5. Nunca altere função, permissão ou Custom Claims pelo atendimento.</Text>
      </StaffRecordCard>
    </StaffSection>
  );
}

export default function SupportScreen() {
  return (
    <AuthorizedPanel
      guide={{
        purpose: "O Suporte atende solicitações, consulta o estado mínimo das contas e provisiona instituições. Ele orienta e diagnostica sem alterar função, permissão, Custom Claims ou decisões de Segurança.",
        boundaries: [
          "Nunca solicite senha, código de verificação, chave privada ou conteúdo de token.",
          "Suspeitas de fraude, bloqueio e contenção devem ser encaminhadas à Segurança.",
          "A consulta de contas não mostra permissões internas nem permite promover ou suspender usuários.",
          "Instituições são sempre criadas com função fixa definida pelo backend; o formulário não aceita role ou permissão.",
        ],
      }}
      role="support"
      sections={[
        {
          id: "requests",
          title: "Atendimentos",
          description: "Responda solicitações privadas de suporte e consulte contas sem alterar permissões.",
          icon: "chatbubbles-outline",
          permission: "support.requests.manage",
          renderContent: () => <SupportInboxContent />,
        },
        {
          id: "accounts",
          title: "Consulta de contas",
          description: "Localize função e status para orientar o usuário, em modo somente leitura e sem visualizar permissões internas.",
          icon: "search-outline",
          permission: "support.accounts.read",
          renderContent: () => <SupportToolsContent mode="accounts" />,
        },
        {
          id: "institution-applications",
          title: "Solicitações de instituição",
          description: "Analise empresas e ONGs que manifestaram interesse pelo formulário público.",
          icon: "document-text-outline",
          permission: "support.requests.manage",
          renderContent: () => <InstitutionApplicationsContent />,
        },
        {
          id: "institutions",
          title: "Instituições",
          description: "Crie instituições e reenvie o link seguro de definição da senha.",
          icon: "business-outline",
          permission: "support.institutions.create",
          renderContent: () => <SupportToolsContent mode="institutions" />,
        },
        {
          id: "guidance",
          title: "Orientações e diagnóstico",
          description: "Consulte procedimentos e valide a sessão e o relógio do serviço.",
          icon: "book-outline",
          permission: "support.panel.access",
          renderContent: () => <SupportGuidanceContent />,
        },
      ]}
      subtitle="Atendimento e consulta controlada das contas do LiberRotas."
      title="Painel do Suporte"
    />
  );
}

const styles = StyleSheet.create({
  multilineField: { minHeight: 78 },
  resultCount: { color: colors.textMuted, fontSize: 11, textAlign: "right" },
  recordHeader: { alignItems: "flex-start", flexDirection: "row", gap: 10, justifyContent: "space-between" },
  recordTitle: { color: colors.primaryDark, flex: 1, fontSize: 14, fontWeight: "900" },
  role: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  uid: { color: colors.text, fontSize: 11, lineHeight: 16 },
  meta: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
  subheading: { color: colors.primaryDark, fontSize: 15, fontWeight: "900", marginTop: 4 },
  supportFilters: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  supportFilter: { borderColor: colors.border, borderRadius: 999, borderWidth: 1, paddingHorizontal: 13, paddingVertical: 8 },
  supportFilterActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  supportFilterText: { color: colors.primary, fontSize: 11, fontWeight: "800" },
  supportFilterTextActive: { color: colors.surface },
  supportWorkspace: { alignItems: "flex-start", flexDirection: "row", flexWrap: "wrap", gap: 14 },
  supportList: { flex: 1, flexBasis: 320, gap: 9, minWidth: 260 },
  supportDetail: { flex: 2, flexBasis: 440, minWidth: 280 },
  supportUnread: { color: colors.accent, fontSize: 10, fontWeight: "900" },
  supportMessages: { gap: 8, marginTop: 10 },
  supportMessage: { alignSelf: "flex-start", backgroundColor: colors.surfaceMuted, borderRadius: 12, maxWidth: "90%", padding: 10 },
  supportMessageStaff: { alignSelf: "flex-end", backgroundColor: colors.cream },
  supportMessageAuthor: { color: colors.primary, fontSize: 10, fontWeight: "900" },
  supportMessageText: { color: colors.text, fontSize: 12, lineHeight: 17, marginTop: 3 },
  supportMessageDate: { color: colors.textMuted, fontSize: 8, marginTop: 4, textAlign: "right" },
  supportReplyField: { minHeight: 110 },
  supportActions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  supportActionButton: { flex: 1, minWidth: 170 },
  applicationDescription: { color: colors.text, fontSize: 12, lineHeight: 18 },
  applicationActions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  applicationAction: { flex: 1, minWidth: 140 },
});
