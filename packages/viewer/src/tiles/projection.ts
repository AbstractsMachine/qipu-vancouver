import type { Point } from "../tiles/frame";

/**
 * World metres (x east, y north, z up) to the plane the city was painted on.
 *
 * The renderer's camera looks north, tilted down, so screen x depends on
 * world x alone and screen y on world y and height:
 *
 *   plane x = √2 · cos30° · x
 *   plane y = √2 · sA · y + zex · z
 *
 * `sA` sets how much roof versus wall the tilt shows and `zex` how much the
 * terrain was exaggerated; both are stated in the pyramid's index.json.
 * Because height moves a point up the screen, one screen pixel is a line of
 * world points, and inverting needs the height you are looking for.
 */
export interface Projection {
  toPlane(x: number, y: number, z: number): Point;
  /** the world point at height `z` that lands on a plane point */
  toWorld(px: number, py: number, z: number): Point;
}

const COS30 = Math.cos(Math.PI / 6);

export function projection(proj: { readonly sA: number; readonly zex: number }): Projection {
  const ax = Math.SQRT2 * COS30;
  const by = Math.SQRT2 * proj.sA;
  return {
    toPlane: (x, y, z) => [ax * x, by * y + proj.zex * z],
    toWorld: (px, py, z) => [px / ax, (py - proj.zex * z) / by],
  };
}
