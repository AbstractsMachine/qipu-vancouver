/**
 * Decoded tile images, shared by everything that composites them.
 *
 * Tiles are fetched rather than loaded as <img> so a 404 is known (a pyramid
 * that does not reach every tile of its box is normal) and so switch maps can
 * be decoded with no colour conversion or alpha premultiplication: their
 * pixels are numbers, not colours. Decoded bitmaps are kept in a small LRU
 * and closed when they fall out of it.
 */
export type ImageKind = "picture" | "data";

export interface TileImages {
  /** resolves to the bitmap, or null where the tile does not exist */
  load(url: string, kind: ImageKind): Promise<ImageBitmap | null>;
  /** the bitmap if it is already decoded; undefined while unknown, null if missing */
  peek(url: string): ImageBitmap | null | undefined;
  /** called after an eviction closes a bitmap, so GPU textures made from it can go too */
  onEvict(listener: (bitmap: ImageBitmap) => void): void;
  clear(): void;
}

export function tileImages(capacity: number, fetcher: typeof fetch = fetch): TileImages {
  const ready = new Map<string, ImageBitmap | null>();
  const pending = new Map<string, Promise<ImageBitmap | null>>();
  const listeners: ((b: ImageBitmap) => void)[] = [];

  const remember = (url: string, bitmap: ImageBitmap | null) => {
    ready.delete(url);
    ready.set(url, bitmap);
    while (ready.size > capacity) {
      const [oldest, old] = ready.entries().next().value as [string, ImageBitmap | null];
      ready.delete(oldest);
      if (old) {
        for (const l of listeners) l(old);
        old.close();
      }
    }
  };

  return {
    load(url, kind) {
      const hit = ready.get(url);
      if (hit !== undefined) {
        remember(url, hit);
        return Promise.resolve(hit);
      }
      let p = pending.get(url);
      if (!p) {
        p = decode(url, kind, fetcher)
          .then((bitmap) => {
            remember(url, bitmap);
            return bitmap;
          })
          .finally(() => pending.delete(url));
        pending.set(url, p);
      }
      return p;
    },
    peek: (url) => ready.get(url),
    onEvict: (l) => listeners.push(l),
    clear() {
      for (const b of ready.values()) b?.close();
      ready.clear();
    },
  };
}

async function decode(url: string, kind: ImageKind, fetcher: typeof fetch): Promise<ImageBitmap | null> {
  let res: Response;
  try {
    res = await fetcher(url, { mode: "cors" });
  } catch {
    return null;
  }
  if (!res.ok) return null;
  const blob = await res.blob();
  try {
    return await createImageBitmap(
      blob,
      kind === "data"
        ? { premultiplyAlpha: "none", colorSpaceConversion: "none" }
        : { premultiplyAlpha: "premultiply" },
    );
  } catch {
    return null;
  }
}
