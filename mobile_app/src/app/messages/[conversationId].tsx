import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { Redirect, router, type Href, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { ProtectedMediaImage } from "@/components/protected-media-image";
import { HeaderBackButton } from "@/components/header-back-button";
import { LoadingScreen } from "@/components/ui";
import { colors, radius, shadow } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import {
  blockMessageProfile,
  createClientMessageId,
  getMessageConversation,
  markMessageConversationRead,
  replyToMessageConversation,
  unblockMessageProfile,
  type MessageConversationDetail,
  type PrivateMessage,
} from "@/security/trq-bec/service";
import {
  prepareImageForUpload,
  uploadImage,
  type PreparedImageUpload,
} from "@/services/media-upload";
import { getAuthenticatedHomeDestination } from "@/utils/account-navigation";

type PendingMessageImage = PreparedImageUpload & {
  mediaId?: string;
};

function formatMessageTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  }).format(date);
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Não foi possível atualizar esta conversa.";
}

type BlockAction = "block" | "unblock" | null;

export default function MessageConversationScreen() {
  const params = useLocalSearchParams<{ conversationId?: string | string[] }>();
  const conversationId = Array.isArray(params.conversationId) ? params.conversationId[0] : params.conversationId || "";
  const {
    accessDestination,
    accessSession,
    deviceApprovalRequired,
    hasFirebaseSession,
    isAuthenticated,
    isHydrated,
    isResolvingAccess,
    profile,
    refreshUnreadMessageCount,
  } = useApp();
  const profileDestination = getAuthenticatedHomeDestination(accessSession?.role, accessDestination);
  const [detail, setDetail] = useState<MessageConversationDetail | null>(null);
  const [draft, setDraft] = useState("");
  const [pendingImage, setPendingImage] = useState<PendingMessageImage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [isUpdatingBlock, setIsUpdatingBlock] = useState(false);
  const [error, setError] = useState("");
  const [sendError, setSendError] = useState("");
  const [blockAction, setBlockAction] = useState<BlockAction>(null);
  const pendingMessageIdRef = useRef("");
  const scrollRef = useRef<ScrollView>(null);
  const isMountedRef = useRef(false);
  const activeConversationIdRef = useRef(conversationId);
  const screenVersionRef = useRef(0);
  const loadRequestIdRef = useRef(0);
  const canUseConversationRoute = isAuthenticated
    && (accessSession?.role === "entrepreneur" || accessSession?.role === "visitor")
    && (accessSession.role === "visitor" || !deviceApprovalRequired);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      screenVersionRef.current += 1;
      loadRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    activeConversationIdRef.current = conversationId;
    screenVersionRef.current += 1;
    loadRequestIdRef.current += 1;
    pendingMessageIdRef.current = "";
    const resetTimer = setTimeout(() => {
      if (!isMountedRef.current || activeConversationIdRef.current !== conversationId) return;
      setDetail(null);
      setDraft("");
      setPendingImage(null);
      setError("");
      setSendError("");
      setBlockAction(null);
      setIsLoading(Boolean(conversationId));
      setIsSending(false);
      setIsUpdatingBlock(false);
    }, 0);
    return () => clearTimeout(resetTimer);
  }, [conversationId]);

  const loadConversation = useCallback(async (silent = false) => {
    if (!conversationId || !canUseConversationRoute) return;
    const requestedConversationId = conversationId;
    const screenVersion = screenVersionRef.current;
    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;
    const isCurrentRequest = () => isMountedRef.current
      && activeConversationIdRef.current === requestedConversationId
      && screenVersionRef.current === screenVersion
      && loadRequestIdRef.current === requestId;
    if (!silent && isCurrentRequest()) {
      setIsLoading(true);
      setError("");
    }
    try {
      const nextDetail = await getMessageConversation(requestedConversationId);
      if (!isCurrentRequest()) return;
      setDetail((current) => mergeConversationDetails(current, nextDetail));
      if (nextDetail.conversation.unread_count > 0) {
        await markMessageConversationRead(requestedConversationId);
        if (!isCurrentRequest()) return;
        setDetail((current) => current?.conversation.conversation_id === requestedConversationId ? {
          ...current,
          conversation: { ...current.conversation, unread_count: 0 },
        } : current);
        await refreshUnreadMessageCount();
      }
    } catch (loadError) {
      if (!silent && isCurrentRequest()) setError(errorMessage(loadError));
    } finally {
      if (isCurrentRequest()) setIsLoading(false);
    }
  }, [canUseConversationRoute, conversationId, refreshUnreadMessageCount]);

  useFocusEffect(useCallback(() => {
    loadConversation().catch(() => undefined);
    return () => {
      loadRequestIdRef.current += 1;
    };
  }, [loadConversation]));

  useEffect(() => {
    if (!conversationId || !canUseConversationRoute) return undefined;
    const timer = setInterval(() => {
      loadConversation(true).catch(() => undefined);
    }, 15_000);
    return () => clearInterval(timer);
  }, [canUseConversationRoute, conversationId, loadConversation]);

  async function sendMessage() {
    const content = draft.trim();
    if ((!content && !pendingImage) || isSending || !detail?.conversation.can_message) return;
    const requestedConversationId = conversationId;
    const screenVersion = screenVersionRef.current;
    const isCurrentScreen = () => isMountedRef.current
      && activeConversationIdRef.current === requestedConversationId
      && screenVersionRef.current === screenVersion;
    if (!pendingMessageIdRef.current) pendingMessageIdRef.current = createClientMessageId();
    const clientMessageId = pendingMessageIdRef.current;
    setIsSending(true);
    setSendError("");
    try {
      let mediaId = pendingImage?.mediaId;
      if (pendingImage && !mediaId) {
        const asset = await uploadImage(pendingImage, {
          entityId: requestedConversationId,
          entityType: "support",
          mediaRole: "support_attachment",
        });
        if (["deleted", "orphaned", "quarantined", "rejected"].includes(asset.status)) {
          throw new Error("O backend recusou a imagem selecionada.");
        }
        mediaId = asset.media_id;
        setPendingImage((current) => current?.clientRequestId === pendingImage.clientRequestId
          ? { ...current, mediaId: asset.media_id }
          : current);
      }
      const message = await replyToMessageConversation(
        requestedConversationId,
        content || "Imagem",
        clientMessageId,
        mediaId,
      );
      if (!isCurrentScreen()) return;
      setDetail((current) => current?.conversation.conversation_id === requestedConversationId ? {
        conversation: {
          ...current.conversation,
          last_message_at: message.created_at,
          last_message_preview: message.content,
        },
        messages: mergeMessages(current.messages, message),
      } : current);
      setDraft("");
      setPendingImage(null);
      pendingMessageIdRef.current = "";
      requestAnimationFrame(() => {
        if (isCurrentScreen()) scrollRef.current?.scrollToEnd({ animated: true });
      });
    } catch (messageError) {
      if (isCurrentScreen()) setSendError(errorMessage(messageError));
    } finally {
      if (isCurrentScreen()) setIsSending(false);
    }
  }

  async function pickMessageImage() {
    if (Platform.OS !== "web") {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setSendError("Permita o acesso à galeria para escolher uma imagem.");
        return;
      }
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.85,
    });
    if (result.canceled) return;
    try {
      setPendingImage(await prepareImageForUpload(result.assets[0]));
      setSendError("");
      pendingMessageIdRef.current = "";
    } catch (imageError) {
      setSendError(errorMessage(imageError));
    }
  }

  async function updateBlock() {
    if (!detail || !blockAction) return;
    const requestedConversationId = conversationId;
    const screenVersion = screenVersionRef.current;
    const isCurrentScreen = () => isMountedRef.current
      && activeConversationIdRef.current === requestedConversationId
      && screenVersionRef.current === screenVersion;
    const participantUid = detail.conversation.participant.firebase_uid;
    const requestedBlockAction = blockAction;
    setIsUpdatingBlock(true);
    setSendError("");
    try {
      if (requestedBlockAction === "block") {
        await blockMessageProfile(participantUid);
      } else {
        await unblockMessageProfile(participantUid);
      }
      if (!isCurrentScreen()) return;
      setBlockAction(null);
      await loadConversation();
    } catch (blockError) {
      if (isCurrentScreen()) setSendError(errorMessage(blockError));
    } finally {
      if (isCurrentScreen()) setIsUpdatingBlock(false);
    }
  }

  if (!isHydrated || isResolvingAccess) return <LoadingScreen />;
  if (!hasFirebaseSession) return <Redirect href={"/login" as Href} />;
  if (!isAuthenticated || accessSession?.access_state !== "AUTHORIZED") {
    return <Redirect href={"/access-pending" as Href} />;
  }
  if (deviceApprovalRequired && accessSession.role !== "visitor") {
    return <Redirect href={"/account/devices" as Href} />;
  }
  if (accessSession.role !== "entrepreneur" && accessSession.role !== "visitor") {
    return <Redirect href={accessDestination as Href} />;
  }

  const conversation = detail?.conversation;
  const composerDisabled = !conversation?.can_message
    || conversation.blocked_by_me
    || conversation.blocked_me
    || conversation.status === "RESOLVED"
    || conversation.status === "CLOSED";

  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <View style={styles.header}>
        <HeaderBackButton fallbackHref={profileDestination} />
        <Pressable
          accessibilityLabel="Abrir meu perfil"
          onPress={() => router.replace(profileDestination)}
          style={[styles.headerButton, styles.profileButton]}
        >
          <Ionicons color={colors.primaryDark} name="person-circle-outline" size={20} />
          <Text style={styles.profileButtonText}>Perfil</Text>
        </Pressable>
        <View style={styles.headerText}>
          <Text numberOfLines={1} style={styles.headerTitle}>{conversation?.participant.display_name || "Conversa"}</Text>
          <Text style={styles.headerSubtitle}>
            {conversation?.blocked_by_me ? "Perfil bloqueado" : conversation?.blocked_me ? "Mensagens indisponíveis" : "Conversa privada"}
          </Text>
        </View>
        {conversation?.kind === "DIRECT" ? (
          <Pressable
            accessibilityLabel={conversation.blocked_by_me ? "Desbloquear perfil" : "Bloquear perfil"}
            onPress={() => setBlockAction(conversation.blocked_by_me ? "unblock" : "block")}
            style={styles.headerButton}
          >
            <Ionicons color={conversation.blocked_by_me ? colors.success : colors.danger} name={conversation.blocked_by_me ? "checkmark-circle-outline" : "ban-outline"} size={22} />
          </Pressable>
        ) : <View style={styles.headerSpacer} />}
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} keyboardVerticalOffset={8} style={styles.flex}>
        {isLoading ? (
          <View style={styles.centerState}>
            <ActivityIndicator color={colors.primary} size="large" />
            <Text style={styles.stateText}>Carregando conversa...</Text>
          </View>
        ) : error ? (
          <View style={styles.centerState}>
            <Ionicons color={colors.danger} name="alert-circle-outline" size={34} />
            <Text style={styles.error}>{error}</Text>
            <Pressable onPress={() => loadConversation()} style={styles.retryButton}>
              <Text style={styles.retryButtonText}>Tentar novamente</Text>
            </Pressable>
          </View>
        ) : (
          <>
            <ScrollView
              contentContainerStyle={styles.messages}
              keyboardShouldPersistTaps="handled"
              onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: false })}
              ref={scrollRef}
            >
              {detail?.messages.length === 0 ? (
                <View style={styles.emptyThread}>
                  <Ionicons color={colors.textMuted} name="chatbubble-ellipses-outline" size={32} />
                  <Text style={styles.emptyTitle}>Início da conversa</Text>
                  <Text style={styles.stateText}>Envie uma mensagem respeitosa e evite compartilhar dados sensíveis.</Text>
                </View>
              ) : null}
              {detail?.messages.map((message) => (
                <MessageBubble currentUid={profile.id} key={message.message_id} message={message} />
              ))}
            </ScrollView>

            {conversation?.blocked_by_me ? (
              <View style={styles.blockedNotice}>
                <Ionicons color={colors.danger} name="ban-outline" size={18} />
                <Text style={styles.blockedNoticeText}>Você bloqueou este perfil. Desbloqueie para voltar a conversar.</Text>
              </View>
            ) : conversation?.blocked_me ? (
              <View style={styles.blockedNotice}>
                <Ionicons color={colors.textMuted} name="lock-closed-outline" size={18} />
                <Text style={styles.blockedNoticeText}>Não é possível enviar mensagens nesta conversa.</Text>
              </View>
            ) : conversation?.status === "RESOLVED" || conversation?.status === "CLOSED" ? (
              <View style={styles.blockedNotice}>
                <Ionicons color={colors.success} name="checkmark-circle-outline" size={18} />
                <Text style={styles.blockedNoticeText}>Este atendimento foi encerrado e permanece disponível para consulta.</Text>
              </View>
            ) : null}

            <View style={styles.composerArea}>
              {pendingImage ? (
                <View style={styles.pendingImageCard}>
                  <Image contentFit="contain" source={{ uri: pendingImage.asset.uri }} style={styles.pendingImagePreview} />
                  <View style={styles.pendingImageText}>
                    <Text numberOfLines={1} style={styles.pendingImageName}>{pendingImage.originalFilename}</Text>
                    <Text style={styles.pendingImageHint}>A imagem será privada nesta conversa.</Text>
                  </View>
                  <Pressable
                    accessibilityLabel="Remover imagem"
                    disabled={isSending}
                    onPress={() => {
                      setPendingImage(null);
                      pendingMessageIdRef.current = "";
                    }}
                    style={styles.removeImageButton}
                  >
                    <Ionicons color={colors.danger} name="close" size={20} />
                  </Pressable>
                </View>
              ) : null}
              <View style={styles.composer}>
              <Pressable
                accessibilityLabel="Anexar imagem"
                disabled={composerDisabled || isSending}
                onPress={pickMessageImage}
                style={[styles.attachButton, (composerDisabled || isSending) && styles.disabledButton]}
              >
                <Ionicons color={colors.primary} name="image-outline" size={22} />
              </Pressable>
              <TextInput
                accessibilityLabel="Mensagem"
                editable={!composerDisabled && !isSending}
                maxLength={2_000}
                multiline
                onChangeText={(value) => {
                  setDraft(value);
                  setSendError("");
                  pendingMessageIdRef.current = "";
                }}
                placeholder={composerDisabled ? "Envio indisponível" : "Escreva uma mensagem..."}
                placeholderTextColor={colors.textMuted}
                style={styles.input}
                textAlignVertical="top"
                value={draft}
              />
              <Pressable
                accessibilityLabel="Enviar mensagem"
                disabled={composerDisabled || isSending || (!draft.trim() && !pendingImage)}
                onPress={sendMessage}
                style={[styles.sendButton, (composerDisabled || isSending || (!draft.trim() && !pendingImage)) && styles.disabledButton]}
              >
                {isSending ? <ActivityIndicator color={colors.surface} /> : <Ionicons color={colors.surface} name="send" size={20} />}
              </Pressable>
              </View>
            </View>
            {sendError ? <Text style={styles.composerError}>{sendError}</Text> : null}
          </>
        )}
      </KeyboardAvoidingView>

      <Modal animationType="fade" onRequestClose={() => setBlockAction(null)} transparent visible={Boolean(blockAction)}>
        <View style={styles.modalBackdrop}>
          <View accessibilityViewIsModal style={styles.modalCard}>
            <View style={[styles.modalIcon, blockAction === "unblock" && styles.modalIconSuccess]}>
              <Ionicons color={colors.surface} name={blockAction === "unblock" ? "checkmark" : "ban"} size={24} />
            </View>
            <Text style={styles.modalTitle}>{blockAction === "unblock" ? "Desbloquear perfil?" : "Bloquear remetente?"}</Text>
            <Text style={styles.modalText}>
              {blockAction === "unblock"
                ? `${conversation?.participant.display_name || "Este perfil"} poderá voltar a enviar mensagens para você.`
                : `${conversation?.participant.display_name || "Este perfil"} não poderá enviar novas mensagens. Você poderá desfazer isso depois.`}
            </Text>
            <View style={styles.modalActions}>
              <Pressable disabled={isUpdatingBlock} onPress={() => setBlockAction(null)} style={styles.modalSecondary}>
                <Text style={styles.modalSecondaryText}>Cancelar</Text>
              </Pressable>
              <Pressable disabled={isUpdatingBlock} onPress={updateBlock} style={[styles.modalPrimary, blockAction === "block" && styles.modalDanger]}>
                <Text style={styles.modalPrimaryText}>{isUpdatingBlock ? "Salvando..." : blockAction === "unblock" ? "Desbloquear" : "Bloquear"}</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const MESSAGE_STATUS_RANK: Record<PrivateMessage["status"], number> = {
  DELIVERED: 2,
  READ: 3,
  SENT: 1,
};

