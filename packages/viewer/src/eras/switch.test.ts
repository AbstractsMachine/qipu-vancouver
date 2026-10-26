import { describe, expect, it } from "vitest";
import { type AreaPass, compositeTile } from "./composite";
import { NEVER, decodeSwitchPixel, midCode, pixelWeights, progress, smoothstep, yearCode } from "./switch";

const c3c = { encoding: "c3c", offset: 1800, scale: 100, leadStep: 0.4 } as const;
const c3d = { ...c3c, encoding: "c3d" } as const;

describe("date codes", () => {
  it("are years from the offset, times the scale", () => {
    expect(yearCode(1906, c3c)).toBe(10600);
    expect(midCode(1906, 1915, c3c)).toBe(11050);
  });
});

describe("decodeSwitchPixel", () => {
  it("reads the date from red and green", () => {
    expect(decodeSwitchPixel(41, 104, 0, 0, c3c).date).toBe(41 * 256 + 104);
  });

  it("maps 0 to the midpoint and 65535 to never", () => {
    expect(decodeSwitchPixel(0, 0, 0, 11050, c3c).date).toBe(11050);
    expect(decodeSwitchPixel(255, 255, 0, 11050, c3c).date).toBe(NEVER);
  });

  it("reads a fade from blue's low bits on a doubling scale", () => {
    expect(decodeSwitchPixel(1, 0, 0, 0, c3c).fade).toBe(0);
    expect(decodeSwitchPixel(1, 0, 1, 0, c3c).fade).toBeCloseTo(0.15, 10);
    expect(decodeSwitchPixel(1, 0, 4, 0, c3c).fade).toBeCloseTo(1.2, 10);
  });

  it("reads a lead from blue's high bits, for c3d only", () => {
    expect(decodeSwitchPixel(1, 0, 0x31, 0, c3d).lead).toBeCloseTo(3 * 0.4 * 100, 10);
    expect(decodeSwitchPixel(1, 0, 0x31, 0, c3c).lead).toBe(0);
  });
});

describe("progress", () => {
  it("is a step without a fade", () => {
    expect(progress(99, 100, 0)).toBe(0);
    expect(progress(100, 100, 0)).toBe(1);
  });

  it("overlaps the two pictures only in the middle of a fade", () => {
    expect(progress(100, 100, 10)).toBe(0);
    expect(progress(103.9, 100, 10)).toBe(0);
    expect(progress(105, 100, 10)).toBeCloseTo(0.5, 10);
    expect(progress(106.1, 100, 10)).toBe(1);
    expect(smoothstep(0, 1, 2)).toBe(1);
  });
});

describe("pixelWeights", () => {
  const px = { date: 1000, fade: 0, lead: 200 };

  it("shows the old picture, then the cleared site, then the new one", () => {
    expect(pixelWeights(700, px)).toEqual({ from: 1, clear: 0, to: 0 });
    expect(pixelWeights(850, px)).toEqual({ from: 0, clear: 1, to: 0 });
    expect(pixelWeights(1000, px)).toEqual({ from: 0, clear: 0, to: 1 });
  });

  it("always sums to one", () => {
    for (const t of [0, 795, 800, 805, 995, 1005, 2000]) {
      const w = pixelWeights(t, { date: 1000, fade: 10, lead: 200 });
      expect(w.from + w.clear + w.to).toBeCloseTo(1, 12);
    }
  });
});

describe("compositeTile", () => {
  const img = (rgba: number[], n = 2) => ({
    width: n,
    height: 1,
    data: new Uint8ClampedArray(Array.from({ length: n }, () => rgba).flat()),
  });
  const RED = [255, 0, 0, 255];
  const BLUE = [0, 0, 255, 255];
  const GREY = [128, 128, 128, 255];
  const pass = (over: Partial<AreaPass>): AreaPass => ({
    from: img(RED),
    to: img(BLUE),
    clear: null,
    switchMap: null,
    sw: c3c,
    t: 0,
    mid: 50,
    ...over,
  });
  const run = (...passes: AreaPass[]) => {
    const out = { width: 2, height: 1, data: new Uint8ClampedArray(8) };
    compositeTile(out, passes);
    return Array.from(out.data);
  };

  it("switches the whole tile at the midpoint without a switch map", () => {
    expect(run(pass({ t: 49 }))).toEqual([...RED, ...RED]);
    expect(run(pass({ t: 50 }))).toEqual([...BLUE, ...BLUE]);
  });

  it("switches each pixel at its own date", () => {
    /* pixel 0 changes at code 10, pixel 1 at code 300 */
    const switchMap = { width: 2, height: 1, data: new Uint8ClampedArray([0, 10, 0, 255, 1, 44, 0, 255]) };
    expect(run(pass({ switchMap, t: 100 }))).toEqual([...BLUE, ...RED]);
    expect(run(pass({ switchMap, t: 300 }))).toEqual([...BLUE, ...BLUE]);
  });

  it("shows the cleared site during a pixel's lead, and the old picture where none was painted", () => {
    const switchMap = {
      width: 2,
      height: 1,
      data: new Uint8ClampedArray([1, 44, 0x10, 255, 1, 44, 0x10, 255]),
    };
    const clear = { width: 2, height: 1, data: new Uint8ClampedArray([...GREY, 0, 0, 0, 0]) };
    const sw = { ...c3d, leadStep: 1 };
    expect(run(pass({ switchMap, clear, sw, t: 250 }))).toEqual([...GREY, ...RED]);
  });

  it("leaves transparent pixels where a tile is missing", () => {
    expect(run(pass({ from: null, t: 0 }))).toEqual([0, 0, 0, 0, 0, 0, 0, 0]);
  });

  it("draws later passes over earlier ones", () => {
    const halfBlue = img([0, 0, 255, 128]);
    const out = run(pass({ t: 0 }), pass({ from: halfBlue, t: 0 }));
    expect(out.slice(0, 4)).toEqual([127, 0, 128, 255]);
  });
});
