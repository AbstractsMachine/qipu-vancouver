import * as L from "leaflet";
import type { EraManifest } from "../eras/model";
import { type PassPlan, type SourceRef, planTile, sourcesOf } from "../eras/plan";
import { type SwitchRange, narrowPass, switchRange } from "../eras/range";
import type { GridOptions } from "../tiles/levels";
import type { Compositor, DrawPass, DrawSource } from "./compositor";
import { readPixels } from "./pixels";
import { closeSeams } from "./seams";
import type { TileImages } from "./tile-images";

export interface EraLayerOptions {
  readonly manifest: EraManifest;
  readonly base: string;
  readonly images: TileImages;
  readonly grid: GridOptions;
  /** returns a working compositor; called again if the current one stops working */
  readonly compositor: () => Compositor;
  readonly year: number;
  /** image pixels per tile edge */
  readonly tilePx: number;
  readonly bounds: L.LatLngBounds;
  readonly maxNativeZoom: number;
}

interface LiveTile {
  readonly canvas: HTMLCanvasElement;
  readonly level: number;
  readonly x: number;
  readonly y: number;
  /** bumped on every request to draw, so a slow load cannot draw an old year */
  seq: number;
}

/**
 * The past, drawn over the present pyramid: one canvas per tile, redrawn for
 * every year the slider passes through. A tile with no era area in it, or a
 * year at or after the present, is left transparent.
 */
export class EraLayer extends L.GridLayer {
  private year: number;
  private compositor: Compositor;
  private readonly live = new Map<string, LiveTile>();
  /** each switch tile's span of change, by URL; null where it could not be read */
  private readonly ranges = new Map<string, SwitchRange | null>();
  private frame = 0;
  private readonly era: EraLayerOptions;

  constructor(options: EraLayerOptions) {
    super({
      tileSize: options.grid.tileSize,
      bounds: options.bounds,
      minNativeZoom: -options.grid.zoomOffset,
      maxNativeZoom: options.maxNativeZoom,
      noWrap: true,
      updateWhenZooming: false,
      keepBuffer: 1,
      className: "qv-era-layer",
    });
    this.era = options;
    this.year = options.year;
    this.compositor = options.compositor();
    closeSeams(this, options.grid.tileSize);
    this.on("tileunload", (e: L.TileEvent) => {
      this.live.delete(tileKey(e.coords));
    });
  }

  setYear(year: number): void {
    if (year === this.year) return;
    this.year = year;
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      for (const tile of this.live.values()) void this.draw(tile);
    });
  }

  /** How many tiles in view are still waiting for images; 0 once the year is fully drawn. */
  pending(): number {
    let n = 0;
    for (const t of this.live.values()) if (t.canvas.dataset.year !== String(this.year)) n++;
    return n;
  }

  override createTile(coords: L.Coords, done: L.DoneCallback): HTMLElement {
    const canvas = document.createElement("canvas");
    canvas.width = this.era.tilePx;
    canvas.height = this.era.tilePx;
    const tile: LiveTile = {
      canvas,
      level: coords.z + this.era.grid.zoomOffset,
      x: coords.x,
      y: coords.y,
      seq: 0,
    };
    this.live.set(tileKey(coords), tile);
    this.draw(tile).then(
      () => {
        done(undefined, canvas);
      },
      (error: unknown) => {
        done(error instanceof Error ? error : new Error(String(error)), canvas);
      },
    );
    return canvas;
  }

  override onRemove(map: L.Map): this {
    cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.live.clear();
    this.compositor.dispose();
    return super.onRemove(map);
  }

  private async draw(tile: LiveTile): Promise<void> {
    const seq = ++tile.seq;
    const year = this.year;
    const planned = planTile(this.era.manifest, this.era.base, tile.level, tile.x, tile.y, year);
    if (planned.length === 0) {
      tile.canvas.getContext("2d")?.clearRect(0, 0, tile.canvas.width, tile.canvas.height);
      tile.canvas.dataset.year = String(year);
      return;
    }
    /* a pass whose tile is not changing at this year needs one picture, not three or four */
    const plans = planned.some((p) => p.switchMap && !this.ranges.has(p.switchMap.url))
      ? await Promise.all(planned.map((p) => this.narrow(p)))
      : planned.map((p) => this.narrowKnown(p));
    if (seq !== tile.seq) return;
    /* the images this draw holds, so none can drop out of the cache between loading and drawing */
    const images = new Map<string, ImageBitmap | null>();
    const sources = sourcesOf(plans);
    for (const s of sources) {
      const hit = this.era.images.peek(s.url);
      if (hit !== undefined) images.set(s.url, hit);
    }
    if (images.size < new Set(sources.map((s) => s.url)).size) {
      const loaded = await Promise.all(
        sources.map(async (s) => [s.url, await this.era.images.load(s.url, s.kind)] as const),
      );
      if (seq !== tile.seq) return;
      for (const [url, bitmap] of loaded) images.set(url, bitmap);
    }
    if (!this.compositor.ok) {
      this.compositor.dispose();
      this.compositor = this.era.compositor();
    }
    this.compositor.draw(
      tile.canvas,
      plans.map((p) => resolve(p, images)),
    );
    tile.canvas.dataset.year = String(year);
  }

  private async narrow(pass: PassPlan): Promise<PassPlan> {
    const sw = pass.switchMap;
    if (sw && !this.ranges.has(sw.url)) {
      const bitmap = await this.era.images.load(sw.url, "data");
      /* no switch tile: the whole tile changes at the segment's midpoint */
      const pixels = bitmap ? readPixels(bitmap) : null;
      const range = bitmap ? pixels && switchRange(pixels, pass.mid, pass.sw) : { first: pass.mid, last: pass.mid };
      /* a few bytes a tile; a long session that has seen many thousands starts again */
      if (this.ranges.size >= 8192) this.ranges.clear();
      this.ranges.set(sw.url, range);
    }
    return this.narrowKnown(pass);
  }

  private narrowKnown(pass: PassPlan): PassPlan {
    const range = pass.switchMap ? this.ranges.get(pass.switchMap.url) : null;
    return range ? narrowPass(pass, range) : pass;
  }
}

function resolve(p: PassPlan, images: ReadonlyMap<string, ImageBitmap | null>): DrawPass {
  const src = (s: SourceRef | null): DrawSource | null =>
    s ? { image: images.get(s.url) ?? null, window: s.window } : null;
  return {
    from: src(p.from),
    to: src(p.to),
    clear: src(p.clear),
    switchMap: src(p.switchMap),
    sw: p.sw,
    t: p.t,
    mid: p.mid,
  };
}

const tileKey = (c: L.Coords): string => `${c.z}/${c.x}/${c.y}`;
