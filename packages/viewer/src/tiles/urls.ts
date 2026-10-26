/** Where a pyramid lives: a key under a release folder, its deepest level, its build stamp and image type. */
export interface PyramidRef {
  readonly key: string;
  readonly zmax: number;
  readonly version: string | undefined;
  readonly ext: "webp" | "png";
}

export function tileUrl(base: string, ref: PyramidRef, z: number, x: number, y: number): string {
  const v = ref.version ? `?v=${encodeURIComponent(ref.version)}` : "";
  return `${trimSlash(base)}/${ref.key}/${z}/${x}/${y}.${ref.ext}${v}`;
}

/** Leaflet's `{z}/{x}/{y}` template for the same tiles. */
export function tileTemplate(base: string, ref: PyramidRef): string {
  const v = ref.version ? `?v=${encodeURIComponent(ref.version)}` : "";
  return `${trimSlash(base)}/${ref.key}/{z}/{x}/{y}.${ref.ext}${v}`;
}

export function trimSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}
