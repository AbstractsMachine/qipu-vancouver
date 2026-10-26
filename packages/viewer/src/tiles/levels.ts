import { TILE_CSS } from "./frame";

/**
 * Which pyramid level a screen should load. A tile holds two image pixels per
 * CSS pixel, so a 2x or 3x screen loads the level matching the zoom and a 1x
 * screen (most desktop monitors) loads one level coarser: the same picture on
 * that screen for a quarter of the bytes.
 *
 * Returned as Leaflet grid options: the coarser level is a 512 px tile asked
 * for one zoom down.
 */
export interface GridOptions {
  readonly tileSize: number;
  readonly zoomOffset: number;
}

export function gridOptionsFor(devicePixelRatio: number): GridOptions {
  return devicePixelRatio < 1.5
    ? { tileSize: TILE_CSS * 2, zoomOffset: -1 }
    : { tileSize: TILE_CSS, zoomOffset: 0 };
}

/** The level a grid loads at a map zoom, clamped to the pyramid. */
export function levelAt(zoom: number, grid: GridOptions, zmax: number): number {
  return Math.max(0, Math.min(zmax, Math.round(zoom) + grid.zoomOffset));
}

/**
 * How many tiles a viewport needs at a zoom, the number the performance budget
 * is stated in. A view rarely aligns with the grid, hence the extra row and column.
 */
export function tilesForViewport(width: number, height: number, grid: GridOptions): number {
  const cols = Math.ceil(width / grid.tileSize) + 1;
  const rows = Math.ceil(height / grid.tileSize) + 1;
  return cols * rows;
}
