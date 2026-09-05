import type { AuthenticatedRequest } from "@/api/http-client";
import type { PublicDirectoryRole } from "@/features/directory/api";

export type MessageParticipant = {
  firebase_uid: string;
  display_name: string;
  role: PublicDirectoryRole | "support" | "unavailable";
  avatar_uri: string | null;
  city: string | null;
};

export type MessageDeliveryStatus = "SENT" | "DELIVERED" | "READ";

export type PrivateMessage = {
  message_id: string;
  conversation_id: string;
  sender: MessageParticipant;
  sender_uid: string;
  recipient_uid: string | null;
  content: string;
  media_id: string | null;
  mine: boolean;
  created_at: string;
  read_at: string | null;
  status: MessageDeliveryStatus;
};

export type MessageConversationSummary = {
  conversation_id: string;
  kind: "DIRECT" | "SUPPORT";
  status: "OPEN" | "IN_PROGRESS" | "WAITING_USER" | "RESOLVED" | "CLOSED";
  subject: string | null;
  participant: MessageParticipant;
  last_message_preview: string;
  last_message_at: string | null;
  unread_count: number;
  blocked_by_me: boolean;
  blocked_me: boolean;
  can_message: boolean;
};

export type MessageConversationDetail = {
  conversation: MessageConversationSummary;
  messages: PrivateMessage[];
};

export type BlockedProfile = {
  profile: MessageParticipant;
  blocked_at: string;
};

export type SupportRequestStatus = "OPEN" | "IN_PROGRESS" | "WAITING_USER" | "RESOLVED" | "CLOSED";

export type SupportRequestSummary = {
  request_id: string;
  requester_uid: string;
  requester_name: string;
  requester_email: string | null;
  subject: string;
  status: SupportRequestStatus;
  unread_count: number;
  last_message_preview: string;
  created_at: string;
  updated_at: string;
};

type SupportSenderRole = "admin" | "support" | "security" | "institution" | "entrepreneur" | "visitor";

export type SupportMessage = {
  message_id: string;
  request_id: string;
  sender_uid: string;
  sender_role: SupportSenderRole;
  sender_name: string;
  content: string;
  created_at: string;
  read_at: string | null;
};

export type SupportRequestDetail = {
  request: SupportRequestSummary;
  messages: SupportMessage[];
};

export type SendPrivateMessageInput = {
  recipientUid: string;
  content: string;
  clientMessageId?: string;
};

export type SendPrivateMessageResult = {
  conversation: MessageConversationSummary;
  message: PrivateMessage;
};

export type CreateSupportRequestInput = {
  subject: string;
  content: string;
  clientMessageId?: string;
};

export type CreateSupportRequestResult = {
  request: SupportRequestSummary;
  message: SupportMessage;
};

