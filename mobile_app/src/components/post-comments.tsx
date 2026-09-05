import { Ionicons } from "@expo/vector-icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { confirmStaffAction } from "@/components/staff-panel-ui";
import { colors, radius } from "@/constants/theme";
import {
  createPostComment,
  deletePostComment,
  listPostComments,
  setPostCommentLiked,
  updatePostComment,
  type PostComment,
} from "@/security/trq-bec/service";

type PostCommentsProps = {
  expanded: boolean;
  onOpenProfile: (profileId: string) => void;
  postId: string;
};

function formatCommentDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  });
}

function commentError(error: unknown) {
  return error instanceof Error ? error.message : "Não foi possível atualizar os comentários.";
}

export function PostComments({
  expanded,
  onOpenProfile,
  postId,
}: PostCommentsProps) {
  const [comments, setComments] = useState<PostComment[]>([]);
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<PostComment | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [updatingLikeId, setUpdatingLikeId] = useState("");
  const [editingCommentId, setEditingCommentId] = useState("");
  const [editDraft, setEditDraft] = useState("");
  const [mutatingCommentId, setMutatingCommentId] = useState("");

  const loadComments = useCallback(async (silent = false) => {
    if (!postId) return;
    if (!silent) setIsLoading(true);
    try {
      const loaded = await listPostComments(postId);
      setComments(loaded);
      setError("");
    } catch (loadError) {
      if (!silent) setError(commentError(loadError));
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, [postId]);

  useEffect(() => {
    if (!expanded) return undefined;
    const initialLoad = setTimeout(() => void loadComments(), 0);
    const timer = setInterval(() => void loadComments(true), 20_000);
    return () => {
      clearTimeout(initialLoad);
      clearInterval(timer);
    };
  }, [expanded, loadComments]);

  const repliesByParent = useMemo(() => {
    const result = new Map<string, PostComment[]>();
    comments.forEach((comment) => {
      if (!comment.parent_comment_id) return;
      const replies = result.get(comment.parent_comment_id) || [];
      replies.push(comment);
      result.set(comment.parent_comment_id, replies);
    });
    return result;
  }, [comments]);

  const rootComments = useMemo(
    () => comments.filter((comment) => !comment.parent_comment_id),
    [comments],
  );

  async function submitComment() {
    const content = draft.trim();
    if (!content || isSending) return;
    setIsSending(true);
    setError("");
    try {
      const saved = await createPostComment(
        postId,
        content,
        replyTo?.parent_comment_id || replyTo?.comment_id,
      );
      setComments((current) => [...current.filter((item) => item.comment_id !== saved.comment_id), saved]);
      setDraft("");
      setReplyTo(null);
    } catch (sendError) {
      setError(commentError(sendError));
    } finally {
      setIsSending(false);
    }
  }

  async function toggleLike(comment: PostComment) {
    if (updatingLikeId) return;
    setUpdatingLikeId(comment.comment_id);
    setError("");
    try {
      const result = await setPostCommentLiked(comment.comment_id, !comment.liked_by_me);
      setComments((current) => current.map((item) => (
        item.comment_id === result.comment_id
          ? { ...item, liked_by_me: result.liked, like_count: result.like_count }
          : item
      )));
    } catch (likeError) {
      setError(commentError(likeError));
    } finally {
      setUpdatingLikeId("");
    }
  }

  function beginEdit(comment: PostComment) {
    setEditingCommentId(comment.comment_id);
    setEditDraft(comment.content);
    setError("");
  }

  async function saveCommentEdit(comment: PostComment) {
    const content = editDraft.trim();
    if (!content || mutatingCommentId) return;
    setMutatingCommentId(comment.comment_id);
    setError("");
    try {
      const saved = await updatePostComment(comment.comment_id, content);
      setComments((current) => current.map((item) => (
        item.comment_id === saved.comment_id ? saved : item
      )));
      setEditingCommentId("");
      setEditDraft("");
    } catch (updateError) {
      setError(commentError(updateError));
    } finally {
      setMutatingCommentId("");
    }
  }

  async function removeComment(comment: PostComment) {
    if (mutatingCommentId) return;
    const hasReplies = comments.some((item) => item.parent_comment_id === comment.comment_id);
    const confirmed = await confirmStaffAction(
      "Excluir comentário?",
      hasReplies
        ? "O comentário e suas respostas vinculadas serão removidos. Esta ação não pode ser desfeita."
        : "O comentário será removido. Esta ação não pode ser desfeita.",
      "Excluir",
      true,
    );
    if (!confirmed) return;
    setMutatingCommentId(comment.comment_id);
    setError("");
    try {
      await deletePostComment(comment.comment_id);
      setComments((current) => current.filter((item) => (
        item.comment_id !== comment.comment_id
        && item.parent_comment_id !== comment.comment_id
      )));
      if (
        replyTo?.comment_id === comment.comment_id
        || replyTo?.parent_comment_id === comment.comment_id
      ) {
        setReplyTo(null);
      }
      if (editingCommentId === comment.comment_id) {
        setEditingCommentId("");
        setEditDraft("");
      }
    } catch (deleteError) {
      setError(commentError(deleteError));
    } finally {
      setMutatingCommentId("");
    }
  }

  if (!expanded) return null;

  function renderComment(comment: PostComment, reply = false) {
    return (
      <View key={comment.comment_id} style={[styles.comment, reply && styles.reply]}>
        <View style={styles.commentHeader}>
          <Pressable onPress={() => onOpenProfile(comment.author.firebase_uid)} style={styles.authorButton}>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{comment.author.display_name.slice(0, 2).toUpperCase()}</Text>
            </View>
            <View style={styles.authorText}>
              <Text numberOfLines={1} style={styles.authorName}>{comment.author.display_name}</Text>
              <Text style={styles.date}>{formatCommentDate(comment.created_at)}</Text>
            </View>
          </Pressable>
        </View>
        {editingCommentId === comment.comment_id ? (
          <View style={styles.editBox}>
            <TextInput
              accessibilityLabel="Editar comentário"
              editable={mutatingCommentId !== comment.comment_id}
              maxLength={1_000}
              multiline
              onChangeText={setEditDraft}
              style={styles.editInput}
              value={editDraft}
            />
            <View style={styles.editActions}>
              <Pressable
                disabled={mutatingCommentId === comment.comment_id}
                onPress={() => {
                  setEditingCommentId("");
                  setEditDraft("");
                }}
                style={styles.smallAction}
              >
                <Text style={styles.smallActionText}>Cancelar</Text>
              </Pressable>
              <Pressable
                disabled={!editDraft.trim() || mutatingCommentId === comment.comment_id}
                onPress={() => void saveCommentEdit(comment)}
                style={styles.editSave}
              >
                {mutatingCommentId === comment.comment_id
                  ? <ActivityIndicator color={colors.surface} size="small" />
                  : <Ionicons color={colors.surface} name="checkmark" size={14} />}
                <Text style={styles.editSaveText}>Salvar</Text>
              </Pressable>
            </View>
          </View>
        ) : (
          <Text style={styles.content}>
            {comment.content}
            {comment.updated_at ? <Text style={styles.editedText}> · editado</Text> : null}
          </Text>
        )}
        <View style={styles.commentActions}>
          <Pressable
            disabled={updatingLikeId === comment.comment_id}
            onPress={() => void toggleLike(comment)}
            style={styles.smallAction}
          >
            <Ionicons
              color={comment.liked_by_me ? colors.danger : colors.primary}
              name={comment.liked_by_me ? "heart" : "heart-outline"}
              size={15}
            />
            <Text style={[styles.smallActionText, comment.liked_by_me && styles.likedText]}>
              {comment.like_count > 0 ? comment.like_count : "Curtir"}
            </Text>
          </Pressable>
          <Pressable onPress={() => setReplyTo(comment)} style={styles.smallAction}>
            <Ionicons color={colors.primary} name="return-down-forward-outline" size={15} />
            <Text style={styles.smallActionText}>Responder</Text>
          </Pressable>
          {comment.mine && editingCommentId !== comment.comment_id ? (
            <>
              <Pressable onPress={() => beginEdit(comment)} style={styles.smallAction}>
                <Ionicons color={colors.primary} name="create-outline" size={15} />
                <Text style={styles.smallActionText}>Editar</Text>
              </Pressable>
              <Pressable
                disabled={mutatingCommentId === comment.comment_id}
                onPress={() => void removeComment(comment)}
                style={styles.smallAction}
              >
                {mutatingCommentId === comment.comment_id
                  ? <ActivityIndicator color={colors.danger} size="small" />
                  : <Ionicons color={colors.danger} name="trash-outline" size={15} />}
                <Text style={styles.deleteActionText}>Excluir</Text>
              </Pressable>
            </>
          ) : null}
        </View>
      </View>
    );
  }

  return (
    <View style={styles.panel}>
      <View style={styles.panelHeader}>
        <Text style={styles.title}>Comentários</Text>
        <Pressable accessibilityLabel="Atualizar comentários" onPress={() => void loadComments()} style={styles.refresh}>
          <Ionicons color={colors.primary} name="refresh" size={17} />
        </Pressable>
      </View>

      {isLoading ? <ActivityIndicator color={colors.primary} style={styles.loading} /> : null}
      {!isLoading && rootComments.length === 0 ? (
        <Text style={styles.empty}>Seja a primeira pessoa a comentar.</Text>
      ) : null}
      {rootComments.map((comment) => (
        <View key={comment.comment_id}>
          {renderComment(comment)}
          {(repliesByParent.get(comment.comment_id) || []).map((reply) => renderComment(reply, true))}
        </View>
      ))}

      {replyTo ? (
        <View style={styles.replyingTo}>
          <Text numberOfLines={1} style={styles.replyingText}>Respondendo a {replyTo.author.display_name}</Text>
          <Pressable accessibilityLabel="Cancelar resposta" onPress={() => setReplyTo(null)}>
            <Ionicons color={colors.danger} name="close-circle" size={19} />
          </Pressable>
        </View>
      ) : null}
      <View style={styles.composer}>
        <TextInput
          accessibilityLabel={replyTo ? "Escrever resposta" : "Escrever comentário"}
          editable={!isSending}
          maxLength={1_000}
          multiline
          onChangeText={setDraft}
          placeholder={replyTo ? "Escreva sua resposta..." : "Escreva um comentário..."}
          placeholderTextColor={colors.textMuted}
          style={styles.input}
          value={draft}
        />
        <Pressable
          accessibilityLabel={replyTo ? "Enviar resposta" : "Enviar comentário"}
          disabled={isSending || !draft.trim()}
          onPress={() => void submitComment()}
          style={[styles.send, (isSending || !draft.trim()) && styles.disabled]}
        >
          {isSending
            ? <ActivityIndicator color={colors.surface} size="small" />
            : <Ionicons color={colors.surface} name="send" size={17} />}
        </Pressable>
      </View>
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  authorButton: { alignItems: "center", flex: 1, flexDirection: "row", gap: 8 },
  authorName: { color: colors.primaryDark, fontSize: 11, fontWeight: "900" },
  authorText: { flex: 1, minWidth: 0 },
  avatar: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 17, height: 34, justifyContent: "center", width: 34 },
  avatarText: { color: colors.primaryDark, fontSize: 10, fontWeight: "900" },
  comment: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, marginTop: 8, padding: 10 },
  commentActions: { flexDirection: "row", flexWrap: "wrap", gap: 14, marginTop: 7 },
  commentHeader: { alignItems: "center", flexDirection: "row" },
  composer: { alignItems: "flex-end", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 8, marginTop: 10, padding: 7 },
  content: { color: colors.text, fontSize: 12, lineHeight: 18, marginTop: 7 },
  date: { color: colors.textMuted, fontSize: 8, marginTop: 1 },
  disabled: { opacity: 0.45 },
  deleteActionText: { color: colors.danger, fontSize: 9, fontWeight: "800" },
  editActions: { alignItems: "center", flexDirection: "row", gap: 12, justifyContent: "flex-end", marginTop: 7 },
  editBox: { marginTop: 7 },
  editedText: { color: colors.textMuted, fontSize: 9, fontStyle: "italic" },
  editInput: { backgroundColor: colors.surfaceMuted, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, color: colors.text, fontSize: 12, minHeight: 64, padding: 8, textAlignVertical: "top" },
  editSave: { alignItems: "center", backgroundColor: colors.success, borderRadius: 999, flexDirection: "row", gap: 5, minHeight: 32, paddingHorizontal: 12 },
  editSaveText: { color: colors.surface, fontSize: 9, fontWeight: "900" },
  empty: { color: colors.textMuted, fontSize: 11, fontStyle: "italic", marginVertical: 10 },
  error: { color: colors.danger, fontSize: 10, lineHeight: 15, marginTop: 7 },
  input: { color: colors.text, flex: 1, fontSize: 12, maxHeight: 100, minHeight: 38, paddingHorizontal: 7, paddingVertical: 8 },
  likedText: { color: colors.danger },
  loading: { marginVertical: 12 },
  panel: { borderTopColor: colors.border, borderTopWidth: 1, marginTop: 10, paddingTop: 10 },
  panelHeader: { alignItems: "center", flexDirection: "row" },
  refresh: { alignItems: "center", height: 32, justifyContent: "center", width: 32 },
  reply: { backgroundColor: colors.surfaceMuted, marginLeft: 28 },
  replyingText: { color: colors.primaryDark, flex: 1, fontSize: 10, fontWeight: "700" },
  replyingTo: { alignItems: "center", backgroundColor: colors.cream, borderRadius: radius.medium, flexDirection: "row", gap: 8, marginTop: 10, paddingHorizontal: 10, paddingVertical: 7 },
  send: { alignItems: "center", backgroundColor: colors.accent, borderRadius: 20, height: 40, justifyContent: "center", width: 40 },
  smallAction: { alignItems: "center", flexDirection: "row", gap: 4 },
  smallActionText: { color: colors.primary, fontSize: 9, fontWeight: "800" },
  title: { color: colors.primaryDark, flex: 1, fontSize: 12, fontWeight: "900" },
});
