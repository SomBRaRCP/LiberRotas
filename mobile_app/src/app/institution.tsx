import { useCallback, useEffect, useState } from "react";
import { router, type Href } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { AuthorizedPanel } from "@/components/authorized-panel";
import { MediaImagePicker } from "@/components/media-image-picker";
import { PublicEntityMediaImage } from "@/components/public-entity-media-image";
import { InstitutionFundedEventsContent } from "@/components/institution-funded-events";
import { InstitutionGroupMemberships } from "@/components/institution-group-memberships";
import { InstitutionSalesReportContent } from "@/components/institution-sales-report";
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
import { colors } from "@/constants/theme";
import { useSessionState } from "@/context/app-context";
import {
  closeInstitutionGroup,
  createInstitutionGroup,
  loadInstitutionProfile,
  loadInstitutionReportsSummary,
  listInstitutionGroups,
  type InstitutionGroup,
  type InstitutionProfile,
  type InstitutionReportsSummary,
  updateInstitutionProfile,
} from "@/security/trq-bec/service";
import { uploadImage, type PreparedImageUpload } from "@/services/media-upload";

function InstitutionProfileContent() {
  const { hasPermission } = useSessionState();
  const canManageProfile = hasPermission("institution.profile.manage");
  const [profile, setProfile] = useState<InstitutionProfile | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [city, setCity] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [logoImage, setLogoImage] = useState<PreparedImageUpload | null>(null);

  const loadProfile = useCallback(async () => {
    if (!canManageProfile) return;
    setIsLoading(true);
    setError("");
    try {
      const loaded = await loadInstitutionProfile();
      setProfile(loaded);
      setName(loaded.name);
      setDescription(loaded.description || "");
      setCity(loaded.city || "");
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar o perfil institucional.");
      setError(message);
      showStaffAlert("Perfil indisponível", message);
    } finally {
      setIsLoading(false);
    }
  }, [canManageProfile]);

  useEffect(() => {
    const timer = setTimeout(() => void loadProfile(), 0);
    return () => clearTimeout(timer);
  }, [loadProfile]);

  async function saveProfile() {
    const normalizedName = name.trim();
    const normalizedCity = city.trim();
    if (normalizedName.length < 2) {
      const message = "Informe um nome com pelo menos 2 caracteres.";
      setError(message);
      showStaffAlert("Revise o nome", message);
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
      const updated = await updateInstitutionProfile({
        name: normalizedName,
        description: description.trim() || null,
        city: normalizedCity || null,
      });
      setProfile(updated);
      setName(updated.name);
      setDescription(updated.description || "");
      setCity(updated.city || "");
      showStaffAlert("Perfil atualizado", "As informações institucionais foram salvas pelo backend.");
    } catch (saveError) {
      const message = getPanelErrorMessage(saveError, "Não foi possível salvar o perfil institucional.");
      setError(message);
      showStaffAlert("Perfil não atualizado", message);
    } finally {
      setIsSaving(false);
    }
  }

  async function saveLogo() {
    if (!profile || !logoImage) return;
    setIsSaving(true);
    setError("");
    try {
      await uploadImage(logoImage, {
        entityType: "institution",
        entityId: profile.firebase_uid,
        mediaRole: "institution_logo",
      });
      setLogoImage(null);
      showStaffAlert("Logo publicado", "A versão processada já está disponível no perfil institucional.");
    } catch (saveError) {
      const message = getPanelErrorMessage(saveError, "Não foi possível publicar o logo institucional.");
      setError(message);
      showStaffAlert("Logo não publicado", message);
    } finally {
      setIsSaving(false);
    }
  }

  if (!canManageProfile) {
    return <StaffMessage>Esta conta não recebeu permissão para gerenciar o perfil institucional.</StaffMessage>;
  }

  return (
    <StaffSection
      description="Somente nome, descrição e cidade podem ser alterados aqui. E-mail, função, status e proprietário não são editáveis."
      title="Perfil institucional"
    >
      {profile ? (
        <StaffRecordCard>
          <PublicEntityMediaImage
            contentFit="cover"
            entityId={profile.firebase_uid}
            entityType="institution"
            fallback={null}
            mediaRole="institution_logo"
            style={styles.institutionLogo}
            variant="display"
          />
          <View style={styles.recordHeader}>
            <Text style={styles.recordTitle}>{profile.email}</Text>
            <StaffStatusBadge label={profile.status === "ACTIVE" ? "Ativa" : profile.status} tone={profile.status === "ACTIVE" ? "success" : "warning"} />
          </View>
          <Text style={styles.meta}>Atualizado em {formatPanelDate(profile.updated_at)}</Text>
        </StaffRecordCard>
      ) : null}
      <FormField
        autoCapitalize="words"
        label="Nome da instituição"
        maxLength={160}
        onChangeText={setName}
        placeholder="Nome público da instituição"
        value={name}
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
        placeholder="Apresente a atuação da instituição."
        style={styles.multilineField}
        textAlignVertical="top"
        value={description}
      />
      <MediaImagePicker
        disabled={isLoading || isSaving || !profile}
        hint="Opcional. O arquivo privado é processado em thumbnail e display antes da leitura pública."
        label="Logo institucional"
        onChange={setLogoImage}
        value={logoImage}
      />
      <AppButton disabled={isLoading || isSaving || !profile || !logoImage} onPress={saveLogo} variant="secondary">
        {isSaving && logoImage ? "Enviando logo..." : "Enviar logo institucional"}
      </AppButton>
      {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
      <AppButton disabled={isLoading || isSaving || !profile} onPress={saveProfile}>
        {isSaving ? "Salvando perfil..." : isLoading ? "Carregando perfil..." : "Salvar perfil institucional"}
      </AppButton>
      <AppButton
        disabled={isLoading || isSaving || !profile}
        onPress={() => {
          if (!profile) return;
          router.push({
            pathname: "/profile/[profileId]",
            params: { profileId: profile.firebase_uid, tab: "fairs" },
          } as unknown as Href);
        }}
        variant="secondary"
      >
        Abrir perfil público e gerenciar feiras
      </AppButton>
      <AppButton disabled={isLoading || isSaving} onPress={loadProfile} variant="secondary">
        Atualizar dados
      </AppButton>
    </StaffSection>
  );
}

function InstitutionGroupsContent() {
  const { hasPermission } = useSessionState();
  const canManageGroups = hasPermission("institution.groups.manage");
  const [groups, setGroups] = useState<InstitutionGroup[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [city, setCity] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [closingGroupId, setClosingGroupId] = useState<string | null>(null);

  const loadGroups = useCallback(async () => {
    if (!canManageGroups) return;
    setIsLoading(true);
    setError("");
    try {
      setGroups(await listInstitutionGroups());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar os grupos da instituição.");
      setError(message);
      showStaffAlert("Grupos indisponíveis", message);
    } finally {
      setIsLoading(false);
    }
  }, [canManageGroups]);

  useEffect(() => {
    const timer = setTimeout(() => void loadGroups(), 0);
    return () => clearTimeout(timer);
  }, [loadGroups]);

  async function handleCreateGroup() {
    const normalizedName = name.trim();
    const normalizedCity = city.trim();
    if (normalizedName.length < 2) {
      const message = "Informe um nome com pelo menos 2 caracteres para o grupo.";
      setError(message);
      showStaffAlert("Nome necessário", message);
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
      const created = await createInstitutionGroup({
        city: normalizedCity || undefined,
        description: description.trim() || undefined,
        name: normalizedName,
      });
      setGroups((current) => [created, ...current.filter((item) => item.group_id !== created.group_id)]);
      setName("");
      setDescription("");
      setCity("");
      showStaffAlert("Grupo criado", `${created.name} já está disponível no painel da instituição.`);
    } catch (saveError) {
      const message = getPanelErrorMessage(saveError, "Não foi possível criar o grupo.");
      setError(message);
      showStaffAlert("Grupo não criado", message);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleCloseGroup(group: InstitutionGroup) {
    setClosingGroupId(group.group_id);
    setError("");
    try {
      const closed = await closeInstitutionGroup(group.group_id);
      setGroups((current) => current.map((item) => item.group_id === closed.group_id ? closed : item));
      showStaffAlert("Grupo encerrado", `${closed.name} foi encerrado e permanece no histórico.`);
    } catch (closeError) {
      const message = getPanelErrorMessage(closeError, "Não foi possível encerrar o grupo.");
      setError(message);
      showStaffAlert("Grupo não encerrado", message);
    } finally {
      setClosingGroupId(null);
    }
  }

  async function confirmCloseGroup(group: InstitutionGroup) {
    const confirmed = await confirmStaffAction(
      "Encerrar este grupo?",
      "O grupo deixará de ficar ativo, mas continuará visível no histórico da instituição.",
      "Encerrar",
      true,
    );
    if (confirmed) await handleCloseGroup(group);
  }

  if (!canManageGroups) {
    return <StaffMessage>Esta conta não recebeu permissão para gerenciar grupos institucionais.</StaffMessage>;
  }

  return (
    <>
      <StaffSection
        description="O backend vincula automaticamente o grupo à instituição autenticada."
        title="Criar grupo"
      >
        <FormField
          autoCapitalize="sentences"
          label="Nome do grupo"
          maxLength={160}
          onChangeText={setName}
          placeholder="Ex.: Rede de Artesãos Locais"
          value={name}
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
          placeholder="Objetivo e atuação do grupo."
          style={styles.multilineField}
          textAlignVertical="top"
          value={description}
        />
        {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
        <AppButton disabled={isSaving || isLoading || Boolean(closingGroupId)} onPress={handleCreateGroup}>
          {isSaving ? "Criando grupo..." : "Criar grupo"}
        </AppButton>
      </StaffSection>

      <StaffSection
        description={`${groups.length} grupo(s) próprio(s) retornado(s) pelo backend.`}
        title="Grupos da instituição"
      >
        <AppButton disabled={isLoading || isSaving || Boolean(closingGroupId)} onPress={loadGroups} variant="secondary">
          {isLoading ? "Atualizando..." : "Atualizar grupos"}
        </AppButton>
        {!isLoading && groups.length === 0 ? <StaffMessage>Nenhum grupo cadastrado.</StaffMessage> : null}
        {groups.map((group) => (
          <StaffRecordCard key={group.group_id}>
            <View style={styles.recordHeader}>
              <Text style={styles.recordTitle}>{group.name}</Text>
              <StaffStatusBadge
                label={group.status === "ACTIVE" ? "Ativo" : "Encerrado"}
                tone={group.status === "ACTIVE" ? "success" : "neutral"}
              />
            </View>
            {group.city ? <Text style={styles.city}>{group.city}</Text> : null}
            {group.description ? <Text style={styles.description}>{group.description}</Text> : null}
            <Text style={styles.meta}>Criado em {formatPanelDate(group.created_at)}</Text>
            {group.closed_at ? <Text style={styles.meta}>Encerrado em {formatPanelDate(group.closed_at)}</Text> : null}
            {group.status === "ACTIVE" ? (
              <AppButton
                disabled={Boolean(closingGroupId) || isSaving}
                onPress={() => confirmCloseGroup(group)}
                variant="danger"
              >
                {closingGroupId === group.group_id ? "Encerrando..." : "Encerrar grupo"}
              </AppButton>
            ) : null}
          </StaffRecordCard>
        ))}
      </StaffSection>
      <InstitutionGroupMemberships groups={groups} />
    </>
  );
}

function ReportMetric({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

function InstitutionReportsContent() {
  const { hasPermission } = useSessionState();
  const canReadReports = hasPermission("institution.reports.read");
  const [summary, setSummary] = useState<InstitutionReportsSummary | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const loadSummary = useCallback(async () => {
    if (!canReadReports) return;
    setIsLoading(true);
    setError("");
    try {
      setSummary(await loadInstitutionReportsSummary());
    } catch (loadError) {
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar os relatórios institucionais.");
      setError(message);
      showStaffAlert("Relatórios indisponíveis", message);
    } finally {
      setIsLoading(false);
    }
  }, [canReadReports]);

  useEffect(() => {
    const timer = setTimeout(() => void loadSummary(), 0);
    return () => clearTimeout(timer);
  }, [loadSummary]);

  if (!canReadReports) {
    return <StaffMessage>Esta conta não recebeu permissão para consultar relatórios.</StaffMessage>;
  }

  return (
    <>
      <StaffSection
        description="Indicadores agregados somente dos grupos pertencentes à instituição autenticada."
        title="Visão geral dos grupos"
      >
        <AppButton disabled={isLoading} onPress={loadSummary} variant="secondary">
          {isLoading ? "Atualizando resumo..." : "Atualizar resumo"}
        </AppButton>
        {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
        {summary ? (
          <>
            <View style={styles.metricGrid}>
              <ReportMetric label="Grupos totais" value={summary.total_groups} />
              <ReportMetric label="Grupos ativos" value={summary.active_groups} />
              <ReportMetric label="Grupos encerrados" value={summary.closed_groups} />
            </View>
            <StaffRecordCard>
              <Text style={styles.recordTitle}>Atualização do resumo</Text>
              <Text style={styles.meta}>Último grupo criado: {formatPanelDate(summary.last_group_created_at)}</Text>
              <Text style={styles.meta}>Resumo gerado em: {formatPanelDate(summary.generated_at)}</Text>
            </StaffRecordCard>
          </>
        ) : !isLoading && !error ? <StaffMessage>Atualize para consultar os indicadores.</StaffMessage> : null}
      </StaffSection>
      <InstitutionSalesReportContent />
    </>
  );
}

export default function InstitutionScreen() {
  return (
    <AuthorizedPanel
      role="institution"
      sections={[
        {
          id: "profile",
          title: "Perfil institucional",
          description: "Mantenha as informações cadastrais da instituição atualizadas.",
          icon: "business-outline",
          permission: "institution.profile.manage",
          renderContent: () => <InstitutionProfileContent />,
        },
        {
          id: "groups",
          title: "Grupos",
          description: "Crie, acompanhe e encerre somente os grupos da sua instituição.",
          icon: "people-outline",
          permission: "institution.groups.manage",
          renderContent: () => <InstitutionGroupsContent />,
        },
        {
          id: "funded-events",
          title: "Eventos com verba",
          description: "Crie promoções financiadas, divida a verba e acompanhe quanto deve a cada afiliado.",
          icon: "cash-outline",
          permission: "institution.events.manage",
          renderContent: () => <InstitutionFundedEventsContent />,
        },
        {
          id: "reports",
          title: "Relatórios",
          description: "Consulte os relatórios disponibilizados para a instituição.",
          icon: "bar-chart-outline",
          permission: "institution.reports.read",
          renderContent: () => <InstitutionReportsContent />,
        },
      ]}
      subtitle="Gestão dos grupos e informações da instituição no LiberRotas."
      title="Painel Institucional"
    />
  );
}

const styles = StyleSheet.create({
  institutionLogo: { backgroundColor: colors.cream, borderRadius: 12, height: 150, marginBottom: 10, width: "100%" },
  multilineField: { minHeight: 78 },
  recordHeader: { alignItems: "flex-start", flexDirection: "row", gap: 10, justifyContent: "space-between" },
  recordTitle: { color: colors.primaryDark, flex: 1, fontSize: 15, fontWeight: "900" },
  city: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  description: { color: colors.text, fontSize: 12, lineHeight: 18 },
  meta: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
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
  metricValue: { color: colors.primaryDark, fontSize: 22, fontWeight: "900" },
  metricLabel: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 2 },
});
