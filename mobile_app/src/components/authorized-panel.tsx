import { Ionicons } from "@expo/vector-icons";
import { Redirect, router, type Href, useLocalSearchParams } from "expo-router";
import { type ReactNode, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { AppButton, LoadingScreen } from "@/components/ui";
import { LocalClock } from "@/components/local-clock";
import { colors, radius, shadow } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import type { AccessRole } from "@/security/trq-bec/service";

type StaffRole = Extract<AccessRole, "admin" | "support" | "security" | "institution">;

export type PanelSection = {
  id?: string;
  title: string;
  description: string;
  icon: keyof typeof Ionicons.glyphMap;
  permission: string;
  /** Permissões adicionais que também precisam existir para a ferramenta funcionar inteira. */
  additionalPermissions?: string[];
  /** Conteúdo criado somente depois que a pessoa abre a ferramenta. */
  renderContent?: () => ReactNode;
};

type AuthorizedPanelProps = {
  role: StaffRole;
  title: string;
  subtitle: string;
  sections: PanelSection[];
  guide?: {
    purpose: string;
    boundaries: string[];
  };
  /** Compatibilidade temporária com painéis ainda não divididos em ferramentas. */
  children?: ReactNode;
};

/**
 * Estrutura compartilhada pelos painéis internos.
 *
 * A rota nunca decide a função do usuário. Ela apenas compara a função e a
 * permissão que o backend já autorizou. Até essa resolução terminar, nenhuma
 * parte privilegiada do painel é renderizada.
 */
export function AuthorizedPanel({ role, title, subtitle, sections, guide, children }: AuthorizedPanelProps) {
  const { tool } = useLocalSearchParams<{ tool?: string | string[] }>();
  const {
    accessDestination,
    accessSession,
    deviceApprovalRequired,
    hasFirebaseSession,
    hasPermission,
    isAuthenticated,
    isHydrated,
    isResolvingAccess,
    logout,
  } = useApp();
  const insets = useSafeAreaInsets();
  const [isLeaving, setIsLeaving] = useState(false);
  const [activeToolId, setActiveToolId] = useState<string | null>(null);
  const authorizedTools = sections
    .map((section, index) => ({
      ...section,
      resolvedId: section.id || `${section.permission}:${section.title}:${index}`,
    }))
    .filter((section) => (
      hasPermission(section.permission)
      && (section.additionalPermissions || []).every((permission) => hasPermission(permission))
    ));
  const requestedToolId = Array.isArray(tool) ? tool[0] : tool;
  const authorizedRouteToolId = requestedToolId
    && authorizedTools.some((section) => section.resolvedId === requestedToolId)
    ? requestedToolId
    : null;

  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (!hasFirebaseSession) return <Redirect href={"/login" as Href} />;

  if (
    !isAuthenticated ||
    accessSession?.access_state !== "AUTHORIZED" ||
    !accessSession.role
  ) {
    return <Redirect href={"/access-pending" as Href} />;
  }

  // Abrir uma URL manualmente nunca promove a conta para outra função.
  if (accessSession.role !== role) {
    return <Redirect href={accessDestination as Href} />;
  }

  if (deviceApprovalRequired) {
    return <Redirect href={"/account/devices" as Href} />;
  }

  if (!hasPermission(`${role}.panel.access`)) {
    return <Redirect href={"/access-pending" as Href} />;
  }

  const effectiveToolId = authorizedRouteToolId || activeToolId;
  const activeTool = authorizedTools.find((section) => section.resolvedId === effectiveToolId) || null;

  async function handleLogout() {
    if (isLeaving) return;
    setIsLeaving(true);
    try {
      await logout();
      router.replace("/");
    } finally {
      setIsLeaving(false);
    }
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <View style={styles.header}>
        <View style={styles.logo}>
          <Text style={styles.logoText}>LR</Text>
        </View>
        <View style={styles.headerText}>
          <Text style={styles.brand}>LiberRotas</Text>
          <Text style={styles.headerLabel}>Área autorizada</Text>
        </View>
        <LocalClock />
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: Math.max(32, insets.bottom + 20) }]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.hero}>
          <View style={styles.heroIcon}>
            <Ionicons color={colors.surface} name="shield-checkmark-outline" size={28} />
          </View>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>

        {activeTool ? (
          <View style={styles.toolView}>
            <Pressable
              accessibilityHint="Retorna para a lista de ferramentas autorizadas"
              accessibilityLabel="Voltar ao painel"
              accessibilityRole="button"
              onPress={() => {
                setActiveToolId(null);
                if (requestedToolId) router.replace(accessDestination as Href);
              }}
              style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}
            >
              <Ionicons color={colors.primary} name="arrow-back-outline" size={20} />
              <Text style={styles.backButtonText}>Voltar ao painel</Text>
            </Pressable>

            <View style={styles.activeToolHeading}>
              <View style={styles.cardIcon}>
                <Ionicons color={colors.primary} name={activeTool.icon} size={22} />
              </View>
              <View style={styles.cardText}>
                <Text style={styles.activeToolTitle}>{activeTool.title}</Text>
                <Text style={styles.cardDescription}>{activeTool.description}</Text>
              </View>
            </View>

            <View style={styles.panelContent}>
              {activeTool.renderContent
                ? activeTool.renderContent()
                : children ?? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyText}>Esta ferramenta ainda não possui uma interface disponível.</Text>
                  </View>
                )}
            </View>
          </View>
        ) : (
          <View style={styles.menuView}>
            {guide ? (
              <View style={styles.guideCard}>
                <View style={styles.guideHeading}>
                  <Ionicons color={colors.primary} name="information-circle-outline" size={22} />
                  <Text style={styles.guideTitle}>Funções autorizadas deste painel</Text>
                </View>
                <Text style={styles.guidePurpose}>{guide.purpose}</Text>
                <Text style={styles.guideSubtitle}>Ferramentas disponíveis para esta conta</Text>
                {authorizedTools.map((section) => (
                  <View key={`guide:${section.resolvedId}`} style={styles.guideItem}>
                    <Text style={styles.guideBullet}>•</Text>
                    <View style={styles.cardText}>
                      <Text style={styles.guideItemTitle}>{section.title}</Text>
                      <Text style={styles.guideItemText}>{section.description}</Text>
                      <Text selectable style={styles.guidePermission}>Permissão: {section.permission}</Text>
                    </View>
                  </View>
                ))}
                <Text style={styles.guideSubtitle}>Limites de segurança</Text>
                {guide.boundaries.map((boundary) => (
                  <View key={boundary} style={styles.guideItem}>
                    <Text style={styles.guideBullet}>•</Text>
                    <Text style={[styles.guideItemText, styles.guideBoundary]}>{boundary}</Text>
                  </View>
                ))}
              </View>
            ) : null}
            <View style={styles.sectionList}>
              {authorizedTools.map((section) => (
                <Pressable
                  accessibilityHint={`Abre a ferramenta ${section.title}`}
                  accessibilityLabel={section.title}
                  accessibilityRole="button"
                  key={section.resolvedId}
                  onPress={() => {
                    setActiveToolId(section.resolvedId);
                  }}
                  style={({ pressed }) => [styles.card, pressed && styles.pressed]}
                >
                  <View style={styles.cardIcon}>
                    <Ionicons color={colors.primary} name={section.icon} size={22} />
                  </View>
                  <View style={styles.cardText}>
                    <Text style={styles.cardTitle}>{section.title}</Text>
                    <Text style={styles.cardDescription}>{section.description}</Text>
                  </View>
                  <Ionicons color={colors.primary} name="chevron-forward-outline" size={20} />
                </Pressable>
              ))}
              {authorizedTools.length === 0 ? (
                <View style={styles.emptyCard}>
                  <Text style={styles.emptyText}>Nenhum recurso adicional foi liberado para esta conta.</Text>
                </View>
              ) : null}
            </View>

            <Pressable
              accessibilityHint="Abre a lista de aparelhos conectados e as opções de senha"
              accessibilityLabel="Segurança da minha conta"
              accessibilityRole="button"
              onPress={() => router.push("/account/devices" as Href)}
              style={({ pressed }) => [styles.accountSecurityButton, pressed && styles.pressed]}
            >
              <Ionicons color={colors.primary} name="phone-portrait-outline" size={20} />
              <View style={styles.cardText}>
                <Text style={styles.accountSecurityTitle}>Segurança da minha conta</Text>
                <Text style={styles.accountSecurityDescription}>Revise dispositivos conectados ou altere sua senha</Text>
              </View>
              <Ionicons color={colors.primary} name="chevron-forward-outline" size={19} />
            </Pressable>

            <AppButton disabled={isLeaving} onPress={handleLogout}>
              {isLeaving ? "Saindo..." : "SAIR"}
            </AppButton>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.cream, flex: 1 },
  header: {
    alignItems: "center",
    backgroundColor: colors.cream,
    flexDirection: "row",
    gap: 12,
    minHeight: 72,
    paddingHorizontal: 22,
  },
  logo: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: 20,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  logoText: { color: colors.accent, fontSize: 12, fontWeight: "900" },
  headerText: { flex: 1 },
  brand: { color: colors.primary, fontSize: 18, fontWeight: "900" },
  headerLabel: { color: colors.textMuted, fontSize: 10, marginTop: 1 },
  content: { backgroundColor: colors.background, flexGrow: 1, padding: 22 },
  hero: {
    alignItems: "center",
    backgroundColor: colors.primaryDark,
    borderRadius: radius.large,
    paddingHorizontal: 20,
    paddingVertical: 26,
    ...shadow,
  },
  heroIcon: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderRadius: 28,
    height: 56,
    justifyContent: "center",
    marginBottom: 14,
    width: 56,
  },
  title: { color: colors.surface, fontSize: 24, fontWeight: "900", textAlign: "center" },
  subtitle: { color: colors.cream, fontSize: 13, lineHeight: 19, marginTop: 7, textAlign: "center" },
  menuView: { gap: 0 },
  guideCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    gap: 9,
    marginTop: 20,
    padding: 16,
  },
  guideHeading: { alignItems: "center", flexDirection: "row", gap: 8 },
  guideTitle: { color: colors.primaryDark, flex: 1, fontSize: 16, fontWeight: "900" },
  guidePurpose: { color: colors.text, fontSize: 12, lineHeight: 18 },
  guideSubtitle: { color: colors.primaryDark, fontSize: 12, fontWeight: "900", marginTop: 3 },
  guideItem: { alignItems: "flex-start", flexDirection: "row", gap: 7 },
  guideBullet: { color: colors.primary, fontSize: 15, fontWeight: "900", lineHeight: 18 },
  guideItemTitle: { color: colors.primaryDark, fontSize: 12, fontWeight: "800" },
  guideItemText: { color: colors.textMuted, flex: 1, fontSize: 11, lineHeight: 16 },
  guidePermission: { color: colors.primary, fontSize: 10, lineHeight: 15, marginTop: 2 },
  guideBoundary: { color: colors.text },
  sectionList: { gap: 12, marginBottom: 14, marginTop: 20 },
  accountSecurityButton: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.primary,
    borderRadius: radius.medium,
    borderWidth: 1,
    flexDirection: "row",
    gap: 11,
    marginBottom: 12,
    minHeight: 66,
    padding: 14,
  },
  accountSecurityTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: "900" },
  accountSecurityDescription: { color: colors.textMuted, fontSize: 10, lineHeight: 14, marginTop: 2 },
  card: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    flexDirection: "row",
    gap: 13,
    minHeight: 88,
    padding: 15,
  },
  pressed: { opacity: 0.65 },
  cardIcon: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderRadius: 22,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  cardText: { flex: 1 },
  cardTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "800" },
  cardDescription: { color: colors.textMuted, fontSize: 12, lineHeight: 17, marginTop: 3 },
  emptyCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    padding: 18,
  },
  emptyText: { color: colors.textMuted, fontSize: 13, lineHeight: 18, textAlign: "center" },
  toolView: { gap: 14, marginTop: 20 },
  backButton: {
    alignItems: "center",
    alignSelf: "flex-start",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    minHeight: 44,
    paddingHorizontal: 16,
  },
  backButtonText: { color: colors.primary, fontSize: 13, fontWeight: "800" },
  activeToolHeading: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    flexDirection: "row",
    gap: 13,
    padding: 15,
  },
  activeToolTitle: { color: colors.primaryDark, fontSize: 18, fontWeight: "900" },
  panelContent: { gap: 14 },
});
