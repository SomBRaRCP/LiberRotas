import { Ionicons } from "@expo/vector-icons";
import { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import {
  confirmStaffAction,
  formatPanelDate,
  getPanelErrorMessage,
  showStaffAlert,
} from "@/components/staff-panel-ui";
import { AppButton } from "@/components/ui";
import { colors, radius } from "@/constants/theme";
import {
  leaveInstitutionMembership,
  listEntrepreneurInstitutionMemberships,
  respondInstitutionInvitation,
  type InstitutionMembership,
} from "@/security/trq-bec/service";

const MEMBERSHIP_STATUS_LABELS: Record<InstitutionMembership["status"], string> = {
  ACTIVE: "Filiação ativa",
  DECLINED: "Convite recusado",
  LEFT: "Filiação encerrada por você",
  PENDING: "Convite pendente",
  REMOVED: "Removido pela instituição",
};

function MembershipCard({
  membership,
  isWorking,
  onAccept,
  onDecline,
  onLeave,
}: {
  membership: InstitutionMembership;
  isWorking: boolean;
  onAccept: () => void;
  onDecline: () => void;
  onLeave: () => void;
}) {
  const isPending = membership.status === "PENDING";
  const isActive = membership.status === "ACTIVE";

  return (
    <View style={styles.membershipCard}>
      <View style={styles.cardHeader}>
        <View style={styles.cardTitleGroup}>
          <Text style={styles.institutionName}>{membership.institution_name}</Text>
          <Text style={styles.groupName}>{membership.group_name}</Text>
        </View>
        <View style={[styles.statusBadge, isActive && styles.statusBadgeActive]}>
          <Text style={[styles.statusText, isActive && styles.statusTextActive]}>
            {MEMBERSHIP_STATUS_LABELS[membership.status]}
          </Text>
        </View>
      </View>
      <Text style={styles.meta}>Convite recebido em {formatPanelDate(membership.invited_at)}</Text>
      {isActive && membership.active_from ? (
        <Text style={styles.meta}>Filiação iniciada em {formatPanelDate(membership.active_from)}</Text>
      ) : null}
      {isPending ? (
        <View style={styles.actions}>
          <AppButton disabled={isWorking} onPress={onDecline} style={styles.actionButton} variant="secondary">
            {isWorking ? "Aguarde..." : "Recusar"}
          </AppButton>
          <AppButton disabled={isWorking} onPress={onAccept} style={styles.actionButton}>
            {isWorking ? "Aguarde..." : "Aceitar convite"}
          </AppButton>
        </View>
      ) : null}
      {isActive ? (
        <AppButton disabled={isWorking} onPress={onLeave} variant="danger">
          {isWorking ? "Saindo do grupo..." : "Sair desta filiação"}
        </AppButton>
      ) : null}
    </View>
  );
}

/** Convites e filiação institucional da conta empreendedora autenticada. */
export function EntrepreneurInstitutionMemberships() {
  const [memberships, setMemberships] = useState<InstitutionMembership[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [workingMembershipId, setWorkingMembershipId] = useState<string | null>(null);
  const requestSequenceRef = useRef(0);

  const loadMemberships = useCallback(async () => {
    const requestSequence = ++requestSequenceRef.current;
    setIsLoading(true);
    setError("");
    try {
      const loaded = await listEntrepreneurInstitutionMemberships();
      if (requestSequence === requestSequenceRef.current) setMemberships(loaded);
    } catch (loadError) {
      if (requestSequence !== requestSequenceRef.current) return;
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar seus convites institucionais.");
      setError(message);
    } finally {
      if (requestSequence === requestSequenceRef.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void loadMemberships(), 0);
    return () => {
      clearTimeout(timer);
      requestSequenceRef.current += 1;
    };
  }, [loadMemberships]);

  function replaceMembership(updated: InstitutionMembership) {
    setMemberships((current) => current.map((item) => (
      item.membership_id === updated.membership_id ? updated : item
    )));
  }

  async function respond(membership: InstitutionMembership, decision: "ACCEPT" | "DECLINE") {
    setWorkingMembershipId(membership.membership_id);
    setError("");
    try {
      const updated = await respondInstitutionInvitation(membership.membership_id, decision);
      replaceMembership(updated);
      showStaffAlert(
        decision === "ACCEPT" ? "Convite aceito" : "Convite recusado",
        decision === "ACCEPT"
          ? `Agora você faz parte do grupo ${updated.group_name}.`
          : `O convite de ${updated.institution_name} foi recusado.`,
      );
    } catch (responseError) {
      const message = getPanelErrorMessage(responseError, "Não foi possível responder ao convite.");
      setError(message);
      showStaffAlert("Convite não atualizado", message);
    } finally {
      setWorkingMembershipId(null);
    }
  }

  async function confirmDecline(membership: InstitutionMembership) {
    const confirmed = await confirmStaffAction(
      "Recusar este convite?",
      `Você recusará o convite para o grupo ${membership.group_name}, de ${membership.institution_name}.`,
      "Recusar",
      true,
    );
    if (confirmed) await respond(membership, "DECLINE");
  }

  async function confirmAccept(membership: InstitutionMembership) {
    const confirmed = await confirmStaffAction(
      "Aceitar esta filiação?",
      `${membership.institution_name} poderá consultar os totais agregados dos seus resgates/vendas e valores registrados durante a filiação ao grupo ${membership.group_name}. A instituição nunca receberá dados do comprador nem sua chave Pix.`,
      "Aceitar filiação",
    );
    if (confirmed) await respond(membership, "ACCEPT");
  }

  async function handleLeave(membership: InstitutionMembership) {
    setWorkingMembershipId(membership.membership_id);
    setError("");
    try {
      const updated = await leaveInstitutionMembership(membership.membership_id);
      replaceMembership(updated);
      showStaffAlert("Filiação encerrada", `Você saiu do grupo ${updated.group_name}.`);
    } catch (leaveError) {
      const message = getPanelErrorMessage(leaveError, "Não foi possível sair desta filiação.");
      setError(message);
      showStaffAlert("Filiação não encerrada", message);
    } finally {
      setWorkingMembershipId(null);
    }
  }

  async function confirmLeave(membership: InstitutionMembership) {
    const confirmed = await confirmStaffAction(
      "Sair desta filiação?",
      "A instituição deixará de receber novos registros de resgates/vendas vinculados a você. O histórico do período em que a filiação esteve ativa será preservado.",
      "Sair da filiação",
      true,
    );
    if (confirmed) await handleLeave(membership);
  }

  const visibleMemberships = memberships.filter((item) => item.status === "PENDING" || item.status === "ACTIVE");
  const pendingCount = visibleMemberships.filter((item) => item.status === "PENDING").length;

  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <View style={styles.sectionIcon}>
          <Ionicons color={colors.primary} name="people-outline" size={21} />
        </View>
        <View style={styles.sectionTitleGroup}>
          <Text style={styles.sectionTitle}>Instituições e grupos</Text>
          <Text style={styles.sectionDescription}>
            Consulte convites e controle sua filiação como vendedor.
          </Text>
        </View>
        <Pressable
          accessibilityLabel="Atualizar convites institucionais"
          accessibilityRole="button"
          disabled={isLoading || Boolean(workingMembershipId)}
          onPress={loadMemberships}
          style={styles.refreshButton}
        >
          <Ionicons color={colors.primary} name="refresh" size={20} />
        </Pressable>
      </View>
      {pendingCount > 0 ? (
        <Text style={styles.pendingNotice}>
          {pendingCount} convite(s) aguardando sua resposta. Aceite apenas instituições que você reconhece.
        </Text>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {isLoading && visibleMemberships.length === 0 ? (
        <Text style={styles.emptyText}>Carregando convites e filiações...</Text>
      ) : null}
      {!isLoading && visibleMemberships.length === 0 ? (
        <Text style={styles.emptyText}>Você não possui convites pendentes nem filiação ativa.</Text>
      ) : null}
      {visibleMemberships.map((membership) => (
        <MembershipCard
          isWorking={workingMembershipId === membership.membership_id}
          key={membership.membership_id}
          membership={membership}
          onAccept={() => void confirmAccept(membership)}
          onDecline={() => void confirmDecline(membership)}
          onLeave={() => void confirmLeave(membership)}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
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
  sectionHeader: { alignItems: "center", flexDirection: "row", gap: 10 },
  sectionIcon: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderRadius: 20,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  sectionTitleGroup: { flex: 1 },
  sectionTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900" },
  sectionDescription: { color: colors.textMuted, fontSize: 11, lineHeight: 15, marginTop: 2 },
  refreshButton: { alignItems: "center", justifyContent: "center", minHeight: 42, minWidth: 42 },
  pendingNotice: {
    backgroundColor: colors.cream,
    borderRadius: radius.small,
    color: colors.primaryDark,
    fontSize: 11,
    fontWeight: "700",
    lineHeight: 16,
    padding: 11,
  },
  membershipCard: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radius.small,
    borderWidth: 1,
    gap: 7,
    padding: 13,
  },
  cardHeader: { alignItems: "flex-start", flexDirection: "row", gap: 8, justifyContent: "space-between" },
  cardTitleGroup: { flex: 1 },
  institutionName: { color: colors.primaryDark, fontSize: 14, fontWeight: "900" },
  groupName: { color: colors.primary, fontSize: 12, fontWeight: "700", marginTop: 2 },
  statusBadge: { backgroundColor: colors.cream, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5 },
  statusBadgeActive: { backgroundColor: "#E8F6EF" },
  statusText: { color: colors.primaryDark, fontSize: 9, fontWeight: "800" },
  statusTextActive: { color: colors.success },
  meta: { color: colors.textMuted, fontSize: 10, lineHeight: 15 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 },
  actionButton: { flexBasis: 140, flexGrow: 1, minHeight: 46 },
  error: { color: colors.danger, fontSize: 11, lineHeight: 16 },
  emptyText: { color: colors.textMuted, fontSize: 11, lineHeight: 16, textAlign: "center" },
});
