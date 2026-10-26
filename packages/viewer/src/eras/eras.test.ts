import { describe, expect, it } from "vitest";
import sfEras from "../test/fixtures/sf-eras.json";
import { parseLiveEras as parseEraManifest } from "../tiles/live-eras";
import { parseTileMask } from "../tiles/mask";
import type { EraArea } from "./model";
import { overlaps, planTile, sourceAt, sourcesOf } from "./plan";
import { areaStateAt, clampYear, sliderTicks } from "./timeline";

const manifest = parseEraManifest(sfEras);
const haight = manifest.areas.find((a) => a.id === "haight") as EraArea;
const goldenGate = manifest.areas.find((a) => a.id === "cf_gg0") as EraArea;

describe("the live eras manifest", () => {
  it("reads the present, the range and the key years", () => {
    expect(manifest.present).toEqual({ template: "render/{z}/{x}/{y}.webp", zmax: 9, version: "r20261001-10171833" });
    expect(manifest.firstYear).toBe(1887);
    expect(manifest.presentYear).toBe(2026);
    expect(manifest.keyYears[0]).toBe(1887);
  });

  it("reads an area's keys in order, ending on the present", () => {
    expect(haight.name).toBe("Haight-Ashbury");
    expect(haight.keys.map((k) => k.year)).toEqual([1900, 1905, 1906, 1915, 1959, 1985, 2026]);
    expect(haight.keys.at(-1)?.pyramid).toBeNull();
    expect(haight.keys[0]?.pyramid?.template).toBe("_preview_eras/area/haight/1900/{z}/{x}/{y}.webp");
    expect(haight.box).toEqual([65, 44, 75, 51]);
  });

  it("reads switch maps with their encoding", () => {
    const s = haight.switches.get("1906-1915");
    expect(s).toMatchObject({ encoding: "c3c", offset: 1800, scale: 100, leadStep: 0.4 });
    expect(s?.template).toMatch(/\.png$/);
    expect(haight.switches.has("1905-1906")).toBe(false);
    const c3d = goldenGate.switches.get("1900-2026");
    expect(c3d?.encoding).toBe("c3d");
    expect(c3d?.clear?.template).toBe("_preview_eras/area/cf_gg0/clear/1900-2026/{z}/{x}/{y}.webp");
  });

  it("drops eras not yet public unless asked", () => {
    const json = { ...sfEras, years: { ...sfEras.years, 1700: { zmax: 1, key: "k", public: false } } };
    expect(parseEraManifest(json).keyYears).not.toContain(1700);
    expect(parseEraManifest(json, { includeUnpublished: true }).keyYears).toContain(1700);
  });

  it("rejects what it cannot draw", () => {
    const bad = (q: object) => ({ ...sfEras, quarters: { x: { ...sfEras.quarters.haight, ...q } } });
    expect(() => parseEraManifest(bad({ years: [{ year: 2026 }] }))).toThrow("at least a key year");
    expect(() => parseEraManifest(bad({ switch: { "1900-1905": { key: "s", zmax: 9, enc: "rise" } } }))).toThrow(
      '"c3", "c3c" or "c3d" (got "rise")',
    );
    expect(() => parseEraManifest(bad({ l9: [1, 2, 3] }))).toThrow("eras.quarters.x.l9: expected 4 numbers");
  });
});

describe("areaStateAt", () => {
  it("is empty before the first key and the present from the last", () => {
    expect(areaStateAt(haight, 1899).kind).toBe("empty");
    expect(areaStateAt(haight, 2026).kind).toBe("present");
    expect(areaStateAt(haight, 2030).kind).toBe("present");
  });

  it("finds the segment a year falls in", () => {
    const s = areaStateAt(haight, 1938);
    expect(s.kind).toBe("between");
    if (s.kind !== "between") return;
    expect([s.from.year, s.to.year]).toEqual([1915, 1959]);
    expect(s.switch?.template).toBe("_preview_eras/area/haight/switch/1915-1959/{z}/{x}/{y}.png");
  });

  it("starts a segment exactly on its key year", () => {
    const s = areaStateAt(haight, 1985);
    expect(s.kind === "between" && [s.from.year, s.to.year]).toEqual([1985, 2026]);
  });

  it("has no switch map where the pipeline wrote none", () => {
    const s = areaStateAt(haight, 1905.5);
    expect(s.kind === "between" && s.switch).toBeUndefined();
  });

  it("holds the first key before it where the format says so", () => {
    const s = areaStateAt({ ...haight, holdsFirstKey: true }, 1850);
    expect(s.kind === "key" && s.key.year).toBe(1900);
  });

  it("treats an area with a single key as empty", () => {
    expect(areaStateAt({ ...haight, keys: haight.keys.slice(0, 1) }, 1950).kind).toBe("empty");
  });
});

