import type { TileMask } from "./mask";

/** One pyramid of tiles under a release folder. */
export interface PyramidRef {
  /** path under the release folder with `{z}`, `{x}` and `{y}`, e.g. `today/{z}/{x}/{y}.webp` */
  readonly template: string;
  /** its deepest level; past it the viewer enlarges the deepest tiles */
  readonly zmax: number;
  /** build stamp, sent as `?v=` so a re-published pyramid is fetched fresh */
  readonly version: string | undefined;
  /** which tiles exist, where the pyramid says */
  readonly mask?: TileMask | undefined;
}

export function tileUrl(base: string, ref: PyramidRef, z: number, x: number, y: number): string {
  const path = ref.template.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
  return `${trimSlash(base)}/${path}${versionQuery(ref)}`;
}

/** Leaflet's URL template for the same tiles. */
export function tileTemplate(base: string, ref: PyramidRef): string {
  return `${trimSlash(base)}/${ref.template}${versionQuery(ref)}`;
}

/** The live qipu.org layout: `<key>/{z}/{x}/{y}.<ext>`. */
export function keyTemplate(key: string, ext: "webp" | "png"): string {
  return `${key}/{z}/{x}/{y}.${ext}`;
}

export function trimSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

const versionQuery = (ref: PyramidRef): string => (ref.version ? `?v=${encodeURIComponent(ref.version)}` : "");
