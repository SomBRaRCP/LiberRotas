import { Ionicons } from "@expo/vector-icons";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import {
  inviteInstitutionSeller,
  listInstitutionGroupMemberships,
  removeInstitutionGroupMember,
  type InstitutionGroup,
  type InstitutionMembership,
} from "@/security/trq-bec/service";

const STATUS_LABELS: Record<InstitutionMembership["status"], string> = {
  ACTIVE: "Filiado",
  DECLINED: "Recusado",
  LEFT: "Saiu do grupo",
  PENDING: "Convite pendente",
  REMOVED: "Removido",
};

function statusTone(status: InstitutionMembership["status"]): "danger" | "neutral" | "success" | "warning" {
  if (status === "ACTIVE") return "success";
  if (status === "PENDING") return "warning";
  if (status === "REMOVED") return "danger";
  return "neutral";
}

export function InstitutionGroupMemberships({ groups }: { groups: InstitutionGroup[] }) {
  const [selectedGroupId, setSelectedGroupId] = useState("");
  const [sellerName, setSellerName] = useState("");
  const [memberships, setMemberships] = useState<InstitutionMembership[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isInviting, setIsInviting] = useState(false);
  const [removingMembershipId, setRemovingMembershipId] = useState<string | null>(null);
  const requestSequenceRef = useRef(0);

  const effectiveSelectedGroupId = groups.some((group) => group.group_id === selectedGroupId)
    ? selectedGroupId
    : groups.find((group) => group.status === "ACTIVE")?.group_id || groups[0]?.group_id || "";

  const selectedGroup = useMemo(
    () => groups.find((group) => group.group_id === effectiveSelectedGroupId) || null,
    [effectiveSelectedGroupId, groups],
  );

  const loadMemberships = useCallback(async () => {
    if (!effectiveSelectedGroupId) {
      setMemberships([]);
      return;
    }
    const requestSequence = ++requestSequenceRef.current;
    setIsLoading(true);
    setError("");
    try {
      const loaded = await listInstitutionGroupMemberships(effectiveSelectedGroupId);
      if (requestSequence === requestSequenceRef.current) setMemberships(loaded);
    } catch (loadError) {
      if (requestSequence !== requestSequenceRef.current) return;
      const message = getPanelErrorMessage(loadError, "Não foi possível carregar os membros e convites deste grupo.");
      setError(message);
    } finally {
      if (requestSequence === requestSequenceRef.current) setIsLoading(false);
    }
  }, [effectiveSelectedGroupId]);

  useEffect(() => {
    const timer = setTimeout(() => void loadMemberships(), 0);
    return () => {
      clearTimeout(timer);
      requestSequenceRef.current += 1;
    };
  }, [loadMemberships, selectedGroup?.status]);

  function mergeMembership(updated: InstitutionMembership) {
    setMemberships((current) => [
      updated,
      ...current.filter((item) => item.membership_id !== updated.membership_id),
    ]);
  }

  async function handleInvite() {
    if (!selectedGroup || selectedGroup.status !== "ACTIVE" || isInviting) return;
    const normalizedName = sellerName.trim();
    if (normalizedName.length < 3) {
      const message = "Digite o nome público único completo do empreendedor.";
      setError(message);
      showStaffAlert("Nome necessário", message);
      return;
    }

    setIsInviting(true);
    setError("");
    try {
      const invited = await inviteInstitutionSeller(selectedGroup.group_id, normalizedName);
      mergeMembership(invited);
      setSellerName("");
      showStaffAlert(
        "Convite enviado",
        `${invited.seller_name} poderá aceitar ou recusar o convite no próprio perfil.`,
      );
    } catch (inviteError) {
      const message = getPanelErrorMessage(inviteError, "Não foi possível enviar o convite.");
      setError(message);
      showStaffAlert("Convite não enviado", message);
    } finally {
      setIsInviting(false);
    }
  }

  async function handleRemove(membership: InstitutionMembership) {
    if (!selectedGroup) return;
    setRemovingMembershipId(membership.membership_id);
    setError("");
    try {
      const removed = await removeInstitutionGroupMember(
        selectedGroup.group_id,
        membership.membership_id,
      );
      mergeMembership(removed);
      showStaffAlert(
        membership.status === "PENDING" ? "Convite cancelado" : "Vendedor removido",
        membership.status === "PENDING"
          ? `O convite pendente de ${removed.seller_name} foi cancelado.`
          : `${removed.seller_name} não está mais filiado a este grupo.`,
      );
    } catch (removeError) {
      const message = getPanelErrorMessage(removeError, "Não foi possível remover este vendedor.");
      setError(message);
      showStaffAlert("Vendedor não removido", message);
    } finally {
      setRemovingMembershipId(null);
    }
  }

  async function confirmRemove(membership: InstitutionMembership) {
    const isPending = membership.status === "PENDING";
    const confirmed = await confirmStaffAction(
      isPending ? "Cancelar este convite?" : "Remover vendedor do grupo?",
      isPending
        ? `${membership.seller_name} não poderá mais aceitar este convite. Você poderá enviar outro convite depois.`
        : `Novos resgates/vendas de ${membership.seller_name} deixarão de entrar no relatório deste grupo. O histórico da filiação será preservado.`,
      isPending ? "Cancelar convite" : "Remover vendedor",
      true,
    );
    if (confirmed) await handleRemove(membership);
  }

  function selectGroup(groupId: string) {
    if (groupId === effectiveSelectedGroupId) return;
    requestSequenceRef.current += 1;
    setMemberships([]);
    setError("");
    setSelectedGroupId(groupId);
  }

  const currentMemberships = memberships.filter((item) => item.status === "ACTIVE" || item.status === "PENDING");
  const historyMemberships = memberships.filter((item) => item.status !== "ACTIVE" && item.status !== "PENDING");

  return (
    <StaffSection
      description="Convide pelo nome público único. E-mail, UID, chave Pix e outros dados privados não são exibidos."
      title="Vendedores filiados"
    >
      {groups.length === 0 ? <StaffMessage>Crie um grupo antes de convidar vendedores.</StaffMessage> : (
        <>
          <Text style={styles.fieldLabel}>Selecione o grupo</Text>
          <View style={styles.groupOptions}>
            {groups.map((group) => {
              const selected = group.group_id === effectiveSelectedGroupId;
              return (
                <Pressable
                  accessibilityRole="radio"
                  accessibilityState={{ checked: selected }}
                  key={group.group_id}
                  onPress={() => selectGroup(group.group_id)}
                  style={[styles.groupOption, selected && styles.groupOptionSelected]}
                >
                  <Ionicons
                    color={selected ? colors.surface : colors.primary}
                    name={group.status === "ACTIVE" ? "people" : "archive-outline"}
                    size={15}
                  />
                  <Text numberOfLines={2} style={[styles.groupOptionText, selected && styles.groupOptionTextSelected]}>
                    {group.name}
                  </Text>
                </Pressable>
              );
            })}
          </View>
          {selectedGroup?.status === "ACTIVE" ? (
            <>
              <FormField
                autoCapitalize="words"
                autoCorrect={false}
                editable={!isInviting && !isLoading && !removingMembershipId}
                label="Nome público único do empreendedor"
                maxLength={60}
                onChangeText={setSellerName}
                placeholder="Digite exatamente como aparece no perfil"
                returnKeyType="send"
                value={sellerName}
              />
              <AppButton
                disabled={isInviting || isLoading || Boolean(removingMembershipId) || sellerName.trim().length < 3}
                onPress={handleInvite}
              >
                {isInviting ? "Enviando convite..." : "Convidar empreendedor"}
              </AppButton>
            </>
          ) : selectedGroup ? (
            <StaffMessage>Este grupo está encerrado e não aceita novos convites.</StaffMessage>
          ) : null}
          <AppButton
            disabled={isLoading || isInviting || Boolean(removingMembershipId)}
            onPress={loadMemberships}
            variant="secondary"
          >
            {isLoading ? "Atualizando membros..." : "Atualizar membros e convites"}
          </AppButton>
          {error ? <StaffMessage tone="danger">{error}</StaffMessage> : null}
          {!isLoading && currentMemberships.length === 0 ? (
            <StaffMessage>Este grupo não possui vendedores filiados nem convites pendentes.</StaffMessage>
          ) : null}
          {currentMemberships.map((membership) => (
            <StaffRecordCard key={membership.membership_id}>
              <View style={styles.memberHeader}>
                <Text style={styles.memberName}>{membership.seller_name}</Text>
                <StaffStatusBadge label={STATUS_LABELS[membership.status]} tone={statusTone(membership.status)} />
              </View>
              <Text style={styles.meta}>Convidado em {formatPanelDate(membership.invited_at)}</Text>
              {membership.active_from ? (
                <Text style={styles.meta}>Filiado desde {formatPanelDate(membership.active_from)}</Text>
              ) : null}
              {membership.status === "ACTIVE" || membership.status === "PENDING" ? (
                <AppButton
                  disabled={Boolean(removingMembershipId) || isInviting}
                  onPress={() => void confirmRemove(membership)}
                  variant="danger"
                >
                  {removingMembershipId === membership.membership_id
                    ? membership.status === "PENDING" ? "Cancelando..." : "Removendo..."
                    : membership.status === "PENDING" ? "Cancelar convite" : "Remover do grupo"}
                </AppButton>
              ) : null}
            </StaffRecordCard>
          ))}
          {historyMemberships.length > 0 ? (
            <>
              <Text style={styles.historyTitle}>Histórico recente</Text>
              {historyMemberships.map((membership) => (
                <StaffRecordCard key={membership.membership_id}>
                  <View style={styles.memberHeader}>
                    <Text style={styles.memberName}>{membership.seller_name}</Text>
                    <StaffStatusBadge label={STATUS_LABELS[membership.status]} tone={statusTone(membership.status)} />
                  </View>
                  <Text style={styles.meta}>Atualizado em {formatPanelDate(membership.updated_at)}</Text>
                </StaffRecordCard>
              ))}
            </>
          ) : null}
        </>
      )}
    </StaffSection>
  );
}

const styles = StyleSheet.create({
  fieldLabel: { color: colors.primaryDark, fontSize: 12, fontWeight: "800" },
  groupOptions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  groupOption: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 6,
    maxWidth: "100%",
    minHeight: 42,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  groupOptionSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  groupOptionText: { color: colors.primary, flexShrink: 1, fontSize: 11, fontWeight: "800", maxWidth: 220 },
  groupOptionTextSelected: { color: colors.surface },
  memberHeader: { alignItems: "flex-start", flexDirection: "row", gap: 8, justifyContent: "space-between" },
  memberName: { color: colors.primaryDark, flex: 1, fontSize: 14, fontWeight: "900" },
  meta: { color: colors.textMuted, fontSize: 10, lineHeight: 15 },
  historyTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: "900", marginTop: 4 },
});
