import { vi } from "vitest";
import type { ImageLike } from "../eras/composite";

/** A stand-in for a decoded tile: one flat colour, which a fake 2D context reads back. */
export interface FlatImage {
  readonly width: number;
  readonly height: number;
  readonly rgba: readonly [number, number, number, number];
  close(): void;
}

export function flatImage(rgba: readonly [number, number, number, number], size = 512): FlatImage & ImageBitmap {
  return { width: size, height: size, rgba, close: vi.fn() };
}

export interface DrawCall {
  readonly image: FlatImage;
  /** source x, y, width, height, then destination x, y, width, height */
  readonly rect: readonly number[];
  readonly smooth: boolean;
}

/**
 * Just enough of CanvasRenderingContext2D for the CPU compositor and the era
 * layer: `getImageData` returns the colour of the last image drawn, or
 * transparent after a clear.
 */
export class Fake2d {
  imageSmoothingEnabled = true;
  readonly draws: DrawCall[] = [];
  clears = 0;
  put: ImageLike | null = null;
  private last: FlatImage | null = null;

  clearRect(): void {
    this.clears++;
    this.last = null;
  }

  drawImage(image: FlatImage, ...rect: number[]): void {
    this.draws.push({ image, rect, smooth: this.imageSmoothingEnabled });
    this.last = image;
  }

  createImageData(width: number, height: number): ImageLike {
    return { width, height, data: new Uint8ClampedArray(width * height * 4) };
  }

  getImageData(_x: number, _y: number, width: number, height: number): ImageLike {
    const out = this.createImageData(width, height);
    if (this.last) for (let i = 0; i < width * height; i++) out.data.set(this.last.rgba, i * 4);
    return out;
  }

  putImageData(data: ImageLike): void {
    this.put = data;
  }
}

export interface CanvasStub {
  /** the context a canvas was given, if it asked for one */
  of(canvas: HTMLCanvasElement): Fake2d | undefined;
  /** every context handed out, in order */
  readonly created: readonly Fake2d[];
}

/**
 * Give every canvas a fake 2D context (jsdom has none) and no WebGL.
 * Undo with `vi.restoreAllMocks()`.
 */
export function stubCanvas(): CanvasStub {
  const contexts = new WeakMap<HTMLCanvasElement, Fake2d>();
  const created: Fake2d[] = [];
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(function (
    this: HTMLCanvasElement,
    kind: string,
  ) {
    if (kind !== "2d") return null;
    let ctx = contexts.get(this);
    if (!ctx) {
      ctx = new Fake2d();
      contexts.set(this, ctx);
      created.push(ctx);
    }
    return ctx as unknown as CanvasRenderingContext2D;
  } as HTMLCanvasElement["getContext"]);
  return { of: (canvas) => contexts.get(canvas), created };
}
