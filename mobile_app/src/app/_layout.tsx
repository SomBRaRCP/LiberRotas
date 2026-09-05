import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AppProvider } from "@/context/app-context";
import { TrustedClockProvider } from "@/context/trusted-clock-context";

/**
 * Layout raiz do Expo Router.
 *
 * O arquivo _layout.tsx envolve todas as rotas com providers compartilhados:
 * SafeAreaProvider fornece os limites seguros da tela e AppProvider oferece
 * sessão/persistência. A Stack registra as rotas que ficam fora das quatro
 * abas, mantendo o cabeçalho nativo oculto porque o app usa BrandHeader.
 */
export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <TrustedClockProvider>
        <AppProvider>
          <StatusBar style="dark" />
          {/* Cada Stack.Screen corresponde a um arquivo ou grupo em src/app. */}
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="index" />
            <Stack.Screen name="login" />
            <Stack.Screen name="register" />
            <Stack.Screen name="access-pending" />
            <Stack.Screen name="admin" />
            <Stack.Screen name="support" />
            <Stack.Screen name="security" />
            <Stack.Screen name="institution" />
            <Stack.Screen name="account/devices" />
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="profile/[profileId]" />
            <Stack.Screen name="messages/[conversationId]" />
            <Stack.Screen name="scanner" options={{ presentation: "fullScreenModal" }} />
            <Stack.Screen name="generate-qr" options={{ presentation: "fullScreenModal" }} />
          </Stack>
        </AppProvider>
      </TrustedClockProvider>
    </SafeAreaProvider>
  );
}