function mergeMessages(current: PrivateMessage[], incoming: PrivateMessage | PrivateMessage[]) {
  const byId = new Map(current.map((message) => [message.message_id, message]));
  const incomingMessages = Array.isArray(incoming) ? incoming : [incoming];
  incomingMessages.forEach((message) => {
    const previous = byId.get(message.message_id);
    if (!previous) {
      byId.set(message.message_id, message);
      return;
    }
    const status = MESSAGE_STATUS_RANK[previous.status] > MESSAGE_STATUS_RANK[message.status]
      ? previous.status
      : message.status;
    byId.set(message.message_id, {
      ...previous,
      ...message,
      mine: previous.mine || message.mine,
      read_at: message.read_at || previous.read_at,
      status,
    });
  });
  return [...byId.values()].sort((left, right) => {
    const timeDifference = Date.parse(left.created_at) - Date.parse(right.created_at);
    return Number.isNaN(timeDifference) ? left.message_id.localeCompare(right.message_id) : timeDifference;
  });
}

function mergeConversationDetails(
  current: MessageConversationDetail | null,
  incoming: MessageConversationDetail,
): MessageConversationDetail {
  if (!current || current.conversation.conversation_id !== incoming.conversation.conversation_id) return incoming;
  const messages = mergeMessages(current.messages, incoming.messages);
  const currentLastMessageAt = current.conversation.last_message_at
    ? Date.parse(current.conversation.last_message_at)
    : Number.NEGATIVE_INFINITY;
  const incomingLastMessageAt = incoming.conversation.last_message_at
    ? Date.parse(incoming.conversation.last_message_at)
    : Number.NEGATIVE_INFINITY;
  const keepCurrentLastMessage = currentLastMessageAt > incomingLastMessageAt;
  return {
    conversation: {
      ...incoming.conversation,
      last_message_at: keepCurrentLastMessage
        ? current.conversation.last_message_at
        : incoming.conversation.last_message_at,
      last_message_preview: keepCurrentLastMessage
        ? current.conversation.last_message_preview
        : incoming.conversation.last_message_preview,
    },
    messages,
  };
}

