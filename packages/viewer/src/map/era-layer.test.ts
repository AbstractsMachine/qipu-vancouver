import * as L from "leaflet";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type CanvasStub, flatImage, stubCanvas } from "../test/canvas";
import sfEras from "../test/fixtures/sf-eras.json";
import { parseLiveEras } from "../tiles/live-eras";
import type { Compositor, DrawPass } from "./compositor";
import { EraLayer } from "./era-layer";
import type * as Pixels from "./pixels";
import { readPixels } from "./pixels";
import type { ImageKind, TileImages } from "./tile-images";

/* the real pixel reader, counted, and able to fail on request */
vi.mock("./pixels", async (importOriginal) => {
  const real = await importOriginal<typeof Pixels>();
  return { readPixels: vi.fn(real.readPixels) };
});

const BASE = "https://tiles.test/sf";
const manifest = parseLiveEras(sfEras, { tile: 512 });

/* level-9 tiles: one inside Haight-Ashbury, one inside the Golden Gate area (a c3d switch), one in neither */
const HAIGHT = { x: 140, y: 95, z: 9 };
const GOLDEN_GATE = { x: 80, y: 30, z: 9 };
const NOWHERE = { x: 0, y: 0, z: 9 };

/* the Haight tile's images for the 1915-1959 segment, whose midpoint is 1937 */
const FROM_1915 = `${BASE}/_preview_eras/area/haight/1915/9/140/95.webp?v=wtrfwe14`;
const TO_1959 = `${BASE}/_preview_eras/area/haight/1959/9/140/95.webp?v=wtrfwe14`;
const SWITCH_1915_1959 = `${BASE}/_preview_eras/area/haight/switch/1915-1959/9/140/95.png?v=pv10171650`;

/*
 * Switch pixels (c3c): red and green hold a date code, (year - 1800) * 100;
 * blue's low four bits a fade. CHANGING starts in 1937 and fades over about
 * 25 years, so the tile is changing at any year between; AT_1939 switches
 * hard in 1939.
 */
const CHANGING = [53, 132, 15, 255] as const;
const AT_1939 = [54, 76, 0, 255] as const;

const coords = (c: { x: number; y: number; z: number }): L.Coords => Object.assign(L.point(c.x, c.y), { z: c.z });
const code = (year: number) => (year - 1800) * 100;
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

/**
 * Tile images held in a map. Pictures are opaque black; switch tiles are
 * filled with `switchPixel`. With `hold` set, loads wait until `release()`;
 * with `keep` unset, a loaded image is not cached, as if evicted at once;
 * URLs in `missing` resolve to null; with `fail` set, loads reject.
 */
class FakeImages implements TileImages {
  readonly ready = new Map<string, ImageBitmap | null>();
  readonly loads: { url: string; kind: ImageKind }[] = [];
  readonly missing = new Set<string>();
  switchPixel: readonly [number, number, number, number] = CHANGING;
  hold = false;
  keep = true;
  fail = false;
  private waiting: (() => void)[] = [];

  load(url: string, kind: ImageKind): Promise<ImageBitmap | null> {
    this.loads.push({ url, kind });
    if (this.fail) return Promise.reject(new Error(`could not load ${url}`));
    const finish = () => {
      const bitmap = this.missing.has(url) ? null : flatImage(kind === "data" ? this.switchPixel : [0, 0, 0, 255]);
      if (this.keep) this.ready.set(url, bitmap);
      return bitmap;
    };
    if (!this.hold) return Promise.resolve(finish());
    return new Promise((resolve) => {
      this.waiting.push(() => {
        resolve(finish());
      });
    });
  }

  release(): void {
    const waiting = this.waiting;
    this.waiting = [];
    for (const go of waiting) go();
  }

  peek(url: string): ImageBitmap | null | undefined {
    return this.ready.get(url);
  }

  clear(): void {
    this.ready.clear();
  }

  /** each URL asked for, once, in the order first asked */
  urls(): string[] {
    return [...new Set(this.loads.map((l) => l.url))];
  }
}

class FakeCompositor implements Compositor {
  readonly kind = "cpu";
  ok = true;
  readonly draws: { target: HTMLCanvasElement; passes: readonly DrawPass[] }[] = [];
  readonly dispose = vi.fn();

  draw(target: HTMLCanvasElement, passes: readonly DrawPass[]): void {
    this.draws.push({ target, passes });
  }
}

