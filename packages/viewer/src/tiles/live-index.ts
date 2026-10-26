import { type Json, FormatError, int, num, optional, record, pair, str } from "../data/validate";
import { type TileMask, parseTileMask } from "./mask";

/** One zoom level of a painted pyramid, as `index.json` states it. */
export interface PyramidLevel {
  /** tile columns and rows */
  readonly tiles: readonly [number, number];
  /** the level's full size in image pixels */
  readonly px: readonly [number, number];
  /** image pixels per plane unit at this level */
  readonly scale: number;
}

/**
 * A painted pyramid's `index.json`: how its tiles were cut from the renderer's
 * view of the city. `ref` is the camera that framed level 3 (centre in plane
 * units, CSS pixels per plane unit at the renderer's `dpr`).
 */
export interface PyramidIndex {
  /** tile edge in image pixels (512) */
  readonly tile: number;
  /** device pixel ratio the renderer cut at (2) */
  readonly dpr: number;
  readonly ref: { readonly cx: number; readonly cy: number; readonly scale: number };
  readonly levels: ReadonlyMap<number, PyramidLevel>;
  readonly zmax: number;
  /** vertical exaggeration of terrain and the camera's tilt, as rendered */
  readonly proj: { readonly zex: number; readonly sA: number };
  /** build stamp, sent as `?v=` on every tile so a rebuilt pyramid is fetched fresh */
  readonly version: string | undefined;
  /** which tiles exist, when the pyramid publishes it */
  readonly mask: TileMask | undefined;
}

/** The tilt every capture used before pyramids stated their own. */
const DEFAULT_SA = 0.42;

export function parsePyramidIndex(json: Json): PyramidIndex {
  const o = record(json, "index");
  const ref = record(o.ref, "index.ref");
  const levelsJson = record(o.levels, "index.levels");
  const levels = new Map<number, PyramidLevel>();
  for (const [key, value] of Object.entries(levelsJson)) {
    const z = Number(key);
    if (!Number.isInteger(z) || z < 0) throw new FormatError(`index.levels.${key}`, "a level number");
    const l = record(value, `index.levels.${key}`);
    levels.set(z, {
      tiles: pair(l.tiles, `index.levels.${key}.tiles`),
      px: pair(l.px, `index.levels.${key}.px`),
      scale: num(l.scale, `index.levels.${key}.scale`),
    });
  }
  if (!levels.has(0)) throw new FormatError("index.levels", "a level 0");
  const proj = optional(o.proj, (p) => record(p, "index.proj"));
  return {
    tile: int(o.tile, "index.tile"),
    dpr: num(o.dpr, "index.dpr"),
    ref: {
      cx: num(ref.cx, "index.ref.cx"),
      cy: num(ref.cy, "index.ref.cy"),
      scale: num(ref.scale, "index.ref.scale"),
    },
    levels,
    zmax: Math.max(...levels.keys()),
    proj: {
      zex: proj ? num(proj.zex, "index.proj.zex") : 1,
      sA: proj ? (optional(proj.sA, (v) => num(v, "index.proj.sA")) ?? DEFAULT_SA) : DEFAULT_SA,
    },
    version: optional(o.v, (v) => str(v, "index.v")),
    mask: optional(o.have, (v) => parseTileMask(v, "index.have")),
  };
}