function MessageBubble({ currentUid, message }: { currentUid: string; message: PrivateMessage }) {
  const isOwn = message.mine || message.sender_uid === currentUid;
  return (
    <View style={[styles.messageRow, isOwn && styles.messageRowOwn]}>
      <View style={[styles.bubble, isOwn && styles.bubbleOwn]}>
        {message.media_id ? (
          <ProtectedMediaImage
            contentFit="contain"
            expandable
            mediaId={message.media_id}
            style={styles.messageImage}
            viewerLabel={`Imagem enviada por ${message.sender.display_name}`}
          />
        ) : null}
        {message.content !== "Imagem" || !message.media_id ? (
          <Text style={[styles.messageText, isOwn && styles.messageTextOwn]}>{message.content}</Text>
        ) : null}
        <View style={styles.messageMetaRow}>
          <Text style={[styles.messageTime, isOwn && styles.messageTimeOwn]}>{formatMessageTime(message.created_at)}</Text>
          {isOwn ? (
            <Ionicons
              color={message.status === "READ" ? colors.accentSoft : "rgba(255,255,255,0.65)"}
              name={message.status === "SENT" ? "checkmark" : "checkmark-done"}
              size={13}
            />
          ) : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.background, flex: 1 },
  flex: { flex: 1 },
  header: { alignItems: "center", backgroundColor: colors.cream, borderBottomColor: colors.border, borderBottomWidth: 1, flexDirection: "row", gap: 12, minHeight: 70, paddingHorizontal: 16 },
  headerButton: { alignItems: "center", backgroundColor: colors.surface, borderRadius: 22, height: 44, justifyContent: "center", width: 44 },
  profileButton: { flexDirection: "row", gap: 5, paddingHorizontal: 10, width: "auto" },
  profileButtonText: { color: colors.primaryDark, fontSize: 11, fontWeight: "900" },
  headerSpacer: { height: 44, width: 44 },
  headerText: { flex: 1 },
  headerTitle: { color: colors.primaryDark, fontSize: 16, fontWeight: "900" },
  headerSubtitle: { color: colors.textMuted, fontSize: 10, marginTop: 2 },
  centerState: { alignItems: "center", flex: 1, gap: 12, justifyContent: "center", padding: 28 },
  stateText: { color: colors.textMuted, fontSize: 12, lineHeight: 17, maxWidth: 360, textAlign: "center" },
  error: { color: colors.danger, fontSize: 12, lineHeight: 17, maxWidth: 420, textAlign: "center" },
  retryButton: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 17, paddingVertical: 10 },
  retryButtonText: { color: colors.surface, fontSize: 11, fontWeight: "900" },
  messages: { alignSelf: "center", flexGrow: 1, justifyContent: "flex-end", maxWidth: 900, padding: 16, width: "100%" },
  emptyThread: { alignItems: "center", gap: 8, paddingVertical: 36 },
  emptyTitle: { color: colors.primaryDark, fontSize: 15, fontWeight: "900" },
  messageRow: { alignItems: "flex-start", marginVertical: 4 },
  messageRowOwn: { alignItems: "flex-end" },
  bubble: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderTopLeftRadius: 5, borderWidth: 1, maxWidth: "82%", paddingHorizontal: 13, paddingVertical: 9, ...shadow },
  bubbleOwn: { backgroundColor: colors.primary, borderColor: colors.primary, borderTopLeftRadius: 18, borderTopRightRadius: 5 },
  messageText: { color: colors.text, fontSize: 14, lineHeight: 20 },
  messageTextOwn: { color: colors.surface },
  messageMetaRow: { alignItems: "center", alignSelf: "flex-end", flexDirection: "row", gap: 4, marginTop: 4 },
  messageTime: { color: colors.textMuted, fontSize: 8 },
  messageTimeOwn: { color: "rgba(255,255,255,0.7)" },
  blockedNotice: { alignItems: "center", alignSelf: "center", backgroundColor: colors.surfaceMuted, borderRadius: radius.medium, flexDirection: "row", gap: 9, marginBottom: 8, maxWidth: 868, padding: 11, width: "94%" },
  blockedNoticeText: { color: colors.textMuted, flex: 1, fontSize: 11, lineHeight: 16 },
  composerArea: { alignSelf: "center", maxWidth: 900, width: "100%" },
  composer: { alignItems: "flex-end", alignSelf: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.large, borderWidth: 1, flexDirection: "row", gap: 10, marginBottom: 8, maxWidth: 900, padding: 8, width: "96%", ...shadow },
  attachButton: { alignItems: "center", borderRadius: 22, height: 44, justifyContent: "center", width: 40 },
  input: { color: colors.text, flex: 1, fontSize: 14, maxHeight: 130, minHeight: 42, paddingHorizontal: 9, paddingVertical: 10 },
  sendButton: { alignItems: "center", backgroundColor: colors.accent, borderRadius: 22, height: 44, justifyContent: "center", width: 44 },
  disabledButton: { opacity: 0.45 },
  composerError: { alignSelf: "center", color: colors.danger, fontSize: 10, marginBottom: 8, maxWidth: 880, paddingHorizontal: 16, width: "100%" },
  messageImage: { backgroundColor: colors.surfaceMuted, borderRadius: 12, height: 240, marginBottom: 6, maxWidth: 320, width: 260 },
  pendingImageCard: { alignItems: "center", alignSelf: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 10, marginBottom: 7, padding: 8, width: "96%" },
  pendingImageHint: { color: colors.textMuted, fontSize: 9, marginTop: 2 },
  pendingImageName: { color: colors.primaryDark, fontSize: 11, fontWeight: "800" },
  pendingImagePreview: { backgroundColor: colors.surfaceMuted, borderRadius: 8, height: 54, width: 70 },
  pendingImageText: { flex: 1, minWidth: 0 },
  removeImageButton: { alignItems: "center", borderRadius: 18, height: 36, justifyContent: "center", width: 36 },
  modalBackdrop: { alignItems: "center", backgroundColor: "rgba(15, 46, 110, 0.45)", flex: 1, justifyContent: "center", padding: 22 },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.large, maxWidth: 440, padding: 22, width: "100%", ...shadow },
  modalIcon: { alignItems: "center", backgroundColor: colors.danger, borderRadius: 24, height: 48, justifyContent: "center", width: 48 },
  modalIconSuccess: { backgroundColor: colors.success },
  modalTitle: { color: colors.primaryDark, fontSize: 20, fontWeight: "900", marginTop: 14 },
  modalText: { color: colors.text, fontSize: 13, lineHeight: 19, marginTop: 8 },
  modalActions: { flexDirection: "row", gap: 10, marginTop: 20 },
  modalSecondary: { alignItems: "center", borderColor: colors.border, borderRadius: radius.pill, borderWidth: 1, flex: 1, padding: 12 },
  modalSecondaryText: { color: colors.primaryDark, fontSize: 12, fontWeight: "800" },
  modalPrimary: { alignItems: "center", backgroundColor: colors.success, borderRadius: radius.pill, flex: 1, padding: 12 },
  modalDanger: { backgroundColor: colors.danger },
  modalPrimaryText: { color: colors.surface, fontSize: 12, fontWeight: "900" },
});
