import * as Crypto from "expo-crypto";
import { fetch as expoFetch } from "expo/fetch";
import { File as ExpoFile } from "expo-file-system";
import type { ImagePickerAsset } from "expo-image-picker";
import { Platform } from "react-native";
import { clearMediaDownloadCache } from "@/services/media-download-cache";
import {
  confirmMediaUpload,
  deleteMediaAsset,
  fetchMediaAsset,
  getTrqBecApiUrl,
  requestMediaUploadAuthorization,
  type MediaAssetResponse,
  type MediaUploadAuthorizationInput,
  type MediaUploadAuthorizationResponse,
} from "@/security/trq-bec/service";

export const MAX_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024;
export const ALLOWED_IMAGE_CONTENT_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
const MEDIA_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export type AllowedImageContentType = (typeof ALLOWED_IMAGE_CONTENT_TYPES)[number];

export type PreparedImageUpload = {
  asset: ImagePickerAsset;
  clientRequestId: string;
  contentType: AllowedImageContentType;
  originalFilename: string;
  sizeBytes: number;
};

export type ImageUploadTarget = {
  entityType: string;
  entityId: string | null;
  mediaRole: string;
};

export class MediaUploadError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
    this.name = "MediaUploadError";
  }
}

const CONTENT_TYPE_BY_EXTENSION: Record<string, AllowedImageContentType> = {
  jpeg: "image/jpeg",
  jpg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
};

const EXTENSION_BY_CONTENT_TYPE: Record<AllowedImageContentType, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
};

const DANGEROUS_INTERMEDIATE_EXTENSIONS = new Set([
  "bat",
  "cmd",
  "com",
  "exe",
  "htm",
  "html",
  "jar",
  "js",
  "msi",
  "mjs",
  "pdf",
  "php",
  "ps1",
  "py",
  "scr",
  "sh",
  "svg",
  "vbs",
  "zip",
]);

function normalizeContentType(value?: string | null): AllowedImageContentType | null {
  const normalized = value?.trim().toLowerCase();
  if (normalized === "image/jpg") return "image/jpeg";
  return ALLOWED_IMAGE_CONTENT_TYPES.includes(normalized as AllowedImageContentType)
    ? normalized as AllowedImageContentType
    : null;
}

function fileExtension(filename?: string | null) {
  const basename = filename?.split(/[\\/]/).pop()?.trim() || "";
  const match = basename.toLowerCase().match(/\.([a-z0-9]+)$/);
  return match?.[1] || "";
}

function safeOriginalFilename(filename: string | null | undefined, contentType: AllowedImageContentType) {
  const basename = filename?.replace(/\0/g, "").split(/[\\/]/).pop()?.trim() || "";
  const fallback = `imagem-${Crypto.randomUUID()}.${EXTENSION_BY_CONTENT_TYPE[contentType]}`;
  const selectedName = basename || fallback;
  if (selectedName.length <= 180) return selectedName;
  const extension = `.${EXTENSION_BY_CONTENT_TYPE[contentType]}`;
  const stem = selectedName.slice(0, selectedName.lastIndexOf("."));
  return `${stem.slice(0, 180 - extension.length)}${extension}`;
}

function assertFilenameIsCompatible(filename: string | null | undefined, contentType: AllowedImageContentType) {
  if (!filename) return;
  const basename = filename.split(/[\\/]/).pop()?.trim().toLowerCase() || "";
  const segments = basename.split(".");
  const extension = fileExtension(basename);
  const extensionType = CONTENT_TYPE_BY_EXTENSION[extension];
  if (!extensionType || extensionType !== contentType) {
    throw new MediaUploadError(
      "Escolha uma imagem JPEG, PNG ou WebP cujo formato corresponda à extensão do arquivo.",
      "IMAGE_EXTENSION_INVALID",
    );
  }
  if (segments.slice(1, -1).some((segment) => DANGEROUS_INTERMEDIATE_EXTENSIONS.has(segment))) {
    throw new MediaUploadError("O nome deste arquivo contém uma extensão não permitida.", "IMAGE_DOUBLE_EXTENSION_INVALID");
  }
}

function nativeFileFor(asset: ImagePickerAsset) {
  try {
    return new ExpoFile(asset.uri);
  } catch {
    throw new MediaUploadError("Não foi possível acessar a imagem selecionada.", "IMAGE_FILE_UNAVAILABLE");
  }
}

