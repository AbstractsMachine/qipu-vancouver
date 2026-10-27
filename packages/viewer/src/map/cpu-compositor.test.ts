import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type CanvasStub, flatImage, stubCanvas } from "../test/canvas";
import type { DrawPass, DrawSource } from "./compositor";
import { createCpuCompositor } from "./cpu-compositor";

const RED = flatImage([255, 0, 0, 255]);
const BLUE = flatImage([0, 0, 255, 255]);
const SW = { encoding: "c3c", scale: 100, leadStep: 0 } as const;
const whole = (image: ImageBitmap | null): DrawSource => ({ image, window: [0, 0, 1] });

function pass(overrides: Partial<DrawPass> = {}): DrawPass {
  return { from: whole(RED), to: whole(BLUE), clear: null, switchMap: null, sw: SW, t: 0, mid: 100, ...overrides };
}

describe("createCpuCompositor", () => {
  let canvas: CanvasStub;
  let target: HTMLCanvasElement;

  beforeEach(() => {
    canvas = stubCanvas();
    target = document.createElement("canvas");
    target.width = 4;
    target.height = 4;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const drawn = () => Array.from(canvas.of(target)?.put?.data ?? []);
  const firstPixel = () => drawn().slice(0, 4);

  it("is a working CPU compositor", () => {
    const c = createCpuCompositor(4);
    expect(c.kind).toBe("cpu");
    expect(c.ok).toBe(true);
  });

  it("shows the earlier picture before the segment's midpoint when there is no switch map", () => {
    createCpuCompositor(4).draw(target, [pass({ t: 99 })]);
    expect(firstPixel()).toEqual([255, 0, 0, 255]);
  });

  it("shows the later picture from the midpoint on", () => {
    createCpuCompositor(4).draw(target, [pass({ t: 100 })]);
    expect(firstPixel()).toEqual([0, 0, 255, 255]);
  });

  it("leaves the tile transparent where its images are missing", () => {
    createCpuCompositor(4).draw(target, [pass({ from: whole(null), to: whole(null), t: 100 })]);
    expect(drawn()).toHaveLength(4 * 4 * 4);
    expect(drawn().every((v) => v === 0)).toBe(true);
  });

  it("cuts each source's window out of its image, and reads switch maps without smoothing", () => {
    const switchMap = flatImage([0, 0, 0, 255]);
    createCpuCompositor(4).draw(target, [
      pass({ from: { image: RED, window: [0.5, 0.25, 0.25] }, switchMap: { image: switchMap, window: [0, 0, 1] } }),
    ]);
    const scratch = canvas.created.find((ctx) => ctx !== canvas.of(target));
    expect(scratch?.draws.find((d) => d.image === RED)).toEqual({
      image: RED,
      rect: [256, 128, 128, 128, 0, 0, 4, 4],
      smooth: true,
    });
    expect(scratch?.draws.find((d) => d.image === switchMap)?.smooth).toBe(false);
  });

  it("does nothing to a canvas it cannot draw on", () => {
    const blind = { width: 4, height: 4, getContext: () => null } as unknown as HTMLCanvasElement;
    expect(() => {
      createCpuCompositor(4).draw(blind, [pass()]);
    }).not.toThrow();
  });
});
