/**
 * Design tokens globais do FeiTUR.
 *
 * Em vez de repetir cores e medidas em cada tela, o projeto centraliza os
 * valores visuais neste arquivo. Isso aplica o princípio de reutilização
 * apresentado nas aulas de estilização e facilita alterações de identidade
 * visual: mudar um token atualiza todos os componentes que o consomem.
 */
export const colors = {
  background: "#FCFAF2",
  surface: "#FFFFFF",
  surfaceMuted: "#F5F0E8",
  cream: "#F5EDDB",
  border: "#E0D6C2",
  primary: "#2B5CC7",
  primaryDark: "#0F2E6E",
  accent: "#FF6E17",
  accentSoft: "#FFB17A",
  text: "#1F2129",
  textMuted: "#737885",
  success: "#178653",
  danger: "#B42318",
} as const;

// Escala curta de bordas para manter cartões, campos e botões consistentes.
export const radius = {
  small: 10,
  medium: 16,
  large: 22,
  pill: 999,
} as const;

// Sombra compartilhada pelos cartões. O elevation produz o efeito no Android.
export const shadow = {
  shadowColor: "#0F2E6E",
  shadowOffset: { width: 0, height: 4 },
  shadowOpacity: 0.08,
  shadowRadius: 12,
  elevation: 3,
} as const;
