import { type Box, TILE_CSS } from "../tiles/frame";
import { type PyramidRef, tileUrl } from "../tiles/urls";
import type { EraArea, EraManifest, EraSwitch } from "./manifest";
import { midCode, yearCode } from "./switch";
import { areaStateAt } from "./timeline";

/** Part of a tile image to draw: origin and size as fractions of the image. */
export type Window = readonly [x: number, y: number, size: number];

export interface SourceRef {
  readonly url: string;
  readonly kind: "picture" | "data";
  readonly window: Window;
}

/** Everything needed to draw one area onto one tile at one year. */
export interface PassPlan {
  readonly areaId: string;
  readonly from: SourceRef;
  readonly to: SourceRef;
  readonly clear: SourceRef | null;
  readonly switchMap: SourceRef | null;
  readonly sw: Pick<EraSwitch, "encoding" | "scale" | "leadStep">;
  /** the year and the segment midpoint as date codes */
  readonly t: number;
  readonly mid: number;
}

/** Date scale for a segment with no switch map: it changes at its midpoint. */
const NO_SWITCH = { encoding: "c3c", offset: 1800, scale: 100, leadStep: 0 } as const;

/**
 * The passes for tile (z, x, y) at a year, in drawing order. Areas whose box
 * misses the tile, or that show nothing at this year, are left out, so an
 * empty list means the present shows through.
 */
export function planTile(
  manifest: EraManifest,
  base: string,
  z: number,
  x: number,
  y: number,
  year: number,
): PassPlan[] {
  const span = TILE_CSS / 2 ** z;
  const tileBox: Box = [x * span, y * span, (x + 1) * span, (y + 1) * span];
  const passes: PassPlan[] = [];
  for (const area of manifest.areas) {
    if (!overlaps(area.box, tileBox)) continue;
    const plan = planArea(area, manifest.present, base, z, x, y, year);
    if (plan) passes.push(plan);
  }
  return passes;
}

function planArea(area: EraArea, present: PyramidRef, base: string, z: number, x: number, y: number, year: number) {
  const state = areaStateAt(area, year);
  if (state.kind !== "between") return null;
  const sw = state.switch ?? NO_SWITCH;
  const src = (ref: PyramidRef, kind: SourceRef["kind"]) => sourceAt(base, ref, z, x, y, kind);
  return {
    areaId: area.id,
    from: src(state.from.pyramid ?? present, "picture"),
    to: src(state.to.pyramid ?? present, "picture"),
    clear: state.switch?.clear ? src(state.switch.clear, "picture") : null,
    switchMap: state.switch ? src(state.switch, "data") : null,
    sw,
    t: yearCode(year, sw),
    mid: midCode(state.from.year, state.to.year, sw),
  } satisfies PassPlan;
}

/**
 * A tile of `ref`, or, past the pyramid's deepest level, the part of its
 * deepest ancestor tile that covers it (drawn enlarged).
 */
export function sourceAt(
  base: string,
  ref: PyramidRef,
  z: number,
  x: number,
  y: number,
  kind: SourceRef["kind"],
): SourceRef {
  const dz = Math.max(0, z - ref.zmax);
  if (dz === 0) return { url: tileUrl(base, ref, z, x, y), kind, window: [0, 0, 1] };
  const k = 2 ** dz;
  const ax = Math.floor(x / k);
  const ay = Math.floor(y / k);
  return {
    url: tileUrl(base, ref, ref.zmax, ax, ay),
    kind,
    window: [(x - ax * k) / k, (y - ay * k) / k, 1 / k],
  };
}

export function overlaps(a: Box, b: Box): boolean {
  return a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
}

/** Every image a list of passes needs. */
export function sourcesOf(passes: readonly PassPlan[]): SourceRef[] {
  const out: SourceRef[] = [];
  for (const p of passes) {
    out.push(p.from, p.to);
    if (p.clear) out.push(p.clear);
    if (p.switchMap) out.push(p.switchMap);
  }
  return out;
}
