/**
 * Decoded tile images, shared by everything that composites them.
 *
 * Tiles are fetched rather than loaded as <img> so a 404 is known (a pyramid
 * that does not reach every tile of its box is normal) and so switch maps can
 * be decoded with no colour conversion or alpha premultiplication: their
 * pixels are numbers, not colours.
 *
 * Era tiles are many (four images per area per tile), so they are fetched at
 * low priority and a few at a time, leaving the present-day tiles, plain
 * <img> elements, to arrive first. Decoded images are kept in a bounded LRU;
 * an image that falls out is dropped, not closed, because a draw that is
 * waiting on other images may still hold it.
 */
export type ImageKind = "picture" | "data";

export interface TileImages {
  /** resolves to the bitmap, or null where the tile does not exist */
  load(url: string, kind: ImageKind): Promise<ImageBitmap | null>;
  /** the bitmap if it is already decoded; undefined while unknown, null if missing */
  peek(url: string): ImageBitmap | null | undefined;
  clear(): void;
}

export interface TileImagesOptions {
  /** decoded images kept */
  readonly capacity: number;
  /** fetches in flight at once */
  readonly concurrency?: number;
  readonly fetcher?: typeof fetch;
}

export function tileImages({ capacity, concurrency = 6, fetcher = fetch }: TileImagesOptions): TileImages {
  const ready = new Map<string, ImageBitmap | null>();
  const pending = new Map<string, Promise<ImageBitmap | null>>();
  const waiting: (() => void)[] = [];
  let inFlight = 0;

  const remember = (url: string, bitmap: ImageBitmap | null) => {
    ready.delete(url);
    ready.set(url, bitmap);
    while (ready.size > capacity) {
      const oldest = ready.keys().next().value as string;
      ready.delete(oldest);
    }
  };

  /* a slot among the `concurrency` fetches allowed at once */
  const slot = async (): Promise<() => void> => {
    if (inFlight >= concurrency) await new Promise<void>((resolve) => waiting.push(resolve));
    inFlight++;
    return () => {
      inFlight--;
      waiting.shift()?.();
    };
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
        p = (async () => {
          const release = await slot();
          try {
            const bitmap = await decode(url, kind, fetcher);
            remember(url, bitmap);
            return bitmap;
          } finally {
            release();
            pending.delete(url);
          }
        })();
        pending.set(url, p);
      }
      return p;
    },
    peek: (url) => ready.get(url),
    clear() {
      ready.clear();
    },
  };
}

async function decode(url: string, kind: ImageKind, fetcher: typeof fetch): Promise<ImageBitmap | null> {
  let res: Response;
  try {
    res = await fetcher(url, { mode: "cors", priority: "low" });
  } catch {
    return null;
  }
  if (!res.ok) {
    /* release the connection's stream rather than leave the body for the garbage collector */
    await res.body?.cancel().catch(() => undefined);
    return null;
  }
  try {
    const blob = await res.blob();
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
