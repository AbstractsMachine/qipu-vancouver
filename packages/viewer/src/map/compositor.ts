import type { EraSwitch } from "../eras/model";
import type { Window } from "../eras/plan";

export interface DrawSource {
  readonly image: ImageBitmap | null;
  readonly window: Window;
}

/** One area's pass with its images resolved; see `eras/plan.ts`. */
export interface DrawPass {
  readonly from: DrawSource | null;
  readonly to: DrawSource | null;
  readonly clear: DrawSource | null;
  readonly switchMap: DrawSource | null;
  readonly sw: Pick<EraSwitch, "encoding" | "scale" | "leadStep">;
  readonly t: number;
  readonly mid: number;
}

/**
 * Draws an era tile: the passes, in order, into a canvas the size of a tile
 * image. Two implementations compute the same picture: WebGL for speed (a
 * year slider redraws every tile on screen per frame) and the CPU for
 * browsers without it.
 */
export interface Compositor {
  readonly kind: "webgl" | "cpu";
  /** false once the GPU context is lost; the caller swaps in a CPU compositor */
  readonly ok: boolean;
  draw(target: HTMLCanvasElement, passes: readonly DrawPass[]): void;
  /** drop anything held for a bitmap that is about to be closed */
  forget(bitmap: ImageBitmap): void;
  dispose(): void;
}
