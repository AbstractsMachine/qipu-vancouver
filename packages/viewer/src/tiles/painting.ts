import type { EraManifest } from "../eras/model";
import { type Point, TILE_CSS } from "./frame";
import type { PyramidRef } from "./urls";

/**
 * A painted city as the map draws it, whichever format it was published in
 * (`qipu-tiles.ts` for the pipeline's qipu-tiles/1, `live-index.ts` and
 * `live-eras.ts` for what qipu.org serves today).
 *
 * Everything is placed in one frame: level-0 CSS pixels, y down, origin at the
 * top-left of level 0. Level z is that frame scaled by 2^z, cut into tiles of
 * `TILE_CSS` CSS pixels (`tile` image pixels).
 */
export interface Painting {
  readonly format: "qipu-tiles/1" | "qipu.org";
  /** tile edge in image pixels */
  readonly tile: number;
  /** level 0's size in CSS pixels */
  readonly width: number;
  readonly height: number;
  readonly present: PyramidRef;
  /** null for a painting with no past: the map then has no year slider */
  readonly eras: EraManifest | null;
  /**
   * Where a point of the city lands on the picture: world metres (x east,
   * y north, z up) to the frame. The camera looks north and down, so height
   * moves a point up the picture.
   */
  readonly worldToFrame: (x: number, y: number, z: number) => Point;
  readonly attribution: readonly string[];
}

/** Tile columns and rows at level `z`. */
export function tilesAt(painting: Pick<Painting, "width" | "height">, z: number): [number, number] {
  const k = 2 ** z / TILE_CSS;
  return [Math.ceil(painting.width * k), Math.ceil(painting.height * k)];
}

export function presentTileExists(painting: Painting, z: number, x: number, y: number): boolean {
  const [cols, rows] = tilesAt(painting, z);
  if (z < 0 || z > painting.present.zmax || x < 0 || y < 0 || x >= cols || y >= rows) return false;
  return painting.present.mask?.has(z, x, y) ?? true;
}
