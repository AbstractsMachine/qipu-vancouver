import { sourceOf, type Source } from "./sources";
import { type Json, FormatError, int, isRecord, list, num, numbers, optional, record, str, strings } from "./validate";

/** How a decision was placed on its block, weakest first. The tier travels with every row. */
export const PRECISIONS = ["street", "corner", "segment", "address", "stated"] as const;
export type Precision = (typeof PRECISIONS)[number];

/** What happened at this step, as the record states it. */
export type Outcome = "decided" | "pending" | "failed" | "unrecorded";

const OUTCOMES: Readonly<Record<string, Outcome>> = {
  d: "decided",
  n: "pending",
  f: "failed",
  u: "unrecorded",
};

export interface Decision {
  readonly year: number;
  /** "MM-DD", or null where the record gives no day */
  readonly date: string | null;
  /** the record series, a one-letter code the city config names */
  readonly kind: string;
  readonly precision: Precision | null;
  /** the largest single figure printed on the row, in the city's currency */
  readonly amount: number | null;
  /** the record's own words */
  readonly printed: string;
  /** qipu's plain-English reading of the record, when it passed review */
  readonly plain: string | null;
  readonly outcome: Outcome | null;
  /** the address register's match, `"349 E|6TH|AV"` */
  readonly address: string | null;
  readonly source: Source;
}

export interface BlockRecord {
  readonly blockId: string;
  readonly decisions: readonly Decision[];
  /** street keys the block fronts, `"PINE|ST"` */
  readonly streets: readonly string[];
}

/** `blocks/block-index.json`: one row per block, in the same order as the geometry. */
export interface BlockIndex {
  readonly shards: number;
  readonly ids: readonly string[];
  /** decisions placed on each block */
  readonly counts: readonly number[];
  /** first and last year of each block's record; 0 where it has none */
  readonly firstYears: readonly number[];
  readonly lastYears: readonly number[];
}

export function parseBlockIndex(json: Json): BlockIndex {
  const o = record(json, "block-index");
  const meta = record(o.meta, "block-index.meta");
  const ids = strings(o.b, "block-index.b");
  const counts = numbers(o.n, "block-index.n");
  const firstYears = numbers(o.y0, "block-index.y0");
  const lastYears = numbers(o.y1, "block-index.y1");
  for (const [name, xs] of [
    ["n", counts],
    ["y0", firstYears],
    ["y1", lastYears],
  ] as const) {
    if (xs.length !== ids.length) throw new FormatError(`block-index.${name}`, `${ids.length} entries`);
  }
  const shards = int(meta.shards, "block-index.meta.shards");
  if (shards <= 0) throw new FormatError("block-index.meta.shards", "a positive shard count");
  return { shards, ids, counts, firstYears, lastYears };
}

/** Block i's record lives in shard `i % shards`, named with two digits. */
export function shardFile(blockPosition: number, index: BlockIndex): string {
  return `block-${String(blockPosition % index.shards).padStart(2, "0")}.json`;
}

/** Read one block out of a shard file. A block absent from its shard has no record. */
export function parseBlockRecord(shardJson: Json, blockId: string): BlockRecord {
  const shard = record(shardJson, "shard");
  const entry = shard[blockId];
  if (entry === undefined) return { blockId, decisions: [], streets: [] };
  const p = `shard.${blockId}`;
  const e = record(entry, p);
  const decisions = list(e.d ?? [], `${p}.d`).map((row, i) => parseDecision(row, `${p}.d[${i}]`));
  decisions.sort((a, b) => b.year - a.year || (b.date ?? "").localeCompare(a.date ?? ""));
  return { blockId, decisions, streets: strings(e.s ?? [], `${p}.s`) };
}

export function parseDecision(json: Json, path: string): Decision {
  const r = record(json, path);
  const p = optional(r.p, (v) => int(v, `${path}.p`));
  const date = str(r.d ?? "", `${path}.d`);
  const amount = optional(r.a, (v) => num(v, `${path}.a`)) ?? 0;
  const hp = optional(r.hp, (v) => str(v, `${path}.hp`));
  return {
    year: int(r.y, `${path}.y`),
    date: /^\d{2}-\d{2}$/.test(date) ? date : null,
    kind: str(r.k, `${path}.k`),
    precision: p === undefined ? null : (PRECISIONS[p] ?? null),
    amount: amount > 0 ? amount : null,
    printed: str(r.t, `${path}.t`),
    plain: optional(r.pl, (v) => str(v, `${path}.pl`)) ?? null,
    outcome: hp === undefined ? null : (OUTCOMES[hp] ?? null),
    address: optional(r.ad, (v) => str(v, `${path}.ad`)) ?? null,
    source: sourceOf({
      u: str(r.u, `${path}.u`),
      c: optional(r.c, (v) => str(v, `${path}.c`)),
      approx: isRecord(r) && (r.approx === 1 || r.approx === true),
    }),
  };
}

/** A named place on a block (a library, a park) and the money the city's files tie to it. */
export interface Place {
  readonly slug: string;
  readonly name: string;
  readonly kind: string | null;
  /** contracts or capital lines adding budget, the whole place's, not the block's share; in the file's currency */
  readonly agreed: number | null;
  readonly paid: number | null;
  readonly contracts: number;
}

/**
 * `blocks/block-money.json`: places by block id, the page pattern for a place, and the ISO 4217 code the amounts are
 * in. Amounts are `agreed` and `paid`. qipu.org's files still name them `agreed_usd` and `paid_usd` in every city
 * (Vancouver's hold Canadian dollars), so those names are read as the same amounts, in `currency` when the file states
 * one and otherwise in the city's.
 */
export interface MoneyFile {
  readonly placePath: string | null;
  /** the currency the file states, or null when it states none */
  readonly currency: string | null;
  readonly byBlock: ReadonlyMap<string, readonly Place[]>;
}

export function parseMoneyFile(json: Json): MoneyFile {
  const o = record(json, "block-money");
  const currency = optional(o.currency, (v) => str(v, "block-money.currency")) ?? null;
  if (currency !== null && !/^[A-Z]{3}$/.test(currency)) {
    throw new FormatError("block-money.currency", "an ISO 4217 code such as CAD");
  }
  const byBlock = new Map<string, Place[]>();
  for (const [id, places] of Object.entries(record(o.b ?? {}, "block-money.b"))) {
    byBlock.set(
      id,
      list(places, `block-money.b.${id}`).map((pl, i) => {
        const p = `block-money.b.${id}[${i}]`;
        const x = record(pl, p);
        const money = (f: "agreed" | "paid") => {
          const field = x[f] !== undefined ? f : `${f}_usd`;
          const n = optional(x[field], (w) => num(w, `${p}.${field}`));
          return n === undefined || n <= 0 ? null : n;
        };
        return {
          slug: str(x.slug, `${p}.slug`),
          name: str(x.name, `${p}.name`),
          kind: optional(x.kind, (v) => str(v, `${p}.kind`)) ?? null,
          agreed: money("agreed"),
          paid: money("paid"),
          contracts: optional(x.n_contracts, (v) => int(v, `${p}.n_contracts`)) ?? 0,
        };
      }),
    );
  }
  return { placePath: optional(o.href, (v) => str(v, "block-money.href")) ?? null, currency, byBlock };
}
