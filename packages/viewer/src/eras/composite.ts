import type { EraSwitch } from "./model";
import { decodeSwitchPixel, pixelWeights } from "./switch";

/**
 * One area's contribution to one tile at one year: the pictures it mixes and
 * the switch map that says how. Images are RGBA, the same size, and `null`
 * where the tile does not exist (transparent).
 */
export interface AreaPass {
  readonly from: ImageLike | null;
  readonly to: ImageLike | null;
  /** c3d's cleared site; missing or transparent pixels fall back to `from` */
  readonly clear: ImageLike | null;
  /** null: the whole tile switches at `mid` */
  readonly switchMap: ImageLike | null;
  readonly sw: Pick<EraSwitch, "encoding" | "scale" | "leadStep">;
  /** the year as a date code, and the segment's midpoint */
  readonly t: number;
  readonly mid: number;
}

/** The pixels of one tile, as `ImageData` holds them (not premultiplied). */
export interface ImageLike {
  readonly width: number;
  readonly height: number;
  readonly data: Uint8ClampedArray;
}

/**
 * The CPU compositor: draws the passes in order, each over the one before,
 * into `out`. Used where WebGL is missing and by the tests; the GL path in
 * `gl-compositor.ts` computes the same thing.
 */
export function compositeTile(out: ImageLike, passes: readonly AreaPass[]): void {
  const o = out.data;
  o.fill(0);
  for (const pass of passes) blendPass(o, pass, out.width * out.height);
}

function blendPass(o: Uint8ClampedArray, p: AreaPass, n: number): void {
  const A = p.from?.data;
  const B = p.to?.data;
  const C = p.clear?.data;
  const D = p.switchMap?.data;
  const hardTo = p.t >= p.mid ? 1 : 0;
  for (let i = 0; i < n; i++) {
    const j = i * 4;
    let wFrom: number;
    let wClear = 0;
    let wTo: number;
    if (D) {
      const px = decodeSwitchPixel(D[j] as number, D[j + 1] as number, D[j + 2] as number, p.mid, p.sw);
      const w = pixelWeights(p.t, px);
      wFrom = w.from;
      wClear = w.clear;
      wTo = w.to;
    } else {
      wFrom = 1 - hardTo;
      wTo = hardTo;
    }
    /* the cleared site only counts where it was painted */
    if (wClear > 0 && (!C || (C[j + 3] as number) < 128)) {
      wFrom += wClear;
      wClear = 0;
    }
    let r = 0;
    let g = 0;
    let b = 0;
    let a = 0;
    if (wFrom > 0 && A) [r, g, b, a] = addPremul(r, g, b, a, A, j, wFrom);
    if (wClear > 0 && C) [r, g, b, a] = addPremul(r, g, b, a, C, j, wClear);
    if (wTo > 0 && B) [r, g, b, a] = addPremul(r, g, b, a, B, j, wTo);
    if (a <= 0) continue;
    /* source over what earlier passes drew, in premultiplied space */
    const da = (o[j + 3] as number) / 255;
    const keep = 1 - a;
    const outA = a + da * keep;
    o[j] = Math.round(((r + ((o[j] as number) / 255) * da * keep) / outA) * 255);
    o[j + 1] = Math.round(((g + ((o[j + 1] as number) / 255) * da * keep) / outA) * 255);
    o[j + 2] = Math.round(((b + ((o[j + 2] as number) / 255) * da * keep) / outA) * 255);
    o[j + 3] = Math.round(outA * 255);
  }
}

function addPremul(
  r: number,
  g: number,
  b: number,
  a: number,
  src: Uint8ClampedArray,
  j: number,
  w: number,
): [number, number, number, number] {
  const sa = ((src[j + 3] as number) / 255) * w;
  return [
    r + ((src[j] as number) / 255) * sa,
    g + ((src[j + 1] as number) / 255) * sa,
    b + ((src[j + 2] as number) / 255) * sa,
    a + sa,
  ];
}
