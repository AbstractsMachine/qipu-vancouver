/**
 * Small readers for JSON that arrives over the network. Each one either returns
 * a value of the stated type or throws a FormatError naming the path, so a bad
 * file fails where it is read instead of three modules later.
 */

export class FormatError extends Error {
  constructor(
    readonly path: string,
    expected: string,
  ) {
    super(`${path}: expected ${expected}`);
    this.name = "FormatError";
  }
}

export type Json = unknown;

export function isRecord(value: Json): value is Record<string, Json> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function record(value: Json, path: string): Record<string, Json> {
  if (!isRecord(value)) throw new FormatError(path, "an object");
  return value;
}

export function num(value: Json, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new FormatError(path, "a number");
  return value;
}

export function int(value: Json, path: string): number {
  const n = num(value, path);
  if (!Number.isInteger(n)) throw new FormatError(path, "an integer");
  return n;
}

/** A number above zero: a size or a scale that is divided by. */
export function positive(value: Json, path: string): number {
  const n = num(value, path);
  if (n <= 0) throw new FormatError(path, "a positive number");
  return n;
}

/** An integer above zero: a count or a size in pixels. */
export function positiveInt(value: Json, path: string): number {
  const n = int(value, path);
  if (n <= 0) throw new FormatError(path, "a positive integer");
  return n;
}

/** An integer of zero or more: an offset, a count that may be empty, a zoom level. */
export function natural(value: Json, path: string): number {
  const n = int(value, path);
  if (n < 0) throw new FormatError(path, "an integer of 0 or more");
  return n;
}

export function str(value: Json, path: string): string {
  if (typeof value !== "string") throw new FormatError(path, "a string");
  return value;
}

export function list(value: Json, path: string): Json[] {
  if (!Array.isArray(value)) throw new FormatError(path, "an array");
  return value;
}

export function optional<T>(value: Json, read: (v: Json) => T): T | undefined {
  return value === undefined || value === null ? undefined : read(value);
}

export function numbers(value: Json, path: string): number[] {
  return list(value, path).map((v, i) => num(v, `${path}[${i}]`));
}

export function strings(value: Json, path: string): string[] {
  return list(value, path).map((v, i) => str(v, `${path}[${i}]`));
}

export function pair(value: Json, path: string): [number, number] {
  const xs = numbers(value, path);
  if (xs.length !== 2) throw new FormatError(path, "2 numbers");
  return [xs[0] as number, xs[1] as number];
}

export function quad(value: Json, path: string): [number, number, number, number] {
  const xs = numbers(value, path);
  if (xs.length !== 4) throw new FormatError(path, "4 numbers");
  return [xs[0] as number, xs[1] as number, xs[2] as number, xs[3] as number];
}