describe("EraLayer", () => {
  let canvas: CanvasStub;
  let images: FakeImages;
  let compositors: FakeCompositor[];
  let makeCompositor: () => Compositor;
  let frames: FrameRequestCallback[];

  beforeEach(() => {
    canvas = stubCanvas();
    vi.mocked(readPixels).mockClear();
    images = new FakeImages();
    compositors = [];
    makeCompositor = vi.fn(() => {
      const c = new FakeCompositor();
      compositors.push(c);
      return c;
    });
    frames = [];
    vi.stubGlobal(
      "requestAnimationFrame",
      vi.fn((cb: FrameRequestCallback) => {
        frames.push(cb);
        return frames.length;
      }),
    );
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function eraLayer(year = 1938): EraLayer {
    return new EraLayer({
      manifest,
      base: BASE,
      images,
      grid: { tileSize: 256, zoomOffset: 0 },
      compositor: makeCompositor,
      year,
      tilePx: 4,
      bounds: L.latLngBounds([0, 0], [-192, 320]),
      maxNativeZoom: 9,
    });
  }

  async function tile(layer: EraLayer, at: { x: number; y: number; z: number }): Promise<HTMLCanvasElement> {
    const done = vi.fn();
    const el = layer.createTile(coords(at), done) as HTMLCanvasElement;
    if (!images.hold) {
      await settle();
      expect(done).toHaveBeenCalledWith(undefined, el);
    }
    return el;
  }

  /** answer held loads until no draw is waiting on any */
  async function drain(): Promise<void> {
    for (let i = 0; i < 5; i++) {
      images.release();
      await settle();
    }
  }

  const runFrame = () => {
    const pending = frames.splice(0);
    for (const cb of pending) cb(0);
  };
  const draws = () => compositors.flatMap((c) => c.draws);
  const firstPass = () => draws()[0]?.passes[0];

  it("clears a tile outside every area without loading anything", async () => {
    const el = await tile(eraLayer(), NOWHERE);
    expect(el.width).toBe(4);
    expect(el.dataset.year).toBe("1938");
    expect(canvas.of(el)?.clears).toBe(1);
    expect(images.loads).toEqual([]);
    expect(draws()).toEqual([]);
  });

  it("leaves an area transparent at the present year", async () => {
    const el = await tile(eraLayer(2026), HAIGHT);
    expect(el.dataset.year).toBe("2026");
    expect(images.loads).toEqual([]);
  });

  describe("a tile that is changing at the year", () => {
    it("loads the switch tile first, then both pictures, and draws all three", async () => {
      const el = await tile(eraLayer(1938), HAIGHT);

      expect(images.loads[0]).toEqual({ url: SWITCH_1915_1959, kind: "data" });
      expect(images.urls()).toEqual([SWITCH_1915_1959, FROM_1915, TO_1959]);
      expect(draws()).toHaveLength(1);
      expect(draws()[0]?.target).toBe(el);
      const p = firstPass();
      expect(p?.t).toBe(code(1938));
      expect(p?.mid).toBe(code((1915 + 1959) / 2));
      expect(p?.from?.image).toBe(images.peek(FROM_1915));
      expect(p?.to?.image).toBe(images.peek(TO_1959));
      expect(p?.switchMap?.image).toBe(images.peek(SWITCH_1915_1959));
      expect(p?.clear).toBeNull();
      expect(el.dataset.year).toBe("1938");
    });

    it("also loads the cleared site where the switch map has one", async () => {
      await tile(eraLayer(1950), GOLDEN_GATE);
      expect(images.urls()).toHaveLength(4);
      expect(images.urls()).toContainEqual(expect.stringContaining("/area/cf_gg0/clear/1900-2026/"));
      expect(firstPass()?.clear?.image).not.toBeNull();
    });

    it("draws with the images it loaded even when the cache has already dropped them", async () => {
      images.keep = false;
      await tile(eraLayer(), HAIGHT);
      const p = firstPass();
      expect(p?.from?.image).not.toBeNull();
      expect(p?.to?.image).not.toBeNull();
      expect(p?.switchMap?.image).not.toBeNull();
    });
  });

  describe("a tile that is not changing at the year", () => {
    beforeEach(() => {
      images.switchPixel = AT_1939;
    });

    it("loads and draws only the earlier picture before its switch", async () => {
      await tile(eraLayer(1938), HAIGHT);
      expect(images.urls()).toEqual([SWITCH_1915_1959, FROM_1915]);
      const p = firstPass();
      expect(p?.from?.image).toBe(images.peek(FROM_1915));
      expect(p?.to?.image).toBe(images.peek(FROM_1915));
      expect(p?.switchMap).toBeNull();
      expect(p?.clear).toBeNull();
    });

    it("loads and draws only the later picture once it has switched", async () => {
      await tile(eraLayer(1940), HAIGHT);
      expect(images.urls()).toEqual([SWITCH_1915_1959, TO_1959]);
      const p = firstPass();
      expect(p?.from?.image).toBe(images.peek(TO_1959));
      expect(p?.switchMap).toBeNull();
    });

    it("draws a picture whole: the year is past the pass's midpoint", async () => {
      await tile(eraLayer(1938), HAIGHT);
      expect(firstPass()).toMatchObject({ t: 1, mid: 0 });
    });

    it("drops the cleared site too", async () => {
      await tile(eraLayer(1950), GOLDEN_GATE);
      expect(images.urls()).toHaveLength(2);
      expect(firstPass()?.clear).toBeNull();
    });
  });

  it("reads a switch tile's pixels once, however often the tile is redrawn", async () => {
    const layer = eraLayer(1938);
    const el = await tile(layer, HAIGHT);
    layer.setYear(1939);
    runFrame();
    await settle();
    layer.setYear(1940);
    runFrame();
    await settle();

    expect(el.dataset.year).toBe("1940");
    expect(readPixels).toHaveBeenCalledOnce();
  });

  it("treats a missing switch tile as the whole tile changing at the midpoint", async () => {
    images.missing.add(SWITCH_1915_1959);
    const layer = eraLayer(1936);
    await tile(layer, HAIGHT);
    expect(images.urls()).toEqual([SWITCH_1915_1959, FROM_1915]);

    await tile(eraLayer(1938), HAIGHT);
    expect(images.urls()).toEqual([SWITCH_1915_1959, FROM_1915, TO_1959]);
    expect(draws()[1]?.passes[0]?.from?.image).toBe(images.peek(TO_1959));
  });

  it("draws the full pass when the switch tile's pixels cannot be read", async () => {
    images.switchPixel = AT_1939;
    vi.mocked(readPixels).mockReturnValueOnce(null);
    await tile(eraLayer(1938), HAIGHT);
    expect(images.urls()).toEqual([SWITCH_1915_1959, FROM_1915, TO_1959]);
    expect(firstPass()?.t).toBe(code(1938));
  });

  it("draws from images already decoded without loading them again", async () => {
    const layer = eraLayer();
    await tile(layer, HAIGHT);
    const loaded = images.loads.length;
    await tile(layer, HAIGHT);
    expect(images.loads).toHaveLength(loaded);
    expect(draws()).toHaveLength(2);
  });

  it("redraws live tiles for a new year on the next animation frame", async () => {
    const layer = eraLayer();
    const el = await tile(layer, HAIGHT);
    layer.setYear(1959);
    layer.setYear(1985);
    layer.setYear(1985);
    expect(frames).toHaveLength(1);
    expect(draws()).toHaveLength(1);

    runFrame();
    await settle();
    expect(draws()).toHaveLength(2);
    expect(el.dataset.year).toBe("1985");
  });

  it("never lets a slow load for an earlier year draw over a later one", async () => {
    images.hold = true;
    const layer = eraLayer(1938);
    const el = await tile(layer, HAIGHT);
    layer.setYear(1959);
    runFrame();
    await drain();

    expect(el.dataset.year).toBe("1959");
    expect(draws().map((d) => d.passes[0]?.t)).toEqual([code(1959)]);
  });

  it("counts the tiles not yet drawn for the current year", async () => {
    images.hold = true;
    const layer = eraLayer();
    await tile(layer, NOWHERE);
    await tile(layer, HAIGHT);
    expect(layer.pending()).toBe(1);

    await drain();
    expect(layer.pending()).toBe(0);
    layer.setYear(1959);
    expect(layer.pending()).toBe(2);
  });

  it("swaps in a new compositor when the current one stops working", async () => {
    const layer = eraLayer();
    const first = compositors[0];
    if (first) first.ok = false;
    await tile(layer, HAIGHT);
    expect(makeCompositor).toHaveBeenCalledTimes(2);
    expect(first?.dispose).toHaveBeenCalledOnce();
    expect(first?.draws).toEqual([]);
    expect(compositors[1]?.draws).toHaveLength(1);
  });

  it("hands Leaflet the error when a tile cannot be drawn", async () => {
    images.fail = true;
    const done = vi.fn();
    const el = eraLayer().createTile(coords(HAIGHT), done);
    await settle();
    expect(done).toHaveBeenCalledWith(new Error(`could not load ${SWITCH_1915_1959}`), el);
  });

  it("forgets a tile once Leaflet unloads it", async () => {
    const layer = eraLayer();
    const el = await tile(layer, HAIGHT);
    layer.fire("tileunload", { tile: el, coords: coords(HAIGHT) });
    layer.setYear(1959);
    expect(layer.pending()).toBe(0);
    runFrame();
    await settle();
    expect(draws()).toHaveLength(1);
  });

  it("cancels a pending redraw, forgets its tiles and releases its compositor when removed from the map", async () => {
    const map = L.map(document.createElement("div"), { crs: L.CRS.Simple }).setView([0, 0], 9);
    const layer = eraLayer().addTo(map);
    await tile(layer, HAIGHT);
    layer.setYear(1959);
    map.removeLayer(layer);
    expect(cancelAnimationFrame).toHaveBeenCalledWith(1);
    expect(layer.pending()).toBe(0);
    expect(compositors[0]?.dispose).toHaveBeenCalledOnce();
    map.remove();
  });
});
