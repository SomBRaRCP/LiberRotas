import { Ionicons } from "@expo/vector-icons";
import { Redirect, router, type Href } from "expo-router";
import { sendPasswordResetEmail, signOut } from "firebase/auth";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { BrandHeader } from "@/components/brand-header";
import { confirmStaffAction, formatPanelDate, showStaffAlert } from "@/components/staff-panel-ui";
import { AppButton, LoadingScreen } from "@/components/ui";
import { colors, radius, shadow } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import { auth } from "@/services/firebase";
import { clearPendingDeviceApprovalToken, consumePendingDeviceApprovalToken } from "@/security/device-approval-token";
import { removeDeviceIdentity } from "@/security/trq-bec/device-signer";
import {
  getCurrentDeviceKeyId,
  listAccountDevices,
  resendAccountDeviceApproval,
  revokeAllAccountDevices,
  TrqBecServiceError,
  type AccountDevice,
  type AccountDeviceStatus,
  type DeviceNotificationStatus,
  type DevicePlatform,
} from "@/security/trq-bec/service";
import { getAuthenticatedHomeDestination, getAuthenticatedHomeLabel } from "@/utils/account-navigation";

const RESEND_COOLDOWN_SECONDS = 60;

function platformLabel(platform: DevicePlatform) {
  const labels: Record<DevicePlatform, string> = {
    android: "Android",
    ios: "iPhone/iPad",
    web: "Navegador web",
    windows: "Windows",
    macos: "macOS",
    linux: "Linux",
    unknown: "Plataforma não identificada",
  };
  return labels[platform];
}

function statusLabel(status: AccountDeviceStatus) {
  if (status === "ACTIVE") return "Ativo";
  if (status === "PENDING_APPROVAL") return "Em período de segurança";
  return "Desconectado";
}

function notificationMessage(status: DeviceNotificationStatus) {
  if (status === "SENT") return "O alerta de segurança foi enviado ao e-mail cadastrado.";
  if (status === "PENDING") return "O alerta de segurança está aguardando envio.";
  if (status === "NOT_CONFIGURED") return "O alerta por e-mail não está configurado. A liberação automática continua normalmente.";
  if (status === "FAILED") return "Não foi possível enviar o alerta. A liberação automática continua; tente reenviar em instantes.";
  return "Nenhum e-mail é necessário para este dispositivo.";
}

function firebaseResetError(error: unknown) {
  const code = typeof error === "object" && error !== null && "code" in error
    ? String((error as { code?: string }).code)
    : "";
  if (code.includes("network-request-failed")) return "Sem conexão com o Firebase. Confira a internet e tente novamente.";
  if (code.includes("too-many-requests")) return "Muitas solicitações foram feitas. Aguarde alguns minutos e tente novamente.";
  if (code.includes("operation-not-allowed")) return "A recuperação de senha não está habilitada no Firebase.";
  return "Não foi possível enviar o e-mail para alterar a senha.";
}

