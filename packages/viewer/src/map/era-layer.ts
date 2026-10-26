import * as L from "leaflet";
import type { EraManifest } from "../eras/manifest";
import { type PassPlan, type SourceRef, planTile, sourcesOf } from "../eras/plan";
import type { GridOptions } from "../tiles/levels";
import type { Compositor, DrawPass, DrawSource } from "./compositor";
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
    options.images.onEvict((b) => {
      this.compositor.forget(b);
    });
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
    void this.draw(tile).then(() => {
      done(undefined, canvas);
    });
    return canvas;
  }

  override onRemove(map: L.Map): this {
    cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.live.clear();
    return super.onRemove(map);
  }

  private async draw(tile: LiveTile): Promise<void> {
    const seq = ++tile.seq;
    const year = this.year;
    const plans = planTile(this.era.manifest, this.era.base, tile.level, tile.x, tile.y, year);
    if (plans.length === 0) {
      tile.canvas.getContext("2d")?.clearRect(0, 0, tile.canvas.width, tile.canvas.height);
      tile.canvas.dataset.year = String(year);
      return;
    }
    const sources = sourcesOf(plans);
    if (sources.some((s) => this.era.images.peek(s.url) === undefined)) {
      await Promise.all(sources.map((s) => this.era.images.load(s.url, s.kind)));
      if (seq !== tile.seq) return;
    }
    if (!this.compositor.ok) this.compositor = this.era.compositor();
    this.compositor.draw(
      tile.canvas,
      plans.map((p) => this.resolve(p)),
    );
    tile.canvas.dataset.year = String(year);
  }

  private resolve(p: PassPlan): DrawPass {
    const src = (s: SourceRef | null): DrawSource | null =>
      s ? { image: this.era.images.peek(s.url) ?? null, window: s.window } : null;
    return {
      from: src(p.from) ?? { image: null, window: p.from.window },
      to: src(p.to) ?? { image: null, window: p.to.window },
      clear: src(p.clear),
      switchMap: src(p.switchMap),
      sw: p.sw,
      t: p.t,
      mid: p.mid,
    };
  }
}

const tileKey = (c: L.Coords): string => `${c.z}/${c.x}/${c.y}`;