type JsonRecord = Record<string, unknown>;
type StableAvatarResolver = (firebaseUid: string, avatarUri?: string | null) => string | undefined;
type ErrorFactory = (message: string, code: string) => Error;

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function createMessagingNormalizers(
  resolveStableAvatar: StableAvatarResolver,
  createError: ErrorFactory,
) {
  function normalizeMessageContent(content: string) {
    const normalized = content.trim();
    if (!normalized || normalized.length > 2_000) {
      throw createError("Digite uma mensagem válida antes de enviar.", "MESSAGE_BODY_INVALID");
    }
    return normalized;
  }

  function normalizeIdentity(value: unknown): MessageParticipant {
    const identity = asRecord(value);
    const role = asString(identity.role, "visitor") as MessageParticipant["role"];
    const firebaseUid = asString(identity.firebase_uid || identity.uid);
    return {
      firebase_uid: firebaseUid,
      display_name: asString(identity.display_name, "Usuário LiberRotas"),
      role: ["visitor", "entrepreneur", "institution", "support", "unavailable"].includes(role)
        ? role
        : "visitor",
      avatar_uri: resolveStableAvatar(firebaseUid, asNullableString(identity.avatar_uri)) || null,
      city: asNullableString(identity.city),
    };
  }

  function normalizeConversation(value: unknown): MessageConversationSummary {
    const item = asRecord(value);
    const status = asString(item.status, "OPEN") as MessageConversationSummary["status"];
    const kind = item.kind === "SUPPORT" ? "SUPPORT" : "DIRECT";
    const blockedByMe = item.blocked_by_me === true;
    const blockedMe = item.blocked_me === true;
    const finalStatus = status === "RESOLVED" || status === "CLOSED";
    return {
      conversation_id: asString(item.conversation_id),
      kind,
      status: ["OPEN", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED"].includes(status)
        ? status
        : "OPEN",
      subject: asNullableString(item.subject),
      participant: normalizeIdentity(item.participant || item.counterpart),
      last_message_preview: asString(item.last_message_preview || item.last_message),
      last_message_at: asNullableString(item.last_message_at),
      unread_count: typeof item.unread_count === "number" ? Math.max(0, item.unread_count) : 0,
      blocked_by_me: blockedByMe,
      blocked_me: blockedMe,
      can_message: typeof item.can_message === "boolean"
        ? item.can_message
        : !blockedByMe && !blockedMe && !finalStatus,
    };
  }

  function normalizePrivateMessage(value: unknown): PrivateMessage {
    const item = asRecord(value);
    const sender = normalizeIdentity(item.sender || {
      uid: item.sender_uid,
      display_name: item.sender_name,
      role: item.sender_role,
    });
    const status = asString(item.status, item.read_at ? "READ" : "SENT") as MessageDeliveryStatus;
    return {
      message_id: asString(item.message_id),
      conversation_id: asString(item.conversation_id),
      sender,
      sender_uid: sender.firebase_uid,
      recipient_uid: asNullableString(item.recipient_uid),
      content: asString(item.content),
      media_id: asNullableString(item.media_id),
      mine: item.mine === true,
      created_at: asString(item.created_at, new Date().toISOString()),
      read_at: asNullableString(item.read_at),
      status: ["SENT", "DELIVERED", "READ"].includes(status) ? status : "SENT",
    };
  }

  function normalizeSupportSummary(value: unknown): SupportRequestSummary {
    const item = asRecord(value);
    const conversation = normalizeConversation(item.request || item);
    const status = asString(item.status, conversation.status) as SupportRequestStatus;
    return {
      request_id: asString(item.request_id, conversation.conversation_id),
      requester_uid: asString(item.requester_uid, conversation.participant.firebase_uid),
      requester_name: asString(item.requester_name, conversation.participant.display_name),
      requester_email: asNullableString(item.requester_email),
      subject: asString(item.subject, conversation.subject || "Atendimento"),
      status: ["OPEN", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED"].includes(status)
        ? status
        : "OPEN",
      unread_count: typeof item.unread_count === "number" ? item.unread_count : conversation.unread_count,
      last_message_preview: asString(item.last_message_preview, conversation.last_message_preview),
      created_at: asString(item.created_at, new Date().toISOString()),
      updated_at: asString(
        item.updated_at,
        item.created_at ? asString(item.created_at) : new Date().toISOString(),
      ),
    };
  }

  function normalizeSupportMessage(value: unknown): SupportMessage {
    const item = asRecord(value);
    const message = normalizePrivateMessage(item);
    return {
      message_id: message.message_id,
      request_id: asString(item.request_id, message.conversation_id),
      sender_uid: message.sender_uid,
      sender_role: message.sender.role === "support" ? "support" : message.sender.role as SupportSenderRole,
      sender_name: message.sender.display_name,
      content: message.content,
      created_at: message.created_at,
      read_at: message.read_at,
    };
  }

  return {
    normalizeMessageContent,
    normalizeIdentity,
    normalizeConversation,
    normalizePrivateMessage,
    normalizeSupportSummary,
    normalizeSupportMessage,
  };
}

type MessagingApiDependencies = {
  requestAuthenticated: AuthenticatedRequest;
  normalizers: ReturnType<typeof createMessagingNormalizers>;
  createError: ErrorFactory;
};

export function createMessagingApi({
  requestAuthenticated,
  normalizers,
  createError,
}: MessagingApiDependencies) {
  const {
    normalizeMessageContent,
    normalizeIdentity,
    normalizeConversation,
    normalizePrivateMessage,
    normalizeSupportSummary,
    normalizeSupportMessage,
  } = normalizers;

  function createClientMessageId(prefix = "msg") {
    return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
  }

  async function listBlockedProfiles(): Promise<BlockedProfile[]> {
    const response = await requestAuthenticated<{ blocked_profiles?: unknown[]; blocks?: unknown[] }>(
      "GET",
      "/v1/messages/blocks",
    );
    return (response.blocked_profiles || response.blocks || []).map((value) => {
      const item = asRecord(value);
      return {
        profile: normalizeIdentity(item.profile),
        blocked_at: asString(item.blocked_at, new Date().toISOString()),
      };
    });
  }

  async function listMessageConversations(): Promise<MessageConversationSummary[]> {
    const response = await requestAuthenticated<{ conversations: unknown[] }>(
      "GET",
      "/v1/messages/conversations?limit=50",
    );
    const blocks = await listBlockedProfiles().catch(() => []);
    const blockedUids = new Set(blocks.map((block) => block.profile.firebase_uid));
    return (response.conversations || []).map((value) => {
      const conversation = normalizeConversation(value);
      const blockedByMe = conversation.blocked_by_me || blockedUids.has(conversation.participant.firebase_uid);
      return {
        ...conversation,
        blocked_by_me: blockedByMe,
        can_message: conversation.can_message && !blockedByMe,
      };
    }).filter((conversation) => Boolean(conversation.conversation_id));
  }

  async function getMessageConversation(conversationId: string): Promise<MessageConversationDetail> {
    const response = await requestAuthenticated<{ conversation: unknown; messages: unknown[] }>(
      "GET",
      `/v1/messages/conversations/${encodeURIComponent(conversationId)}?limit=100`,
    );
    const blocks = await listBlockedProfiles().catch(() => []);
    const conversation = normalizeConversation(response.conversation);
    const blockedByMe = conversation.blocked_by_me
      || blocks.some((block) => block.profile.firebase_uid === conversation.participant.firebase_uid);
    return {
      conversation: {
        ...conversation,
        blocked_by_me: blockedByMe,
        can_message: conversation.can_message && !blockedByMe,
      },
      messages: (response.messages || []).map(normalizePrivateMessage),
    };
  }

  async function sendPrivateMessage(input: SendPrivateMessageInput): Promise<SendPrivateMessageResult> {
    const response = await requestAuthenticated<unknown>("POST", "/v1/messages", {
      recipient_uid: input.recipientUid,
      content: normalizeMessageContent(input.content),
      client_message_id: input.clientMessageId || createClientMessageId(),
    });
    const envelope = asRecord(response);
    const messages = Array.isArray(envelope.messages) ? envelope.messages : [];
    const message = normalizePrivateMessage(envelope.message || messages[messages.length - 1] || response);
    const conversation = envelope.conversation
      ? normalizeConversation(envelope.conversation)
      : normalizeConversation({
        conversation_id: message.conversation_id,
        counterpart: { uid: input.recipientUid, display_name: "Perfil LiberRotas", role: "visitor" },
        last_message: message.content,
        last_message_at: message.created_at,
      });
    if (!conversation.conversation_id || !message.message_id) {
      throw createError("O backend não confirmou a conversa criada.", "MESSAGE_RESPONSE_INVALID");
    }
    return { conversation, message };
  }

  async function replyToMessageConversation(
    conversationId: string,
    content: string,
    clientMessageId = createClientMessageId(),
    mediaId?: string,
  ): Promise<PrivateMessage> {
    const response = await requestAuthenticated<unknown>(
      "POST",
      `/v1/messages/conversations/${encodeURIComponent(conversationId)}/messages`,
      {
        content: normalizeMessageContent(content),
        client_message_id: clientMessageId,
        media_id: mediaId || null,
      },
    );
    const envelope = asRecord(response);
    const messages = Array.isArray(envelope.messages) ? envelope.messages : [];
    const message = normalizePrivateMessage(envelope.message || messages[messages.length - 1] || response);
    if (!message.message_id || !message.conversation_id) {
      throw createError("O backend não confirmou a mensagem enviada.", "MESSAGE_RESPONSE_INVALID");
    }
    return message;
  }

  async function markMessageConversationRead(conversationId: string): Promise<void> {
    await requestAuthenticated<{ status: string }>(
      "POST",
      `/v1/messages/conversations/${encodeURIComponent(conversationId)}/read`,
    );
  }

  async function blockMessageProfile(firebaseUid: string): Promise<BlockedProfile> {
    const response = await requestAuthenticated<unknown>(
      "POST",
      `/v1/messages/blocks/${encodeURIComponent(firebaseUid)}`,
    );
    const item = asRecord(response);
    return {
      profile: normalizeIdentity(item.profile),
      blocked_at: asString(item.blocked_at, new Date().toISOString()),
    };
  }

  async function unblockMessageProfile(firebaseUid: string): Promise<void> {
    await requestAuthenticated<{ status: string }>(
      "DELETE",
      `/v1/messages/blocks/${encodeURIComponent(firebaseUid)}`,
    );
  }

  async function createSupportRequest(input: CreateSupportRequestInput): Promise<CreateSupportRequestResult> {
    const subject = input.subject.trim();
    if (!subject || subject.length > 120) {
      throw createError("Informe um assunto de até 120 caracteres.", "SUPPORT_SUBJECT_INVALID");
    }
    const response = await requestAuthenticated<unknown>("POST", "/v1/support/requests", {
      subject,
      content: normalizeMessageContent(input.content),
      client_message_id: input.clientMessageId || createClientMessageId("support"),
    });
    const envelope = asRecord(response);
    const messages = Array.isArray(envelope.messages) ? envelope.messages : [];
    const rawMessage = envelope.message || messages[messages.length - 1] || {};
    const result = {
      request: normalizeSupportSummary(envelope.request || envelope.conversation || response),
      message: normalizeSupportMessage(rawMessage),
    };
    if (!result.request.request_id || !result.message.message_id) {
      throw createError("O backend não confirmou o atendimento criado.", "SUPPORT_RESPONSE_INVALID");
    }
    return result;
  }

  async function listSupportRequests(
    options: { status?: SupportRequestStatus } = {},
  ): Promise<SupportRequestSummary[]> {
    const status = options.status ? `&status=${encodeURIComponent(options.status)}` : "";
    const response = await requestAuthenticated<{ requests?: unknown[]; conversations?: unknown[] }>(
      "GET",
      `/v1/support/requests?limit=100${status}`,
    );
    const rawItems = response.requests || response.conversations || [];
    return rawItems
      .filter((value) => {
        const item = asRecord(value);
        return Boolean(item.request_id) || normalizeConversation(item.request || value).kind === "SUPPORT";
      })
      .map(normalizeSupportSummary)
      .filter((request) => !options.status || request.status === options.status);
  }

  async function getSupportRequest(requestId: string): Promise<SupportRequestDetail> {
    const response = await requestAuthenticated<{ request?: unknown; conversation?: unknown; messages?: unknown[] }>(
      "GET",
      `/v1/support/requests/${encodeURIComponent(requestId)}`,
    );
    return {
      request: normalizeSupportSummary(response.request || response.conversation || { conversation_id: requestId }),
      messages: (response.messages || []).map(normalizeSupportMessage),
    };
  }

  async function replySupportRequest(
    requestId: string,
    content: string,
    clientMessageId = createClientMessageId("support"),
  ): Promise<SupportMessage> {
    const response = await requestAuthenticated<unknown>(
      "POST",
      `/v1/support/requests/${encodeURIComponent(requestId)}/messages`,
      { content: normalizeMessageContent(content), client_message_id: clientMessageId },
    );
    const envelope = asRecord(response);
    const message = normalizeSupportMessage(envelope.message || response);
    if (!message.message_id || !message.request_id) {
      throw createError("O backend não confirmou a resposta enviada.", "SUPPORT_RESPONSE_INVALID");
    }
    return message;
  }

  async function resolveSupportRequest(requestId: string): Promise<SupportRequestSummary> {
    const response = await requestAuthenticated<unknown>(
      "POST",
      `/v1/support/requests/${encodeURIComponent(requestId)}/resolve`,
    );
    const envelope = asRecord(response);
    return normalizeSupportSummary(envelope.request || envelope.conversation || response);
  }

  return {
    createClientMessageId,
    listMessageConversations,
    getMessageConversation,
    sendPrivateMessage,
    replyToMessageConversation,
    markMessageConversationRead,
    listBlockedProfiles,
    blockMessageProfile,
    unblockMessageProfile,
    createSupportRequest,
    listSupportRequests,
    getSupportRequest,
    replySupportRequest,
    resolveSupportRequest,
  };
}
