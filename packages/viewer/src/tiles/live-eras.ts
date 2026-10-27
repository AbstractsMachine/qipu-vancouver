import { type Json, FormatError, int, isRecord, list, num, optional, quad, record, str } from "../data/validate";
import type { EraArea, EraKey, EraManifest, EraSwitch } from "../eras/model";
import { level9BoxToFrame } from "./frame";
import { type PyramidRef, keyTemplate } from "./urls";

/** How to read a live eras manifest. */
export interface LiveErasOptions {
  /** the pyramids' tile size in image pixels, for converting area boxes */
  readonly tile?: number;
  /** keep eras the manifest marks as not yet public */
  readonly includeUnpublished?: boolean;
}

/**
 * The live site's eras manifest (`_preview_eras/render-years.json`): the
 * present, the whole-city key years, and "quarters", areas painted at their
 * own key years with their own switch maps. Area boxes are in level-9 image
 * pixels; pyramids are named by key. Throws a `FormatError` naming the field
 * that is wrong.
 */
export function parseLiveEras(json: Json, options: LiveErasOptions = {}): EraManifest {
  const o = record(json, "eras");
  const present = pyramidRef(o.now, "eras.now", "webp");
  const years = record(o.years ?? {}, "eras.years");
  const keyYears = Object.entries(years)
    .filter(([, v]) => options.includeUnpublished || !isRecord(v) || v.public !== false)
    .map(([y]) => yearKey(y, "eras.years"))
    .sort((a, b) => a - b);

  const quarters = record(o.quarters ?? {}, "eras.quarters");
  const areas = Object.entries(quarters).map(([id, q]) => parseArea(id, q, options.tile ?? 512));
  if (keyYears.length === 0 && areas.length === 0) throw new FormatError("eras", "at least one year or quarter");
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
    holdsFirstKey: false,
  };
}

function parseSwitch(json: Json, path: string): EraSwitch {
  const s = record(json, path);
  const enc = optional(s.enc, (v) => str(v, `${path}.enc`)) ?? "c3";
  if (enc !== "c3" && enc !== "c3c" && enc !== "c3d") {
    throw new FormatError(`${path}.enc`, `"c3", "c3c" or "c3d" (got "${enc}")`);
  }
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
    template: keyTemplate(str(o.key, `${path}.key`), e),
    zmax: int(o.zmax, `${path}.zmax`),
    version: optional(o.v, (v) => str(v, `${path}.v`)),
  };
}

function yearKey(text: string, path: string): number {
  const y = Number(text);
  if (!Number.isInteger(y)) throw new FormatError(`${path}.${text}`, "a year");
  return y;
}
