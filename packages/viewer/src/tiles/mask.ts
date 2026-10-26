import { type Json, FormatError, int, isRecord, list, optional, record, str } from "../data/validate";

/**
 * Which tiles of a pyramid exist. Most of a city's bounding box is sea or
 * outside the render, and asking for those tiles costs a 404 each, so a
 * pyramid publishes per level a box origin, a row width and a bitmask
 * (base64, row-major).
 *
 * Two forms are read:
 *   qipu-tiles/1   {"3": {"x0", "y0", "cols", "rows", "bits"}}, most significant bit first;
 *                  a level that is not listed has no tiles
 *   qipu.org live  {"3": [x0, y0, cols, bits]}, least significant bit first;
 *                  a level that is not listed is not masked
 */
export interface TileMask {
  has(z: number, x: number, y: number): boolean;
}

interface LevelBits {
  readonly x0: number;
  readonly y0: number;
  readonly cols: number;
  readonly rows: number;
  readonly bits: Uint8Array;
  readonly msbFirst: boolean;
}

/** `unlisted`: whether a level the mask does not list has its tiles (live) or none (qipu-tiles/1) */
export function parseTileMask(json: Json, path: string, unlisted: "present" | "absent" = "present"): TileMask {
  const levels = new Map<number, LevelBits>();
  const unlistedLevelsExist = unlisted === "present";
  for (const [key, value] of Object.entries(record(json, path))) {
    const p = `${path}.${key}`;
    levels.set(Number(key), isRecord(value) ? objectLevel(value, p) : arrayLevel(value, p));
  }
  return {
    has(z, x, y) {
      const l = levels.get(z);
      if (!l) return unlistedLevelsExist;
      const i = x - l.x0;
      const j = y - l.y0;
      if (i < 0 || j < 0 || i >= l.cols || j >= l.rows) return false;
      const bit = j * l.cols + i;
      const byte = l.bits[bit >> 3];
      const mask = l.msbFirst ? 0x80 >> (bit & 7) : 1 << (bit & 7);
      return byte !== undefined && (byte & mask) !== 0;
    },
  };
}

function objectLevel(o: Record<string, Json>, p: string): LevelBits {
  return {
    x0: int(o.x0, `${p}.x0`),
    y0: int(o.y0, `${p}.y0`),
    cols: positive(o.cols, `${p}.cols`),
    rows: optional(o.rows, (v) => positive(v, `${p}.rows`)) ?? Number.POSITIVE_INFINITY,
    bits: decodeBase64(str(o.bits, `${p}.bits`)),
    msbFirst: true,
  };
}

function arrayLevel(value: Json, p: string): LevelBits {
  const row = list(value, p);
  if (row.length !== 4) throw new FormatError(p, "[x0, y0, cols, bits]");
  return {
    x0: int(row[0], `${p}[0]`),
    y0: int(row[1], `${p}[1]`),
    cols: positive(row[2], `${p}[2]`),
    rows: Number.POSITIVE_INFINITY,
    bits: decodeBase64(str(row[3], `${p}[3]`)),
    msbFirst: false,
  };
}

function positive(value: Json, path: string): number {
  const n = int(value, path);
  if (n <= 0) throw new FormatError(path, "a positive count");
  return n;
}

function decodeBase64(text: string): Uint8Array {
  const binary = atob(text);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}
