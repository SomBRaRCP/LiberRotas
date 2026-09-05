import { createElement, useEffect, useId, useMemo, useRef } from "react";
import { StyleSheet } from "react-native";
import type { LayerGroup, Map as LeafletMap } from "leaflet";
import {
  getPinhaisCategoryIconGlyph,
  loadPinhaisCategoryIconFont,
  PINHAIS_IONICONS_FONT_FAMILY,
} from "@/constants/pinhais-icons";
import { pinhaisCategoryColors, pinhaisCategoryLabels, type PinhaisPlace } from "@/data/pinhais";
import {
  buildOverlappingMarkerOffsets,
  buildMapPointsSignature,
  type InteractivePlaceMapProps,
} from "./interactive-place-map.types";

const LEAFLET_CSS_ID = "liberrotas-leaflet-css";
const LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

function ensureLeafletStylesheet() {
  if (document.getElementById(LEAFLET_CSS_ID)) return;
  const link = document.createElement("link");
  link.crossOrigin = "";
  link.href = LEAFLET_CSS_URL;
  link.id = LEAFLET_CSS_ID;
  link.integrity = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=";
  link.rel = "stylesheet";
  document.head.appendChild(link);
}

function createMarkerContent(place: PinhaisPlace, selected: boolean) {
  const marker = document.createElement("div");
  marker.setAttribute("aria-label", place.nome);
  marker.style.alignItems = "center";
  marker.style.backgroundColor = pinhaisCategoryColors[place.categoriaApp];
  marker.style.border = `${selected ? 4 : 3}px solid #FFFFFF`;
  marker.style.borderRadius = "999px";
  marker.style.boxShadow = selected ? "0 0 0 4px rgba(15, 46, 110, 0.30)" : "0 3px 8px rgba(15, 46, 110, 0.35)";
  marker.style.color = "#FFFFFF";
  marker.style.display = "flex";
  marker.style.fontFamily = PINHAIS_IONICONS_FONT_FAMILY;
  marker.style.fontSize = selected ? "18px" : "15px";
  marker.style.fontWeight = "900";
  marker.style.height = "100%";
  marker.style.justifyContent = "center";
  marker.style.lineHeight = "1";
  marker.style.width = "100%";
  marker.textContent = getPinhaisCategoryIconGlyph(place.categoriaApp);
  return marker;
}

function createPopupContent(place: PinhaisPlace) {
  const popup = document.createElement("div");
  const title = document.createElement("strong");
  const category = document.createElement("div");
  const address = document.createElement("div");
  title.textContent = place.nome;
  category.textContent = pinhaisCategoryLabels[place.categoriaApp];
  category.style.color = "#2B5CC7";
  category.style.fontSize = "11px";
  category.style.fontWeight = "700";
  category.style.marginTop = "4px";
  address.textContent = place.endereco;
  address.style.fontSize = "11px";
  address.style.marginTop = "4px";
  popup.append(title, category, address);
  return popup;
}

/** Mapa web gratuito com marcadores geográficos que acompanham zoom e arraste. */
export function InteractivePlaceMap({ center, onSelectPoint, points, selectedPointId, style }: InteractivePlaceMapProps) {
  const containerId = useId();
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const markerLayerRef = useRef<LayerGroup | null>(null);
  const pointSignatureRef = useRef("");
  const pointsSignature = buildMapPointsSignature(points);
  const stablePoints = useMemo(() => points, [pointsSignature]); // eslint-disable-line react-hooks/exhaustive-deps -- estabiliza arrays equivalentes gerados pelo relogio

  useEffect(() => {
    let cancelled = false;

    async function renderMap() {
      ensureLeafletStylesheet();
      const [leaflet] = await Promise.all([
        leafletRef.current ? Promise.resolve(leafletRef.current) : import("leaflet"),
        loadPinhaisCategoryIconFont(),
      ]);
      const container = document.getElementById(containerId);
      if (cancelled || !(container instanceof HTMLDivElement)) return;
      leafletRef.current = leaflet;

      if (!mapRef.current) {
        const map = leaflet.map(container, {
          minZoom: 11,
          scrollWheelZoom: true,
          zoomControl: true,
        }).setView([center.latitude, center.longitude], 13);
        leaflet.tileLayer(TILE_URL, {
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          maxZoom: 19,
        }).addTo(map);
        mapRef.current = map;
        markerLayerRef.current = leaflet.layerGroup().addTo(map);
        window.setTimeout(() => map.invalidateSize(), 0);
      }

      const map = mapRef.current;
      const markerLayer = markerLayerRef.current;
      if (!map || !markerLayer) return;
      markerLayer.clearLayers();
      const markerOffsets = buildOverlappingMarkerOffsets(stablePoints);
      stablePoints.forEach((place) => {
        const selected = place.id === selectedPointId;
        const size = selected ? 40 : 34;
        const offset = markerOffsets.get(place.id) || { x: 0, y: 0 };
        const marker = leaflet.marker([place.latitude, place.longitude], {
          alt: place.nome,
          icon: leaflet.divIcon({
            className: "liberrotas-map-marker",
            html: createMarkerContent(place, selected),
            iconAnchor: [size / 2 - offset.x, size / 2 - offset.y],
            iconSize: [size, size],
            popupAnchor: [offset.x, -size / 2 + offset.y],
          }),
          keyboard: true,
          riseOnHover: true,
          title: place.nome,
          zIndexOffset: selected ? 1000 : 0,
        });
        marker.bindPopup(createPopupContent(place));
        marker.on("click", () => onSelectPoint(place.id));
        marker.addTo(markerLayer);
      });

      const nextSignature = buildMapPointsSignature(stablePoints);
      if (nextSignature !== pointSignatureRef.current) {
        pointSignatureRef.current = nextSignature;
        if (stablePoints.length === 0) {
          map.setView([center.latitude, center.longitude], 13);
        } else if (stablePoints.length === 1) {
          map.setView([stablePoints[0].latitude, stablePoints[0].longitude], 15);
        } else {
          map.fitBounds(
            leaflet.latLngBounds(stablePoints.map((point) => [point.latitude, point.longitude])),
            { maxZoom: 15, padding: [34, 34] },
          );
        }
      }
    }

    void renderMap();
    return () => {
      cancelled = true;
    };
  }, [center.latitude, center.longitude, containerId, onSelectPoint, selectedPointId, stablePoints]);

  useEffect(() => () => {
    mapRef.current?.remove();
    mapRef.current = null;
    markerLayerRef.current = null;
  }, []);

  const resolvedStyle = StyleSheet.flatten(style) as Record<string, string | number> | undefined;
  return createElement("div", {
    "aria-label": "Mapa interativo dos pontos de Pinhais",
    id: containerId,
    role: "application",
    style: {
      backgroundColor: "#E8F2EF",
      height: "100%",
      width: "100%",
      ...resolvedStyle,
    },
  });
}
