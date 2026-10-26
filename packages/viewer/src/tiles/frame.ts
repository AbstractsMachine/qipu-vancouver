import type { PyramidIndex } from "./pyramid";

/** A tile is shown at this many CSS pixels, half its image size, so it is sharp on a 2x screen. */
export const TILE_CSS = 256;

export type Point = readonly [number, number];

/**
 * The pyramid's frame: level-0 CSS pixels, y down, origin at the top-left of
 * level 0. Leaflet's CRS.Simple maps it as (lat, lng) = (-Y, X).
 *
 * The renderer put `ref` at the centre of every level, `ref.scale` CSS pixels
 * per plane unit at level 3. Plane y runs up, frame y runs down.
 */
export interface Frame {
  /** CSS pixels per plane unit at level 0 */
  readonly s0: number;
  /** level 0's size in CSS pixels */
  readonly width: number;
  readonly height: number;
  readonly zmax: number;
  toFrame(plane: Point): Point;
  toPlane(frame: Point): Point;
  /** CSS pixels per plane unit at a (fractional) zoom */
  scaleAt(zoom: number): number;
}

export function frameOf(index: PyramidIndex): Frame {
  const level0 = index.levels.get(0);
  if (!level0) throw new Error("pyramid has no level 0");
  const shown = (index.dpr * TILE_CSS) / index.tile;
  const s0 = (index.ref.scale * shown) / 2 ** 3;
  const width = (level0.px[0] * TILE_CSS) / index.tile;
  const height = (level0.px[1] * TILE_CSS) / index.tile;
  const { cx, cy } = index.ref;
  return {
    s0,
    width,
    height,
    zmax: index.zmax,
    toFrame: ([px, py]) => [(px - cx) * s0 + width / 2, height / 2 - (py - cy) * s0],
    toPlane: ([x, y]) => [cx + (x - width / 2) / s0, cy + (height / 2 - y) / s0],
    scaleAt: (zoom) => s0 * 2 ** zoom,
  };
}

/** A box in level-9 image pixels (how era areas state their extent) in frame units. */
export type Box = readonly [number, number, number, number];

export function level9BoxToFrame(box: Box, tile = 512): Box {
  /* level 9 is 2^9 times level 0, and these are image pixels, `tile / TILE_CSS` per CSS pixel */
  const k = 2 ** 9 * (tile / TILE_CSS);
  return [box[0] / k, box[1] / k, box[2] / k, box[3] / k];
}

/** The tiles of level `z` a frame box touches, as inclusive tile ranges. */
export function tilesInBox(box: Box, z: number): { x0: number; y0: number; x1: number; y1: number } {
  const k = 2 ** z / TILE_CSS;
  return {
    x0: Math.floor(box[0] * k),
    y0: Math.floor(box[1] * k),
    x1: Math.ceil(box[2] * k) - 1,
    y1: Math.ceil(box[3] * k) - 1,
  };
}
