import type { AuthenticatedRequest } from "@/api/http-client";
import type {
  MessageParticipant,
  createMessagingNormalizers,
} from "@/features/messaging/api";

export type PostComment = {
  comment_id: string;
  post_id: string;
  parent_comment_id: string | null;
  author: MessageParticipant;
  content: string;
  mine: boolean;
  liked_by_me: boolean;
  like_count: number;
  created_at: string;
  updated_at: string | null;
};

export type PostCommentLike = {
  comment_id: string;
  liked: boolean;
  like_count: number;
};

export type CuratedPlacePublishInput = {
  name: string;
  address: string;
  category: string;
  latitude: number;
  longitude: number;
};

export type LiveFairPublishInput = {
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  startsAtMs: number;
  endsAtMs: number;
};

export type CommunityPostPublishInput = {
  text: string;
  media?: {
    type: "image";
    media_id: string;
  };
};

type CommunityDocumentResponse = {
  document_id: string;
  status: "approved" | "scheduled" | "live" | "ended" | "published";
};

type JsonRecord = Record<string, unknown>;
type MessagingNormalizers = ReturnType<typeof createMessagingNormalizers>;

type CommunityApiDependencies = {
  requestAuthenticated: AuthenticatedRequest;
  messagingNormalizers: MessagingNormalizers;
  createClientMessageId: (prefix?: string) => string;
  createError: (message: string, code: string) => Error;
};

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : {};
}

function asString(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function createCommunityApi({
  requestAuthenticated,
  messagingNormalizers,
  createClientMessageId,
  createError,
}: CommunityApiDependencies) {
  const { normalizeIdentity, normalizeMessageContent } = messagingNormalizers;

  function normalizePostComment(value: unknown): PostComment {
    const item = asRecord(value);
    return {
      comment_id: asString(item.comment_id),
      post_id: asString(item.post_id),
      parent_comment_id: asNullableString(item.parent_comment_id),
      author: normalizeIdentity(item.author),
      content: asString(item.content),
      mine: item.mine === true,
      liked_by_me: item.liked_by_me === true,
      like_count: typeof item.like_count === "number" ? Math.max(0, item.like_count) : 0,
      created_at: asString(item.created_at, new Date().toISOString()),
      updated_at: asNullableString(item.updated_at),
    };
  }

  async function listPostComments(postId: string, limit = 100): Promise<PostComment[]> {
    const response = await requestAuthenticated<{ comments?: unknown[] }>(
      "GET",
      `/v1/feed/posts/${encodeURIComponent(postId)}/comments?limit=${Math.max(1, Math.min(limit, 200))}`,
    );
    return (response.comments || [])
      .map(normalizePostComment)
      .filter((comment) => Boolean(comment.comment_id));
  }

  async function createPostComment(
    postId: string,
    content: string,
    parentCommentId?: string,
    clientCommentId = createClientMessageId("comment"),
  ): Promise<PostComment> {
    const response = await requestAuthenticated<unknown>(
      "POST",
      `/v1/feed/posts/${encodeURIComponent(postId)}/comments`,
      {
        content: normalizeMessageContent(content),
        parent_comment_id: parentCommentId || null,
        client_comment_id: clientCommentId,
      },
    );
    const comment = normalizePostComment(response);
    if (!comment.comment_id || !comment.post_id) {
      throw createError("O backend não confirmou o comentário.", "COMMENT_RESPONSE_INVALID");
    }
    return comment;
  }

  async function updatePostComment(commentId: string, content: string): Promise<PostComment> {
    const response = await requestAuthenticated<unknown>(
      "PATCH",
      `/v1/feed/comments/${encodeURIComponent(commentId)}`,
      { content: normalizeMessageContent(content) },
    );
    const comment = normalizePostComment(response);
    if (!comment.comment_id) {
      throw createError("O backend não confirmou a edição do comentário.", "COMMENT_RESPONSE_INVALID");
    }
    return comment;
  }

  async function deletePostComment(commentId: string): Promise<void> {
    await requestAuthenticated<unknown>(
      "DELETE",
      `/v1/feed/comments/${encodeURIComponent(commentId)}`,
    );
  }

  async function setPostCommentLiked(commentId: string, liked: boolean): Promise<PostCommentLike> {
    const response = await requestAuthenticated<Record<string, unknown>>(
      liked ? "PUT" : "DELETE",
      `/v1/feed/comments/${encodeURIComponent(commentId)}/like`,
    );
    return {
      comment_id: asString(response.comment_id, commentId),
      liked: response.liked === true,
      like_count: typeof response.like_count === "number" ? Math.max(0, response.like_count) : 0,
    };
  }

  async function publishCommunityPost(input: CommunityPostPublishInput): Promise<string> {
    const response = await requestAuthenticated<CommunityDocumentResponse>(
      "POST",
      "/v1/community/posts",
      input,
    );
    return response.document_id;
  }

  async function updateCommunityPost(postId: string, text: string): Promise<void> {
    await requestAuthenticated<CommunityDocumentResponse>(
      "PATCH",
      `/v1/community/posts/${encodeURIComponent(postId)}`,
      { text: text.trim() },
    );
  }

  async function deleteCommunityPost(postId: string): Promise<void> {
    await requestAuthenticated<CommunityDocumentResponse>(
      "DELETE",
      `/v1/community/posts/${encodeURIComponent(postId)}`,
    );
  }

  async function publishCuratedPlace(input: CuratedPlacePublishInput): Promise<string> {
    const response = await requestAuthenticated<CommunityDocumentResponse>(
      "POST",
      "/v1/community/places",
      input,
    );
    return response.document_id;
  }

  async function deleteCuratedPlace(placeId: string): Promise<void> {
    await requestAuthenticated<unknown>(
      "DELETE",
      `/v1/community/places/${encodeURIComponent(placeId)}`,
    );
  }

  async function publishLiveFair(input: LiveFairPublishInput): Promise<string> {
    const response = await requestAuthenticated<CommunityDocumentResponse>(
      "POST",
      "/v1/community/live-fairs",
      {
        name: input.name,
        address: input.address,
        latitude: input.latitude,
        longitude: input.longitude,
        starts_at_ms: input.startsAtMs,
        ends_at_ms: input.endsAtMs,
      },
    );
    return response.document_id;
  }

  async function finishLiveFair(fairId: string): Promise<void> {
    await requestAuthenticated<CommunityDocumentResponse>(
      "POST",
      `/v1/community/live-fairs/${encodeURIComponent(fairId)}/end`,
    );
  }

  async function deleteLiveFair(fairId: string): Promise<void> {
    await requestAuthenticated<CommunityDocumentResponse>(
      "DELETE",
      `/v1/community/live-fairs/${encodeURIComponent(fairId)}`,
    );
  }

  return {
    normalizePostComment,
    listPostComments,
    createPostComment,
    updatePostComment,
    deletePostComment,
    setPostCommentLiked,
    publishCommunityPost,
    updateCommunityPost,
    deleteCommunityPost,
    publishCuratedPlace,
    deleteCuratedPlace,
    publishLiveFair,
    finishLiveFair,
    deleteLiveFair,
  };
}
