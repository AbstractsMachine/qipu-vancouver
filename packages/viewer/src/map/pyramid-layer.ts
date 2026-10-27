import * as L from "leaflet";
import type { GridOptions } from "../tiles/levels";
import { type Painting, presentTileExists } from "../tiles/painting";
import { tileTemplate } from "../tiles/urls";
import { clipToPainting } from "./extent";
import { closeSeams } from "./seams";

export interface PyramidLayerOptions {
  readonly base: string;
  readonly painting: Painting;
  readonly grid: GridOptions;
  readonly bounds: L.LatLngBounds;
  readonly attribution: string;
}

/**
 * The present-day painting, as plain <img> tiles. Tiles outside a level's
 * grid, or missing from the pyramid's published mask, are never requested.
 */
export class PyramidLayer extends L.TileLayer {
  private readonly painting: Painting;
  private readonly offset: number;

  constructor(options: PyramidLayerOptions) {
    super(tileTemplate(options.base, options.painting.present), {
      tileSize: options.grid.tileSize,
      zoomOffset: options.grid.zoomOffset,
      minNativeZoom: -options.grid.zoomOffset,
      maxNativeZoom: options.painting.present.zmax - options.grid.zoomOffset,
      bounds: options.bounds,
      noWrap: true,
      keepBuffer: 2,
      crossOrigin: "anonymous",
      attribution: options.attribution,
      className: "qv-present-layer",
    });
    this.painting = options.painting;
    this.offset = options.grid.zoomOffset;
    closeSeams(this, options.grid.tileSize);
    clipToPainting(this, options.painting, options.grid.zoomOffset);
  }

  override createTile(coords: L.Coords, done: L.DoneCallback): HTMLElement {
    if (!presentTileExists(this.painting, coords.z + this.offset, coords.x, coords.y)) {
      const empty = document.createElement("div");
      queueMicrotask(() => {
        done(undefined, empty);
      });
      return empty;
    }
    return super.createTile(coords, done);
  }
}
