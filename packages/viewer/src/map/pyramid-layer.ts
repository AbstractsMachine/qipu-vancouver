import * as L from "leaflet";
import type { PyramidIndex } from "../tiles/pyramid";
import type { GridOptions } from "../tiles/levels";

export interface PyramidLayerOptions {
  readonly template: string;
  readonly index: PyramidIndex;
  readonly grid: GridOptions;
  readonly bounds: L.LatLngBounds;
  readonly attribution: string;
}

/**
 * The present-day painting, as plain <img> tiles. Tiles outside a level's
 * grid, or missing from the pyramid's published mask, are never requested.
 */
export class PyramidLayer extends L.TileLayer {
  private readonly index: PyramidIndex;
  private readonly offset: number;

  constructor(options: PyramidLayerOptions) {
    super(options.template, {
      tileSize: options.grid.tileSize,
      zoomOffset: options.grid.zoomOffset,
      minNativeZoom: -options.grid.zoomOffset,
      maxNativeZoom: options.index.zmax - options.grid.zoomOffset,
      bounds: options.bounds,
      noWrap: true,
      keepBuffer: 2,
      crossOrigin: "anonymous",
      attribution: options.attribution,
      className: "qv-present-layer",
    });
    this.index = options.index;
    this.offset = options.grid.zoomOffset;
  }

  override createTile(coords: L.Coords, done: L.DoneCallback): HTMLElement {
    if (!this.exists(coords.z + this.offset, coords.x, coords.y)) {
      const empty = document.createElement("div");
      queueMicrotask(() => {
        done(undefined, empty);
      });
      return empty;
    }
    return super.createTile(coords, done);
  }

  private exists(level: number, x: number, y: number): boolean {
    const l = this.index.levels.get(level);
    if (!l || x < 0 || y < 0 || x >= l.tiles[0] || y >= l.tiles[1]) return false;
    return this.index.mask?.has(level, x, y) ?? true;
  }
}