describe("slider years", () => {
  it("clamps and rounds", () => {
    expect(clampYear(1700, 1887, 2026)).toBe(1887);
    expect(clampYear(1938.4, 1887, 2026)).toBe(1938);
    expect(clampYear(Number.NaN, 1887, 2026)).toBe(2026);
  });

  it("thins ticks and always keeps both ends", () => {
    expect(sliderTicks([1887, 1890, 1906, 1915, 1938, 2020], 1887, 2026)).toEqual([1887, 1906, 1915, 1938, 2026]);
    expect(sliderTicks([], 1930, 2026)).toEqual([1930, 2026]);
    expect(sliderTicks([2000], 2000, 2000)).toEqual([2000]);
  });
});

describe("planTile", () => {
  const base = "https://tiles.example/sf";

  it("draws nothing at the present", () => {
    expect(planTile(manifest, base, 9, 135, 90, 2026)).toEqual([]);
  });

  it("draws nothing on tiles outside every area", () => {
    expect(planTile(manifest, base, 9, 0, 0, 1938)).toEqual([]);
  });

  it("plans a pass from one key to the next with its switch map", () => {
    const [pass, ...rest] = planTile(manifest, base, 9, 135, 90, 1938);
    expect(rest).toEqual([]);
    expect(pass?.areaId).toBe("haight");
    expect(pass?.from?.url).toBe(`${base}/_preview_eras/area/haight/1915/9/135/90.webp?v=wtrfwe14`);
    expect(pass?.to?.url).toBe(`${base}/_preview_eras/area/haight/1959/9/135/90.webp?v=wtrfwe14`);
    expect(pass?.switchMap?.url).toBe(`${base}/_preview_eras/area/haight/switch/1915-1959/9/135/90.png?v=pv10171650`);
    expect(pass?.switchMap?.kind).toBe("data");
    expect(pass?.t).toBe((1938 - 1800) * 100);
    expect(pass?.mid).toBe((1937 - 1800) * 100);
  });

  it("draws the last segment towards the present pyramid", () => {
    const [pass] = planTile(manifest, base, 9, 135, 90, 2000);
    expect(pass?.to?.url).toBe(`${base}/render/9/135/90.webp?v=r20261001-10171833`);
  });

  it("switches at the midpoint where there is no switch map", () => {
    const [pass] = planTile(manifest, base, 9, 135, 90, 1905);
    expect(pass?.switchMap).toBeNull();
    expect(pass?.mid).toBe((1905.5 - 1800) * 100);
  });

  it("adds the cleared site for c3d segments", () => {
    const [pass] = planTile(manifest, base, 9, 80, 30, 1950);
    expect(pass?.areaId).toBe("cf_gg0");
    expect(pass?.clear?.url).toContain("/cf_gg0/clear/1900-2026/9/80/30.webp");
    expect(sourcesOf(pass ? [pass] : [])).toHaveLength(4);
  });
});

describe("sourceAt", () => {
  const ref = { template: "k/{z}/{x}/{y}.webp", zmax: 6, version: undefined };

  it("uses the tile itself within the pyramid", () => {
    expect(sourceAt("b", ref, 5, 3, 4, "picture")).toEqual({
      url: "b/k/5/3/4.webp",
      kind: "picture",
      window: [0, 0, 1],
    });
  });

  it("enlarges part of the deepest ancestor past it", () => {
    expect(sourceAt("b", ref, 8, 13, 6, "picture")).toEqual({
      url: "b/k/6/3/1.webp",
      kind: "picture",
      window: [0.25, 0.5, 0.25],
    });
  });

  it("skips tiles the mask says are missing, at the ancestor's level", () => {
    const mask = parseTileMask({ 6: { x0: 3, y0: 1, cols: 1, rows: 1, bits: "gA==" } }, "have", "absent");
    expect(sourceAt("b", { ...ref, mask }, 8, 13, 6, "picture")).not.toBeNull();
    expect(sourceAt("b", { ...ref, mask }, 8, 17, 6, "picture")).toBeNull();
  });

  it("tests box overlap with open edges", () => {
    expect(overlaps([0, 0, 1, 1], [1, 0, 2, 1])).toBe(false);
    expect(overlaps([0, 0, 1, 1], [0.5, 0.5, 2, 2])).toBe(true);
  });
});