export async function prepareImageForUpload(asset: ImagePickerAsset): Promise<PreparedImageUpload> {
  if (asset.type && asset.type !== "image") {
    throw new MediaUploadError("Inicialmente, o LiberRotas aceita somente imagens.", "IMAGE_ONLY");
  }

  const nativeFile = Platform.OS === "web" ? null : nativeFileFor(asset);
  const contentType = normalizeContentType(asset.mimeType || asset.file?.type || nativeFile?.type);
  const extension = fileExtension(asset.fileName);
  const fallbackContentType = extension ? CONTENT_TYPE_BY_EXTENSION[extension] : null;
  const resolvedContentType = contentType || fallbackContentType;
  if (!resolvedContentType) {
    throw new MediaUploadError("Formato não permitido. Use somente JPEG, PNG ou WebP.", "IMAGE_CONTENT_TYPE_INVALID");
  }
  assertFilenameIsCompatible(asset.fileName, resolvedContentType);

  const sizeBytes = asset.fileSize ?? asset.file?.size ?? nativeFile?.size ?? 0;
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    throw new MediaUploadError("Não foi possível identificar o tamanho da imagem.", "IMAGE_SIZE_UNKNOWN");
  }
  if (sizeBytes > MAX_IMAGE_UPLOAD_BYTES) {
    throw new MediaUploadError("A imagem deve ter no máximo 5 MB.", "IMAGE_TOO_LARGE");
  }

  return {
    asset,
    clientRequestId: Crypto.randomUUID(),
    contentType: resolvedContentType,
    originalFilename: safeOriginalFilename(asset.fileName, resolvedContentType),
    sizeBytes: Math.floor(sizeBytes),
  };
}

export function requestUploadAuthorization(
  image: PreparedImageUpload,
  target: ImageUploadTarget,
): Promise<MediaUploadAuthorizationResponse> {
  const input: MediaUploadAuthorizationInput = {
    entity_type: target.entityType,
    entity_id: target.entityId,
    media_role: target.mediaRole,
    original_filename: image.originalFilename,
    content_type: image.contentType,
    size_bytes: image.sizeBytes,
    client_request_id: image.clientRequestId,
  };
  return requestMediaUploadAuthorization(input);
}

async function uploadBodyFor(image: PreparedImageUpload): Promise<Blob> {
  let body: Blob;
  if (Platform.OS === "web") {
    if (image.asset.file) {
      body = image.asset.file;
    } else {
      const response = await expoFetch(image.asset.uri);
      if (!response.ok) throw new MediaUploadError("Não foi possível ler a imagem selecionada.", "IMAGE_FILE_UNAVAILABLE");
      body = await response.blob();
    }
  } else {
    body = nativeFileFor(image.asset);
  }

  if (body.size !== image.sizeBytes) {
    throw new MediaUploadError("A imagem foi alterada depois da seleção. Escolha o arquivo novamente.", "IMAGE_SIZE_CHANGED");
  }
  if (body.size > MAX_IMAGE_UPLOAD_BYTES) {
    throw new MediaUploadError("A imagem deve ter no máximo 5 MB.", "IMAGE_TOO_LARGE");
  }
  return body;
}

export async function uploadToSignedUrl(
  image: PreparedImageUpload,
  authorization: MediaUploadAuthorizationResponse,
): Promise<void> {
  if (authorization.method !== "PUT" || !authorization.upload_url.startsWith("https://")) {
    throw new MediaUploadError("A autorização temporária de upload é inválida.", "UPLOAD_AUTHORIZATION_INVALID");
  }

  const headers = { ...authorization.required_headers };
  const contentTypeHeader = Object.keys(headers).find((name) => name.toLowerCase() === "content-type");
  if (contentTypeHeader && headers[contentTypeHeader].trim().toLowerCase() !== image.contentType) {
    throw new MediaUploadError("O servidor autorizou um tipo de imagem diferente do arquivo.", "UPLOAD_CONTENT_TYPE_MISMATCH");
  }
  if (!contentTypeHeader) headers["Content-Type"] = image.contentType;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90_000);
  try {
    const response = await expoFetch(authorization.upload_url, {
      body: await uploadBodyFor(image),
      credentials: "omit",
      headers,
      method: "PUT",
      signal: controller.signal,
    });
    if (!response.ok) {
      const message = response.status === 401 || response.status === 403
        ? "A autorização de upload expirou. Tente publicar novamente."
        : `O armazenamento recusou a imagem (HTTP ${response.status}).`;
      throw new MediaUploadError(message, "SIGNED_UPLOAD_FAILED");
    }
  } catch (error) {
    if (error instanceof MediaUploadError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new MediaUploadError("O envio da imagem demorou demais. Confira sua conexão e tente novamente.", "SIGNED_UPLOAD_TIMEOUT");
    }
    throw new MediaUploadError("Não foi possível enviar a imagem. Confira sua conexão e tente novamente.", "SIGNED_UPLOAD_NETWORK_ERROR");
  } finally {
    clearTimeout(timeout);
  }
}

