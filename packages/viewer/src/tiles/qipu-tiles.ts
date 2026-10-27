import { type Json, FormatError, int, list, num, numbers, optional, record, str, strings } from "../data/validate";
import { type EraKey, type EraManifest, type EraSwitch, segmentName } from "../eras/model";
import { TILE_CSS } from "./frame";
import { parseTileMask } from "./mask";
import type { Painting } from "./painting";
import type { PyramidRef } from "./urls";

export const QIPU_TILES = "qipu-tiles/1";

/**
 * A release in the format `packages/map-pipeline` writes (docs/tiles-format.md):
 * one manifest with the canvas, a world-to-pixel matrix, today, the past
 * years and a switch map between each consecutive pair.
 */
export function parseQipuTiles(json: Json): Painting {
  const o = record(json, "manifest");
  const format = str(o.format, "manifest.format");
  if (format !== QIPU_TILES) throw new FormatError("manifest.format", `"${QIPU_TILES}" (got "${format}")`);
  const tile = int(o.tile_size, "manifest.tile_size");
  const canvas = record(o.canvas, "manifest.canvas");
  const zmax = int(canvas.zmax, "manifest.canvas.zmax");
  /* canvas pixels at zmax to level-0 CSS pixels */
  const k = TILE_CSS / tile / 2 ** zmax;
  const m = matrix(o.world_to_px);

  const today = record(o.today, "manifest.today");
  const present = layer(today, "manifest.today");
  const presentYear = int(today.year, "manifest.today.year");
  const width = int(canvas.width, "manifest.canvas.width") * k;
  const height = int(canvas.height, "manifest.canvas.height") * k;

  const years = list(o.years ?? [], "manifest.years").map((y, i) => {
    const p = `manifest.years[${i}]`;
    const r = record(y, p);
    return { year: num(r.year, `${p}.year`), pyramid: layer(r, p) };
  });
  years.sort((a, b) => a.year - b.year);

  return {
    format: QIPU_TILES,
    tile,
    width,
    height,
    present,
    eras: years.length ? eras(o, present, presentYear, years, width, height) : null,
    worldToFrame: (x, y, z) => [
      (m[0] * x + m[1] * y + m[2] * z + m[3]) * k,
      (m[4] * x + m[5] * y + m[6] * z + m[7]) * k,
    ],
    attribution: optional(o.attribution, (v) => strings(v, "manifest.attribution")) ?? [],
  };
}

function eras(
  o: Record<string, Json>,
  present: PyramidRef,
  presentYear: number,
  years: readonly { year: number; pyramid: PyramidRef }[],
  width: number,
  height: number,
): EraManifest {
  const keys: EraKey[] = [...years, { year: presentYear, pyramid: null }];
  const switches = new Map<string, EraSwitch>();
  list(o.switch ?? [], "manifest.switch").forEach((s, i) => {
    const p = `manifest.switch[${i}]`;
    const r = record(s, p);
    switches.set(segmentName(num(r.from, `${p}.from`), num(r.to, `${p}.to`)), {
      ...layer(r, p),
      encoding: "q1",
      offset: 1800,
      scale: 100,
      leadStep: 0,
      clear: undefined,
    });
  });
  const keyYears = years.map((y) => y.year);
  return {
    present,
    firstYear: Math.floor(keyYears[0] ?? presentYear),
    presentYear,
    keyYears,
    areas: [
      {
        id: optional(o.area, (v) => str(v, "manifest.area")) ?? "city",
        name: optional(o.area, (v) => str(v, "manifest.area")) ?? "city",
        box: [0, 0, width, height],
        keys,
        switches,
        holdsFirstKey: true,
      },
    ],
  };
}

function layer(r: Record<string, Json>, p: string): PyramidRef {
  return {
    template: str(r.path, `${p}.path`),
    zmax: int(r.zmax, `${p}.zmax`),
    version: optional(r.v, (v) => str(v, `${p}.v`)),
    mask: optional(r.have, (v) => parseTileMask(v, `${p}.have`, "absent")),
  };
}

function matrix(json: Json): [number, number, number, number, number, number, number, number] {
  const rows = list(json, "manifest.world_to_px");
  const a = numbers(rows[0], "manifest.world_to_px[0]");
  const b = numbers(rows[1], "manifest.world_to_px[1]");
  if (rows.length !== 2 || a.length !== 4 || b.length !== 4) {
    throw new FormatError("manifest.world_to_px", "a 2 x 4 matrix");
  }
  return [...a, ...b] as [number, number, number, number, number, number, number, number];
}
