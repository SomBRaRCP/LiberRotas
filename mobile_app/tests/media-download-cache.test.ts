import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearMediaDownloadCache,
  resolveCachedMediaDownload,
} from "../src/services/media-download-cache";


function readyAsset(mediaId: string) {
  return {
    media_id: mediaId,
    status: "ready",
    download_url: `https://storage.example.test/${mediaId}`,
    download_expires_in: 300,
  } as never;
}

afterEach(() => {
  clearMediaDownloadCache();
});

describe("cache temporario de download de midia", () => {
  it("reutiliza a mesma consulta enquanto a URL assinada continua segura", async () => {
    const loader = vi.fn(async (mediaId: string) => readyAsset(mediaId));

    const first = await resolveCachedMediaDownload("media-1", loader, 1_000);
    const second = await resolveCachedMediaDownload("media-1", loader, 2_000);

    expect(first.asset.download_url).toBe(second.asset.download_url);
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("consolida componentes simultaneos em uma unica requisicao", async () => {
    const loader = vi.fn(async (mediaId: string) => readyAsset(mediaId));

    await Promise.all([
      resolveCachedMediaDownload("media-2", loader, 1_000),
      resolveCachedMediaDownload("media-2", loader, 1_000),
    ]);

    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("renova depois da margem anterior a expiracao", async () => {
    const loader = vi.fn(async (mediaId: string) => readyAsset(mediaId));

    await resolveCachedMediaDownload("media-3", loader, 1_000);
    await resolveCachedMediaDownload("media-3", loader, 272_000);

    expect(loader).toHaveBeenCalledTimes(2);
  });
});