function deviceError(error: unknown, fallback: string) {
  if (error instanceof TrqBecServiceError) return error.userMessage;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function secondsUntilResend(lastSentAt: string | null) {
  if (!lastSentAt) return 0;
  const lastSentMs = Date.parse(lastSentAt);
  if (Number.isNaN(lastSentMs)) return 0;
  return Math.max(0, Math.ceil((lastSentMs + RESEND_COOLDOWN_SECONDS * 1_000 - Date.now()) / 1_000));
}

function secondsUntilActivation(activationAt: string | null) {
  if (!activationAt) return 0;
  const activationMs = Date.parse(activationAt);
  if (Number.isNaN(activationMs)) return 0;
  return Math.max(0, Math.ceil((activationMs - Date.now()) / 1_000));
}

function formatCountdown(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export default function AccountDevicesScreen() {
  const {
    accessDestination,
    accessSession,
    deviceApprovalRequired,
    hasFirebaseSession,
    isAuthenticated,
    isHydrated,
    isResolvingAccess,
    logout,
    refreshAccess,
  } = useApp();
  const insets = useSafeAreaInsets();
  const [devices, setDevices] = useState<AccountDevice[]>([]);
  const [currentDeviceKeyId, setCurrentDeviceKeyId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRetryingDevice, setIsRetryingDevice] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [activationCooldown, setActivationCooldown] = useState(0);
  const [isCheckingActivation, setIsCheckingActivation] = useState(false);
  const activationCheckInFlightRef = useRef(false);
  const lastActivationCheckAtRef = useRef(0);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const canLoad = isAuthenticated && accessSession?.access_state === "AUTHORIZED" && Boolean(accessSession.role);
  const authorizedHomeDestination = getAuthenticatedHomeDestination(accessSession?.role, accessDestination);
  const authorizedHomeLabel = getAuthenticatedHomeLabel(accessSession?.role);

  useEffect(() => {
    // Remove da barra qualquer fragmento de confirmação emitido por versões
    // antigas. O novo fluxo não usa nem guarda esse token.
    consumePendingDeviceApprovalToken();
    clearPendingDeviceApprovalToken();
  }, []);

  const loadDevices = useCallback(async (refreshing = false) => {
    if (!canLoad) return;
    if (refreshing) setIsRefreshing(true);
    else setIsLoading(true);
    setError("");
    const [devicesResult, keyResult] = await Promise.allSettled([
      listAccountDevices(),
      getCurrentDeviceKeyId(),
    ]);
    if (devicesResult.status === "fulfilled") {
      setDevices(devicesResult.value);
    } else {
      setError(deviceError(devicesResult.reason, "Não foi possível carregar os dispositivos conectados."));
    }
    if (keyResult.status === "fulfilled") {
      setCurrentDeviceKeyId(keyResult.value);
    } else {
      setCurrentDeviceKeyId("");
    }
    setIsLoading(false);
    setIsRefreshing(false);
  }, [canLoad]);

  useEffect(() => {
    if (!canLoad) return;
    const task = setTimeout(() => {
      void loadDevices();
    }, 0);
    return () => clearTimeout(task);
  }, [canLoad, loadDevices]);

  const currentDevice = useMemo(
    () => devices.find((device) => device.device_key_id === currentDeviceKeyId) || null,
    [currentDeviceKeyId, devices],
  );

  const checkAutomaticActivation = useCallback(async () => {
    if (activationCheckInFlightRef.current) return;
    activationCheckInFlightRef.current = true;
    setIsCheckingActivation(true);
    setError("");
    try {
      const destination = await refreshAccess();
      await loadDevices(true);
      if (destination !== "/account/devices") {
        setFeedback("Período de segurança concluído. Este dispositivo foi liberado.");
        router.replace(destination as Href);
      }
    } catch (activationError) {
      setError(deviceError(activationError, "Não foi possível verificar a liberação automática. Tentaremos novamente."));
    } finally {
      activationCheckInFlightRef.current = false;
      setIsCheckingActivation(false);
    }
  }, [loadDevices, refreshAccess]);

  useEffect(() => {
    const initialTask = setTimeout(() => {
      setResendCooldown(
        currentDevice?.status === "PENDING_APPROVAL"
          ? secondsUntilResend(currentDevice.approval_last_sent_at)
          : 0,
      );
    }, 0);
    if (currentDevice?.status !== "PENDING_APPROVAL") return () => clearTimeout(initialTask);
    const timer = setInterval(() => {
      setResendCooldown((current) => Math.max(0, current - 1));
    }, 1_000);
    return () => {
      clearTimeout(initialTask);
      clearInterval(timer);
    };
  }, [currentDevice?.approval_last_sent_at, currentDevice?.status]);

  useEffect(() => {
    if (currentDevice?.status !== "PENDING_APPROVAL") {
      const resetTask = setTimeout(() => setActivationCooldown(0), 0);
      return () => clearTimeout(resetTask);
    }
    const tick = () => {
      const remaining = secondsUntilActivation(currentDevice.approval_expires_at);
      setActivationCooldown(remaining);
      if (
        remaining === 0
        && Date.now() - lastActivationCheckAtRef.current >= 5_000
      ) {
        lastActivationCheckAtRef.current = Date.now();
        void checkAutomaticActivation();
      }
    };
    const initialTask = setTimeout(tick, 0);
    const timer = setInterval(tick, 1_000);
    return () => {
      clearTimeout(initialTask);
      clearInterval(timer);
    };
  }, [checkAutomaticActivation, currentDevice?.approval_expires_at, currentDevice?.status]);

  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (!hasFirebaseSession) {
    return <Redirect href={{ pathname: "/login", params: { returnTo: "/account/devices" } } as unknown as Href} />;
  }
  if (!isAuthenticated || accessSession?.access_state !== "AUTHORIZED" || !accessSession.role) {
    return <Redirect href={"/access-pending" as Href} />;
  }

  async function handleRetryDeviceValidation() {
    if (isRetryingDevice) return;
    setIsRetryingDevice(true);
    setError("");
    setFeedback("");
    try {
      const destination = await refreshAccess();
      if (destination !== "/account/devices") {
        router.replace(destination as Href);
        return;
      }
      await loadDevices(true);
      setFeedback("O período de segurança ainda não terminou. A liberação ocorrerá automaticamente.");
    } catch (retryError) {
      setError(deviceError(retryError, "Não foi possível validar este dispositivo. Confira a internet e tente novamente."));
    } finally {
      setIsRetryingDevice(false);
    }
  }

  async function handleResendApproval() {
    if (!currentDevice || currentDevice.status !== "PENDING_APPROVAL" || isResending || resendCooldown > 0) return;
    setIsResending(true);
    setError("");
    setFeedback("");
    try {
      const result = await resendAccountDeviceApproval(currentDevice.device_key_id);
      const message = notificationMessage(result.notification_status);
      setFeedback(message);
      setResendCooldown(RESEND_COOLDOWN_SECONDS);
      await loadDevices(true);
    } catch (resendError) {
      if (resendError instanceof TrqBecServiceError && resendError.code === "APPROVAL_RESEND_COOLDOWN") {
        setResendCooldown(RESEND_COOLDOWN_SECONDS);
      }
      setError(deviceError(resendError, "Não foi possível reenviar o alerta de segurança."));
    } finally {
      setIsResending(false);
    }
  }

  async function handleChangePassword() {
    if (isChangingPassword) return;
    if (!currentDevice || currentDevice.status !== "ACTIVE") {
      setError("Aguarde o fim do período de segurança para alterar a senha e desconectar os dispositivos.");
      return;
    }
    const confirmed = await confirmStaffAction(
      "Alterar senha e desconectar dispositivos?",
      "Enviaremos um link ao e-mail cadastrado. Todos os dispositivos conectados serão desconectados, inclusive este, e será necessário entrar novamente.",
      "Enviar link e desconectar",
      true,
    );
    if (!confirmed) return;

    const firebaseUser = auth.currentUser;
    if (!firebaseUser?.email) {
      setError("Sua conta não possui um e-mail disponível no Firebase. Entre novamente ou procure o suporte.");
      return;
    }

    setIsChangingPassword(true);
    setError("");
    setFeedback("");
    try {
      await sendPasswordResetEmail(auth, firebaseUser.email);
    } catch (resetError) {
      setError(firebaseResetError(resetError));
      setIsChangingPassword(false);
      return;
    }

    try {
      await revokeAllAccountDevices();
    } catch (revokeError) {
      setError(
        `O e-mail para alterar a senha foi enviado, mas não foi possível concluir a desconexão de todos os acessos: ${deviceError(revokeError, "tente novamente antes de usar o link")}`,
      );
      setIsChangingPassword(false);
      return;
    }

    const uid = firebaseUser.uid;
    clearPendingDeviceApprovalToken();
    try {
      await removeDeviceIdentity(uid);
    } catch (identityError) {
      console.warn("A identidade local será renovada no próximo acesso.", identityError);
    }
    await signOut(auth).catch((signOutError) => {
      console.warn("A sessão já foi revogada no backend, mas a saída local falhou.", signOutError);
    });
    setIsChangingPassword(false);
    router.replace("/");
    showStaffAlert(
      "Dispositivos desconectados",
      "O link para alterar sua senha foi enviado. Todos os dispositivos foram desconectados; entre novamente depois de criar a nova senha.",
    );
  }

  function returnToAuthorizedArea() {
    if (accessDestination === "/account/devices") {
      setFeedback("Aguarde o fim do período de segurança para liberar este dispositivo.");
      return;
    }
    router.replace(authorizedHomeDestination);
  }

  async function handleLogout() {
    await logout();
    router.replace({ pathname: "/", params: { returnTo: "/account/devices" } } as Href);
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <BrandHeader subtitle="acessos e proteção da conta" title="Dispositivos conectados" />
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: Math.max(36, insets.bottom + 24) }]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.introCard}>
          <View style={styles.introIcon}>
            <Ionicons color={colors.surface} name="shield-checkmark-outline" size={28} />
          </View>
          <View style={styles.introText}>
            <Text style={styles.title}>Segurança da minha conta</Text>
            <Text style={styles.description}>
              {accessSession.role === "visitor"
                ? "Confira onde sua conta foi conectada. Contas de visitante liberam novos aparelhos imediatamente."
                : "Confira onde sua conta foi conectada. Um aparelho novo passa por 10 minutos de segurança antes da liberação automática."}
            </Text>
          </View>
        </View>

        {currentDevice?.status === "PENDING_APPROVAL" ? (
          <View style={styles.pendingCard}>
            <Text style={styles.pendingTitle}>Período de segurança: {formatCountdown(activationCooldown)}</Text>
            <Text style={styles.pendingText}>
              Este dispositivo será liberado automaticamente quando a contagem terminar. Se não reconhece este acesso, altere a senha para desconectar todos os aparelhos.
            </Text>
            <Text style={styles.notificationText}>{notificationMessage(currentDevice.notification_status)}</Text>
            <Pressable
              accessibilityRole="button"
              disabled={isResending || resendCooldown > 0}
              onPress={handleResendApproval}
              style={({ pressed }) => [styles.resendButton, (pressed || isResending || resendCooldown > 0) && styles.pressed]}
            >
              <Ionicons color={colors.primary} name="refresh-outline" size={18} />
              <Text style={styles.resendText}>
                {isResending
                  ? "Reenviando..."
                  : resendCooldown > 0
                    ? `Reenviar alerta em ${resendCooldown}s`
                    : "Reenviar alerta de segurança"}
              </Text>
            </Pressable>
            {isCheckingActivation ? (
              <Text style={styles.notificationText}>Verificando a liberação no servidor...</Text>
            ) : null}
          </View>
        ) : null}

        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        {feedback ? <Text accessibilityRole="alert" style={styles.feedback}>{feedback}</Text> : null}
        {deviceApprovalRequired && currentDevice?.status !== "PENDING_APPROVAL" ? (
          <View style={styles.validationCard}>
            <Text style={styles.validationTitle}>Não foi possível confirmar o estado deste aparelho</Text>
            <Text style={styles.validationText}>
              As áreas protegidas permanecem fechadas até o backend reconhecer uma chave ativa.
            </Text>
            <AppButton disabled={isRetryingDevice} onPress={handleRetryDeviceValidation}>
              {isRetryingDevice ? "Validando..." : "Tentar novamente"}
            </AppButton>
          </View>
        ) : null}

        <View style={styles.sectionHeading}>
          <View>
            <Text style={styles.sectionTitle}>Aparelhos da conta</Text>
            <Text style={styles.sectionSubtitle}>{devices.length} registro(s) encontrado(s)</Text>
          </View>
          <Pressable
            accessibilityLabel="Atualizar lista de dispositivos"
            accessibilityRole="button"
            disabled={isRefreshing}
            onPress={() => void loadDevices(true)}
            style={({ pressed }) => [styles.refreshButton, (pressed || isRefreshing) && styles.pressed]}
          >
            {isRefreshing
              ? <ActivityIndicator color={colors.primary} size="small" />
              : <Ionicons color={colors.primary} name="refresh-outline" size={21} />}
          </Pressable>
        </View>

        {isLoading ? (
          <View style={styles.loadingCard}>
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.loadingText}>Carregando dispositivos...</Text>
          </View>
        ) : devices.length === 0 ? (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyText}>Nenhum dispositivo foi encontrado para esta conta.</Text>
          </View>
        ) : (
          <View style={styles.deviceList}>
            {devices.map((device) => {
              const isCurrent = device.device_key_id === currentDeviceKeyId;
              return (
                <View key={device.device_key_id} style={[styles.deviceCard, isCurrent && styles.currentDeviceCard]}>
                  <View style={styles.deviceTopRow}>
                    <View style={styles.deviceIcon}>
                      <Ionicons
                        color={device.status === "REVOKED" ? colors.textMuted : colors.primary}
                        name={device.platform === "web" ? "globe-outline" : "phone-portrait-outline"}
                        size={23}
                      />
                    </View>
                    <View style={styles.deviceTitleGroup}>
                      <Text style={styles.deviceName}>{device.device_name || device.model_name || platformLabel(device.platform)}</Text>
                      <Text style={styles.devicePlatform}>
                        {[platformLabel(device.platform), device.model_name, device.app_version ? `LiberRotas ${device.app_version}` : null]
                          .filter(Boolean)
                          .join(" · ")}
                      </Text>
                    </View>
                    {isCurrent ? <Text style={styles.currentBadge}>Este aparelho</Text> : null}
                  </View>
                  <View style={styles.deviceDetails}>
                    <View style={styles.detailRow}>
                      <Text style={styles.detailLabel}>Status</Text>
                      <Text style={[
                        styles.detailValue,
                        device.status === "ACTIVE" && styles.activeStatus,
                        device.status === "PENDING_APPROVAL" && styles.pendingStatus,
                      ]}>
                        {statusLabel(device.status)}
                      </Text>
                    </View>
                    <View style={styles.detailRow}>
                      <Text style={styles.detailLabel}>Primeiro acesso</Text>
                      <Text style={styles.detailValue}>{formatPanelDate(device.created_at)}</Text>
                    </View>
                    <View style={styles.detailRow}>
                      <Text style={styles.detailLabel}>Último acesso</Text>
                      <Text style={styles.detailValue}>{formatPanelDate(device.last_seen_at)}</Text>
                    </View>
                    {device.status === "PENDING_APPROVAL" ? (
                      <View style={styles.detailRow}>
                        <Text style={styles.detailLabel}>Liberação automática</Text>
                        <Text style={styles.detailValue}>{formatPanelDate(device.approval_expires_at)}</Text>
                      </View>
                    ) : null}
                  </View>
                </View>
              );
            })}
          </View>
        )}

        {currentDevice?.status === "ACTIVE" ? (
          <View style={styles.passwordCard}>
            <View style={styles.passwordHeading}>
              <Ionicons color={colors.danger} name="key-outline" size={23} />
              <View style={styles.passwordTextGroup}>
                <Text style={styles.passwordTitle}>Alterar senha</Text>
                <Text style={styles.passwordDescription}>
                  Por segurança, a troca desconecta todos os dispositivos, inclusive este.
                </Text>
              </View>
            </View>
            <AppButton disabled={isChangingPassword} onPress={handleChangePassword} variant="danger">
              {isChangingPassword ? "Enviando e desconectando..." : "Alterar senha e desconectar todos"}
            </AppButton>
          </View>
        ) : null}

        <AppButton disabled={isChangingPassword} onPress={returnToAuthorizedArea} variant="secondary">
          {authorizedHomeLabel}
        </AppButton>
        <AppButton disabled={isChangingPassword} onPress={handleLogout}>
          SAIR
        </AppButton>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  content: { backgroundColor: colors.background, flexGrow: 1, gap: 16, padding: 20 },
  introCard: {
    alignItems: "center",
    backgroundColor: colors.primaryDark,
    borderRadius: radius.large,
    flexDirection: "row",
    gap: 14,
    padding: 20,
    ...shadow,
  },
  introIcon: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 25, height: 50, justifyContent: "center", width: 50 },
  introText: { flex: 1 },
  title: { color: colors.surface, fontSize: 20, fontWeight: "900" },
  description: { color: colors.cream, fontSize: 12, lineHeight: 17, marginTop: 5 },
  approvalCard: { backgroundColor: "#EFF5FF", borderColor: colors.primary, borderRadius: radius.medium, borderWidth: 1, gap: 10, padding: 16 },
  approvalText: { gap: 3 },
  approvalTitle: { color: colors.primaryDark, fontSize: 16, fontWeight: "900" },
  approvalDescription: { color: colors.textMuted, fontSize: 12, lineHeight: 17 },
  approveButton: { marginTop: 2 },
  pendingCard: { backgroundColor: "#FFF8E8", borderColor: "#E8B44E", borderRadius: radius.medium, borderWidth: 1, padding: 16 },
  pendingTitle: { color: colors.primaryDark, fontSize: 16, fontWeight: "900" },
  pendingText: { color: colors.text, fontSize: 12, lineHeight: 18, marginTop: 6 },
  notificationText: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 7 },
  resendButton: { alignItems: "center", alignSelf: "flex-start", flexDirection: "row", gap: 7, marginTop: 12, minHeight: 38 },
  resendText: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  pressed: { opacity: 0.55 },
  error: { backgroundColor: "#FFF0EE", borderRadius: radius.small, color: colors.danger, fontSize: 12, lineHeight: 17, padding: 12 },
  feedback: { backgroundColor: "#EAF8F0", borderRadius: radius.small, color: colors.success, fontSize: 12, lineHeight: 17, padding: 12 },
  validationCard: { backgroundColor: colors.surface, borderColor: colors.danger, borderRadius: radius.medium, borderWidth: 1, gap: 10, padding: 16 },
  validationTitle: { color: colors.danger, fontSize: 14, fontWeight: "900" },
  validationText: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
  sectionHeading: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  sectionTitle: { color: colors.primaryDark, fontSize: 18, fontWeight: "900" },
  sectionSubtitle: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  refreshButton: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 20, borderWidth: 1, height: 40, justifyContent: "center", width: 40 },
  loadingCard: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, gap: 10, padding: 22 },
  loadingText: { color: colors.textMuted, fontSize: 12 },
  emptyCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, padding: 20 },
  emptyText: { color: colors.textMuted, fontSize: 12, textAlign: "center" },
  deviceList: { gap: 12 },
  deviceCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, padding: 15 },
  currentDeviceCard: { borderColor: colors.primary, borderWidth: 2 },
  deviceTopRow: { alignItems: "center", flexDirection: "row", gap: 11 },
  deviceIcon: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 21, height: 42, justifyContent: "center", width: 42 },
  deviceTitleGroup: { flex: 1 },
  deviceName: { color: colors.primaryDark, fontSize: 14, fontWeight: "900" },
  devicePlatform: { color: colors.textMuted, fontSize: 10, lineHeight: 14, marginTop: 2 },
  currentBadge: { backgroundColor: "#EAF8F0", borderRadius: radius.pill, color: colors.success, fontSize: 9, fontWeight: "900", overflow: "hidden", paddingHorizontal: 8, paddingVertical: 5 },
  deviceDetails: { borderTopColor: colors.border, borderTopWidth: 1, gap: 7, marginTop: 12, paddingTop: 11 },
  detailRow: { alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  detailLabel: { color: colors.textMuted, fontSize: 11 },
  detailValue: { color: colors.text, flexShrink: 1, fontSize: 11, fontWeight: "700", marginLeft: 12, textAlign: "right" },
  activeStatus: { color: colors.success },
  pendingStatus: { color: "#A15C00" },
  passwordCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, gap: 14, padding: 16 },
  passwordHeading: { alignItems: "center", flexDirection: "row", gap: 11 },
  passwordTextGroup: { flex: 1 },
  passwordTitle: { color: colors.primaryDark, fontSize: 16, fontWeight: "900" },
  passwordDescription: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 3 },
});
