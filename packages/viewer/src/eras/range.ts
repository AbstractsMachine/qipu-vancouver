import type { EraSwitch } from "./model";
import type { PassPlan } from "./plan";
import { NEVER, decodeSwitchPixel } from "./switch";

/** The span of date codes over which any pixel of a switch tile is changing. */
export interface SwitchRange {
  /** before this nothing in the tile has started to change */
  readonly first: number;
  /** from this on every pixel has finished changing */
  readonly last: number;
}

/**
 * Scan a switch tile once. Most tiles change over a few years of a segment
 * that spans decades, and at any year outside that span the tile shows one
 * picture whole, so the other one need not be fetched at all.
 */
export function switchRange(
  data: Uint8ClampedArray,
  mid: number,
  sw: Pick<EraSwitch, "encoding" | "scale" | "leadStep">,
): SwitchRange {
  let first = Number.POSITIVE_INFINITY;
  let last = Number.NEGATIVE_INFINITY;
  for (let j = 0; j < data.length; j += 4) {
    const px = decodeSwitchPixel(data[j] as number, data[j + 1] as number, data[j + 2] as number, mid, sw);
    if (px.date >= NEVER) continue;
    first = Math.min(first, px.date - px.lead);
    last = Math.max(last, px.date + px.fade);
  }
  return { first, last };
}

/** A pass reduced to the one picture it shows when the year is outside its tile's range. */
export function narrowPass(pass: PassPlan, range: SwitchRange): PassPlan {
  if (pass.t < range.first) return whole(pass, pass.from);
  if (pass.t >= range.last) return whole(pass, pass.to);
  return pass;
}

function whole(pass: PassPlan, picture: PassPlan["from"]): PassPlan {
  return { ...pass, from: picture, to: picture, clear: null, switchMap: null, t: 1, mid: 0 };
}
