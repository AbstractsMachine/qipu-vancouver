import type { Chunk, FieldArray } from "./qct";
import { FormatError, record, strings } from "./validate";

/**
 * The city's blocks: the unit a council decision is placed on. Geometry comes
 * from the `base/blocks` chunk, ids from `base/blocks-id.json`, and the two are
 * joined by position, so the loader checks that their lengths agree.
 */
export interface Blocks {
  readonly count: number;
  readonly ids: readonly string[];
  /** ring i is vertices offsets[i] .. offsets[i + 1] of xs / ys, world metres */
  readonly offsets: Uint32Array;
  readonly xs: Float32Array;
  readonly ys: Float32Array;
  /** ground elevation of each ring, metres */
  readonly elevation: Float32Array;
  /** index into `neighbourhoods`, or -1 */
  readonly hood: Int16Array;
  readonly neighbourhoods: readonly string[];
}

export function decodeBlocks(chunk: Chunk, idsJson: unknown, neighbourhoods: readonly string[]): Blocks {
  const cnt = field(chunk, "cnt");
  const sc = field(chunk, "sc");
  const ox = field(chunk, "ox");
  const oy = field(chunk, "oy");
  const vx = field(chunk, "vx");
  const vy = field(chunk, "vy");
  const z = field(chunk, "z");
  const hoodField = chunk.fields.get("hood");
  const ids = strings(record(idsJson, "blocks-id").id, "blocks-id.id");
  const count = cnt.length;
  if (ids.length !== count)
    throw new FormatError("blocks-id.id", `${count} ids, one per ring (got ${ids.length})`);

  const offsets = new Uint32Array(count + 1);
  for (let i = 0; i < count; i++) offsets[i + 1] = (offsets[i] as number) + (cnt[i] as number);
  const total = offsets[count] as number;
  if (vx.length < total || vy.length < total)
    throw new FormatError("blocks", "a vertex for every ring count");

  const xs = new Float32Array(total);
  const ys = new Float32Array(total);
  const elevation = new Float32Array(count);
  const hood = new Int16Array(count);
  for (let i = 0; i < count; i++) {
    /* vertices are offsets from the ring origin in tenths of 2^sc metres */
    const q = 2 ** (sc[i] as number) / 10;
    const x0 = ox[i] as number;
    const y0 = oy[i] as number;
    for (let k = offsets[i] as number; k < (offsets[i + 1] as number); k++) {
      xs[k] = x0 + (vx[k] as number) * q;
      ys[k] = y0 + (vy[k] as number) * q;
    }
    /* elevation is stored in decimetres */
    elevation[i] = (z[i] as number) / 10;
    const h = hoodField ? (hoodField[i] as number) : 255;
    hood[i] = h < neighbourhoods.length ? h : -1;
  }
  return { count, ids, offsets, xs, ys, elevation, hood, neighbourhoods };
}

export function blockIndexOf(blocks: Blocks, id: string): number {
  return blocks.ids.indexOf(id);
}

/** A ring's vertex-average centre, metres; good enough to fly the camera to. */
export function ringCentre(blocks: Blocks, i: number): [number, number] {
  const a = blocks.offsets[i] as number;
  const b = blocks.offsets[i + 1] as number;
  let sx = 0;
  let sy = 0;
  for (let k = a; k < b; k++) {
    sx += blocks.xs[k] as number;
    sy += blocks.ys[k] as number;
  }
  const n = Math.max(1, b - a);
  return [sx / n, sy / n];
}

function field(chunk: Chunk, name: string): FieldArray {
  const f = chunk.fields.get(name);
  if (!f) throw new FormatError(`blocks.${name}`, "a field in the blocks chunk");
  return f;
}
