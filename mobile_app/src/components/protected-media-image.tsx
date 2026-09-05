import { Image, type ImageProps } from "expo-image";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet } from "react-native";
import { ImageViewerModal } from "@/components/image-viewer-modal";
import { resolveCachedMediaDownload } from "@/services/media-download-cache";
import { getMedia, getPublicMediaUrl } from "@/services/media-upload";

type ProtectedMediaImageProps = Omit<ImageProps, "source"> & {
  mediaId?: string;
  legacyUri?: string;
  publicVariant?: "thumbnail" | "display";
  expandable?: boolean;
  viewerLabel?: string;
};

function isRenderableUri(value?: string | null) {
  return Boolean(value && /^https?:\/\//i.test(value));
}

/**
 * Resolve uma referência permanente de mídia em uma URL curta de leitura.
 *
 * A URL assinada vive somente no estado deste componente: ela não é gravada
 * no Firestore, AsyncStorage ou objeto da publicação.
 */
export function ProtectedMediaImage({
  cachePolicy = "memory-disk",
  expandable = false,
  legacyUri,
  mediaId,
  publicVariant,
  transition = 150,
  viewerLabel,
  ...imageProps
}: ProtectedMediaImageProps) {
  const legacySource = isRenderableUri(legacyUri) ? legacyUri : undefined;
  const normalizedMediaId = mediaId?.trim() || "";
  const publicUri = normalizedMediaId && publicVariant
    ? getPublicMediaUrl(normalizedMediaId, publicVariant)
    : undefined;
  const [resolvedMedia, setResolvedMedia] = useState<{ mediaId: string; uri?: string } | null>(null);
  const [viewerVisible, setViewerVisible] = useState(false);

  useEffect(() => {
    let active = true;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    let failedAttempts = 0;

    if (!normalizedMediaId) {
      return () => {
        active = false;
      };
    }

    if (publicVariant) {
      return () => {
        active = false;
      };
    }

    async function resolveMedia() {
      try {
        const cached = await resolveCachedMediaDownload(normalizedMediaId, getMedia);
        const asset = cached.asset;
        if (!active) return;
        failedAttempts = 0;
        const nextUri = isRenderableUri(asset.download_url) ? asset.download_url || undefined : legacySource;
        setResolvedMedia({ mediaId: normalizedMediaId, uri: nextUri });

        if (nextUri && asset.download_expires_in) {
          const refreshInSeconds = Math.max(15, asset.download_expires_in - 30);
          refreshTimer = setTimeout(resolveMedia, refreshInSeconds * 1_000);
        } else if (["pending", "uploaded", "processing"].includes(asset.status)) {
          refreshTimer = setTimeout(resolveMedia, 3_000);
        }
      } catch {
        if (active) {
          setResolvedMedia({ mediaId: normalizedMediaId, uri: legacySource });
          // Falhas temporarias da API ou da rede nao congelam a imagem para
          // sempre. A nova tentativa continua sem persistir a URL assinada.
          failedAttempts += 1;
          if (failedAttempts <= 6) {
            refreshTimer = setTimeout(resolveMedia, 5_000);
          }
        }
      }
    }

    void resolveMedia();
    return () => {
      active = false;
      if (refreshTimer) clearTimeout(refreshTimer);
    };
  }, [legacySource, normalizedMediaId, publicVariant]);

  const resolvedUri = publicUri || (normalizedMediaId && resolvedMedia?.mediaId === normalizedMediaId
    ? resolvedMedia.uri || legacySource
    : legacySource);

  const image = (
    <Image
      {...imageProps}
      cachePolicy={cachePolicy}
      source={resolvedUri ? { uri: resolvedUri } : undefined}
      transition={transition}
    />
  );

  if (!expandable) return image;

  return (
    <>
      <Pressable
        accessibilityHint="Abre a imagem em tamanho maior com controles de zoom"
        accessibilityLabel={viewerLabel || "Ampliar imagem"}
        accessibilityRole="imagebutton"
        disabled={!resolvedUri}
        onPress={() => setViewerVisible(true)}
        style={styles.expandable}
      >
        {image}
      </Pressable>
      <ImageViewerModal
        accessibilityLabel={viewerLabel}
        onClose={() => setViewerVisible(false)}
        uri={resolvedUri}
        visible={viewerVisible}
      />
    </>
  );
}

const styles = StyleSheet.create({
  expandable: { width: "100%" },
});
