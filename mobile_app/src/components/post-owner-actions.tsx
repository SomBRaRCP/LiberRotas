import { Ionicons } from "@expo/vector-icons";
import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { confirmStaffAction, showStaffAlert } from "@/components/staff-panel-ui";
import { colors, radius } from "@/constants/theme";
import { type FeedPost, useApp } from "@/context/app-context";

type PostOwnerActionsProps = {
  post: FeedPost;
};

function actionError(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Não foi possível atualizar a publicação.";
}

export function PostOwnerActions({ post }: PostOwnerActionsProps) {
  const { deletePost, profile, updatePost } = useApp();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(post.text);
  const [busyAction, setBusyAction] = useState<"edit" | "delete" | "">("");

  if (post.authorId !== profile.id) return null;

  async function saveEdit() {
    const text = draft.trim();
    if (!text || busyAction) return;
    setBusyAction("edit");
    try {
      await updatePost(post.id, text);
      setEditing(false);
    } catch (error) {
      showStaffAlert("Não foi possível editar", actionError(error));
    } finally {
      setBusyAction("");
    }
  }

  async function removePost() {
    if (busyAction) return;
    const confirmed = await confirmStaffAction(
      "Excluir publicação?",
      "Ela desaparecerá do Feed e seus comentários também serão removidos. Esta ação não pode ser desfeita.",
      "Excluir",
      true,
    );
    if (!confirmed) return;
    setBusyAction("delete");
    try {
      await deletePost(post.id);
    } catch (error) {
      showStaffAlert("Não foi possível excluir", actionError(error));
    } finally {
      setBusyAction("");
    }
  }

  if (editing) {
    return (
      <View style={styles.editor}>
        <Text style={styles.editorLabel}>Editar publicação</Text>
        <TextInput
          accessibilityLabel="Texto da publicação"
          editable={!busyAction}
          maxLength={2_000}
          multiline
          onChangeText={setDraft}
          style={styles.input}
          value={draft}
        />
        <View style={styles.editorActions}>
          <Pressable
            disabled={Boolean(busyAction)}
            onPress={() => setEditing(false)}
            style={styles.cancelButton}
          >
            <Text style={styles.cancelText}>Cancelar</Text>
          </Pressable>
          <Pressable
            disabled={Boolean(busyAction) || !draft.trim()}
            onPress={() => void saveEdit()}
            style={[styles.saveButton, (!draft.trim() || busyAction) && styles.disabled]}
          >
            {busyAction === "edit"
              ? <ActivityIndicator color={colors.surface} size="small" />
              : <Ionicons color={colors.surface} name="checkmark" size={16} />}
            <Text style={styles.saveText}>Salvar edição</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.actions}>
      <Pressable
        accessibilityLabel="Editar minha publicação"
        disabled={Boolean(busyAction)}
        onPress={() => {
          setDraft(post.text);
          setEditing(true);
        }}
        style={styles.actionButton}
      >
        <Ionicons color={colors.primary} name="create-outline" size={16} />
        <Text style={styles.actionText}>Editar</Text>
      </Pressable>
      <Pressable
        accessibilityLabel="Excluir minha publicação"
        disabled={Boolean(busyAction)}
        onPress={() => void removePost()}
        style={[styles.actionButton, styles.deleteButton]}
      >
        {busyAction === "delete"
          ? <ActivityIndicator color={colors.danger} size="small" />
          : <Ionicons color={colors.danger} name="trash-outline" size={16} />}
        <Text style={styles.deleteText}>Excluir</Text>
      </Pressable>
      {post.updatedAt ? <Text style={styles.editedLabel}>editada</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  actionButton: {
    alignItems: "center",
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: "row",
    gap: 5,
    minHeight: 34,
    paddingHorizontal: 11,
  },
  actionText: { color: colors.primary, fontSize: 10, fontWeight: "900" },
  actions: { alignItems: "center", flexDirection: "row", gap: 8, marginTop: 10 },
  cancelButton: { alignItems: "center", borderRadius: 999, justifyContent: "center", minHeight: 38, paddingHorizontal: 14 },
  cancelText: { color: colors.textMuted, fontSize: 11, fontWeight: "800" },
  deleteButton: { borderColor: colors.danger },
  deleteText: { color: colors.danger, fontSize: 10, fontWeight: "900" },
  disabled: { opacity: 0.45 },
  editedLabel: { color: colors.textMuted, fontSize: 9, fontStyle: "italic" },
  editor: { backgroundColor: colors.surfaceMuted, borderRadius: radius.medium, marginTop: 10, padding: 10 },
  editorActions: { flexDirection: "row", justifyContent: "flex-end", marginTop: 8 },
  editorLabel: { color: colors.primaryDark, fontSize: 11, fontWeight: "900", marginBottom: 6 },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: radius.medium,
    borderWidth: 1,
    color: colors.text,
    fontSize: 12,
    lineHeight: 18,
    minHeight: 76,
    padding: 10,
    textAlignVertical: "top",
  },
  saveButton: {
    alignItems: "center",
    backgroundColor: colors.success,
    borderRadius: 999,
    flexDirection: "row",
    gap: 6,
    justifyContent: "center",
    minHeight: 38,
    paddingHorizontal: 14,
  },
  saveText: { color: colors.surface, fontSize: 11, fontWeight: "900" },
});
