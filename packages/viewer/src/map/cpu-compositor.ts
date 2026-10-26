import { type AreaPass, type ImageLike, compositeTile } from "../eras/composite";
import type { Compositor, DrawSource } from "./compositor";

/**
 * The compositor for browsers without WebGL, and for tests. It reads each
 * source into pixels on a scratch canvas and runs `eras/composite.ts`.
 * Switch maps are drawn without smoothing so their codes survive enlargement.
 */
export function createCpuCompositor(size: number): Compositor {
  const scratch = document.createElement("canvas");
  scratch.width = size;
  scratch.height = size;
  const sctx = scratch.getContext("2d", { willReadFrequently: true });

  const pixels = (src: DrawSource | null, smooth: boolean): ImageLike | null => {
    if (!src?.image || !sctx) return null;
    const [wx, wy, ws] = src.window;
    const { width, height } = src.image;
    sctx.clearRect(0, 0, size, size);
    sctx.imageSmoothingEnabled = smooth;
    sctx.drawImage(src.image, wx * width, wy * height, ws * width, ws * height, 0, 0, size, size);
    return sctx.getImageData(0, 0, size, size);
  };

  return {
    kind: "cpu",
    ok: true,
    draw(target, passes) {
      const ctx = target.getContext("2d");
      if (!ctx) return;
      const out = ctx.createImageData(target.width, target.height);
      const resolved: AreaPass[] = passes.map((p) => ({
        from: pixels(p.from, true),
        to: pixels(p.to, true),
        clear: pixels(p.clear, true),
        switchMap: pixels(p.switchMap, false),
        sw: p.sw,
        t: p.t,
        mid: p.mid,
      }));
      compositeTile(out, resolved);
      ctx.putImageData(out, 0, 0);
    },
    dispose() {},
  };
}
