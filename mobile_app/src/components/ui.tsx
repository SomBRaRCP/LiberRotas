import { Ionicons } from "@expo/vector-icons";
import { PropsWithChildren, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, TextInputProps, View, ViewStyle } from "react-native";
import { colors, radius } from "@/constants/theme";
import type { AccountType } from "@/context/app-context";

/**
 * Pequena biblioteca de componentes visuais do projeto.
 *
 * Os componentes encapsulam estilos e comportamentos repetidos. As telas
 * continuam responsáveis pelos dados, enquanto este arquivo se preocupa com
 * a apresentação de botões, campos, seleções e estado de carregamento.
 */
type ButtonProps = PropsWithChildren<{
  accessibilityLabel?: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  style?: ViewStyle;
}>;

// A prop variant troca o estilo sem exigir três componentes de botão distintos.
export function AppButton({ accessibilityLabel, children, onPress, variant = "primary", disabled, style }: ButtonProps) {
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        variant === "secondary" && styles.buttonSecondary,
        variant === "danger" && styles.buttonDanger,
        (pressed || disabled) && styles.buttonPressed,
        style,
      ]}
    >
      <Text style={[styles.buttonText, variant === "secondary" && styles.buttonTextSecondary]}>{children}</Text>
    </Pressable>
  );
}

type FieldProps = TextInputProps & { label: string; containerStyle?: ViewStyle };

