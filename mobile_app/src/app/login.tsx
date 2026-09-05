import { Redirect, router, type Href, useLocalSearchParams } from "expo-router";
import { sendPasswordResetEmail } from "firebase/auth";
import { useState } from "react";
import { Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { BrandHeader } from "@/components/brand-header";
import { AppButton, FormField, LoadingScreen } from "@/components/ui";
import { colors } from "@/constants/theme";
import { type LoginResult, useApp } from "@/context/app-context";
import { auth } from "@/services/firebase";
import { normalizeSafeReturnTo } from "@/utils/share";

type LoginFailureReason = Exclude<LoginResult, { ok: true }>["reason"];

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function getFirebaseAuthCode(error: unknown) {
  return typeof error === "object" && error !== null && "code" in error ? String((error as { code?: string }).code) : "";
}

function getPasswordResetErrorMessage(error: unknown) {
  const code = getFirebaseAuthCode(error);
  if (code.includes("invalid-email")) return "Informe um e-mail válido.";
  if (code.includes("network-request-failed")) return "Sem conexão com o Firebase. Confira a internet e tente novamente.";
  if (code.includes("too-many-requests")) return "Muitas tentativas foram feitas. Aguarde alguns minutos e tente novamente.";
  if (code.includes("operation-not-allowed")) return "A recuperação de senha ainda não está habilitada no Firebase.";
  return "Não foi possível enviar o e-mail de recuperação. Tente novamente.";
}

function getLoginErrorMessage(reason: LoginFailureReason) {
  switch (reason) {
    case "empty":
      return "Informe o login e uma senha com pelo menos 6 caracteres.";
    case "not-found":
      return "Login não encontrado. Confira o e-mail/usuário ou crie uma conta.";
    case "password":
      return "Senha incorreta. Tente novamente.";
    case "too-many":
      return "Muitas tentativas foram feitas. Aguarde alguns minutos ou recupere a senha.";
    case "disabled":
      return "Esta conta está desativada no Firebase. Procure o responsável pelo LiberRotas.";
    case "network":
      return "Sem conexão com o Firebase. Confira a internet e tente novamente.";
    case "backend":
      return "Não foi possível validar as permissões da conta. Tente novamente em instantes.";
    case "unknown":
      return "Não foi possível entrar pelo Firebase. Confira o console e tente novamente.";
    default:
      return "Não foi possível entrar. Confira os dados informados.";
  }
}

/**
 * Tela de autenticação acessada pela apresentação pública.
 *
 * A tela usa inputs controlados: cada TextInput recebe seu valor de um state e
 * atualiza esse state com onChangeText. O envio chama a função global login e
 * o Expo Router substitui a rota para impedir que o botão Voltar retorne ao
 * formulário depois de uma autenticação bem-sucedida. A validação real agora
 * usa Firebase Authentication e o backend define o painel autorizado com base
 * nas permissões reais da conta.
 */
export default function LoginScreen() {
  const { accessDestination, accessSession, hasFirebaseSession, isAuthenticated, isHydrated, isResolvingAccess, login } = useApp();
  const { returnTo } = useLocalSearchParams<{ returnTo?: string | string[] }>();
  const safeReturnTo = normalizeSafeReturnTo(returnTo);
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isResettingPassword, setIsResettingPassword] = useState(false);

  // Não renderiza nenhum painel enquanto o backend valida função, status e permissões.
  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (isAuthenticated || hasFirebaseSession) {
    const canReturnToPublicProfile = isAuthenticated
      && accessSession?.access_state === "AUTHORIZED"
      && (accessSession.role === "entrepreneur" || accessSession.role === "visitor");
    const canReturnToAccountDevices = isAuthenticated
      && accessSession?.access_state === "AUTHORIZED"
      && safeReturnTo === "/account/devices";
    const canUseSafeReturn = canReturnToAccountDevices
      || (canReturnToPublicProfile && Boolean(safeReturnTo?.startsWith("/profile/")));
    return <Redirect href={(canUseSafeReturn && safeReturnTo ? safeReturnTo : accessDestination) as Href} />;
  }

  // Validação e navegação ficam fora do JSX para melhorar leitura e reutilização.
  async function handleLogin() {
    setError("");
    const result = await login(user, password);
    if (!result.ok) {
      const message = getLoginErrorMessage(result.reason);
      setError(message);
      Alert.alert("Não foi possível entrar", message);
      return;
    }
    const canReturnToAccountDevices = safeReturnTo === "/account/devices"
      && result.destination !== "/access-pending";
    const canReturnToPublicProfile = result.destination === "/(tabs)/feed"
      && Boolean(safeReturnTo?.startsWith("/profile/"));
    const destination = (canReturnToAccountDevices || canReturnToPublicProfile) && safeReturnTo
      ? safeReturnTo
      : result.destination;
    router.replace(destination as Href);
  }

  async function handlePasswordReset() {
    const normalizedEmail = user.trim().toLowerCase();
    setError("");

    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      const message = "Digite um e-mail válido no campo E-mail para recuperar sua senha.";
      setError(message);
      Alert.alert("E-mail necessário", message);
      return;
    }

    setIsResettingPassword(true);
    try {
      await sendPasswordResetEmail(auth, normalizedEmail);
      setUser(normalizedEmail);
      Alert.alert(
        "E-mail de recuperação enviado",
        "Se este e-mail estiver cadastrado, você receberá uma mensagem com o link para criar uma nova senha. Confira também a caixa de spam.",
      );
    } catch (resetError) {
      const code = getFirebaseAuthCode(resetError);

      // Não revela se uma conta existe ou não para determinado endereço.
      if (code.includes("user-not-found")) {
        Alert.alert(
          "Solicitação recebida",
          "Se este e-mail estiver cadastrado, você receberá uma mensagem com o link para criar uma nova senha.",
        );
        return;
      }

      const message = getPasswordResetErrorMessage(resetError);
      setError(message);
      Alert.alert("Não foi possível recuperar a senha", message);
    } finally {
      setIsResettingPassword(false);
    }
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <BrandHeader subtitle="acesso seguro a todas as contas" title="Entrar" />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.flex}>
        {/* ScrollView mantém o formulário acessível em telas pequenas e com o teclado aberto. */}
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={styles.heading}>Bem-vindo ao LiberRotas</Text>
          <Text style={styles.lead}>
            Entre com seu e-mail e senha. O LiberRotas identifica automaticamente o acesso autorizado para sua conta.
          </Text>
          <View style={styles.form}>
            <FormField
              autoComplete="email"
              autoCapitalize="none"
              keyboardType="email-address"
              label="E-mail"
              onChangeText={setUser}
              placeholder="voce@email.com"
              value={user}
            />
            <FormField
              autoCapitalize="none"
              autoComplete="current-password"
              autoCorrect={false}
              label="Senha"
              onChangeText={setPassword}
              placeholder="••••••••"
              secureTextEntry
              value={password}
            />
            <Pressable
              accessibilityRole="button"
              disabled={isResettingPassword}
              onPress={handlePasswordReset}
              style={styles.forgotPasswordButton}
            >
              <Text style={[styles.forgotPasswordText, isResettingPassword && styles.forgotPasswordTextDisabled]}>
                {isResettingPassword ? "Enviando e-mail..." : "Esqueceu a senha?"}
              </Text>
            </Pressable>
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <AppButton disabled={isResettingPassword} onPress={handleLogin}>Entrar</AppButton>
            <AppButton disabled={isResettingPassword} onPress={() => router.push("/register")} variant="secondary">
              Criar conta
            </AppButton>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  flex: { backgroundColor: colors.background, flex: 1 },
  content: { padding: 24, paddingBottom: 40 },
  heading: { color: colors.primaryDark, fontSize: 30, fontWeight: "900", marginTop: 8 },
  lead: { color: colors.textMuted, fontSize: 16, lineHeight: 21, marginTop: 8 },
  form: { gap: 14, marginTop: 18 },
  error: { color: colors.danger, fontSize: 12, lineHeight: 17 },
  forgotPasswordButton: { alignSelf: "flex-end", paddingHorizontal: 2, paddingVertical: 2 },
  forgotPasswordText: { color: colors.primary, fontSize: 14, fontWeight: "800" },
  forgotPasswordTextDisabled: { opacity: 0.55 },
});
