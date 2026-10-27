import type { Blocks } from "./blocks";
import type { BlockIndex, BlockRecord, Decision, Outcome, Precision } from "./records";
import { sourceOf } from "./sources";
import { type Json, FormatError, isRecord, list, num, optional, record, str } from "./validate";

/*
 * packages/records writes `decisions.jsonl`: one decision per line, its places as latitude and longitude
 * (docs/data-model.md). The viewer shows decisions by block. This module is the bridge: it reads the rows and puts
 * each one on the block its places fall in, giving the same block index and block records the published shards give.
 */

/** The city data manifest's `proj`: a local equirectangular projection, the one the block outlines are drawn in. */
export interface LocalProjection {
  readonly lon0: number;
  readonly lat0: number;
  /** metres per degree of latitude */
  readonly mpd: number;
  /** cos(lat0), so a degree of longitude is mpd * cosl metres */
  readonly cosl: number;
}

export function projectionOf(manifest: Json): LocalProjection {
  const p = record(record(manifest, "manifest").proj, "manifest.proj");
  const lat0 = num(p.lat0, "manifest.proj.lat0");
  return {
    lon0: num(p.lon0, "manifest.proj.lon0"),
    lat0,
    mpd: num(p.mpd, "manifest.proj.mpd"),
    cosl: optional(p.cosl, (v) => num(v, "manifest.proj.cosl")) ?? Math.cos((lat0 * Math.PI) / 180),
  };
}

export function toWorld(p: LocalProjection, lat: number, lon: number): [number, number] {
  return [(lon - p.lon0) * p.mpd * p.cosl, (lat - p.lat0) * p.mpd];
}

/**
 * How far outside every outline a point may fall and still go to the nearest block, metres. A corner geocodes to the
 * middle of the crossing, about half a street's width from the four blocks around it.
 */
export const SNAP_METRES = 25;

/* records' `outcome` in the viewer's terms */
const OUTCOMES: Readonly<Record<string, Outcome>> = {
  passed: "decided",
  "submitted to voters": "decided",
  "veto overridden": "decided",
  pending: "pending",
  refused: "failed",
  vetoed: "failed",
  withdrawn: "failed",
  unknown: "unrecorded",
};

/* records' `placed_as` in the viewer's precision tiers; an `area` (a neighbourhood) names no block, so it is not placed */
const PRECISION: Readonly<Record<string, Precision>> = { address: "address", intersection: "corner" };

interface Point {
  readonly lat: number;
  readonly lon: number;
  readonly precision: Precision;
}

/** One line of decisions.jsonl, reduced to what the panel shows and where it goes. */
export interface PlacedRow {
  readonly decision: Decision;
  readonly points: readonly Point[];
}

/**
 * Read decisions.jsonl. Rows with no meeting date are left out, because the panel and the slider need a year; so are
 * places with no coordinates or placed only as an area.
 */
export function parseDecisionsJsonl(text: string): PlacedRow[] {
  const rows: PlacedRow[] = [];
  text.split("\n").forEach((line, n) => {
    if (!line.trim()) return;
    let json: Json;
    try {
      json = JSON.parse(line) as Json;
    } catch {
      throw new FormatError(`decisions.jsonl line ${n + 1}`, "a JSON object");
    }
    const row = parseRow(json, `decisions.jsonl line ${n + 1}`);
    if (row) rows.push(row);
  });
  return rows;
}

function parseRow(json: Json, path: string): PlacedRow | null {
  const r = record(json, path);
  const date = optional(r.date, (v) => str(v, `${path}.date`)) ?? "";
  const ymd = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!ymd) return null;
  const source = record(r.source, `${path}.source`);
  const pageUrl = optional(source.page_url, (v) => str(v, `${path}.source.page_url`)) ?? null;
  const itemUrl = str(source.item_url, `${path}.source.item_url`);
  const amounts = list(r.money ?? [], `${path}.money`).map((m, i) =>
    isRecord(m) ? (optional(m.amount, (v) => num(v, `${path}.money[${i}].amount`)) ?? 0) : 0,
  );
  const amount = Math.max(0, ...amounts);
  const points: Point[] = [];
  list(r.places ?? [], `${path}.places`).forEach((p, i) => {
    const place = record(p, `${path}.places[${i}]`);
    const precision = PRECISION[String(place.placed_as)];
    if (
      precision === undefined ||
      place.lat === undefined ||
      place.lat === null ||
      place.lon === undefined ||
      place.lon === null
    )
      return;
    points.push({
      lat: num(place.lat, `${path}.places[${i}].lat`),
      lon: num(place.lon, `${path}.places[${i}].lon`),
      precision,
    });
  });
  const outcome = optional(r.outcome, (v) => str(v, `${path}.outcome`));
  const precisions = points.map((p) => p.precision);
  return {
    decision: {
      year: Number(ymd[1]),
      date: `${ymd[2]}-${ymd[3]}`,
      kind: str(r.kind, `${path}.kind`),
      precision: precisions.includes("address") ? "address" : (precisions[0] ?? null),
      amount: amount > 0 ? amount : null,
      printed: str(r.quote, `${path}.quote`),
      plain: optional(r.summary, (v) => str(v, `${path}.summary`)) ?? null,
      outcome: outcome === undefined ? null : (OUTCOMES[outcome] ?? null),
      address: null,
      source: sourceOf({ u: pageUrl ?? itemUrl, c: "x", approx: pageUrl === null }),
    },
    points,
  };
}

