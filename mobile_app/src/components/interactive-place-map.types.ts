import type { StyleProp, ViewStyle } from "react-native";
import type { PinhaisPlace } from "@/data/pinhais";

export type InteractivePlaceMapProps = {
  center: { latitude: number; longitude: number };
  onSelectPoint: (placeId: string) => void;
  points: PinhaisPlace[];
  selectedPointId?: string;
  style?: StyleProp<ViewStyle>;
};

export type MapMarkerOffset = { x: number; y: number };

/** Identifica mudancas reais sem reagir a novos arrays criados pelo relogio. */
export function buildMapPointsSignature(points: PinhaisPlace[]) {
  return JSON.stringify(
    points
      .map((point) => [
        point.id,
        point.nome,
        point.endereco,
        point.categoriaApp,
        point.latitude,
        point.longitude,
      ])
      .sort((left, right) => String(left[0]).localeCompare(String(right[0]))),
  );
}

/**
 * Separa apenas a aparencia de pontos com coordenadas identicas. A latitude e
 * a longitude do marcador continuam intactas para zoom, popup e rota.
 */
export function buildOverlappingMarkerOffsets(points: PinhaisPlace[]) {
  const groups = new Map<string, PinhaisPlace[]>();
  const offsets = new Map<string, MapMarkerOffset>();

  points.forEach((point) => {
    const coordinateKey = `${point.latitude.toFixed(6)}:${point.longitude.toFixed(6)}`;
    const group = groups.get(coordinateKey) || [];
    group.push(point);
    groups.set(coordinateKey, group);
  });

  groups.forEach((group) => {
    const orderedGroup = [...group].sort((left, right) => left.id.localeCompare(right.id));
    if (orderedGroup.length === 1) {
      offsets.set(orderedGroup[0].id, { x: 0, y: 0 });
      return;
    }

    const radius = orderedGroup.length === 2 ? 22 : Math.max(26, orderedGroup.length * 8);
    orderedGroup.forEach((point, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI * 2) / orderedGroup.length;
      offsets.set(point.id, {
        x: Math.round(Math.cos(angle) * radius),
        y: Math.round(Math.sin(angle) * radius),
      });
    });
  });

  return offsets;
}
