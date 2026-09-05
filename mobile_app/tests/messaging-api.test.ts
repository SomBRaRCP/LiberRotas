import { describe, expect, it, vi } from "vitest";

import type { AuthenticatedRequest } from "../src/api/http-client";
import {
  createMessagingApi,
  createMessagingNormalizers,
} from "../src/features/messaging/api";


class TestServiceError extends Error {
  constructor(
    message: string,
    public readonly code: string,
  ) {
    super(message);
  }
}

const createError = (message: string, code: string) => new TestServiceError(message, code);
const resolveAvatar = (uid: string) => `https://api.example.test/v1/public/profile/${uid}/avatar`;

function buildApi(requestAuthenticated: AuthenticatedRequest) {
  return createMessagingApi({
    requestAuthenticated,
    normalizers: createMessagingNormalizers(resolveAvatar, createError),
    createError,
  });
}

describe("messaging api", () => {
  it("normaliza identidade sem aceitar função privilegiada do payload", () => {
    const normalizers = createMessagingNormalizers(resolveAvatar, createError);

    const participant = normalizers.normalizeIdentity({
      uid: "user-1",
      display_name: "Pessoa Teste",
      role: "admin",
    });

    expect(participant).toEqual({
      firebase_uid: "user-1",
      display_name: "Pessoa Teste",
      role: "visitor",
      avatar_uri: "https://api.example.test/v1/public/profile/user-1/avatar",
      city: null,
    });
  });

  it("preserva o contrato de envio de mensagem privada", async () => {
    const request = vi.fn(async () => ({
      conversation: {
        conversation_id: "conversation-1",
        counterpart: { uid: "recipient-1", display_name: "Destino", role: "visitor" },
      },
      message: {
        message_id: "message-1",
        conversation_id: "conversation-1",
        sender_uid: "sender-1",
        sender_name: "Origem",
        sender_role: "visitor",
        content: "Olá",
        created_at: "2026-08-03T12:00:00Z",
      },
    })) as unknown as AuthenticatedRequest;

    const result = await buildApi(request).sendPrivateMessage({
      recipientUid: "recipient-1",
      content: "  Olá  ",
      clientMessageId: "client-message-1",
    });

    expect(request).toHaveBeenCalledWith("POST", "/v1/messages", {
      recipient_uid: "recipient-1",
      content: "Olá",
      client_message_id: "client-message-1",
    });
    expect(result.message.message_id).toBe("message-1");
  });

  it("combina a lista autoritativa de bloqueios com as conversas", async () => {
    const request = vi.fn(async (_method: string, path: string) => {
      if (path === "/v1/messages/blocks") {
        return {
          blocked_profiles: [{
            profile: { uid: "blocked-1", display_name: "Bloqueado", role: "visitor" },
            blocked_at: "2026-08-03T12:00:00Z",
          }],
        };
      }
      return {
        conversations: [{
          conversation_id: "conversation-1",
          counterpart: { uid: "blocked-1", display_name: "Bloqueado", role: "visitor" },
          can_message: true,
        }],
      };
    }) as unknown as AuthenticatedRequest;

    const conversations = await buildApi(request).listMessageConversations();

    expect(conversations[0]).toMatchObject({
      blocked_by_me: true,
      can_message: false,
    });
  });

  it("rejeita chamado sem assunto antes de chamar o backend", async () => {
    const request = vi.fn() as unknown as AuthenticatedRequest;

    await expect(buildApi(request).createSupportRequest({
      subject: "   ",
      content: "Preciso de ajuda",
    })).rejects.toMatchObject({ code: "SUPPORT_SUBJECT_INVALID" });
    expect(request).not.toHaveBeenCalled();
  });
});
