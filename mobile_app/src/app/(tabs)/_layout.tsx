import { Ionicons } from "@expo/vector-icons";
import { Redirect, Tabs, type Href } from "expo-router";
import { colors } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import { LoadingScreen } from "@/components/ui";

/**
 * Layout do grupo protegido de abas.
 *
 * Pastas entre parênteses organizam rotas sem acrescentar um segmento à URL.
 * Tabs cria a navegação inferior e associa cada arquivo a um rótulo/ícone. O
 * layout também funciona como barreira de acesso: sem sessão, renderiza um
 * Redirect para a tela inicial.
 */
const icons = {
  feed: "home-outline",
  cupons: "ticket-outline",
  feiras: "map-outline",
  mensagens: "chatbubbles-outline",
  perfil: "person-outline",
} as const;

export default function TabsLayout() {
  const {
    accessDestination,
    accessSession,
    deviceApprovalRequired,
    hasFirebaseSession,
    hasPermission,
    isAuthenticated,
    isHydrated,
    isResolvingAccess,
    unreadMessageCount,
  } = useApp();

  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (!hasFirebaseSession) return <Redirect href={"/login" as Href} />;

  if (
    !isAuthenticated ||
    accessSession?.access_state !== "AUTHORIZED" ||
    !accessSession.role
  ) {
    return <Redirect href={"/access-pending" as Href} />;
  }

  if (accessSession.role !== "entrepreneur" && accessSession.role !== "visitor") {
    return <Redirect href={accessDestination as Href} />;
  }

  if (deviceApprovalRequired && accessSession.role === "entrepreneur") {
    return <Redirect href={"/account/devices" as Href} />;
  }

  if (!hasPermission(`${accessSession.role}.panel.access`)) {
    return <Redirect href={"/access-pending" as Href} />;
  }

  return (
    <Tabs
      initialRouteName="feed"
      // screenOptions recebe a rota atual para escolher o ícone correspondente.
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.text,
        tabBarLabelStyle: { fontSize: 10, fontWeight: "600" },
        tabBarStyle: {
          backgroundColor: colors.background,
          borderTopColor: colors.border,
          height: 72,
          paddingBottom: 8,
          paddingTop: 8,
        },
        tabBarIcon: ({ color, size }) => (
          <Ionicons color={color} name={icons[route.name as keyof typeof icons]} size={size} />
        ),
      })}
    >
      <Tabs.Screen name="feed" options={{ title: "Feed" }} />
      <Tabs.Screen name="cupons" options={{ title: "Cupons" }} />
      <Tabs.Screen name="feiras" options={{ title: "Mapa" }} />
      <Tabs.Screen
        name="mensagens"
        options={{
          tabBarBadge: unreadMessageCount > 0 ? Math.min(99, unreadMessageCount) : undefined,
          title: "Mensagens",
        }}
      />
      <Tabs.Screen name="perfil" options={{ title: "Perfil" }} />
    </Tabs>
  );
}
