import { Ionicons } from "@expo/vector-icons";
import { Redirect, router, type Href } from "expo-router";
import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { AppButton, LoadingScreen } from "@/components/ui";
import { colors, radius, shadow } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import {
  resendPublicEmailVerification,
  TrqBecServiceError,
} from "@/security/trq-bec/service";

/** Tela neutra: não revela nem monta qualquer painel privilegiado. */
export default function AccessPendingScreen() {
  const {
    accessDestination,
    accessError,
    accessSession,
    hasFirebaseSession,
    hasPermission,
    isAuthenticated,
    isHydrated,
    isResolvingAccess,
    logout,
    refreshAccess,
  } = useApp();
  const insets = useSafeAreaInsets();
  const [isRetrying, setIsRetrying] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [resendStatus, setResendStatus] = useState("");
  const [retryError, setRetryError] = useState("");
  const emailVerificationRequired = accessSession?.reason === "EMAIL_VERIFICATION_REQUIRED";

  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (!hasFirebaseSession) return <Redirect href={"/login" as Href} />;

  if (
    isAuthenticated
    && accessSession?.access_state === "AUTHORIZED"
    && accessSession.role
    && hasPermission(`${accessSession.role}.panel.access`)
  ) {
    return <Redirect href={accessDestination as Href} />;
  }

  async function handleRetry() {
    if (isRetrying) return;
    setRetryError("");
    setIsRetrying(true);
    try {
      const destination = await refreshAccess();
      router.replace(destination as Href);
    } catch {
      setRetryError("Não foi possível confirmar o acesso agora. Verifique sua conexão e tente novamente.");
    } finally {
      setIsRetrying(false);
    }
  }

  async function handleLogout() {
    await logout();
    router.replace("/");
  }

  async function handleResend() {
    if (isResending) return;
    setRetryError("");
    setResendStatus("");
    setIsResending(true);
    try {
      const result = await resendPublicEmailVerification();
      setResendStatus(
        result.status === "ALREADY_VERIFIED"
          ? "Seu e-mail já foi confirmado. Toque em “Verificar novamente”."
          : "E-mail colocado na fila de envio. Confira também a caixa de spam.",
      );
    } catch (error) {
      setRetryError(
        error instanceof TrqBecServiceError
          ? error.userMessage
          : "Não foi possível reenviar o e-mail agora. Tente novamente.",
      );
    } finally {
      setIsResending(false);
    }
  }

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <View style={[styles.content, { paddingBottom: Math.max(24, insets.bottom + 16) }]}>
        <View style={styles.brand}>
          <View style={styles.logo}>
            <Text style={styles.logoText}>LR</Text>
          </View>
          <Text style={styles.brandName}>LiberRotas</Text>
        </View>

        <View style={styles.card}>
          <View style={styles.icon}>
            <Ionicons color={colors.primary} name="hourglass-outline" size={30} />
          </View>
          <Text style={styles.title}>
            {emailVerificationRequired ? "Verifique seu e-mail" : "Acesso em análise"}
          </Text>
          <Text style={styles.message}>
            {emailVerificationRequired
              ? "Sua conta foi criada. Abra o link enviado ao e-mail cadastrado e depois volte para confirmar a liberação."
              : "Sua conta foi autenticada, mas o acesso ainda não está liberado. O LiberRotas precisa confirmar a situação e as permissões da conta."}
          </Text>
          {resendStatus ? <Text style={styles.success}>{resendStatus}</Text> : null}
          {accessError || retryError ? (
            <Text accessibilityRole="alert" style={styles.error}>{retryError || accessError}</Text>
          ) : null}
        </View>

        <View style={styles.actions}>
          {emailVerificationRequired ? (
            <AppButton disabled={isRetrying || isResending} onPress={handleResend} variant="secondary">
              {isResending ? "Enfileirando..." : "Reenviar e-mail"}
            </AppButton>
          ) : null}
          <AppButton disabled={isRetrying} onPress={handleRetry}>
            {isRetrying
              ? "Verificando..."
              : emailVerificationRequired
                ? "Verificar novamente"
                : "Tentar novamente"}
          </AppButton>
          <AppButton disabled={isRetrying} onPress={handleLogout} variant="secondary">
            SAIR
          </AppButton>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.background, flex: 1 },
  content: { flex: 1, justifyContent: "center", padding: 24 },
  brand: { alignItems: "center", flexDirection: "row", gap: 10, justifyContent: "center", marginBottom: 20 },
  logo: {
    alignItems: "center",
    backgroundColor: colors.accent,
    borderRadius: 22,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  logoText: { color: colors.surface, fontSize: 14, fontWeight: "900" },
  brandName: { color: colors.primaryDark, fontSize: 21, fontWeight: "900" },
  card: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.large,
    borderWidth: 1,
    padding: 24,
    ...shadow,
  },
  icon: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderRadius: 30,
    height: 60,
    justifyContent: "center",
    marginBottom: 15,
    width: 60,
  },
  title: { color: colors.primaryDark, fontSize: 23, fontWeight: "900", textAlign: "center" },
  message: { color: colors.textMuted, fontSize: 14, lineHeight: 21, marginTop: 9, textAlign: "center" },
  error: {
    backgroundColor: "#FFF0EE",
    borderRadius: radius.small,
    color: colors.danger,
    fontSize: 12,
    lineHeight: 17,
    marginTop: 16,
    padding: 12,
    textAlign: "center",
    width: "100%",
  },
  success: {
    backgroundColor: "#E7F8F1",
    borderRadius: radius.small,
    color: "#087A55",
    fontSize: 12,
    lineHeight: 17,
    marginTop: 16,
    padding: 12,
    textAlign: "center",
    width: "100%",
  },
  actions: { gap: 11, marginTop: 20 },
});
