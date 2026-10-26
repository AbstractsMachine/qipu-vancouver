import { type Json, FormatError, int, list, record, str } from "../data/validate";

/**
 * Which tiles of a pyramid exist. Most of a city's bounding box is sea or
 * outside the render, and asking for those tiles costs a 404 each, so a
 * pyramid may publish per level a box origin, a row width and a bitmask
 * (base64, least significant bit first, row-major).
 */
export interface TileMask {
  has(z: number, x: number, y: number): boolean;
}

interface LevelBits {
  readonly x0: number;
  readonly y0: number;
  readonly nx: number;
  readonly bits: Uint8Array;
}

export function parseTileMask(json: Json, path: string): TileMask {
  const levels = new Map<number, LevelBits>();
  for (const [key, value] of Object.entries(record(json, path))) {
    const p = `${path}.${key}`;
    const row = list(value, p);
    if (row.length !== 4) throw new FormatError(p, "[x0, y0, nx, bits]");
    const nx = int(row[2], `${p}[2]`);
    if (nx <= 0) throw new FormatError(`${p}[2]`, "a positive row width");
    levels.set(Number(key), {
      x0: int(row[0], `${p}[0]`),
      y0: int(row[1], `${p}[1]`),
      nx,
      bits: decodeBase64(str(row[3], `${p}[3]`)),
    });
  }
  return {
    has(z, x, y) {
      const l = levels.get(z);
      if (!l) return true;
      const i = x - l.x0;
      const j = y - l.y0;
      if (i < 0 || j < 0 || i >= l.nx) return false;
      const bit = j * l.nx + i;
      const byte = l.bits[bit >> 3];
      return byte !== undefined && (byte & (1 << (bit & 7))) !== 0;
    },
  };
}

function decodeBase64(text: string): Uint8Array {
  const binary = atob(text);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}
