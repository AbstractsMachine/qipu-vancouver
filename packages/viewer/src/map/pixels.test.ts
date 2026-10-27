import { afterEach, describe, expect, it, vi } from "vitest";
import { flatImage, stubCanvas } from "../test/canvas";
import { readPixels } from "./pixels";

describe("readPixels", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns an image's pixels, four bytes each", () => {
    stubCanvas();
    const pixels = readPixels(flatImage([10, 20, 30, 255], 2));
    expect(Array.from(pixels ?? [])).toEqual([10, 20, 30, 255, 10, 20, 30, 255, 10, 20, 30, 255, 10, 20, 30, 255]);
  });

  it("reads the image unscaled, at its own size", () => {
    const canvas = stubCanvas();
    const image = flatImage([0, 0, 0, 255], 3);
    expect(readPixels(image)).toHaveLength(3 * 3 * 4);
    expect(canvas.created[0]?.draws).toEqual([{ image, rect: [0, 0], smooth: true }]);
  });

  it("returns null where the browser has no 2D canvas", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    expect(readPixels(flatImage([0, 0, 0, 255]))).toBeNull();
  });
});
