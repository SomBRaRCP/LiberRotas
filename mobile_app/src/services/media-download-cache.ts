import type { MediaAssetResponse } from "@/security/trq-bec/service";

type CachedDownload = {
  asset: MediaAssetResponse;
  expiresAtMs: number;
};

const cachedDownloads = new Map<string, CachedDownload>();
const pendingDownloads = new Map<string, Promise<CachedDownload>>();

export async function resolveCachedMediaDownload(
  mediaId: string,
  loader: (mediaId: string) => Promise<MediaAssetResponse>,
  nowMs = Date.now(),
) {
  const cached = cachedDownloads.get(mediaId);
  if (cached && cached.expiresAtMs > nowMs) return cached;

  const pending = pendingDownloads.get(mediaId);
  if (pending) return pending;

  const request = loader(mediaId).then((asset) => {
    const usableSeconds = asset.download_url && asset.download_expires_in
      ? Math.max(15, asset.download_expires_in - 30)
      : ["pending", "uploaded", "processing"].includes(asset.status) ? 3 : 15;
    const resolved = { asset, expiresAtMs: nowMs + usableSeconds * 1_000 };
    cachedDownloads.set(mediaId, resolved);
    return resolved;
  }).finally(() => {
    pendingDownloads.delete(mediaId);
  });

  pendingDownloads.set(mediaId, request);
  return request;
}

export function clearMediaDownloadCache(mediaId?: string) {
  if (mediaId) {
    cachedDownloads.delete(mediaId);
    pendingDownloads.delete(mediaId);
    return;
  }
  cachedDownloads.clear();
  pendingDownloads.clear();
}
