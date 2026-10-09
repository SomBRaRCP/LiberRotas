import { Ionicons } from "@expo/vector-icons";
import { router, type Href } from "expo-router";
import { Pressable, StyleSheet } from "react-native";
import { colors } from "@/constants/theme";

export function HeaderBackButton({ fallbackHref, disabled = false }: { fallbackHref: Href; disabled?: boolean }) {
  return (
    <Pressable
      accessibilityLabel="Voltar"
      accessibilityRole="button"
      disabled={disabled}
      onPress={() => {
        if (router.canGoBack()) router.back();
        else router.replace(fallbackHref);
      }}
      style={({ pressed }) => [styles.button, (pressed || disabled) && styles.pressed]}
    >
      <Ionicons color={colors.primaryDark} name="arrow-back" size={20} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { alignItems: "center", backgroundColor: colors.surface, borderRadius: 22, flexShrink: 0, height: 44, justifyContent: "center", width: 36 },
  pressed: { opacity: 0.5 },
});
