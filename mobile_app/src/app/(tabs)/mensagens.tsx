import { Ionicons } from "@expo/vector-icons";
import { router, useFocusEffect, type Href } from "expo-router";
import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { BrandHeader } from "@/components/brand-header";
import { colors, radius, shadow } from "@/constants/theme";
import { useApp } from "@/context/app-context";
import {
  blockMessageProfile,
  listBlockedProfiles,
  listMessageConversations,
  unblockMessageProfile,
  type BlockedProfile,
  type MessageConversationSummary,
} from "@/security/trq-bec/service";

function formatConversationDate(value: string | null) {
  if (!value) return "Sem mensagens";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
  }).format(date);
}

function getServiceMessage(error: unknown) {
  return error instanceof Error ? error.message : "Não foi possível carregar suas mensagens.";
}

export default function MessagesInboxScreen() {
  const { refreshUnreadMessageCount } = useApp();
  const [conversations, setConversations] = useState<MessageConversationSummary[]>([]);
  const [blockedProfiles, setBlockedProfiles] = useState<BlockedProfile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingBlocks, setIsLoadingBlocks] = useState(false);
  const [showBlockedProfiles, setShowBlockedProfiles] = useState(false);
  const [error, setError] = useState("");
  const [blocksError, setBlocksError] = useState("");
  const [pendingUnblock, setPendingUnblock] = useState<BlockedProfile | null>(null);
  const [pendingBlock, setPendingBlock] = useState<MessageConversationSummary | null>(null);
  const [isUnblocking, setIsUnblocking] = useState(false);
  const [isBlocking, setIsBlocking] = useState(false);

  const loadConversations = useCallback(async (refresh = false) => {
    if (refresh) setIsRefreshing(true);
    else setIsLoading(true);
    setError("");
    try {
      const items = await listMessageConversations();
      setConversations(items);
      await refreshUnreadMessageCount();
    } catch (loadError) {
      setError(getServiceMessage(loadError));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [refreshUnreadMessageCount]);

  useFocusEffect(useCallback(() => {
    loadConversations().catch(() => undefined);
  }, [loadConversations]));

  async function toggleBlockedProfiles() {
    const nextVisible = !showBlockedProfiles;
    setShowBlockedProfiles(nextVisible);
    if (!nextVisible) return;
    setIsLoadingBlocks(true);
    setBlocksError("");
    try {
      setBlockedProfiles(await listBlockedProfiles());
    } catch (loadError) {
      setBlocksError(getServiceMessage(loadError));
    } finally {
      setIsLoadingBlocks(false);
    }
  }

  async function confirmUnblock() {
    if (!pendingUnblock) return;
    setIsUnblocking(true);
    setBlocksError("");
    try {
      await unblockMessageProfile(pendingUnblock.profile.firebase_uid);
      setBlockedProfiles((current) => current.filter(
        (item) => item.profile.firebase_uid !== pendingUnblock.profile.firebase_uid,
      ));
      setPendingUnblock(null);
      await loadConversations(true);
    } catch (unblockError) {
      setBlocksError(getServiceMessage(unblockError));
    } finally {
      setIsUnblocking(false);
    }
  }

  async function confirmBlock() {
    if (!pendingBlock) return;
    const participantUid = pendingBlock.participant.firebase_uid;
    setIsBlocking(true);
    setError("");
    try {
      const blocked = await blockMessageProfile(participantUid);
      setConversations((current) => current.map((conversation) => (
        conversation.conversation_id === pendingBlock.conversation_id
          ? { ...conversation, blocked_by_me: true, can_message: false }
          : conversation
      )));
      setBlockedProfiles((current) => (
        current.some((item) => item.profile.firebase_uid === participantUid)
          ? current
          : [...current, blocked]
      ));
      setPendingBlock(null);
    } catch (blockError) {
      setError(getServiceMessage(blockError));
    } finally {
      setIsBlocking(false);
    }
  }

  function openConversation(conversationId: string) {
    router.push({
      pathname: "/messages/[conversationId]",
      params: { conversationId },
    } as unknown as Href);
  }

  return (
    <SafeAreaView edges={["top"]} style={styles.safeArea}>
      <BrandHeader subtitle="conversas privadas e protegidas" title="Mensagens" />
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl onRefresh={() => loadConversations(true)} refreshing={isRefreshing} />}
      >
        <View style={styles.introCard}>
          <View style={styles.introIcon}>
            <Ionicons color={colors.surface} name="chatbubbles-outline" size={24} />
          </View>
          <View style={styles.introText}>
            <Text style={styles.introTitle}>Caixa de entrada</Text>
            <Text style={styles.introDescription}>
              Suas conversas são privadas. A equipe de suporte não vê mensagens trocadas entre usuários.
            </Text>
          </View>
        </View>

        <Pressable onPress={toggleBlockedProfiles} style={styles.blockedToggle}>
          <Ionicons color={colors.primary} name="ban-outline" size={18} />
          <Text style={styles.blockedToggleText}>
            {showBlockedProfiles ? "Ocultar pessoas bloqueadas" : "Gerenciar pessoas bloqueadas"}
          </Text>
          <Ionicons color={colors.primary} name={showBlockedProfiles ? "chevron-up" : "chevron-down"} size={18} />
        </Pressable>

        {showBlockedProfiles ? (
          <View style={styles.blockedPanel}>
            {isLoadingBlocks ? <ActivityIndicator color={colors.primary} /> : null}
            {blocksError ? <Text style={styles.error}>{blocksError}</Text> : null}
            {!isLoadingBlocks && !blocksError && blockedProfiles.length === 0 ? (
              <Text style={styles.emptyText}>Você não bloqueou nenhum perfil.</Text>
            ) : null}
            {blockedProfiles.map((item) => (
              <View key={item.profile.firebase_uid} style={styles.blockedRow}>
                <View style={styles.avatarSmall}>
                  <Text style={styles.avatarSmallText}>{item.profile.display_name.slice(0, 2).toUpperCase()}</Text>
                </View>
                <View style={styles.rowText}>
                  <Text style={styles.rowTitle}>{item.profile.display_name}</Text>
                  <Text style={styles.rowMeta}>Mensagens bloqueadas</Text>
                </View>
                <Pressable onPress={() => setPendingUnblock(item)} style={styles.unblockButton}>
                  <Text style={styles.unblockButtonText}>Desbloquear</Text>
                </Pressable>
              </View>
            ))}
          </View>
        ) : null}

        <Text style={styles.sectionTitle}>Conversas</Text>
        {isLoading ? (
          <View style={styles.loadingState}>
            <ActivityIndicator color={colors.primary} size="large" />
            <Text style={styles.loadingText}>Carregando mensagens...</Text>
          </View>
        ) : null}
        {error ? (
          <View style={styles.stateCard}>
            <Ionicons color={colors.danger} name="cloud-offline-outline" size={28} />
            <Text style={styles.error}>{error}</Text>
            <Pressable onPress={() => loadConversations()} style={styles.retryButton}>
              <Text style={styles.retryButtonText}>Tentar novamente</Text>
            </Pressable>
          </View>
        ) : null}
        {!isLoading && !error && conversations.length === 0 ? (
          <View style={styles.stateCard}>
            <Ionicons color={colors.textMuted} name="mail-open-outline" size={32} />
            <Text style={styles.emptyTitle}>Nenhuma conversa ainda</Text>
            <Text style={styles.emptyText}>Abra o perfil de outra pessoa e toque em “Enviar mensagem”.</Text>
          </View>
        ) : null}

        {conversations.map((conversation) => (
          <View key={conversation.conversation_id} style={styles.conversationCard}>
            <Pressable
              accessibilityHint="Abre a conversa privada"
              accessibilityRole="button"
              onPress={() => openConversation(conversation.conversation_id)}
              style={styles.conversationOpen}
            >
              <View style={styles.avatar}>
                <Text style={styles.avatarText}>{conversation.participant.display_name.slice(0, 2).toUpperCase()}</Text>
              </View>
              <View style={styles.conversationText}>
                <View style={styles.conversationHeader}>
                  <Text numberOfLines={1} style={styles.conversationName}>{conversation.participant.display_name}</Text>
                  <Text style={styles.conversationDate}>{formatConversationDate(conversation.last_message_at)}</Text>
                </View>
                <View style={styles.previewRow}>
                  <Text numberOfLines={1} style={styles.preview}>
                    {conversation.blocked_by_me ? "Você bloqueou este perfil" : conversation.last_message_preview || "Conversa iniciada"}
                  </Text>
                  {conversation.unread_count > 0 ? (
                    <View style={styles.unreadBadge}>
                      <Text style={styles.unreadBadgeText}>{Math.min(99, conversation.unread_count)}</Text>
                    </View>
                  ) : null}
                </View>
              </View>
            </Pressable>
            {conversation.kind === "DIRECT" && !conversation.blocked_by_me ? (
              <Pressable
                accessibilityLabel={`Bloquear ${conversation.participant.display_name}`}
                onPress={() => setPendingBlock(conversation)}
                style={styles.blockButton}
              >
                <Ionicons color={colors.danger} name="ban-outline" size={16} />
                <Text style={styles.blockButtonText}>Bloquear</Text>
              </Pressable>
            ) : null}
          </View>
        ))}
      </ScrollView>

      <Modal animationType="fade" onRequestClose={() => setPendingUnblock(null)} transparent visible={Boolean(pendingUnblock)}>
        <View style={styles.modalBackdrop}>
          <View accessibilityViewIsModal style={styles.modalCard}>
            <Text style={styles.modalTitle}>Desbloquear perfil?</Text>
            <Text style={styles.modalText}>
              {pendingUnblock?.profile.display_name} poderá voltar a enviar mensagens para você.
            </Text>
            <View style={styles.modalActions}>
              <Pressable disabled={isUnblocking} onPress={() => setPendingUnblock(null)} style={styles.modalSecondary}>
                <Text style={styles.modalSecondaryText}>Cancelar</Text>
              </Pressable>
              <Pressable disabled={isUnblocking} onPress={confirmUnblock} style={styles.modalPrimary}>
                <Text style={styles.modalPrimaryText}>{isUnblocking ? "Desbloqueando..." : "Desbloquear"}</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>

      <Modal animationType="fade" onRequestClose={() => setPendingBlock(null)} transparent visible={Boolean(pendingBlock)}>
        <View style={styles.modalBackdrop}>
          <View accessibilityViewIsModal style={styles.modalCard}>
            <Text style={styles.modalTitle}>Bloquear remetente?</Text>
            <Text style={styles.modalText}>
              {pendingBlock?.participant.display_name} não poderá enviar novas mensagens para você. Esta ação pode ser desfeita depois.
            </Text>
            <View style={styles.modalActions}>
              <Pressable disabled={isBlocking} onPress={() => setPendingBlock(null)} style={styles.modalSecondary}>
                <Text style={styles.modalSecondaryText}>Cancelar</Text>
              </Pressable>
              <Pressable disabled={isBlocking} onPress={confirmBlock} style={[styles.modalPrimary, styles.modalDanger]}>
                <Text style={styles.modalPrimaryText}>{isBlocking ? "Bloqueando..." : "Bloquear"}</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.background, flex: 1 },
  content: { alignSelf: "center", maxWidth: 900, padding: 16, paddingBottom: 36, width: "100%" },
  introCard: { alignItems: "center", backgroundColor: colors.primaryDark, borderRadius: radius.large, flexDirection: "row", gap: 14, padding: 18 },
  introIcon: { alignItems: "center", backgroundColor: colors.primary, borderRadius: 24, height: 48, justifyContent: "center", width: 48 },
  introText: { flex: 1 },
  introTitle: { color: colors.surface, fontSize: 18, fontWeight: "900" },
  introDescription: { color: colors.surface, fontSize: 12, lineHeight: 17, marginTop: 4, opacity: 0.85 },
  blockedToggle: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 9, marginTop: 14, minHeight: 48, paddingHorizontal: 14 },
  blockedToggleText: { color: colors.primary, flex: 1, fontSize: 12, fontWeight: "800" },
  blockedPanel: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderTopWidth: 0, borderWidth: 1, gap: 10, padding: 12 },
  blockedRow: { alignItems: "center", flexDirection: "row", gap: 10, paddingVertical: 5 },
  avatarSmall: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 18, height: 36, justifyContent: "center", width: 36 },
  avatarSmallText: { color: colors.primaryDark, fontSize: 11, fontWeight: "900" },
  rowText: { flex: 1 },
  rowTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: "800" },
  rowMeta: { color: colors.textMuted, fontSize: 10, marginTop: 2 },
  unblockButton: { borderColor: colors.primary, borderRadius: radius.pill, borderWidth: 1, paddingHorizontal: 11, paddingVertical: 7 },
  unblockButtonText: { color: colors.primary, fontSize: 10, fontWeight: "800" },
  sectionTitle: { color: colors.primaryDark, fontSize: 18, fontWeight: "900", marginBottom: 10, marginTop: 20 },
  loadingState: { alignItems: "center", gap: 10, paddingVertical: 36 },
  loadingText: { color: colors.textMuted, fontSize: 12 },
  stateCard: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.large, borderWidth: 1, gap: 10, padding: 28 },
  emptyTitle: { color: colors.primaryDark, fontSize: 16, fontWeight: "900" },
  emptyText: { color: colors.textMuted, fontSize: 12, lineHeight: 17, textAlign: "center" },
  error: { color: colors.danger, fontSize: 12, lineHeight: 17, textAlign: "center" },
  retryButton: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 16, paddingVertical: 10 },
  retryButtonText: { color: colors.surface, fontSize: 11, fontWeight: "900" },
  conversationCard: { alignItems: "center", backgroundColor: colors.surface, borderColor: colors.border, borderRadius: radius.medium, borderWidth: 1, flexDirection: "row", gap: 8, marginBottom: 10, padding: 10, ...shadow },
  conversationOpen: { alignItems: "center", flex: 1, flexDirection: "row", gap: 12, minWidth: 0, padding: 4 },
  blockButton: { alignItems: "center", borderColor: colors.danger, borderRadius: radius.pill, borderWidth: 1, gap: 3, paddingHorizontal: 9, paddingVertical: 7 },
  blockButtonText: { color: colors.danger, fontSize: 9, fontWeight: "900" },
  avatar: { alignItems: "center", backgroundColor: colors.cream, borderRadius: 24, height: 48, justifyContent: "center", width: 48 },
  avatarText: { color: colors.primaryDark, fontSize: 13, fontWeight: "900" },
  conversationText: { flex: 1, minWidth: 0 },
  conversationHeader: { alignItems: "center", flexDirection: "row", gap: 8 },
  conversationName: { color: colors.primaryDark, flex: 1, fontSize: 14, fontWeight: "900" },
  conversationDate: { color: colors.textMuted, fontSize: 9 },
  previewRow: { alignItems: "center", flexDirection: "row", gap: 8, marginTop: 5 },
  preview: { color: colors.textMuted, flex: 1, fontSize: 11 },
  unreadBadge: { alignItems: "center", backgroundColor: colors.accent, borderRadius: 12, minWidth: 22, paddingHorizontal: 6, paddingVertical: 3 },
  unreadBadgeText: { color: colors.surface, fontSize: 9, fontWeight: "900" },
  modalBackdrop: { alignItems: "center", backgroundColor: "rgba(15, 46, 110, 0.45)", flex: 1, justifyContent: "center", padding: 22 },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.large, maxWidth: 430, padding: 22, width: "100%", ...shadow },
  modalTitle: { color: colors.primaryDark, fontSize: 20, fontWeight: "900" },
  modalText: { color: colors.text, fontSize: 13, lineHeight: 19, marginTop: 10 },
  modalActions: { flexDirection: "row", gap: 10, marginTop: 20 },
  modalSecondary: { alignItems: "center", borderColor: colors.border, borderRadius: radius.pill, borderWidth: 1, flex: 1, padding: 12 },
  modalSecondaryText: { color: colors.primaryDark, fontSize: 12, fontWeight: "800" },
  modalPrimary: { alignItems: "center", backgroundColor: colors.primary, borderRadius: radius.pill, flex: 1, padding: 12 },
  modalDanger: { backgroundColor: colors.danger },
  modalPrimaryText: { color: colors.surface, fontSize: 12, fontWeight: "900" },
});
