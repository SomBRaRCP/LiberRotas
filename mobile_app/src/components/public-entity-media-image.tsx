import { Image, type ImageProps } from "expo-image";
import { useState, type ReactNode } from "react";
import { getPublicEntityMediaUrl } from "@/services/media-upload";

type EntityMediaTarget =
  | { entityType: "product"; mediaRole: "product_image" }
  | { entityType: "fair"; mediaRole: "fair_cover" }
  | { entityType: "institution"; mediaRole: "institution_logo" };

type PublicEntityMediaImageProps = Omit<ImageProps, "onError" | "source"> & EntityMediaTarget & {
  entityId: string;
  fallback?: ReactNode;
  variant?: "thumbnail" | "display";
};

/**
 * Exibe a variante publica atual sem armazenar URL assinada no estado global.
 * Quando a entidade ainda nao possui imagem, preserva o fallback da tela.
 */
export function PublicEntityMediaImage({
  cachePolicy = "memory-disk",
  entityId,
  entityType,
  fallback = null,
  mediaRole,
  transition = 150,
  variant = "thumbnail",
  ...imageProps
}: PublicEntityMediaImageProps) {
  const sourceKey = `${entityType}:${entityId}:${mediaRole}:${variant}`;
  const [failedSourceKey, setFailedSourceKey] = useState("");

  if (failedSourceKey === sourceKey) return fallback;

  let uri: string;
  try {
    uri = getPublicEntityMediaUrl({ entityId, entityType, mediaRole, variant } as Parameters<typeof getPublicEntityMediaUrl>[0]);
  } catch {
    return fallback;
  }

  return (
    <Image
      {...imageProps}
      cachePolicy={cachePolicy}
      onError={() => setFailedSourceKey(sourceKey)}
      source={{ uri }}
      transition={transition}
    />
  );
}
