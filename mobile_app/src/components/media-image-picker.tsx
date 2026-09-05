import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { showStaffAlert } from "@/components/staff-panel-ui";
import { colors, radius } from "@/constants/theme";
import { prepareImageForUpload, type PreparedImageUpload } from "@/services/media-upload";

type MediaImagePickerProps = {
  disabled?: boolean;
  hint: string;
  label: string;
  onChange: (image: PreparedImageUpload | null) => void;
  value: PreparedImageUpload | null;
};

export function MediaImagePicker({ disabled = false, hint, label, onChange, value }: MediaImagePickerProps) {
  async function select(source: "camera" | "library") {
    const permission = source === "camera"
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (Platform.OS !== "web" && !permission.granted) {
      showStaffAlert(
        "Permissao necessaria",
        source === "camera"
          ? "Permita o acesso a camera para registrar a imagem."
          : "Permita o acesso a galeria para escolher a imagem.",
      );
      return;
    }

    const result = source === "camera"
      ? await ImagePicker.launchCameraAsync({ allowsEditing: true, mediaTypes: ["images"], quality: 0.85 })
      : await ImagePicker.launchImageLibraryAsync({ allowsEditing: true, mediaTypes: ["images"], quality: 0.85 });
    if (result.canceled) return;
    try {
      onChange(await prepareImageForUpload(result.assets[0]));
    } catch (error) {
      showStaffAlert(
        "Imagem nao permitida",
        error instanceof Error ? error.message : "Escolha uma imagem JPEG, PNG ou WebP de ate 5 MB.",
      );
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.hint}>{hint}</Text>
      {value ? (
        <Image contentFit="cover" source={{ uri: value.asset.uri }} style={styles.preview} transition={120} />
      ) : null}
      <View style={styles.actions}>
        <Pressable disabled={disabled} onPress={() => void select("library")} style={[styles.button, disabled && styles.disabled]}>
          <Ionicons color={colors.primary} name="images-outline" size={18} />
          <Text style={styles.buttonText}>Galeria</Text>
        </Pressable>
        <Pressable disabled={disabled} onPress={() => void select("camera")} style={[styles.button, disabled && styles.disabled]}>
          <Ionicons color={colors.primary} name="camera-outline" size={18} />
          <Text style={styles.buttonText}>Camera</Text>
        </Pressable>
        {value ? (
          <Pressable disabled={disabled} onPress={() => onChange(null)} style={[styles.button, disabled && styles.disabled]}>
            <Ionicons color={colors.danger} name="close-circle-outline" size={18} />
            <Text style={[styles.buttonText, styles.removeText]}>Remover</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  button: { alignItems: "center", borderColor: colors.border, borderRadius: radius.small, borderWidth: 1, flexDirection: "row", gap: 6, paddingHorizontal: 12, paddingVertical: 9 },
  buttonText: { color: colors.primary, fontSize: 13, fontWeight: "700" },
  container: { gap: 8 },
  disabled: { opacity: 0.55 },
  hint: { color: colors.textMuted, fontSize: 12, lineHeight: 18 },
  label: { color: colors.text, fontSize: 14, fontWeight: "700" },
  preview: { backgroundColor: colors.cream, borderRadius: radius.small, height: 150, width: "100%" },
  removeText: { color: colors.danger },
});
