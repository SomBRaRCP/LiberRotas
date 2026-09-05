import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";
import {
  getPinhaisCategoryIconGlyph,
  PINHAIS_IONICONS_FONT_FAMILY,
  PINHAIS_IONICONS_FONT_URL,
} from "@/constants/pinhais-icons";
import { pinhaisCategoryColors, pinhaisCategoryLabels } from "@/data/pinhais";
import {
  buildOverlappingMarkerOffsets,
  buildMapPointsSignature,
  type InteractivePlaceMapProps,
} from "./interactive-place-map.types";

const LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

function safeJson(value: unknown) {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

function buildMapHtml(
  points: InteractivePlaceMapProps["points"],
  center: InteractivePlaceMapProps["center"],
) {
  const markerOffsets = buildOverlappingMarkerOffsets(points);
  const mapPoints = points.map((point) => ({
    address: point.endereco,
    category: pinhaisCategoryLabels[point.categoriaApp],
    color: pinhaisCategoryColors[point.categoriaApp],
    id: point.id,
    latitude: point.latitude,
    longitude: point.longitude,
    name: point.nome,
    iconGlyph: getPinhaisCategoryIconGlyph(point.categoriaApp),
    offsetX: markerOffsets.get(point.id)?.x || 0,
    offsetY: markerOffsets.get(point.id)?.y || 0,
  }));

  return `<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=yes" />
  <link rel="stylesheet" href="${LEAFLET_CSS_URL}" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
  <style>
    @font-face { font-family:'${PINHAIS_IONICONS_FONT_FAMILY}'; font-style:normal; font-weight:normal; src:url('${PINHAIS_IONICONS_FONT_URL}') format('truetype'); }
    html, body, #map { height: 100%; margin: 0; width: 100%; }
    body { background: #E8F2EF; font-family: system-ui, sans-serif; }
    .liberrotas-marker { align-items:center; border:3px solid #fff; border-radius:999px; box-sizing:border-box; box-shadow:0 3px 8px rgba(15,46,110,.35); color:#fff; display:flex; font-family:'${PINHAIS_IONICONS_FONT_FAMILY}'; font-size:16px; font-weight:normal; height:34px; justify-content:center; line-height:1; width:34px; }
    .liberrotas-marker-host { background:transparent; border:0; }
    .liberrotas-marker-selected { border-width:4px; box-shadow:0 4px 12px rgba(15,46,110,.55); transform:scale(1.18); }
  </style>
</head>
<body>
  <div id="map" aria-label="Mapa interativo dos pontos de Pinhais"></div>
  <script>
    function notifyMapError() {
      window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'map-error' }));
    }
  </script>
  <script src="${LEAFLET_JS_URL}" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin="" onerror="notifyMapError()"></script>
  <script>
    if (!window.L) {
      notifyMapError();
    } else {
    const points = ${safeJson(mapPoints)};
    const center = ${safeJson(center)};
    const map = L.map('map', { minZoom: 11, scrollWheelZoom: true }).setView([center.latitude, center.longitude], 13);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19
    }).addTo(map);

    const bounds = [];
    const markerRecords = {};
    points.forEach((point) => {
      const markerNode = document.createElement('div');
      markerNode.className = 'liberrotas-marker';
      markerNode.style.backgroundColor = point.color;
      markerNode.textContent = point.iconGlyph;
      const icon = L.divIcon({
        className: 'liberrotas-marker-host',
        html: markerNode,
        iconAnchor: [17 - point.offsetX, 17 - point.offsetY],
        iconSize: [34, 34],
        popupAnchor: [point.offsetX, -17 + point.offsetY]
      });
      const marker = L.marker([point.latitude, point.longitude], { alt: point.name, icon, keyboard: true, riseOnHover: true, title: point.name }).addTo(map);
      const popup = document.createElement('div');
      const title = document.createElement('strong');
      const category = document.createElement('div');
      const address = document.createElement('div');
      title.textContent = point.name;
      category.textContent = point.category;
      category.style.cssText = 'color:#2B5CC7;font-size:11px;font-weight:700;margin-top:4px';
      address.textContent = point.address;
      address.style.cssText = 'font-size:11px;margin-top:4px';
      popup.append(title, category, address);
      marker.bindPopup(popup);
      marker.on('click', () => window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'select-place', id: point.id })));
      markerRecords[point.id] = { marker, markerNode };
      bounds.push([point.latitude, point.longitude]);
    });

    window.selectLiberRotasPoint = function (selectedId) {
      Object.keys(markerRecords).forEach((pointId) => {
        const record = markerRecords[pointId];
        const selected = pointId === selectedId;
        record.markerNode.classList.toggle('liberrotas-marker-selected', selected);
        record.marker.setZIndexOffset(selected ? 1000 : 0);
      });
    };

    if (bounds.length === 1) map.setView(bounds[0], 15);
    if (bounds.length > 1) map.fitBounds(bounds, { maxZoom: 15, padding: [34, 34] });
    window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'map-ready' }));
    }
  </script>
</body>
</html>`;
}

/** Mapa Android/iOS executado no WebView com os marcadores dentro do Leaflet. */
export function InteractivePlaceMap({ center, onSelectPoint, points, selectedPointId, style }: InteractivePlaceMapProps) {
  const [mapLoadError, setMapLoadError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const webViewRef = useRef<WebView>(null);
  const pointsSignature = buildMapPointsSignature(points);
  const stablePoints = useMemo(() => points, [pointsSignature]); // eslint-disable-line react-hooks/exhaustive-deps -- estabiliza arrays equivalentes gerados pelo relogio
  const centerLatitude = center.latitude;
  const centerLongitude = center.longitude;
  const html = useMemo(
    () => buildMapHtml(stablePoints, { latitude: centerLatitude, longitude: centerLongitude }),
    [centerLatitude, centerLongitude, stablePoints],
  );
  const source = useMemo(() => ({ html }), [html]);

  const applySelectedPoint = useCallback(() => {
    webViewRef.current?.injectJavaScript(
      `window.selectLiberRotasPoint && window.selectLiberRotasPoint(${safeJson(selectedPointId || null)}); true;`,
    );
  }, [selectedPointId]);

  useEffect(() => {
    applySelectedPoint();
  }, [applySelectedPoint]);

  function handleMessage(event: WebViewMessageEvent) {
    try {
      const message = JSON.parse(event.nativeEvent.data) as { type?: string; id?: string };
      if (message.type === "select-place" && message.id && stablePoints.some((point) => point.id === message.id)) {
        onSelectPoint(message.id);
      }
      if (message.type === "map-error") setMapLoadError(true);
      if (message.type === "map-ready") {
        setMapLoadError(false);
        applySelectedPoint();
      }
    } catch {
      // Mensagens desconhecidas do conteúdo incorporado são ignoradas.
    }
  }

  if (mapLoadError) {
    return (
      <View style={[styles.fallback, style]}>
        <Text style={styles.fallbackTitle}>Nao foi possivel carregar o mapa.</Text>
        <Text style={styles.fallbackText}>Confira a internet e tente novamente.</Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => {
            setMapLoadError(false);
            setReloadKey((current) => current + 1);
          }}
          style={styles.retryButton}
        >
          <Text style={styles.retryText}>Tentar novamente</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <WebView
      key={reloadKey}
      ref={webViewRef}
      accessibilityLabel="Mapa interativo dos pontos de Pinhais"
      bounces={false}
      javaScriptEnabled
      onError={() => setMapLoadError(true)}
      onHttpError={() => setMapLoadError(true)}
      onMessage={handleMessage}
      originWhitelist={["*"]}
      source={source}
      style={style}
    />
  );
}

const styles = StyleSheet.create({
  fallback: {
    alignItems: "center",
    backgroundColor: "#E8F2EF",
    justifyContent: "center",
    padding: 24,
  },
  fallbackTitle: {
    color: "#0F2E6E",
    fontSize: 16,
    fontWeight: "800",
    textAlign: "center",
  },
  fallbackText: {
    color: "#52627A",
    marginTop: 6,
    textAlign: "center",
  },
  retryButton: {
    backgroundColor: "#FF6B16",
    borderRadius: 999,
    marginTop: 16,
    paddingHorizontal: 20,
    paddingVertical: 11,
  },
  retryText: {
    color: "#FFFFFF",
    fontWeight: "800",
  },
});
