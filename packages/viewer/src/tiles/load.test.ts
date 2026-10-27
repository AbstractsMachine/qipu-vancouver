import { describe, expect, it, vi } from "vitest";
import { type CityConfig, SAN_FRANCISCO } from "../config";
import { HttpError } from "../data/fetch";
import { fakeFetch } from "../test/builders";
import westEnd from "../test/fixtures/qipu-tiles-west-end.json";
import sfEras from "../test/fixtures/sf-eras.json";
import sfIndex from "../test/fixtures/sf-index.json";
import { loadPainting } from "./load";

const BASE = "https://tiles.test/sf/r1";

function live(tiles: Partial<{ eras: string }> = {}): CityConfig {
  return { ...SAN_FRANCISCO, tiles: { format: "qipu.org", base: `${BASE}/`, present: "render", ...tiles } };
}

describe("loadPainting", () => {
  describe("a release as qipu.org serves it", () => {
    const routes = {
      [`${BASE}/render/index.json`]: sfIndex,
      [`${BASE}/eras.json`]: sfEras,
    };

    it("reads the present pyramid's index and the eras manifest", async () => {
      const painting = await loadPainting(live({ eras: "eras.json" }), fakeFetch(routes));
      expect(painting.format).toBe("qipu.org");
      expect(painting.tile).toBe(512);
      expect(painting.present).toMatchObject({ template: "render/{z}/{x}/{y}.webp", zmax: 9, version: sfIndex.v });
      expect(painting.eras).toMatchObject({ firstYear: 1887, presentYear: 2026 });
      expect(painting.eras?.areas.map((a) => a.id)).toEqual(["haight", "cf_gg0"]);
    });

    it("has no past when the city names no eras manifest", async () => {
      const fetcher = vi.fn(fakeFetch(routes));
      const painting = await loadPainting(live(), fetcher);
      expect(painting.eras).toBeNull();
      expect(fetcher).toHaveBeenCalledExactlyOnceWith(`${BASE}/render/index.json`, undefined);
    });

    it("fails with the URL of a file that is missing", async () => {
      const failure = loadPainting(live({ eras: "eras.json" }), fakeFetch({ [`${BASE}/eras.json`]: sfEras }));
      await expect(failure).rejects.toThrow(HttpError);
      await expect(failure).rejects.toThrow(`${BASE}/render/index.json: HTTP 404`);
    });
  });

  describe("a qipu-tiles/1 release", () => {
    const city = (manifest?: string): CityConfig => ({
      ...SAN_FRANCISCO,
      tiles: { format: "qipu-tiles/1", base: BASE, ...(manifest ? { manifest } : {}) },
    });

    it("reads manifest.json by default", async () => {
      const painting = await loadPainting(city(), fakeFetch({ [`${BASE}/manifest.json`]: westEnd }));
      expect(painting.format).toBe("qipu-tiles/1");
      expect(painting.present).toMatchObject({ template: "today/{z}/{x}/{y}.webp", zmax: 3, version: "3f9a1c2e" });
      expect(painting.eras).toMatchObject({ firstYear: 1950, presentYear: 2026, keyYears: [1950] });
      expect(painting.attribution).toHaveLength(2);
    });

    it("reads the manifest the city names", async () => {
      const painting = await loadPainting(city("west-end.json"), fakeFetch({ [`${BASE}/west-end.json`]: westEnd }));
      expect(painting.format).toBe("qipu-tiles/1");
    });
  });
});