export function confirmUpload(mediaId: string): Promise<MediaAssetResponse> {
  return confirmMediaUpload(mediaId);
}

export function getMedia(mediaId: string): Promise<MediaAssetResponse> {
  return fetchMediaAsset(mediaId);
}

export async function deleteMedia(mediaId: string): Promise<void> {
  await deleteMediaAsset(mediaId);
  clearMediaDownloadCache(mediaId);
}

/** URL publica estavel; o backend renova a URL assinada a cada abertura. */
export function getPublicMediaUrl(
  mediaId: string,
  variant?: "thumbnail" | "display",
) {
  const cleanMediaId = mediaId.trim().toLowerCase();
  const apiUrl = getTrqBecApiUrl();
  if (!apiUrl || !MEDIA_ID_PATTERN.test(cleanMediaId)) {
    throw new MediaUploadError("A referencia publica da imagem e invalida.", "PUBLIC_MEDIA_REFERENCE_INVALID");
  }
  const baseUrl = `${apiUrl}/v1/public/media/${encodeURIComponent(cleanMediaId)}`;
  return variant ? `${baseUrl}?variant=${variant}` : baseUrl;
}

type PublicEntityMediaTarget =
  | { entityType: "product"; mediaRole: "product_image" }
  | { entityType: "fair"; mediaRole: "fair_cover" }
  | { entityType: "institution"; mediaRole: "institution_logo" };

/** URL publica estavel da variante atual de uma entidade do dominio. */
export function getPublicEntityMediaUrl(
  target: PublicEntityMediaTarget & {
    entityId: string;
    variant?: "thumbnail" | "display";
  },
) {
  const apiUrl = getTrqBecApiUrl();
  const entityId = target.entityId.trim();
  if (!apiUrl || !entityId || entityId.length > 160 || !/^[A-Za-z0-9:_-]+$/.test(entityId)) {
    throw new MediaUploadError("A referencia publica da entidade e invalida.", "PUBLIC_ENTITY_MEDIA_REFERENCE_INVALID");
  }
  const baseUrl = [
    apiUrl,
    "v1/public/media/entities",
    target.entityType,
    encodeURIComponent(entityId),
    target.mediaRole,
  ].join("/");
  return `${baseUrl}?variant=${target.variant || "thumbnail"}`;
}

/** Recupera o media ID apenas de URLs publicas emitidas pelo backend atual. */
export function getPublicMediaId(uri?: string) {
  const apiUrl = getTrqBecApiUrl();
  const prefix = apiUrl ? `${apiUrl}/v1/public/media/` : "";
  if (!uri || !prefix || !uri.startsWith(prefix)) return null;
  const mediaId = decodeURIComponent(uri.slice(prefix.length).split("?", 1)[0]).trim().toLowerCase();
  return MEDIA_ID_PATTERN.test(mediaId) ? mediaId : null;
}

export async function uploadImage(
  image: PreparedImageUpload,
  target: ImageUploadTarget,
): Promise<MediaAssetResponse> {
  const authorization = await requestUploadAuthorization(image, target);
  await uploadToSignedUrl(image, authorization);
  const asset = await confirmUpload(authorization.media_id);
  if (asset.media_id !== authorization.media_id) {
    throw new MediaUploadError("O backend confirmou uma imagem diferente da autorizada.", "MEDIA_CONFIRMATION_MISMATCH");
  }
  return asset;
}
