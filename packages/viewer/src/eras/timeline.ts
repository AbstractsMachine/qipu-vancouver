import { type EraArea, type EraKey, type EraSwitch, segmentName } from "./manifest";

/** What an area shows at a year. */
export type AreaState =
  /** before its first key: nothing, the layers under it show */
  | { readonly kind: "empty" }
  /** at or after the present: nothing, the present pyramid shows */
  | { readonly kind: "present" }
  /** between two keys, `from` changing into `to` pixel by pixel */
  | {
      readonly kind: "between";
      readonly from: EraKey;
      readonly to: EraKey;
      /** absent where the pipeline wrote no switch map: the area changes at the midpoint */
      readonly switch: EraSwitch | undefined;
    };

export function areaStateAt(area: EraArea, year: number): AreaState {
  const keys = area.keys;
  const first = keys[0];
  const last = keys.at(-1);
  if (!first || !last || keys.length < 2) return { kind: "empty" };
  if (year < first.year) return { kind: "empty" };
  if (year >= last.year) return { kind: "present" };
  let i = 0;
  while (i + 2 < keys.length && year >= (keys[i + 1] as EraKey).year) i++;
  const from = keys[i] as EraKey;
  const to = keys[i + 1] as EraKey;
  return { kind: "between", from, to, switch: area.switches.get(segmentName(from.year, to.year)) };
}

/** Clamp and round a slider value to the year the map can show. */
export function clampYear(year: number, first: number, present: number): number {
  if (!Number.isFinite(year)) return present;
  return Math.min(present, Math.max(first, Math.round(year)));
}

/**
 * Tick marks for the slider: the key years, thinned so no two are closer than
 * `minGap` years, always keeping the first and the present.
 */
export function sliderTicks(keyYears: readonly number[], first: number, present: number, minGap = 8): number[] {
  const inner = keyYears.filter((y) => y > first && y < present).sort((a, b) => a - b);
  const out = [first];
  for (const y of inner) if (y - (out.at(-1) as number) >= minGap) out.push(y);
  if (out.length > 1 && present - (out.at(-1) as number) < minGap) out.pop();
  if (present > first) out.push(present);
  return out;
}
