import type { Blocks } from "../data/blocks";
import type { Point } from "../tiles/frame";

/**
 * Which block is under a point of the painted map.
 *
 * Blocks are not drawn as such; they are the unit the record is placed on.
 * Each ring is placed on the picture at its own ground elevation, so on a
 * hill it sits where the painting shows it, not where the flat ground plane
 * would put it. Where rings overlap on the picture (a slope seen from the
 * south) the ray from the camera meets the higher ground first, so the
 * highest ring wins.
 *
 * Built heights are not modelled: a click on a tall roof can land on the
 * block behind it. The site's picker marches through building solids for
 * that; this one trades it for needing nothing but the blocks file.
 */
export interface BlockPicker {
  /** the block at a frame point, as a geometry position, or null */
  at(point: Point): number | null;
  /** a block's outline in the frame, for highlighting */
  outline(position: number): Point[];
  /** the centre of a block's box in the frame */
  centre(position: number): Point;
}

/** grid cell in frame units: a level-0 CSS pixel is tens of metres, so this is a few blocks */
const CELL = 2;

type WorldToFrame = (x: number, y: number, z: number) => Point;

export function blockPicker(blocks: Blocks, worldToFrame: WorldToFrame): BlockPicker {
  const { count, offsets, xs, ys, elevation } = blocks;
  const px = new Float32Array(xs.length);
  const py = new Float32Array(ys.length);
  const box = new Float32Array(count * 4);
  for (let i = 0; i < count; i++) {
    let x0 = Infinity;
    let y0 = Infinity;
    let x1 = -Infinity;
    let y1 = -Infinity;
    const z = elevation[i] as number;
    for (let k = offsets[i] as number; k < (offsets[i + 1] as number); k++) {
      const [x, y] = worldToFrame(xs[k] as number, ys[k] as number, z);
      px[k] = x;
      py[k] = y;
      x0 = Math.min(x0, x);
      y0 = Math.min(y0, y);
      x1 = Math.max(x1, x);
      y1 = Math.max(y1, y);
    }
    box.set([x0, y0, x1, y1], i * 4);
  }

  /* a uniform grid over the frame, each cell listing the rings whose box touches it */
  const grid = new Map<string, number[]>();
  const cellKey = (cx: number, cy: number) => `${cx},${cy}`;
  for (let i = 0; i < count; i++) {
    const b = i * 4;
    if (!((box[b + 2] as number) >= (box[b] as number))) continue;
    for (let cx = Math.floor((box[b] as number) / CELL); cx <= Math.floor((box[b + 2] as number) / CELL); cx++) {
      for (let cy = Math.floor((box[b + 1] as number) / CELL); cy <= Math.floor((box[b + 3] as number) / CELL); cy++) {
        const key = cellKey(cx, cy);
        const list = grid.get(key);
        if (list) list.push(i);
        else grid.set(key, [i]);
      }
    }
  }

  const contains = (i: number, x: number, y: number): boolean => {
    const b = i * 4;
    if (
      x < (box[b] as number) ||
      x > (box[b + 2] as number) ||
      y < (box[b + 1] as number) ||
      y > (box[b + 3] as number)
    ) {
      return false;
    }
    let inside = false;
    const start = offsets[i] as number;
    const end = offsets[i + 1] as number;
    for (let k = start, j = end - 1; k < end; j = k++) {
      const xk = px[k] as number;
      const yk = py[k] as number;
      const xj = px[j] as number;
      const yj = py[j] as number;
      if (yk > y !== yj > y && x < ((xj - xk) * (y - yk)) / (yj - yk) + xk) inside = !inside;
    }
    return inside;
  };

  return {
    at([x, y]) {
      const candidates = grid.get(cellKey(Math.floor(x / CELL), Math.floor(y / CELL))) ?? [];
      let best: number | null = null;
      for (const i of candidates) {
        if (!contains(i, x, y)) continue;
        if (best === null || (elevation[i] as number) > (elevation[best] as number)) best = i;
      }
      return best;
    },
    outline(i) {
      const out: Point[] = [];
      for (let k = offsets[i] as number; k < (offsets[i + 1] as number); k++)
        out.push([px[k] as number, py[k] as number]);
      return out;
    },
    centre(i) {
      const b = i * 4;
      return [((box[b] as number) + (box[b + 2] as number)) / 2, ((box[b + 1] as number) + (box[b + 3] as number)) / 2];
    },
  };
}
