import { sendPasswordResetEmail } from "firebase/auth";
import { useCallback, useEffect, useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { AuthorizedPanel } from "@/components/authorized-panel";
import {
  ACCOUNT_STATUS_LABELS,
  ACCOUNT_ROLE_LABELS,
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
import { auth } from "@/services/firebase";
import {
  createManagedInstitution,
  createStaffAccount,
  listAdminAccounts,
  listManagedInstitutions,
  listStaffAccounts,
  loadAdminOperationsSummary,
  validateStaffAccount,
  type AccessRole,
  type AdminOperationsSummary,
  type ManagedAccountSummary,
  type ManagedInstitution,
} from "@/security/trq-bec/service";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function AdminAccountsContent() {
  const { hasPermission } = useApp();
  const canManageAccounts = hasPermission("admin.accounts.manage");
  const [accounts, setAccounts] = useState<ManagedAccountSummary[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const loadAccounts = useCallback(async () => {
    if (!canManageAccounts) return;
    setIsLoading(true);
    setError("");
    try {
      setAccounts(await listAdminAccounts());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível consultar as contas.");
      setError(message);
      showStaffAlert("Contas indisponíveis", message);
    } finally {
      setIsLoading(false);
    }
  }, [canManageAccounts]);

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

  if (!canManageAccounts) {
    return <StaffMessage>Esta conta não recebeu permissão para consultar contas e acessos.</StaffMessage>;
  }

  return (
    <StaffSection
      description="Consulta administrativa. Funções e permissões são definidas pelo backend e não podem ser editadas livremente nesta tela."
      title="Contas e acessos"
    >
      <FormField
        autoCapitalize="none"
        autoCorrect={false}
        label="Filtrar por e-mail, UID, função ou status"
        onChangeText={setQuery}
        placeholder="Digite para filtrar"
        value={query}
      />
      <AppButton disabled={isLoading} onPress={loadAccounts} variant="secondary">
        {isLoading ? "Atualizando contas..." : "Atualizar contas"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
      {!isLoading ? <Text style={styles.resultCount}>{filteredAccounts.length} de {accounts.length} conta(s)</Text> : null}
      {!isLoading && filteredAccounts.length === 0 ? <StaffMessage>Nenhuma conta encontrada.</StaffMessage> : null}
      {filteredAccounts.map((account) => (
        <StaffRecordCard key={account.firebase_uid}>
          <View style={styles.recordHeader}>
            <Text style={styles.recordTitle}>{account.email || "E-mail não informado"}</Text>
            <StaffStatusBadge
              label={ACCOUNT_STATUS_LABELS[account.status]}
              tone={getAccountStatusTone(account.status)}
            />
          </View>
          <Text style={styles.role}>{ACCOUNT_ROLE_LABELS[account.role]}</Text>
          <Text selectable style={styles.recordMeta}>UID: {account.firebase_uid}</Text>
          <Text style={styles.recordDescription}>
            Permissões autorizadas: {account.permissions?.length ? account.permissions.join(", ") : "nenhuma"}
          </Text>
          <Text style={styles.recordMeta}>Atualizada em {formatPanelDate(account.updated_at)}</Text>
        </StaffRecordCard>
      ))}
    </StaffSection>
  );
}

type StaffRole = Extract<AccessRole, "admin" | "support" | "security">;

const STAFF_ROLE_OPTIONS: { label: string; role: StaffRole }[] = [
  { label: "Suporte", role: "support" },
  { label: "Segurança", role: "security" },
  { label: "Administrador", role: "admin" },
];

const VALIDATION_LABELS = {
  APPROVED: "Autoridade validada",
  PENDING: "Aguardando validação",
  REJECTED: "Validação rejeitada",
  REVOKED: "Autoridade revogada",
} as const;

function AdminStaffContent() {
  const { hasPermission } = useApp();
  const canManageStaff = hasPermission("admin.staff_accounts.manage");
  const [accounts, setAccounts] = useState<ManagedAccountSummary[]>([]);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<StaffRole>("support");
  const [pendingValidation, setPendingValidation] = useState<ManagedAccountSummary | null>(null);
  const [validationReason, setValidationReason] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [validatingUid, setValidatingUid] = useState<string | null>(null);

  const loadAccounts = useCallback(async () => {
    if (!canManageStaff) return;
    setIsLoading(true);
    setError("");
    try {
      setAccounts(await listStaffAccounts());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar a equipe autorizada.");
      setError(message);
      showStaffAlert("Equipe indisponível", message);
    } finally {
      setIsLoading(false);
    }
  }, [canManageStaff]);

  useEffect(() => {
    const timer = setTimeout(() => void loadAccounts(), 0);
    return () => clearTimeout(timer);
  }, [loadAccounts]);

  async function handleCreate() {
    const normalizedEmail = email.trim().toLowerCase();
    const normalizedName = displayName.trim();
    if (!EMAIL_PATTERN.test(normalizedEmail) || normalizedName.length < 3) {
      const message = "Informe um nome com ao menos 3 caracteres e um e-mail válido.";
      setError(message);
      showStaffAlert("Revise os dados", message);
      return;
    }
    const confirmed = await confirmStaffAction(
      "Criar conta de equipe pendente?",
      `Será criada uma conta de ${ACCOUNT_ROLE_LABELS[role]} para ${normalizedEmail}. Ela não terá acesso até confirmar o e-mail e ser validada nesta ferramenta.`,
      "Criar pendente",
    );
    if (!confirmed) return;

    setIsSaving(true);
    setError("");
    try {
      const created = await createStaffAccount({
        displayName: normalizedName,
        email: normalizedEmail,
        role,
      });
      setAccounts((current) => [created, ...current.filter((item) => item.firebase_uid !== created.firebase_uid)]);
      setEmail("");
      setDisplayName("");
      try {
        await sendPasswordResetEmail(auth, normalizedEmail);
        showStaffAlert(
          "Conta criada sem acesso",
          "O backend colocou a conta na fila de verificação do e-mail, e o Firebase enviou o link para definição da senha. Depois que o endereço for confirmado, volte aqui para validar a autoridade.",
        );
      } catch (resetError) {
        console.warn("A conta de equipe foi criada, mas a definição de senha não foi enviada.", resetError);
        showStaffAlert(
          "Conta criada sem acesso",
          "A conta permanece pendente e protegida. O e-mail de definição da senha falhou; use a recuperação de senha antes de tentar validá-la.",
        );
      }
    } catch (saveError) {
      const message = getPanelErrorMessage(saveError, "Não foi possível criar a conta de equipe.");
      setError(message);
      showStaffAlert("Conta não criada", message);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleValidate() {
    if (!pendingValidation) return;
    const reason = validationReason.trim();
    if (reason.length < 10) {
      const message = "Registre um motivo de validação com pelo menos 10 caracteres.";
      setError(message);
      showStaffAlert("Motivo obrigatório", message);
      return;
    }
    const confirmed = await confirmStaffAction(
      "Validar autoridade da conta?",
      "O backend confirmará o e-mail no Firebase, aplicará as claims da função, ativará as permissões fechadas e revogará sessões anteriores.",
      "Validar conta",
    );
    if (!confirmed) return;

    setValidatingUid(pendingValidation.firebase_uid);
    setError("");
    try {
      const validated = await validateStaffAccount(pendingValidation.firebase_uid, reason);
      setAccounts((current) => current.map((item) => (
        item.firebase_uid === validated.firebase_uid ? validated : item
      )));
      setPendingValidation(null);
      setValidationReason("");
      showStaffAlert(
        "Conta validada",
        "A autoridade foi registrada no ledger de acesso. A pessoa deverá entrar novamente para receber o token com as novas claims.",
      );
    } catch (validationError) {
      const message = getPanelErrorMessage(validationError, "Não foi possível validar esta conta.");
      setError(message);
      showStaffAlert("Validação não concluída", message);
    } finally {
      setValidatingUid(null);
    }
  }

  if (!canManageStaff) {
    return <StaffMessage>Esta conta não recebeu permissão para criar ou validar equipe.</StaffMessage>;
  }

  return (
    <>
      <StaffSection
        description="O administrador solicita a função, mas não escolhe permissões livres. O backend aplica um pacote fechado e mantém a conta bloqueada até confirmar o e-mail e concluir a validação."
        title="Criar conta de equipe"
      >
        <FormField
          autoCapitalize="words"
          label="Nome da pessoa responsável"
          maxLength={120}
          onChangeText={setDisplayName}
          placeholder="Nome completo"
          value={displayName}
        />
        <FormField
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          label="E-mail oficial"
          maxLength={254}
          onChangeText={setEmail}
          placeholder="pessoa@liberrotas.com.br"
          value={email}
        />
        <Text style={styles.fieldLabel}>Função solicitada</Text>
        <View style={styles.roleSelector}>
          {STAFF_ROLE_OPTIONS.map((option) => (
            <AppButton
              key={option.role}
              disabled={isSaving}
              onPress={() => setRole(option.role)}
              variant={role === option.role ? "primary" : "secondary"}
            >
              {option.label}
            </AppButton>
          ))}
        </View>
        <StaffMessage>
          Fluxo: criar pendente → definir senha → confirmar e-mail → validar com motivo → entrar novamente.
        </StaffMessage>
        <AppButton disabled={isSaving || isLoading} onPress={handleCreate}>
          {isSaving ? "Criando conta pendente..." : "Criar conta pendente"}
        </AppButton>
      </StaffSection>

      {pendingValidation ? (
        <StaffSection
          description="A validação só será aceita se o Firebase já marcar o e-mail como confirmado. Nenhuma função ou permissão pode ser alterada neste formulário."
          title="Validar autoridade"
        >
          <StaffRecordCard>
            <Text style={styles.recordTitle}>{pendingValidation.email}</Text>
            <Text style={styles.role}>{ACCOUNT_ROLE_LABELS[pendingValidation.role]}</Text>
            <Text selectable style={styles.recordMeta}>UID: {pendingValidation.firebase_uid}</Text>
          </StaffRecordCard>
          <FormField
            label="Motivo e conferências realizadas"
            maxLength={500}
            multiline
            onChangeText={setValidationReason}
            placeholder="Ex.: identidade, e-mail oficial e responsabilidade funcional conferidos."
            style={styles.multilineField}
            textAlignVertical="top"
            value={validationReason}
          />
          <Text style={styles.resultCount}>{validationReason.trim().length}/500 caracteres</Text>
          <AppButton disabled={Boolean(validatingUid)} onPress={handleValidate}>
            {validatingUid ? "Validando com o backend..." : "Validar conta"}
          </AppButton>
          <AppButton
            disabled={Boolean(validatingUid)}
            onPress={() => {
              setPendingValidation(null);
              setValidationReason("");
            }}
            variant="secondary"
          >
            Cancelar
          </AppButton>
        </StaffSection>
      ) : null}

      <StaffSection
        description="Contas oficiais são protegidas. Contas novas permanecem pendentes até a validação explícita acima."
        title="Equipe autorizada"
      >
        <AppButton disabled={isLoading || isSaving || Boolean(validatingUid)} onPress={loadAccounts} variant="secondary">
          {isLoading ? "Atualizando equipe..." : "Atualizar equipe"}
        </AppButton>
        {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
        {!isLoading && accounts.length === 0 ? <StaffMessage>Nenhuma conta de equipe encontrada.</StaffMessage> : null}
        {accounts.map((account) => {
          const validationState = account.authority_validation_state;
          const official = account.protection_level === "SYSTEM";
          return (
            <StaffRecordCard key={account.firebase_uid}>
              <View style={styles.recordHeader}>
                <Text style={styles.recordTitle}>{account.email || "E-mail não informado"}</Text>
                <StaffStatusBadge
                  label={official ? "Oficial protegida" : VALIDATION_LABELS[validationState || "PENDING"]}
                  tone={official || validationState === "APPROVED" ? "success" : "warning"}
                />
              </View>
              <Text style={styles.role}>{ACCOUNT_ROLE_LABELS[account.role]}</Text>
              <Text selectable style={styles.recordMeta}>UID: {account.firebase_uid}</Text>
              <Text style={styles.recordDescription}>
                Estado de acesso: {ACCOUNT_STATUS_LABELS[account.status]}. Origem: {account.account_origin === "BOOTSTRAP" ? "conta oficial existente" : "convite administrativo"}.
              </Text>
              <Text style={styles.recordMeta}>Validada em {formatPanelDate(account.authority_validated_at)}</Text>
              {validationState === "PENDING" && account.status === "PENDING" ? (
                <AppButton
                  disabled={Boolean(validatingUid)}
                  onPress={() => {
                    setPendingValidation(account);
                    setValidationReason("");
                  }}
                  variant="secondary"
                >
                  Preparar validação
                </AppButton>
              ) : null}
            </StaffRecordCard>
          );
        })}
      </StaffSection>
    </>
  );
}

function AdminInstitutionsContent() {
  const { hasPermission } = useApp();
  const canManageInstitutions = hasPermission("admin.institutions.manage");
  const [institutions, setInstitutions] = useState<ManagedInstitution[]>([]);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [city, setCity] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [resendingUid, setResendingUid] = useState<string | null>(null);

  const loadInstitutions = useCallback(async () => {
    if (!canManageInstitutions) return;
    setIsLoading(true);
    setError("");
    try {
      setInstitutions(await listManagedInstitutions());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar as instituições.");
      setError(message);
      showStaffAlert("Instituições indisponíveis", message);
    } finally {
      setIsLoading(false);
    }
  }, [canManageInstitutions]);

  useEffect(() => {
    const timer = setTimeout(() => void loadInstitutions(), 0);
    return () => clearTimeout(timer);
  }, [loadInstitutions]);

  async function handleCreateInstitution() {
    const normalizedEmail = email.trim().toLowerCase();
    const normalizedName = name.trim();
    const normalizedCity = city.trim();

    if (!EMAIL_PATTERN.test(normalizedEmail) || normalizedName.length < 2) {
      const message = "Informe o nome da instituição e um e-mail válido para a conta responsável.";
      setError(message);
      showStaffAlert("Revise os dados", message);
      return;
    }
    if (normalizedCity.length === 1) {
      const message = "A cidade deve ter pelo menos 2 caracteres ou ficar em branco.";
      setError(message);
      showStaffAlert("Revise a cidade", message);
      return;
    }

    setIsSaving(true);
    setError("");
    try {
      const created = await createManagedInstitution({
        city: normalizedCity || undefined,
        description: description.trim() || undefined,
        email: normalizedEmail,
        name: normalizedName,
      });
      setInstitutions((current) => [created, ...current.filter((item) => item.firebase_uid !== created.firebase_uid)]);
      setEmail("");
      setName("");
      setDescription("");
      setCity("");
      showStaffAlert(
        "Instituição criada",
        `O cadastro de ${created.name} foi concluído e o backend enviou a ${created.email} o link de primeiro acesso.`,
      );
    } catch (saveError) {
      const message = getPanelErrorMessage(saveError, "Não foi possível criar a instituição.");
      setError(message);
      showStaffAlert("Instituição não criada", message);
    } finally {
      setIsSaving(false);
    }
  }

  async function resendPasswordSetup(institution: ManagedInstitution) {
    setResendingUid(institution.firebase_uid);
    setError("");
    try {
      await sendPasswordResetEmail(auth, institution.email);
      showStaffAlert(
        "E-mail reenviado",
        `O Firebase enviou um novo link de definição de senha para ${institution.email}.`,
      );
    } catch (resetError) {
      console.warn("Não foi possível reenviar o e-mail de definição de senha.", resetError);
      const message = "O e-mail não pôde ser reenviado agora. Aguarde alguns minutos e tente novamente.";
      setError(message);
      showStaffAlert("E-mail não enviado", message);
    } finally {
      setResendingUid(null);
    }
  }

  async function confirmPasswordSetupResend(institution: ManagedInstitution) {
    const confirmed = await confirmStaffAction(
      "Reenviar definição de senha?",
      `Um novo link será enviado somente para ${institution.email}. Links anteriores poderão deixar de ser utilizados.`,
      "Reenviar",
    );
    if (confirmed) await resendPasswordSetup(institution);
  }

  if (!canManageInstitutions) {
    return <StaffMessage>Esta conta não recebeu permissão para gerenciar instituições.</StaffMessage>;
  }

  return (
    <>
      <StaffSection
        description="Cadastre uma instituição usando o e-mail que receberá o link seguro para definir a senha."
        title="Nova instituição"
      >
        <FormField
          autoCapitalize="words"
          label="Nome da instituição"
          maxLength={160}
          onChangeText={setName}
          placeholder="Ex.: Associação de Turismo Local"
          value={name}
        />
        <FormField
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          label="E-mail da conta responsável"
          maxLength={254}
          onChangeText={setEmail}
          placeholder="contato@instituicao.org.br"
          value={email}
        />
        <FormField
          label="Cidade (opcional)"
          maxLength={120}
          onChangeText={setCity}
          placeholder="Cidade - UF"
          value={city}
        />
        <FormField
          label="Descrição (opcional)"
          maxLength={1000}
          multiline
          onChangeText={setDescription}
          placeholder="Explique brevemente a atuação da instituição."
          style={styles.multilineField}
          textAlignVertical="top"
          value={description}
        />
        {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
        <AppButton disabled={isSaving || isLoading || Boolean(resendingUid)} onPress={handleCreateInstitution}>
          {isSaving ? "Criando instituição..." : "Criar instituição"}
        </AppButton>
      </StaffSection>

      <StaffSection
        description={`${institutions.length} instituição(ões) retornada(s) pelo backend.`}
        title="Instituições cadastradas"
      >
        <AppButton disabled={isLoading || isSaving || Boolean(resendingUid)} onPress={loadInstitutions} variant="secondary">
          {isLoading ? "Atualizando..." : "Atualizar lista"}
        </AppButton>
        {!isLoading && institutions.length === 0 ? (
          <StaffMessage>Nenhuma instituição cadastrada.</StaffMessage>
        ) : null}
        {institutions.map((institution) => (
          <StaffRecordCard key={institution.firebase_uid}>
            <View style={styles.recordHeader}>
              <Text style={styles.recordTitle}>{institution.name}</Text>
              <StaffStatusBadge
                label={ACCOUNT_STATUS_LABELS[institution.status]}
                tone={getAccountStatusTone(institution.status)}
              />
            </View>
            <Text style={styles.recordValue}>{institution.email}</Text>
            {institution.city ? <Text style={styles.recordMeta}>{institution.city}</Text> : null}
            {institution.description ? <Text style={styles.recordDescription}>{institution.description}</Text> : null}
            <Text style={styles.recordMeta}>Criada em {formatPanelDate(institution.created_at)}</Text>
            {institution.status === "ACTIVE" || institution.status === "PENDING" ? (
              <AppButton
                disabled={isSaving || Boolean(resendingUid)}
                onPress={() => confirmPasswordSetupResend(institution)}
                variant="secondary"
              >
                {resendingUid === institution.firebase_uid ? "Reenviando..." : "Reenviar definição de senha"}
              </AppButton>
            ) : (
              <Text style={styles.recordMeta}>Reenvio indisponível enquanto a conta estiver suspensa ou desativada.</Text>
            )}
          </StaffRecordCard>
        ))}
      </StaffSection>
    </>
  );
}

function OperationMetric({ label, value }: { label: string; value: number | string }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

function AdminOperationsContent() {
  const { hasPermission } = useApp();
  const canViewOperations = hasPermission("admin.marketplace.manage");
  const [summary, setSummary] = useState<AdminOperationsSummary | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const loadSummary = useCallback(async () => {
    if (!canViewOperations) return;
    setIsLoading(true);
    setError("");
    try {
      setSummary(await loadAdminOperationsSummary());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível consultar a operação da plataforma.");
      setError(message);
      showStaffAlert("Operação indisponível", message);
    } finally {
      setIsLoading(false);
    }
  }, [canViewOperations]);

  useEffect(() => {
    const timer = setTimeout(() => void loadSummary(), 0);
    return () => clearTimeout(timer);
  }, [loadSummary]);

  if (!canViewOperations) {
    return <StaffMessage>Esta conta não recebeu permissão para consultar a operação da plataforma.</StaffMessage>;
  }

  return (
    <StaffSection
      description="Resumo somente leitura calculado pelo backend. Nenhuma chave, segredo ou checkpoint é exposto nesta ferramenta."
      title="Operação da plataforma"
    >
      <AppButton disabled={isLoading} onPress={loadSummary} variant="secondary">
        {isLoading ? "Atualizando operação..." : "Atualizar resumo"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
      {summary ? (
        <>
          <View style={styles.metricGrid}>
            <OperationMetric label="Contas" value={summary.accounts_total} />
            <OperationMetric label="Instituições" value={summary.institutions_total} />
            <OperationMetric label="Grupos ativos" value={summary.groups_active} />
            <OperationMetric label="Grupos totais" value={summary.groups_total} />
            <OperationMetric label="Empreendedores ativos" value={summary.merchants_active} />
            <OperationMetric label="Empreendedores suspensos" value={summary.merchants_suspended} />
            <OperationMetric label="Produtos ativos" value={summary.products_active} />
            <OperationMetric label="Ofertas ativas" value={summary.offers_active} />
          </View>
          <StaffRecordCard>
            <Text style={styles.recordTitle}>Serviços</Text>
            <View style={styles.statusRow}>
              <StaffStatusBadge label={`API: ${summary.health_status}`} tone={summary.health_status === "ok" ? "success" : "danger"} />
              <StaffStatusBadge label={`Banco: ${summary.database_ok ? "online" : "indisponível"}`} tone={summary.database_ok ? "success" : "danger"} />
              <StaffStatusBadge label={`Redis: ${summary.redis_ok ? "online" : "indisponível"}`} tone={summary.redis_ok ? "success" : "danger"} />
              <StaffStatusBadge label={`PQC: ${summary.pqc_ready ? "disponível" : "não aprovada"}`} tone={summary.pqc_ready ? "success" : "warning"} />
            </View>
            <Text style={styles.recordMeta}>Hora do servidor: {formatPanelDate(summary.server_time_iso)}</Text>
          </StaffRecordCard>
          <StaffRecordCard>
            <Text style={styles.recordTitle}>Contas por função</Text>
            {Object.entries(summary.accounts_by_role).map(([role, total]) => (
              <Text key={role} style={styles.recordMeta}>{role}: {total}</Text>
            ))}
            <Text style={styles.recordTitle}>Contas por status</Text>
            {Object.entries(summary.accounts_by_status).map(([status, total]) => (
              <Text key={status} style={styles.recordMeta}>{status}: {total}</Text>
            ))}
          </StaffRecordCard>
        </>
      ) : !isLoading && !error ? <StaffMessage>Atualize o resumo para visualizar a operação.</StaffMessage> : null}
    </StaffSection>
  );
}

export default function AdminScreen() {
  return (
    <AuthorizedPanel
      guide={{
        purpose: "O Administrador governa contas, instituições e a operação. Toda autorização real continua no backend; a tela nunca aceita permissões livres nem promove uma conta por parâmetro de rota.",
        boundaries: [
          "Não atende mensagens privadas nem investiga incidentes no lugar do Suporte ou da Segurança.",
          "Novas contas de equipe permanecem bloqueadas até confirmação do e-mail e validação registrada com motivo.",
          "Contas oficiais protegidas não podem ser excluídas ou suspensas pelos fluxos comuns.",
          "Chaves, senhas, tokens e dados privados do ledger nunca são exibidos neste painel.",
        ],
      }}
      role="admin"
      sections={[
        {
          id: "accounts",
          title: "Contas e acessos",
          description: "Acompanhe contas autorizadas e seus estados de acesso.",
          icon: "people-outline",
          permission: "admin.accounts.manage",
          renderContent: () => <AdminAccountsContent />,
        },
        {
          id: "staff",
          title: "Equipe autorizada",
          description: "Crie Admin, Suporte ou Segurança como contas pendentes e valide a autoridade somente após a confirmação do e-mail.",
          icon: "person-add-outline",
          permission: "admin.staff_accounts.manage",
          renderContent: () => <AdminStaffContent />,
        },
        {
          id: "institutions",
          title: "Instituições",
          description: "Crie instituições e acompanhe os vínculos autorizados.",
          icon: "business-outline",
          permission: "admin.institutions.manage",
          renderContent: () => <AdminInstitutionsContent />,
        },
        {
          id: "operations",
          title: "Operação da plataforma",
          description: "Acompanhe contas, instituições, marketplace e saúde dos serviços em modo sanitizado e somente leitura.",
          icon: "options-outline",
          permission: "admin.marketplace.manage",
          renderContent: () => <AdminOperationsContent />,
        },
      ]}
      subtitle="Gerenciamento autorizado da plataforma e das contas do LiberRotas."
      title="Painel do Administrador"
    />
  );
}

const styles = StyleSheet.create({
  multilineField: { minHeight: 78 },
  fieldLabel: { color: colors.primaryDark, fontSize: 12, fontWeight: "800" },
  roleSelector: { gap: 8 },
  recordHeader: { alignItems: "flex-start", flexDirection: "row", gap: 10, justifyContent: "space-between" },
  recordTitle: { color: colors.primaryDark, flex: 1, fontSize: 15, fontWeight: "900" },
  recordValue: { color: colors.text, fontSize: 13, fontWeight: "600" },
  recordMeta: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
  recordDescription: { color: colors.text, fontSize: 12, lineHeight: 17 },
  role: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  resultCount: { color: colors.textMuted, fontSize: 11, textAlign: "right" },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  metricCard: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    flexBasis: 150,
    flexGrow: 1,
    minWidth: 130,
    padding: 13,
  },
  metricValue: { color: colors.primaryDark, fontSize: 22, fontWeight: "900" },
  metricLabel: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 2 },
  statusRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
});
