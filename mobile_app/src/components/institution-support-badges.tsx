import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { FormField, AppButton } from "@/components/ui";
import { StaffMessage, StaffStatusBadge, getPanelErrorMessage } from "@/components/staff-panel-ui";
import { colors } from "@/constants/theme";
import type { InstitutionGroup, SupportBadge } from "@/features/institutions/api";
import { setInstitutionBadgePolicy } from "@/security/trq-bec/service";

export const SUPPORT_BADGES = [
  { value: "RED", label: "Vermelho — Precisa de ajuda", tone: "danger", field: "red_percent" },
  { value: "YELLOW", label: "Amarelo — Precisa de atenção", tone: "warning", field: "yellow_percent" },
  { value: "GREEN", label: "Verde — OK", tone: "success", field: "green_percent" },
] as const;

export function SupportBadgeLabel({ badge }: { badge: SupportBadge | null | undefined }) {
  const option = SUPPORT_BADGES.find((item) => item.value === badge);
  return <StaffStatusBadge label={option?.label || "Sem classificação"} tone={option?.tone || "neutral"} />;
}

export function SupportBadgeSelector({ badge, disabled, onSelect }: {
  badge: SupportBadge | null; disabled: boolean; onSelect: (badge: SupportBadge) => void;
}) {
  return (
    <View style={styles.options}>
      {SUPPORT_BADGES.map((option) => (
        <Pressable
          key={option.value}
          accessibilityRole="radio"
          accessibilityLabel={option.label}
          accessibilityState={{ checked: badge === option.value, disabled }}
          disabled={disabled}
          onPress={() => onSelect(option.value)}
          style={[styles.option, badge === option.value && styles.selected, disabled && styles.disabled]}
        >
          <StaffStatusBadge label={`${badge === option.value ? "✓ " : ""}${option.label}`} tone={option.tone} />
        </Pressable>
      ))}
    </View>
  );
}

export function InstitutionBadgePolicyEditor({ group, onUpdated }: {
  group: InstitutionGroup; onUpdated: (group: InstitutionGroup) => void;
}) {
  const [values, setValues] = useState(() => ({
    green_percent: group.badge_policy ? String(group.badge_policy.green_percent) : "",
    yellow_percent: group.badge_policy ? String(group.badge_policy.yellow_percent) : "",
    red_percent: group.badge_policy ? String(group.badge_policy.red_percent) : "",
  }));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const total = Object.values(values).reduce((sum, value) => sum + (Number(value) || 0), 0);
  const valid = total === 100 && Object.values(values).every((value) => /^\d{1,3}$/.test(value) && Number(value) <= 100);

  async function save() {
    if (!valid || saving || group.status !== "ACTIVE") return;
    setSaving(true);
    setMessage("");
    try {
      const updated = await setInstitutionBadgePolicy(group.group_id, {
        green_percent: Number(values.green_percent), yellow_percent: Number(values.yellow_percent), red_percent: Number(values.red_percent),
      });
      onUpdated(updated);
      setFailed(false);
      setMessage("Percentuais salvos. Aplique a divisão no rascunho do evento para calcular as cotas.");
    } catch (error) {
      setFailed(true);
      setMessage(getPanelErrorMessage(error, "Não foi possível salvar os percentuais."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.policy}>
      <Text style={styles.title}>Recursos por selo</Text>
      <Text style={styles.description}>
        Defina quanto do total vai para cada categoria. Use percentuais inteiros que somem 100%.
        Dentro de cada selo, a parcela será dividida igualmente entre os participantes do evento.
        O vermelho indica maior necessidade de ajuda.
      </Text>
      {group.badge_policy ? (
        <StaffMessage>
          Configuração salva: vermelho {group.badge_policy.red_percent}%, amarelo {group.badge_policy.yellow_percent}%, verde {group.badge_policy.green_percent}%.
          Aplique a divisão no rascunho do evento para calcular as cotas.
        </StaffMessage>
      ) : <StaffMessage>Este grupo ainda não tem percentuais configurados.</StaffMessage>}
      {SUPPORT_BADGES.map((option) => (
        <View key={option.value}>
          <StaffStatusBadge label={option.label} tone={option.tone} />
          <FormField
            label={`Parcela do selo ${option.value === "RED" ? "vermelho" : option.value === "YELLOW" ? "amarelo" : "verde"} (%)`}
            keyboardType="number-pad"
            maxLength={3}
            editable={!saving && group.status === "ACTIVE"}
            value={values[option.field]}
            onChangeText={(value) => { setValues((current) => ({ ...current, [option.field]: value })); setMessage(""); }}
          />
        </View>
      ))}
      <Text style={styles.title}>Total: {total}% de 100%</Text>
      {!valid ? <StaffMessage>Preencha os três percentuais. A soma deve ser exatamente 100%.</StaffMessage> : null}
      <Text style={styles.description}>Se um selo não tiver participantes no evento, seu percentual deverá ser zero. Mudanças não alteram cotas já aplicadas.</Text>
      {message ? <StaffMessage tone={failed ? "danger" : "neutral"}>{message}</StaffMessage> : null}
      {group.status === "ACTIVE" ? (
        <AppButton disabled={!valid || saving} onPress={save}>{saving ? "Salvando..." : "Salvar percentuais dos selos"}</AppButton>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  options: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  option: { borderWidth: 2, borderColor: colors.border, borderRadius: 12, padding: 6, minHeight: 44, maxWidth: "100%", justifyContent: "center" },
  selected: { borderColor: colors.primaryDark },
  disabled: { opacity: 0.6 },
  policy: { gap: 10, paddingVertical: 12 },
  title: { color: colors.primaryDark, fontWeight: "800", fontSize: 14 },
  description: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
});
