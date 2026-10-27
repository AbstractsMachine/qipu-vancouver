import { describe, expect, it } from "vitest";
import westEnd from "../test/fixtures/qipu-tiles-west-end.json";
import { planTile } from "../eras/plan";
import { areaStateAt } from "../eras/timeline";
import { presentTileExists } from "./painting";
import { parseQipuTiles } from "./qipu-tiles";

/* the example manifest in docs/tiles-format.md */
const painting = parseQipuTiles(westEnd);
const base = "https://tiles.example/van/r1";

describe("parseQipuTiles", () => {
  it("sizes the frame from the canvas at its deepest level", () => {
    expect(painting.format).toBe("qipu-tiles/1");
    expect(painting.width).toBeCloseTo(2390 / 16, 10);
    expect(painting.height).toBeCloseTo(1720 / 16, 10);
    expect(painting.present).toMatchObject({ template: "today/{z}/{x}/{y}.webp", zmax: 3, version: "3f9a1c2e" });
    expect(painting.attribution).toHaveLength(2);
  });

  it("places world points with the manifest's matrix", () => {
    /* the matrix gives canvas pixels at zmax; the frame is that over 2^3, at half size */
    expect(painting.worldToFrame(0, 0, 0)).toEqual([5650.1 / 16, 6700.3 / 16]);
    const [, ground] = painting.worldToFrame(0, 0, 0);
    const [, roof] = painting.worldToFrame(0, 0, 10);
    expect(ground - roof).toBeCloseTo((10 * 3.4396) / 16, 10);
  });

  it("reads `have` as qipu-tiles/1 does: an empty list means no tiles", () => {
    expect(presentTileExists(painting, 0, 0, 0)).toBe(false);
    const open = parseQipuTiles({ ...westEnd, today: { ...westEnd.today, have: undefined } });
    expect(presentTileExists(open, 0, 0, 0)).toBe(true);
  });

  it("models the past as one area that holds its first year before it", () => {
    const eras = painting.eras;
    expect(eras?.firstYear).toBe(1950);
    expect(eras?.presentYear).toBe(2026);
    const area = eras?.areas[0];
    expect(area?.id).toBe("west-end");
    expect(area?.keys.map((k) => k.year)).toEqual([1950, 2026]);
    expect(area && areaStateAt(area, 1940).kind).toBe("key");
    expect(area?.switches.get("1950-2026")?.encoding).toBe("q1");
  });

  it("plans a year from the past layer to today through the date map", () => {
    const open = parseQipuTiles({
      ...westEnd,
      today: { ...westEnd.today, have: undefined },
      years: westEnd.years.map((y) => ({ ...y, have: undefined })),
      switch: westEnd.switch.map((s) => ({ ...s, have: undefined })),
    });
    const [pass] = open.eras ? planTile(open.eras, base, 2, 1, 1, 1961.5) : [];
    expect(pass?.from?.url).toBe(`${base}/years/1950/2/1/1.webp?v=8b0e44d1`);
    expect(pass?.to?.url).toBe(`${base}/today/2/1/1.webp?v=3f9a1c2e`);
    expect(pass?.switchMap?.url).toBe(`${base}/switch/1950-2026/2/1/1.png?v=c2d9e0aa`);
    expect(pass?.t).toBeCloseTo(16150, 6);
  });

  it("has no slider without past years", () => {
    expect(parseQipuTiles({ ...westEnd, years: [], switch: [] }).eras).toBeNull();
  });

  it("refuses another format or a malformed matrix", () => {
    expect(() => parseQipuTiles({ ...westEnd, format: "qipu-tiles/2" })).toThrow('"qipu-tiles/1" (got "qipu-tiles/2")');
    expect(() => parseQipuTiles({ ...westEnd, world_to_px: [[1, 2, 3, 4]] })).toThrow("manifest.world_to_px[1]");
    expect(() =>
      parseQipuTiles({
        ...westEnd,
        world_to_px: [
          [1, 2, 3],
          [1, 2, 3],
        ],
      }),
    ).toThrow("a 2 x 4 matrix");
  });

  it("refuses a tile size or zoom that would put the map at infinity", () => {
    expect(() => parseQipuTiles({ ...westEnd, tile_size: 0 })).toThrow(
      "manifest.tile_size: expected a positive integer",
    );
    expect(() => parseQipuTiles({ ...westEnd, canvas: { ...westEnd.canvas, zmax: -1 } })).toThrow(
      "manifest.canvas.zmax: expected an integer of 0 or more",
    );
  });
});
