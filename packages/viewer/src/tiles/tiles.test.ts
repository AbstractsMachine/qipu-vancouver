import { describe, expect, it } from "vitest";
import sfIndex from "../test/fixtures/sf-index.json";
import vanIndex from "../test/fixtures/vancouver-index.json";
import { FormatError } from "../data/validate";
import { TILE_CSS, frameOf, level9BoxToFrame, tilesInBox } from "./frame";
import { gridOptionsFor, levelAt, tilesForViewport } from "./levels";
import { parseTileMask } from "./mask";
import { parsePyramidIndex } from "./pyramid";
import { tileTemplate, tileUrl, trimSlash } from "./urls";

describe("parsePyramidIndex", () => {
  it("reads the San Francisco pyramid as published", () => {
    const index = parsePyramidIndex(sfIndex);
    expect(index.tile).toBe(512);
    expect(index.zmax).toBe(9);
    expect(index.levels.get(3)?.tiles).toEqual([5, 3]);
    expect(index.proj).toEqual({ zex: sfIndex.proj.zex, sA: 0.42 });
    expect(index.version).toBe("r20261001-10171833");
    expect(index.mask).toBeUndefined();
  });

  it("reads Vancouver's tile mask", () => {
    const index = parsePyramidIndex(vanIndex);
    expect(index.mask?.has(0, 0, 0)).toBe(true);
    expect(index.mask?.has(3, 0, 0)).toBe(false);
    expect(index.mask?.has(3, 1, 0)).toBe(true);
  });

  it("defaults the projection for pyramids captured before it was stated", () => {
    const { proj, ...rest } = sfIndex;
    expect(proj).toBeDefined();
    expect(parsePyramidIndex(rest).proj).toEqual({ zex: 1, sA: 0.42 });
  });

  it("names the field that is wrong", () => {
    expect(() => parsePyramidIndex({ ...sfIndex, tile: "512" })).toThrow("index.tile: expected a number");
    expect(() => parsePyramidIndex({ ...sfIndex, levels: { 1: sfIndex.levels[1] } })).toThrow(FormatError);
    expect(() => parsePyramidIndex({ ...sfIndex, levels: { x: {} } })).toThrow("index.levels.x");
    expect(() => parsePyramidIndex(null)).toThrow("index: expected an object");
  });
});

describe("frameOf", () => {
  const index = parsePyramidIndex(sfIndex);
  const frame = frameOf(index);

  it("sizes level 0 in CSS pixels", () => {
    expect(frame.width).toBe(160);
    expect(frame.height).toBe(96);
  });

  it("puts the reference camera at the centre of the frame", () => {
    expect(frame.toFrame([index.ref.cx, index.ref.cy])).toEqual([80, 48]);
  });

  it("round-trips plane and frame", () => {
    const [x, y] = frame.toPlane(frame.toFrame([1234.5, -678.9]));
    expect(x).toBeCloseTo(1234.5, 6);
    expect(y).toBeCloseTo(-678.9, 6);
  });

  it("flips y: north on the plane is up in the frame", () => {
    const [, low] = frame.toFrame([0, 0]);
    const [, high] = frame.toFrame([0, 1000]);
    expect(high).toBeLessThan(low);
  });

  it("matches the renderer's scale at level 3", () => {
    /* at level 3 one plane unit is ref.scale renderer CSS px, shown at dpr * TILE_CSS / tile */
    expect(frame.scaleAt(3)).toBeCloseTo((index.ref.scale * index.dpr * TILE_CSS) / index.tile, 12);
  });

  it("converts an era area's level-9 box to frame units", () => {
    expect(level9BoxToFrame([36864, 13312, 47104, 21504])).toEqual([36, 13, 46, 21]);
  });

  it("lists the tiles a box touches", () => {
    expect(tilesInBox([36, 13, 46, 21], 9)).toEqual({ x0: 72, y0: 26, x1: 91, y1: 41 });
    expect(tilesInBox([0, 0, 160, 96], 0)).toEqual({ x0: 0, y0: 0, x1: 0, y1: 0 });
  });
});

describe("tile mask", () => {
  const mask = parseTileMask({ 2: [1, 1, 3, btoa(String.fromCharCode(0b00100101))] }, "have");

  it("reads bits least significant first, row by row", () => {
    expect(mask.has(2, 1, 1)).toBe(true);
    expect(mask.has(2, 2, 1)).toBe(false);
    expect(mask.has(2, 3, 1)).toBe(true);
    expect(mask.has(2, 3, 2)).toBe(true);
    expect(mask.has(2, 1, 2)).toBe(false);
  });

  it("treats tiles outside the box as missing and unknown levels as present", () => {
    expect(mask.has(2, 0, 1)).toBe(false);
    expect(mask.has(2, 4, 1)).toBe(false);
    expect(mask.has(2, 1, 9)).toBe(false);
    expect(mask.has(5, 0, 0)).toBe(true);
  });

  it("rejects a malformed row", () => {
    expect(() => parseTileMask({ 1: [0, 0, 2] }, "have")).toThrow("have.1: expected [x0, y0, nx, bits]");
    expect(() => parseTileMask({ 1: [0, 0, 0, "AA=="] }, "have")).toThrow("positive row width");
  });
});

describe("tile URLs", () => {
  const ref = { key: "render", zmax: 9, version: "r1-2", ext: "webp" } as const;

  it("puts the build stamp on every tile", () => {
    expect(tileUrl("https://t.example/sf/", ref, 3, 2, 1)).toBe("https://t.example/sf/render/3/2/1.webp?v=r1-2");
    expect(tileTemplate("https://t.example/sf", ref)).toBe("https://t.example/sf/render/{z}/{x}/{y}.webp?v=r1-2");
  });

  it("leaves the query off when there is no stamp", () => {
    expect(tileUrl("b", { ...ref, version: undefined, ext: "png" }, 0, 0, 0)).toBe("b/render/0/0/0.png");
    expect(tileTemplate("b", { ...ref, version: undefined })).toBe("b/render/{z}/{x}/{y}.webp");
    expect(trimSlash("a/")).toBe("a");
  });
});

describe("levels", () => {
  it("loads one level coarser on a 1x screen", () => {
    expect(gridOptionsFor(1)).toEqual({ tileSize: 512, zoomOffset: -1 });
    expect(gridOptionsFor(2)).toEqual({ tileSize: 256, zoomOffset: 0 });
    expect(gridOptionsFor(3)).toEqual({ tileSize: 256, zoomOffset: 0 });
  });

  it("clamps the level to the pyramid", () => {
    const retina = gridOptionsFor(2);
    expect(levelAt(4.4, retina, 9)).toBe(4);
    expect(levelAt(11, retina, 9)).toBe(9);
    expect(levelAt(0.2, gridOptionsFor(1), 9)).toBe(0);
  });

  it("states the tile budget of a viewport", () => {
    expect(tilesForViewport(1440, 900, gridOptionsFor(2))).toBe(7 * 5);
    expect(tilesForViewport(1440, 900, gridOptionsFor(1))).toBe(4 * 3);
    expect(tilesForViewport(390, 844, gridOptionsFor(3))).toBe(3 * 5);
  });
});