/**
 * Put each row on the blocks its places fall in: the block whose outline holds the point, or the nearest one within
 * `SNAP_METRES`. A row with places on two blocks is listed on both, and once per block however many of its places
 * fall there. The result has the shape of the published files, so the rest of the viewer cannot tell them apart.
 */
export function placeOnBlocks(
  rows: readonly PlacedRow[],
  blocks: Blocks,
  projection: LocalProjection,
): { index: BlockIndex; records: ReadonlyMap<string, BlockRecord> } {
  const finder = blockFinder(blocks);
  const byBlock = new Map<number, Decision[]>();
  for (const { decision, points } of rows) {
    const on = new Set<number>();
    for (const point of points) {
      const at = finder(...toWorld(projection, point.lat, point.lon));
      if (at !== null) on.add(at);
    }
    for (const position of on) {
      const decisions = byBlock.get(position) ?? [];
      decisions.push(decision);
      byBlock.set(position, decisions);
    }
  }
  const counts = blocks.ids.map((_, i) => byBlock.get(i)?.length ?? 0);
  const years = blocks.ids.map((_, i) => (byBlock.get(i) ?? []).map((d) => d.year));
  const records = new Map<string, BlockRecord>();
  for (const [position, decisions] of byBlock) {
    const blockId = blocks.ids[position] as string;
    decisions.sort((a, b) => b.year - a.year || (b.date ?? "").localeCompare(a.date ?? ""));
    records.set(blockId, { blockId, decisions, streets: [] });
  }
  return {
    index: {
      shards: 1,
      ids: blocks.ids,
      counts,
      firstYears: years.map((ys) => (ys.length ? Math.min(...ys) : 0)),
      lastYears: years.map((ys) => (ys.length ? Math.max(...ys) : 0)),
    },
    records,
  };
}

/** The block a world point falls in, or the nearest one within SNAP_METRES, or null. */
function blockFinder(blocks: Blocks): (x: number, y: number) => number | null {
  const boxes = Array.from({ length: blocks.count }, (_, i) => ringBox(blocks, i));
  return (x, y) => {
    let best: number | null = null;
    let bestDistance = SNAP_METRES;
    for (let i = 0; i < blocks.count; i++) {
      const [x0, y0, x1, y1] = boxes[i] as [number, number, number, number];
      if (x < x0 - SNAP_METRES || x > x1 + SNAP_METRES || y < y0 - SNAP_METRES || y > y1 + SNAP_METRES) continue;
      if (contains(blocks, i, x, y)) return i;
      const d = distanceToRing(blocks, i, x, y);
      if (d <= bestDistance) {
        best = i;
        bestDistance = d;
      }
    }
    return best;
  };
}

function ringBox(blocks: Blocks, i: number): [number, number, number, number] {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (let k = blocks.offsets[i] as number; k < (blocks.offsets[i + 1] as number); k++) {
    const x = blocks.xs[k] as number;
    const y = blocks.ys[k] as number;
    x0 = Math.min(x0, x);
    y0 = Math.min(y0, y);
    x1 = Math.max(x1, x);
    y1 = Math.max(y1, y);
  }
  return [x0, y0, x1, y1];
}

function contains(blocks: Blocks, i: number, x: number, y: number): boolean {
  const a = blocks.offsets[i] as number;
  const b = blocks.offsets[i + 1] as number;
  let inside = false;
  for (let k = a, j = b - 1; k < b; j = k++) {
    const xk = blocks.xs[k] as number;
    const yk = blocks.ys[k] as number;
    const xj = blocks.xs[j] as number;
    const yj = blocks.ys[j] as number;
    if (yk > y !== yj > y && x < ((xj - xk) * (y - yk)) / (yj - yk) + xk) inside = !inside;
  }
  return inside;
}

function distanceToRing(blocks: Blocks, i: number, x: number, y: number): number {
  const a = blocks.offsets[i] as number;
  const b = blocks.offsets[i + 1] as number;
  let best = Infinity;
  for (let k = a, j = b - 1; k < b; j = k++) {
    const ax = blocks.xs[j] as number;
    const ay = blocks.ys[j] as number;
    const dx = (blocks.xs[k] as number) - ax;
    const dy = (blocks.ys[k] as number) - ay;
    const len = dx * dx + dy * dy;
    const t = len === 0 ? 0 : Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / len));
    best = Math.min(best, Math.hypot(x - ax - t * dx, y - ay - t * dy));
  }
  return best;
}
