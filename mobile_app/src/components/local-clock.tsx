import { Ionicons } from "@expo/vector-icons";
import { StyleSheet, Text, View } from "react-native";
import { colors } from "@/constants/theme";
import { useTrustedClock } from "@/context/trusted-clock-context";

export function LocalClock() {
  const { nowMs, status } = useTrustedClock();
  const localTime = new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(nowMs));

  return (
    <View
      accessibilityLabel={`Hora local ${localTime}. ${status === "synchronized" ? "Sincronizada com o servidor" : "Sem sincronização com o servidor"}.`}
      style={styles.container}
    >
      <Ionicons color={colors.primary} name="time-outline" size={16} />
      <View>
        <Text style={styles.label}>HORA LOCAL</Text>
        <Text style={styles.time}>{localTime}</Text>
      </View>
      <View style={[styles.status, status === "synchronized" ? styles.statusOnline : styles.statusOffline]} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: "row",
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  label: { color: colors.textMuted, fontSize: 7, fontWeight: "800", letterSpacing: 0.4 },
  time: { color: colors.primaryDark, fontSize: 11, fontVariant: ["tabular-nums"], fontWeight: "900" },
  status: { borderRadius: 4, height: 7, marginLeft: 1, width: 7 },
  statusOnline: { backgroundColor: colors.success },
  statusOffline: { backgroundColor: colors.accent },
});
