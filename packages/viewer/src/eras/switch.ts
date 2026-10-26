import type { EraSwitch } from "./manifest";

/**
 * The per-pixel switch, written once in TypeScript. The WebGL shader in
 * `map/gl-compositor.ts` is a line-for-line port and the CPU compositor calls this
 * directly, so the tests here pin down what both draw.
 *
 * A switch pixel stores a date code in red and green (`r * 256 + g`), where a
 * code is `(year - offset) * scale`. 0 means "switches at the segment's
 * midpoint" and 65535 "never switches". In c3c and c3d, blue holds two 4-bit
 * fields: the low one is the fade length (0 = a hard switch, else
 * 0.0015 * 2^(w - 1) years), the high one (c3d only) a lead in `leadStep`
 * years during which the cleared site shows before the new building appears.
 * In the older c3 form blue is the fade alone, in steps of 0.005 years.
 */
export interface SwitchPixel {
  /** date code from which the later picture shows */
  readonly date: number;
  /** fade length in date-code units, 0 for a hard switch */
  readonly fade: number;
  /** how long before `date` the cleared site shows, in date-code units */
  readonly lead: number;
}

export const NEVER = 1e9;

export function yearCode(year: number, sw: Pick<EraSwitch, "offset" | "scale">): number {
  return (year - sw.offset) * sw.scale;
}

/** The date code of the midpoint between two key years. */
export function midCode(fromYear: number, toYear: number, sw: Pick<EraSwitch, "offset" | "scale">): number {
  return yearCode((fromYear + toYear) / 2, sw);
}

export function decodeSwitchPixel(
  r: number,
  g: number,
  b: number,
  mid: number,
  sw: Pick<EraSwitch, "encoding" | "scale" | "leadStep">,
): SwitchPixel {
  const code = r * 256 + g;
  const date = code === 0 ? mid : code === 65535 ? NEVER : code;
  if (sw.encoding === "c3") return { date, fade: b * 0.005 * sw.scale, lead: 0 };
  const w = b & 15;
  const fade = w > 0 ? 0.0015 * 2 ** (w - 1) * sw.scale : 0;
  const lead = sw.encoding === "c3d" ? (b >> 4) * sw.leadStep * sw.scale : 0;
  return { date, fade, lead };
}

/**
 * How far a pixel has gone from one picture to the next at year code `t`:
 * 0 before its date, 1 after, and inside a fade an S-curve that keeps the two
 * pictures overlapping only for the middle fifth, so a building never shows
 * as a see-through ghost of itself.
 */
export function progress(t: number, date: number, fade: number): number {
  if (fade <= 0) return t >= date ? 1 : 0;
  const u = Math.min(1, Math.max(0, (t - date) / fade));
  return smoothstep(0.4, 0.6, u);
}

export function smoothstep(e0: number, e1: number, x: number): number {
  const u = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return u * u * (3 - 2 * u);
}

/**
 * The weights of the three pictures a pixel can show at year code `t`:
 * the earlier key, the cleared site and the later key. They sum to 1.
 */
export function pixelWeights(t: number, px: SwitchPixel): { from: number; clear: number; to: number } {
  const toW = progress(t, px.date, px.fade);
  const clearW = px.lead > 0 ? progress(t, px.date - px.lead, px.fade) : 0;
  return { from: (1 - clearW) * (1 - toW), clear: clearW * (1 - toW), to: toW };
}