// TextInputProps permite repassar props nativas como secureTextEntry e keyboardType.
export function FormField({ label, style, containerStyle, secureTextEntry, ...props }: FieldProps) {
  const [isPasswordVisible, setIsPasswordVisible] = useState(false);
  const hasPasswordToggle = Boolean(secureTextEntry);

  return (
    <View style={[styles.fieldContainer, containerStyle]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.fieldRow}>
        <TextInput
          placeholderTextColor={colors.textMuted}
          secureTextEntry={hasPasswordToggle && !isPasswordVisible}
          style={[styles.field, style]}
          {...props}
        />
        {hasPasswordToggle ? (
          <Pressable
            accessibilityLabel={isPasswordVisible ? "Ocultar senha" : "Mostrar senha"}
            accessibilityRole="button"
            disabled={props.editable === false}
            hitSlop={8}
            onPress={() => setIsPasswordVisible((current) => !current)}
            style={styles.passwordToggle}
          >
            <Ionicons
              color={colors.primary}
              name={isPasswordVisible ? "eye-off-outline" : "eye-outline"}
              size={22}
            />
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

type CheckOptionProps = { label: string; selected: boolean; onPress: () => void };

// Caixa de seleção customizada com semântica acessível para leitores de tela.
export function CheckOption({ label, selected, onPress }: CheckOptionProps) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[styles.checkOption, selected && styles.checkOptionSelected]}
    >
      <Ionicons color={selected ? colors.surface : colors.primary} name={selected ? "checkmark" : "add"} size={16} />
      <Text style={[styles.checkText, selected && styles.checkTextSelected]}>{label}</Text>
    </Pressable>
  );
}

type AccountTypeSelectorProps = {
  value: AccountType;
  onChange: (value: AccountType) => void;
};

const accountTypes: {
  value: AccountType;
  label: string;
  description: string;
  icon: "storefront-outline" | "person-outline";
}[] = [
  {
    value: "entrepreneur",
    label: "Empreendedor",
    description: "Divulga produtos, serviços e experiências.",
    icon: "storefront-outline",
  },
  {
    value: "visitor",
    label: "Visitante",
    description: "Descobre feiras, cupons e roteiros locais.",
    icon: "person-outline",
  },
];

/** Seleção visual do tipo de acesso; a autorização real nunca é decidida por este componente. */
export function AccountTypeSelector({ value, onChange }: AccountTypeSelectorProps) {
  return (
    <View style={styles.accountTypeList}>
      {accountTypes.map((option) => {
        const selected = value === option.value;
        return (
          <Pressable
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            key={option.value}
            onPress={() => onChange(option.value)}
            style={[styles.accountTypeCard, selected && styles.accountTypeCardSelected]}
          >
            <View style={[styles.accountTypeIcon, selected && styles.accountTypeIconSelected]}>
              <Ionicons color={selected ? colors.surface : colors.primary} name={option.icon} size={20} />
            </View>
            <View style={styles.accountTypeText}>
              <Text style={[styles.accountTypeLabel, selected && styles.accountTypeLabelSelected]}>{option.label}</Text>
              <Text style={[styles.accountTypeDescription, selected && styles.accountTypeDescriptionSelected]}>
                {option.description}
              </Text>
            </View>
            <Ionicons color={selected ? colors.accent : colors.border} name={selected ? "radio-button-on" : "radio-button-off"} size={20} />
          </Pressable>
        );
      })}
    </View>
  );
}

// Tela neutra exibida enquanto o AsyncStorage restaura a sessão.
export function LoadingScreen() {
  return (
    <View style={styles.loading}>
      <View style={styles.loadingLogo}>
        <Text style={styles.loadingText}>LR</Text>
      </View>
      <Text style={styles.loadingLabel}>Carregando LiberRotas...</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: "center",
    backgroundColor: colors.accent,
    borderRadius: radius.pill,
    justifyContent: "center",
    minHeight: 50,
    paddingHorizontal: 22,
  },
  buttonSecondary: { backgroundColor: colors.surface },
  buttonDanger: { backgroundColor: colors.danger },
  buttonPressed: { opacity: 0.65 },
  buttonText: { color: colors.surface, fontSize: 14, fontWeight: "700" },
  buttonTextSecondary: { color: colors.primary },
  fieldContainer: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    minHeight: 78,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  fieldLabel: { color: colors.textMuted, fontSize: 12, marginBottom: 6 },
  fieldRow: { alignItems: "center", flex: 1, flexDirection: "row" },
  field: { color: colors.text, flex: 1, fontSize: 16, padding: 0 },
  passwordToggle: { alignItems: "center", justifyContent: "center", marginLeft: 10, padding: 4 },
  checkOption: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderColor: colors.border,
    borderRadius: radius.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  checkOptionSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  checkText: { color: colors.primary, fontSize: 12, fontWeight: "600" },
  checkTextSelected: { color: colors.surface },
  accountTypeList: { gap: 10 },
  accountTypeCard: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    flexDirection: "row",
    gap: 12,
    minHeight: 76,
    padding: 12,
  },
  accountTypeCardSelected: { backgroundColor: "#F2F6FF", borderColor: colors.primary, borderWidth: 2 },
  accountTypeIcon: {
    alignItems: "center",
    backgroundColor: colors.cream,
    borderRadius: 20,
    height: 40,
    justifyContent: "center",
    width: 40,
  },
  accountTypeIconSelected: { backgroundColor: colors.primary },
  accountTypeText: { flex: 1 },
  accountTypeLabel: { color: colors.primaryDark, fontSize: 14, fontWeight: "800" },
  accountTypeLabelSelected: { color: colors.primary },
  accountTypeDescription: { color: colors.textMuted, fontSize: 11, lineHeight: 15, marginTop: 2 },
  accountTypeDescriptionSelected: { color: colors.primaryDark },
  loading: { alignItems: "center", backgroundColor: colors.background, flex: 1, justifyContent: "center" },
  loadingLogo: {
    alignItems: "center",
    backgroundColor: colors.accent,
    borderRadius: 32,
    height: 64,
    justifyContent: "center",
    width: 64,
  },
  loadingText: { color: colors.surface, fontSize: 20, fontWeight: "900" },
  loadingLabel: { color: colors.primaryDark, fontSize: 14, fontWeight: "600", marginTop: 14 },
});
