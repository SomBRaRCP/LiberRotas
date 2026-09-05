import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

type ImageViewerModalProps = {
  accessibilityLabel?: string;
  onClose: () => void;
  uri?: string;
  visible: boolean;
};

const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.5;

export function ImageViewerModal({
  accessibilityLabel = "Imagem ampliada",
  onClose,
  uri,
  visible,
}: ImageViewerModalProps) {
  const { height, width } = useWindowDimensions();
  const [zoom, setZoom] = useState(MIN_ZOOM);

  const viewportWidth = Math.max(280, width - 32);
  const viewportHeight = Math.max(280, height - 170);
  const scaledWidth = viewportWidth * zoom;
  const scaledHeight = viewportHeight * zoom;

  function changeZoom(nextZoom: number) {
    setZoom(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom)));
  }

  function closeViewer() {
    setZoom(MIN_ZOOM);
    onClose();
  }

  return (
    <Modal
      animationType="fade"
      onRequestClose={closeViewer}
      statusBarTranslucent
      transparent
      visible={visible && Boolean(uri)}
    >
      <SafeAreaView accessibilityViewIsModal style={styles.backdrop}>
        <View style={styles.header}>
          <Text style={styles.title}>{accessibilityLabel}</Text>
          <Pressable accessibilityLabel="Fechar imagem" onPress={closeViewer} style={styles.iconButton}>
            <Ionicons color="#FFFFFF" name="close" size={26} />
          </Pressable>
        </View>

        <ScrollView
          contentContainerStyle={styles.verticalContent}
          maximumZoomScale={MAX_ZOOM}
          minimumZoomScale={MIN_ZOOM}
          showsVerticalScrollIndicator
          style={styles.viewer}
        >
          <ScrollView horizontal showsHorizontalScrollIndicator>
            <Image
              accessibilityLabel={accessibilityLabel}
              cachePolicy="memory"
              contentFit="contain"
              source={uri ? { uri } : undefined}
              style={{ height: scaledHeight, width: scaledWidth }}
            />
          </ScrollView>
        </ScrollView>

        <View style={styles.controls}>
          <Pressable
            accessibilityLabel="Diminuir zoom"
            disabled={zoom <= MIN_ZOOM}
            onPress={() => changeZoom(zoom - ZOOM_STEP)}
            style={[styles.controlButton, zoom <= MIN_ZOOM && styles.disabled]}
          >
            <Ionicons color="#FFFFFF" name="remove" size={22} />
          </Pressable>
          <Pressable accessibilityLabel="Restaurar zoom" onPress={() => changeZoom(MIN_ZOOM)} style={styles.zoomValue}>
            <Text style={styles.zoomText}>{Math.round(zoom * 100)}%</Text>
          </Pressable>
          <Pressable
            accessibilityLabel="Aumentar zoom"
            disabled={zoom >= MAX_ZOOM}
            onPress={() => changeZoom(zoom + ZOOM_STEP)}
            style={[styles.controlButton, zoom >= MAX_ZOOM && styles.disabled]}
          >
            <Ionicons color="#FFFFFF" name="add" size={22} />
          </Pressable>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { backgroundColor: "rgba(0,0,0,0.96)", flex: 1 },
  controlButton: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.16)",
    borderRadius: 22,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  controls: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    justifyContent: "center",
    paddingBottom: 10,
    paddingTop: 8,
  },
  disabled: { opacity: 0.35 },
  header: {
    alignItems: "center",
    flexDirection: "row",
    minHeight: 58,
    paddingHorizontal: 16,
  },
  iconButton: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.14)",
    borderRadius: 22,
    height: 44,
    justifyContent: "center",
    width: 44,
  },
  title: { color: "#FFFFFF", flex: 1, fontSize: 14, fontWeight: "800" },
  verticalContent: { alignItems: "center", justifyContent: "center" },
  viewer: { flex: 1 },
  zoomText: { color: "#FFFFFF", fontSize: 12, fontWeight: "900" },
  zoomValue: {
    alignItems: "center",
    backgroundColor: "rgba(255,255,255,0.12)",
    borderRadius: 18,
    justifyContent: "center",
    minWidth: 74,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
});
