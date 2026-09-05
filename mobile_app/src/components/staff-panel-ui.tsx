import type { PropsWithChildren } from "react";
import { Alert, Platform, StyleSheet, Text, View } from "react-native";
import { colors, radius } from "@/constants/theme";
import { TrqBecServiceError, type AccessRole, type ManagedAccountStatus } from "@/security/trq-bec/service";

type StatusTone = "danger" | "neutral" | "success" | "warning";

type WebDialogGlobal = typeof globalThis & {
  alert?: (message?: string) => void;
  confirm?: (message?: string) => boolean;
};

function staffDialogMessage(title: string, message: string) {
  return message ? `${title}\n\n${message}` : title;
}

/** Exibe mensagens também no React Native Web, onde Alert.alert não abre diálogo. */
export function showStaffAlert(title: string, message: string) {
  if (Platform.OS === "web") {
    const webAlert = (globalThis as WebDialogGlobal).alert;
    if (typeof webAlert === "function") webAlert.call(globalThis, staffDialogMessage(title, message));
    return;
  }
  Alert.alert(title, message);
}

/**
 * Confirma uma ação privilegiada sem depender do Alert.alert no navegador.
 * Na ausência segura de um diálogo Web, a ação permanece cancelada.
 */
export function confirmStaffAction(
  title: string,
  message: string,
  confirmLabel = "Confirmar",
  destructive = false,
): Promise<boolean> {
  if (Platform.OS === "web") {
    const webConfirm = (globalThis as WebDialogGlobal).confirm;
    return Promise.resolve(
      typeof webConfirm === "function"
        ? webConfirm.call(globalThis, staffDialogMessage(title, message))
        : false,
    );
  }

  return new Promise((resolve) => {
    let settled = false;
    const finish = (confirmed: boolean) => {
      if (settled) return;
      settled = true;
      resolve(confirmed);
    };

    Alert.alert(
      title,
      message,
      [
        { text: "Cancelar", style: "cancel", onPress: () => finish(false) },
        {
          text: confirmLabel,
          style: destructive ? "destructive" : "default",
          onPress: () => finish(true),
        },
      ],
      { cancelable: true, onDismiss: () => finish(false) },
    );
  });
}

export const ACCOUNT_ROLE_LABELS: Record<AccessRole, string> = {
  admin: "Administrador",
  entrepreneur: "Empreendedor",
  institution: "Instituição",
  security: "Segurança",
  support: "Suporte",
  visitor: "Visitante",
};

export const ACCOUNT_STATUS_LABELS: Record<ManagedAccountStatus, string> = {
  ACTIVE: "Ativa",
  DISABLED: "Desativada",
  PENDING: "Pendente",
  SUSPENDED: "Suspensa",
};

export function getAccountStatusTone(status: ManagedAccountStatus): StatusTone {
  if (status === "ACTIVE") return "success";
  if (status === "SUSPENDED" || status === "DISABLED") return "danger";
  return "warning";
}

export function formatPanelDate(value: string | null | undefined) {
  if (!value) return "Não informado";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Não informado";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function getPanelErrorMessage(error: unknown, fallback: string) {
  if (error instanceof TrqBecServiceError) return error.userMessage;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function StaffSection({
  children,
  description,
  title,
}: PropsWithChildren<{ description?: string; title: string }>) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {description ? <Text style={styles.sectionDescription}>{description}</Text> : null}
      <View style={styles.sectionContent}>{children}</View>
    </View>
  );
}

export function StaffRecordCard({ children }: PropsWithChildren) {
  return <View style={styles.recordCard}>{children}</View>;
}

export function StaffStatusBadge({ label, tone = "neutral" }: { label: string; tone?: StatusTone }) {
  return (
    <View
      style={[
        styles.badge,
        tone === "success" && styles.badgeSuccess,
        tone === "warning" && styles.badgeWarning,
        tone === "danger" && styles.badgeDanger,
      ]}
    >
      <Text
        style={[
          styles.badgeText,
          tone === "success" && styles.badgeTextSuccess,
          tone === "danger" && styles.badgeTextDanger,
        ]}
      >
        {label}
      </Text>
    </View>
  );
}

export function StaffMessage({
  children,
  tone = "neutral",
}: PropsWithChildren<{ tone?: "danger" | "neutral" }>) {
  return (
    <View style={[styles.message, tone === "danger" && styles.messageDanger]}>
      <Text style={[styles.messageText, tone === "danger" && styles.messageTextDanger]}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    padding: 16,
  },
  sectionTitle: { color: colors.primaryDark, fontSize: 18, fontWeight: "900" },
  sectionDescription: { color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 4 },
  sectionContent: { gap: 12, marginTop: 14 },
  recordCard: {
    backgroundColor: colors.background,
    borderColor: colors.border,
    borderRadius: radius.small,
    borderWidth: 1,
    gap: 6,
    padding: 13,
  },
  badge: {
    alignSelf: "flex-start",
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  badgeSuccess: { backgroundColor: "#E8F6EF" },
  badgeWarning: { backgroundColor: colors.cream },
  badgeDanger: { backgroundColor: "#FDECEC" },
  badgeText: { color: colors.primaryDark, fontSize: 11, fontWeight: "800" },
  badgeTextSuccess: { color: colors.success },
  badgeTextDanger: { color: colors.danger },
  message: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.small,
    padding: 13,
  },
  messageDanger: { backgroundColor: "#FDECEC" },
  messageText: { color: colors.textMuted, fontSize: 12, lineHeight: 18, textAlign: "center" },
  messageTextDanger: { color: colors.danger },
});
