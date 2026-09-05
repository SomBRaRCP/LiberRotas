import { describe, expect, it, vi } from "vitest";

import type { AuthenticatedRequest } from "../src/api/http-client";
import { createCommunityApi } from "../src/features/community/api";
import { createMessagingNormalizers } from "../src/features/messaging/api";


class TestServiceError extends Error {
  constructor(
    message: string,
    public readonly code: string,
  ) {
    super(message);
  }
}

const createError = (message: string, code: string) => new TestServiceError(message, code);

function buildApi(requestAuthenticated: AuthenticatedRequest) {
  return createCommunityApi({
    requestAuthenticated,
    messagingNormalizers: createMessagingNormalizers(
      (uid) => `https://api.example.test/v1/public/profile/${uid}/avatar`,
      createError,
    ),
    createClientMessageId: (prefix = "msg") => `${prefix}_fixed`,
    createError,
  });
}

describe("community api", () => {
  it("normaliza comentário sem aceitar função privilegiada do payload", () => {
    const request = vi.fn() as unknown as AuthenticatedRequest;
    const comment = buildApi(request).normalizePostComment({
      comment_id: "comment-1",
      post_id: "post-1",
      author: { uid: "user-1", display_name: "Pessoa", role: "admin" },
      content: "Comentário",
      like_count: -10,
      created_at: "2026-08-03T12:00:00Z",
    });

    expect(comment.author.role).toBe("visitor");
    expect(comment.author.avatar_uri).toContain("/user-1/avatar");
    expect(comment.like_count).toBe(0);
  });

  it("preserva o contrato de criação de comentário", async () => {
    const request = vi.fn(async () => ({
      comment_id: "comment-1",
      post_id: "post-1",
      author: { uid: "user-1", display_name: "Pessoa", role: "visitor" },
      content: "Resposta",
      created_at: "2026-08-03T12:00:00Z",
    })) as unknown as AuthenticatedRequest;

    const result = await buildApi(request).createPostComment(
      "post-1",
      "  Resposta  ",
      "parent-1",
      "comment-client-1",
    );

    expect(request).toHaveBeenCalledWith("POST", "/v1/feed/posts/post-1/comments", {
      content: "Resposta",
      parent_comment_id: "parent-1",
      client_comment_id: "comment-client-1",
    });
    expect(result.comment_id).toBe("comment-1");
  });

  it("seleciona PUT ou DELETE para a curtida", async () => {
    const requestMock = vi.fn(async (_method: string) => ({
      comment_id: "comment-1",
      liked: _method === "PUT",
      like_count: _method === "PUT" ? 1 : 0,
    }));
    const request = requestMock as unknown as AuthenticatedRequest;
    const api = buildApi(request);

    await api.setPostCommentLiked("comment-1", true);
    await api.setPostCommentLiked("comment-1", false);

    expect(requestMock.mock.calls[0][0]).toBe("PUT");
    expect(requestMock.mock.calls[1][0]).toBe("DELETE");
  });

  it("converte horários da feira para o contrato do backend", async () => {
    const request = vi.fn(async () => ({ document_id: "fair-1", status: "live" })) as unknown as AuthenticatedRequest;

    const documentId = await buildApi(request).publishLiveFair({
      name: "Feira Local",
      address: "Rua de Teste, 100",
      latitude: -25.4,
      longitude: -49.2,
      startsAtMs: 1_800_000_000_000,
      endsAtMs: 1_800_003_600_000,
    });

    expect(request).toHaveBeenCalledWith("POST", "/v1/community/live-fairs", {
      name: "Feira Local",
      address: "Rua de Teste, 100",
      latitude: -25.4,
      longitude: -49.2,
      starts_at_ms: 1_800_000_000_000,
      ends_at_ms: 1_800_003_600_000,
    });
    expect(documentId).toBe("fair-1");
  });

  it("exclui a feira pela rota protegida do backend", async () => {
    const request = vi.fn(async () => ({ document_id: "fair/a", status: "deleted" })) as unknown as AuthenticatedRequest;

    await buildApi(request).deleteLiveFair("fair/a");

    expect(request).toHaveBeenCalledWith("DELETE", "/v1/community/live-fairs/fair%2Fa");
  });

  it("exclui o ponto próprio pela rota protegida do backend", async () => {
    const request = vi.fn(async () => ({ document_id: "place/a", status: "deleted" })) as unknown as AuthenticatedRequest;

    await buildApi(request).deleteCuratedPlace("place/a");

    expect(request).toHaveBeenCalledWith("DELETE", "/v1/community/places/place%2Fa");
  });

  it("rejeita comentário vazio antes de chamar o backend", async () => {
    const request = vi.fn() as unknown as AuthenticatedRequest;

    await expect(buildApi(request).createPostComment("post-1", "   ")).rejects.toMatchObject({
      code: "MESSAGE_BODY_INVALID",
    });
    expect(request).not.toHaveBeenCalled();
  });
});
