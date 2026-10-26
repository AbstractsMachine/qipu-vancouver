import type { CityConfig } from "../config";
import type { Outcome, Precision } from "../data/records";
import type { Source } from "../data/sources";

export type Currency = CityConfig["record"]["currency"];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

function dayOf(mmdd: string | null): { mm: string; dd: string; month: string; day: number } | null {
  const m = mmdd === null ? null : /^(\d{2})-(\d{2})$/.exec(mmdd);
  if (!m) return null;
  const [, mm = "", dd = ""] = m;
  const month = MONTHS[Number(mm) - 1];
  const day = Number(dd);
  if (month === undefined || day < 1 || day > 31) return null;
  return { mm, dd, month, day };
}

/** "17 Nov 1976", or the year alone where the record gives no day. */
export function formatDate(year: number, mmdd: string | null): string {
  const d = dayOf(mmdd);
  return d ? `${d.day} ${d.month} ${year}` : String(year);
}

/** The same date for a `<time dateTime>`: "1976-11-17", or "1976". */
export function isoDate(year: number, mmdd: string | null): string {
  const d = dayOf(mmdd);
  return d ? `${year}-${d.mm}-${d.dd}` : String(year);
}

export function decadeOf(year: number): number {
  return Math.floor(year / 10) * 10;
}

export interface DecadeGroup<T> {
  readonly decade: number;
  readonly items: readonly T[];
}

/** Rows grouped by decade, keeping the order the rows come in. */
export function groupByDecade<T extends { readonly year: number }>(rows: readonly T[]): DecadeGroup<T>[] {
  const groups = new Map<number, T[]>();
  for (const row of rows) {
    const decade = decadeOf(row.year);
    const group = groups.get(decade);
    if (group) group.push(row);
    else groups.set(decade, [row]);
  }
  return Array.from(groups, ([decade, items]) => ({ decade, items }));
}

const numberFormat = new Intl.NumberFormat("en-US");

/** "1 decision", "1,204 decisions". */
export function countOf(n: number, noun: string): string {
  return `${numberFormat.format(n)} ${noun}${n === 1 ? "" : "s"}`;
}

const moneyFormats = new Map<Currency, Intl.NumberFormat>();

/** Whole units in the city's currency: "$60,000,000", "CA$4,000,000". */
export function formatMoney(amount: number, currency: Currency): string {
  let format = moneyFormats.get(currency);
  if (!format) {
    format = new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 });
    moneyFormats.set(currency, format);
  }
  return format.format(amount);
}

const PRECISION_PHRASES: Readonly<Record<Precision, string>> = {
  stated: "names this block",
  address: "at an address on this block",
  segment: "on a stretch of street along this block",
  corner: "at a corner of this block",
  street: "somewhere on a street this block fronts",
};

export function precisionPhrase(precision: Precision): string {
  return PRECISION_PHRASES[precision];
}

const OUTCOME_WORDS: Readonly<Record<Outcome, string | null>> = {
  decided: "Decided",
  pending: "Pending",
  failed: "Failed",
  unrecorded: null,
};

export function outcomeWord(outcome: Outcome | null): string | null {
  return outcome === null ? null : OUTCOME_WORDS[outcome];
}

const COMPASS = new Set(["N", "S", "E", "W", "NE", "NW", "SE", "SW"]);

function streetWord(word: string): string {
  const ordinal = /^0*(\d+)(ST|ND|RD|TH)$/i.exec(word);
  if (ordinal) return `${Number(ordinal[1])}${(ordinal[2] ?? "").toLowerCase()}`;
  if (COMPASS.has(word.toUpperCase())) return word.toUpperCase();
  return word.toLowerCase().replace(/(^|['-])\p{L}/gu, (s) => s.toUpperCase());
}

/**
 * A street or address key as a reader writes it: "PINE|ST" → "Pine St",
 * "349 E|06TH|AV" → "349 E 6th Av". A "*" part marks a street with no type.
 */
export function streetLabel(key: string): string {
  return key
    .split("|")
    .filter((part) => part !== "*")
    .flatMap((part) => part.split(" "))
    .filter((word) => word !== "")
    .map(streetWord)
    .join(" ");
}

/** "37 decisions, 1912–2016", or null for an empty record. */
export function recordSummary(rows: readonly { readonly year: number }[]): string | null {
  if (rows.length === 0) return null;
  let first = Infinity;
  let last = -Infinity;
  for (const { year } of rows) {
    first = Math.min(first, year);
    last = Math.max(last, year);
  }
  return `${countOf(rows.length, "decision")}, ${first === last ? first : `${first}–${last}`}`;
}

function withPage(label: string, page: string | null): string {
  return page === null ? label : `${label}, page ${page}`;
}

/** What a source link opens, in words: "Scan, page n292 · Internet Archive". */
export function sourceLabel(source: Source): string {
  const { system, page, document } = source;
  // Internet Archive pages are leaf numbers, written "n292" in its own URLs.
  const leaf = page === null ? null : `n${page}`;
  switch (system) {
    case "archive":
      return `${withPage("Scan", leaf)} · Internet Archive`;
    case "clerk":
      return withPage("Clerk's minutes PDF", page === null ? null : String(page));
    case "legistar":
      return withPage("Legistar minutes", page === null ? null : String(page));
    case "url":
      return document === "archive.org" ? `${withPage("Scan", leaf)} · Internet Archive` : document;
  }
}
