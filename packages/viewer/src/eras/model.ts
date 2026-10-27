import type { Box } from "../tiles/frame";
import type { PyramidRef } from "../tiles/urls";

/**
 * The past, as the viewer models it, whichever format it was read from: the
 * city split into areas, each painted at a few key years. Between two key
 * years a switch map stores, per pixel, the date that pixel changes from the
 * earlier picture to the later one, so the slider rebuilds the city one
 * building at a time instead of cross-fading whole pictures.
 */
export interface EraManifest {
  /** the present-day pyramid, which every area ends on */
  readonly present: PyramidRef;
  /** the earliest year the slider offers */
  readonly firstYear: number;
  /** the year of the present pyramid */
  readonly presentYear: number;
  /** key years across all areas, for the slider's tick marks */
  readonly keyYears: readonly number[];
  /** drawn in this order, each over the one before */
  readonly areas: readonly EraArea[];
}

export interface EraKey {
  readonly year: number;
  /** null for the present, which is drawn from the present pyramid */
  readonly pyramid: PyramidRef | null;
}

/**
 * How a switch map packs a date (see `switch.ts`):
 *   c3, c3c, c3d   the live qipu.org forms; date code 0 means "at the midpoint"
 *   q1             qipu-tiles/1: every code is a date, blue is unused
 */
export type SwitchEncoding = "c3" | "c3c" | "c3d" | "q1";

export interface EraSwitch extends PyramidRef {
  readonly encoding: SwitchEncoding;
  /** a date code is `(year - offset) * scale` */
  readonly offset: number;
  readonly scale: number;
  /** c3d: years per step of a pixel's lead (when the cleared site shows) */
  readonly leadStep: number;
  /** c3d: the site with the old building gone and the new one not yet built */
  readonly clear: PyramidRef | undefined;
}

export interface EraArea {
  readonly id: string;
  readonly name: string;
  /** extent in frame units (level-0 CSS pixels) */
  readonly box: Box;
  /** ascending; the last is the present */
  readonly keys: readonly EraKey[];
  /** switch maps by segment name, `"1906-1915"` */
  readonly switches: ReadonlyMap<string, EraSwitch>;
  /** before its first key the area shows that key (qipu-tiles/1) rather than nothing (live) */
  readonly holdsFirstKey: boolean;
}

export const segmentName = (a: number, b: number): string => `${a}-${b}`;
