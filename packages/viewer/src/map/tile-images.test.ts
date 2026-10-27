import { afterEach, beforeEach, describe, expect, it, type Mock, vi } from "vitest";
import { tileImages } from "./tile-images";

interface FakeBitmap {
  readonly close: Mock;
  readonly options: ImageBitmapOptions | undefined;
}

const ok = () => Promise.resolve(new Response(new Uint8Array([1, 2, 3])));
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("tileImages", () => {
  let decoded: FakeBitmap[];
  let decode: Mock;

  beforeEach(() => {
    decoded = [];
    decode = vi.fn((_blob: Blob, options?: ImageBitmapOptions) => {
      const bitmap = { close: vi.fn(), options };
      decoded.push(bitmap);
      return Promise.resolve(bitmap);
    });
    vi.stubGlobal("createImageBitmap", decode);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("decodes a fetched tile and keeps it for peek", async () => {
    const fetcher = vi.fn(ok);
    const images = tileImages({ capacity: 4, fetcher });
    expect(images.peek("a.webp")).toBeUndefined();
    const bitmap = await images.load("a.webp", "picture");
    expect(bitmap).toBe(decoded[0]);
    expect(images.peek("a.webp")).toBe(bitmap);
  });

  it("fetches at low priority, across origins", async () => {
    const fetcher = vi.fn(ok);
    await tileImages({ capacity: 4, fetcher }).load("a.webp", "picture");
    expect(fetcher).toHaveBeenCalledWith("a.webp", { mode: "cors", priority: "low" });
  });

  it("decodes pictures premultiplied and switch maps as raw numbers", async () => {
    const images = tileImages({ capacity: 4, fetcher: ok });
    await images.load("picture.webp", "picture");
    await images.load("switch.png", "data");
    expect(decoded.map((b) => b.options)).toEqual([
      { premultiplyAlpha: "premultiply" },
      { premultiplyAlpha: "none", colorSpaceConversion: "none" },
    ]);
  });

  it("serves a cached tile without fetching it again", async () => {
    const fetcher = vi.fn(ok);
    const images = tileImages({ capacity: 4, fetcher });
    const first = await images.load("a.webp", "picture");
    expect(await images.load("a.webp", "picture")).toBe(first);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("shares one fetch between concurrent loads of the same tile", async () => {
    const fetcher = vi.fn(ok);
    const images = tileImages({ capacity: 4, fetcher });
    const [a, b] = await Promise.all([images.load("a.webp", "picture"), images.load("a.webp", "picture")]);
    expect(a).toBe(b);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("keeps no more fetches in flight than its concurrency", async () => {
    const started: string[] = [];
    const answers: (() => void)[] = [];
    const fetcher: typeof fetch = (input) => {
      started.push(input instanceof Request ? input.url : input.toString());
      return new Promise<Response>((resolve) => {
        answers.push(() => {
          resolve(new Response(new Uint8Array([1])));
        });
      });
    };
    const images = tileImages({ capacity: 8, concurrency: 2, fetcher });
    const loads = ["a", "b", "c"].map((url) => images.load(url, "picture"));
    await settle();
    expect(started).toEqual(["a", "b"]);

    answers[0]?.();
    await settle();
    expect(started).toEqual(["a", "b", "c"]);

    for (const answer of answers.slice(1)) answer();
    expect(await Promise.all(loads)).toHaveLength(3);
  });

  it("resolves a missing tile to null, remembers it and releases the response", async () => {
    const missing = new Response("Not Found", { status: 404 });
    const cancel = vi.spyOn(missing.body!, "cancel");
    const fetcher = vi.fn(() => Promise.resolve(missing));
    const images = tileImages({ capacity: 4, fetcher });
    expect(await images.load("gone.webp", "picture")).toBeNull();
    expect(cancel).toHaveBeenCalledOnce();
    expect(images.peek("gone.webp")).toBeNull();
    expect(await images.load("gone.webp", "picture")).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("resolves to null when the network fails or the image does not decode", async () => {
    const offline = tileImages({ capacity: 4, fetcher: () => Promise.reject(new TypeError("Failed to fetch")) });
    expect(await offline.load("a.webp", "picture")).toBeNull();

    decode.mockRejectedValueOnce(new DOMException("bad image", "InvalidStateError"));
    expect(await tileImages({ capacity: 4, fetcher: ok }).load("b.webp", "picture")).toBeNull();
  });

  it("drops the least recently used tile without closing it", async () => {
    const images = tileImages({ capacity: 2, fetcher: ok });
    const a = await images.load("a", "picture");
    await images.load("b", "picture");
    await images.load("a", "picture");
    await images.load("c", "picture");

    expect(images.peek("b")).toBeUndefined();
    expect(images.peek("a")).toBe(a);
    expect(decoded.every((b) => b.close.mock.calls.length === 0)).toBe(true);
  });

  it("forgets everything on clear", async () => {
    const fetcher = vi.fn(ok);
    const images = tileImages({ capacity: 4, fetcher });
    await images.load("a", "picture");
    images.clear();
    expect(images.peek("a")).toBeUndefined();
    await images.load("a", "picture");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
});
