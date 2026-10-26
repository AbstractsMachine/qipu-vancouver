import {
  type Json,
  FormatError,
  int,
  isRecord,
  list,
  num,
  optional,
  record,
  str,
  quad,
} from "../data/validate";
import { type Box, level9BoxToFrame } from "../tiles/frame";
import type { PyramidRef } from "../tiles/urls";

/**
 * The eras manifest (`render-years.json`): the present pyramid, and the city
 * split into areas, each painted at a few key years. Between two key years a
 * "switch" pyramid stores, per pixel, the date that pixel changes from the
 * earlier picture to the later one, so a year slider can rebuild the city one
 * building at a time instead of cross-fading whole pictures.
 */
export interface EraManifest {
  readonly present: PyramidRef;
  /** the earliest year the slider offers */
  readonly firstYear: number;
  /** the year of the present pyramid */
  readonly presentYear: number;
  /** key years across all areas, for the slider's tick marks */
  readonly keyYears: readonly number[];
  readonly areas: readonly EraArea[];
}

export interface EraKey {
  readonly year: number;
  /** null for the present, which is drawn from the present pyramid */
  readonly pyramid: PyramidRef | null;
}

export type SwitchEncoding = "c3c" | "c3d";

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
  /** switch pyramids by segment name, `"1906-1915"` */
  readonly switches: ReadonlyMap<string, EraSwitch>;
}

export interface ParseOptions {
  /** the pyramids' tile size in image pixels, for converting area boxes */
  readonly tile?: number;
  /** keep eras the manifest marks as not yet public */
  readonly includeUnpublished?: boolean;
}

export const segmentName = (a: number, b: number): string => `${a}-${b}`;

export function parseEraManifest(json: Json, options: ParseOptions = {}): EraManifest {
  const o = record(json, "eras");
  const present = pyramidRef(o.now, "eras.now", "webp");
  const years = record(o.years ?? {}, "eras.years");
  const keyYears = Object.entries(years)
    .filter(([, v]) => options.includeUnpublished || !isRecord(v) || v.public !== false)
    .map(([y]) => yearKey(y, "eras.years"))
    .sort((a, b) => a - b);

  const quarters = record(o.quarters ?? {}, "eras.quarters");
  const areas = Object.entries(quarters).map(([id, q]) => parseArea(id, q, options.tile ?? 512));
  const presentYear = Math.max(...areas.map((a) => a.keys.at(-1)?.year ?? 0), ...keyYears);
  const firstYear = optional(o.min, (v) => int(v, "eras.min")) ?? Math.min(...keyYears, presentYear);
  return { present, firstYear, presentYear, keyYears, areas };
}

function parseArea(id: string, json: Json, tile: number): EraArea {
  const p = `eras.quarters.${id}`;
  const q = record(json, p);
  const keysJson = record(q.keys ?? {}, `${p}.keys`);
  const years = list(q.years, `${p}.years`).map((y, i) =>
    int(record(y, `${p}.years[${i}]`).year, `${p}.years[${i}].year`),
  );
  if (years.length < 2) throw new FormatError(`${p}.years`, "at least a key year and the present");
  const last = years.length - 1;
  const keys: EraKey[] = [];
  years.forEach((year, i) => {
    const k = keysJson[String(year)];
    if (k !== undefined) keys.push({ year, pyramid: pyramidRef(k, `${p}.keys.${year}`, "webp") });
    else if (i === last) keys.push({ year, pyramid: null });
  });
  keys.sort((a, b) => a.year - b.year);

  const switches = new Map<string, EraSwitch>();
  for (const [name, s] of Object.entries(record(q.switch ?? {}, `${p}.switch`))) {
    switches.set(name, parseSwitch(s, `${p}.switch.${name}`));
  }
  return {
    id,
    name: optional(q.name, (v) => str(v, `${p}.name`)) ?? id,
    box: level9BoxToFrame(quad(q.l9, `${p}.l9`), tile),
    keys,
    switches,
  };
}

function parseSwitch(json: Json, path: string): EraSwitch {
  const s = record(json, path);
  const enc = str(s.enc, `${path}.enc`);
  if (enc !== "c3c" && enc !== "c3d") throw new FormatError(`${path}.enc`, `"c3c" or "c3d" (got "${enc}")`);
  return {
    ...pyramidRef(s, path, "png"),
    encoding: enc,
    offset: optional(s.offset, (v) => num(v, `${path}.offset`)) ?? 1800,
    scale: optional(s.scale, (v) => num(v, `${path}.scale`)) ?? 100,
    leadStep: optional(s.leadStep, (v) => num(v, `${path}.leadStep`)) ?? 0.2,
    clear: optional(s.clear, (v) => pyramidRef(v, `${path}.clear`, "webp")),
  };
}

function pyramidRef(json: Json, path: string, ext: "webp" | "png"): PyramidRef {
  const o = record(json, path);
  const e = optional(o.ext, (v) => str(v, `${path}.ext`)) ?? ext;
  if (e !== "webp" && e !== "png") throw new FormatError(`${path}.ext`, '"webp" or "png"');
  return {
    key: str(o.key, `${path}.key`),
    zmax: int(o.zmax, `${path}.zmax`),
    version: optional(o.v, (v) => str(v, `${path}.v`)),
    ext: e,
  };
}

function yearKey(text: string, path: string): number {
  const y = Number(text);
  if (!Number.isInteger(y)) throw new FormatError(`${path}.${text}`, "a year");
  return y;
}
