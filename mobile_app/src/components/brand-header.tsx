import { StyleSheet, Text, View } from "react-native";
import { colors } from "@/constants/theme";
import { LocalClock } from "@/components/local-clock";

/**
 * Cabeçalho reutilizado nas telas do FeiTUR.
 *
 * title e subtitle são props: o componente mantém a mesma estrutura visual,
 * mas recebe conteúdo diferente de cada tela. Esse padrão reduz duplicação e
 * demonstra a composição por componentes.
 */
type BrandHeaderProps = {
  title: string;
  subtitle: string;
};

export function BrandHeader({ title, subtitle }: BrandHeaderProps) {
  return (
    <View style={styles.container}>
      <View style={styles.brandRow}>
        <View style={styles.logo}>
          <Text style={styles.logoText}>LR</Text>
        </View>
        <View style={styles.titleBlock}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>
      </View>
      <LocalClock />
    </View>
  );
}

// StyleSheet valida os nomes das propriedades e organiza a estilização nativa.
const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    backgroundColor: colors.cream,
    flexDirection: "row",
    height: 72,
    justifyContent: "space-between",
    paddingHorizontal: 22,
  },
  brandRow: { alignItems: "center", flex: 1, flexDirection: "row", gap: 12 },
  logo: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: 20,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  logoText: { color: colors.accent, fontSize: 12, fontWeight: "800" },
  titleBlock: { flex: 1, paddingRight: 8 },
  title: { color: colors.primary, fontSize: 18, fontWeight: "800" },
  subtitle: { color: colors.textMuted, fontSize: 10, marginTop: 1 },
});
