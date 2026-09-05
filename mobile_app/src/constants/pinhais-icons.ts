import { Ionicons } from "@expo/vector-icons";
import type { PinhaisCategory } from "@/data/pinhais";

export type PinhaisIconName = keyof typeof Ionicons.glyphMap;

/** Mesmos Ionicons usados nos cards, filtros e marcadores do mapa. */
export const pinhaisCategoryIcons: Record<PinhaisCategory, PinhaisIconName> = {
  pontos_turisticos: "camera-outline",
  parques: "leaf-outline",
  feiras_livres: "basket-outline",
  artesanato: "color-palette-outline",
  bordados: "shirt-outline",
  gastronomia: "restaurant-outline",
  eventos: "calendar-outline",
  comercio_local: "storefront-outline",
};

export const PINHAIS_IONICONS_FONT_FAMILY = Ionicons.getFontFamily();
export const PINHAIS_IONICONS_FONT_URL =
  "https://unpkg.com/@expo/vector-icons@15.1.1/build/vendor/react-native-vector-icons/Fonts/Ionicons.ttf";

export function getPinhaisCategoryIconGlyph(category: PinhaisCategory) {
  const glyph = Ionicons.glyphMap[pinhaisCategoryIcons[category]];
  return typeof glyph === "number" ? String.fromCodePoint(glyph) : glyph;
}

export function loadPinhaisCategoryIconFont() {
  return Ionicons.loadFont();
}
