import { Ionicons } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors, radius } from "@/constants/theme";
import { clampPage, getPageCount, HISTORY_PAGE_SIZE } from "@/utils/pagination";

export function PaginationControls({
  label,
  onPageChange,
  page,
  pageSize = HISTORY_PAGE_SIZE,
  totalItems,
}: {
  label: string;
  onPageChange: (page: number) => void;
  page: number;
  pageSize?: number;
  totalItems: number;
}) {
  const totalPages = getPageCount(totalItems, pageSize);
  const currentPage = clampPage(page, totalItems, pageSize);

  if (totalPages <= 1) return null;

  return (
    <View accessibilityLabel={`Paginação de ${label}`} style={styles.container}>
      <Pressable
        accessibilityLabel={`Página anterior de ${label}`}
        accessibilityRole="button"
        accessibilityState={{ disabled: currentPage === 1 }}
        disabled={currentPage === 1}
        onPress={() => onPageChange(currentPage - 1)}
        style={[styles.button, currentPage === 1 && styles.buttonDisabled]}
      >
        <Ionicons color={colors.primary} name="chevron-back" size={17} />
        <Text style={styles.buttonText}>Anterior</Text>
      </Pressable>
      <Text accessibilityLiveRegion="polite" style={styles.pageText}>
        Página {currentPage} de {totalPages}
      </Text>
      <Pressable
        accessibilityLabel={`Próxima página de ${label}`}
        accessibilityRole="button"
        accessibilityState={{ disabled: currentPage === totalPages }}
        disabled={currentPage === totalPages}
        onPress={() => onPageChange(currentPage + 1)}
        style={[styles.button, currentPage === totalPages && styles.buttonDisabled]}
      >
        <Text style={styles.buttonText}>Próxima</Text>
        <Ionicons color={colors.primary} name="chevron-forward" size={17} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
    justifyContent: "center",
    paddingTop: 12,
  },
  button: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 5,
    minHeight: 40,
    paddingHorizontal: 14,
  },
  buttonDisabled: { opacity: 0.42 },
  buttonText: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  pageText: { color: colors.primaryDark, fontSize: 12, fontWeight: "800", minWidth: 96, textAlign: "center" },
});
