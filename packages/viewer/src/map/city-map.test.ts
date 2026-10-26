import * as L from "leaflet";
import { afterEach, beforeEach, describe, expect, it, type Mock, vi } from "vitest";
import { type CityConfig, SAN_FRANCISCO } from "../config";
import { decodeBlocks } from "../data/blocks";
import { decodeChunk } from "../data/qct";
import { fakeFetch, twoBlocks } from "../test/builders";
import { stubCanvas } from "../test/canvas";
import sfEras from "../test/fixtures/sf-eras.json";
import type { Point } from "../tiles/frame";
import { parseLiveEras } from "../tiles/live-eras";
import type { Painting } from "../tiles/painting";
import { type CityMap, type CityMapOptions, createCityMap } from "./city-map";
import type { Compositor } from "./compositor";
import type * as CpuCompositor from "./cpu-compositor";

/* the real CPU compositor, with each one's dispose() recorded */
const disposals = vi.hoisted(() => [] as Mock[]);
vi.mock("./cpu-compositor", async (importOriginal) => {
  const real = await importOriginal<typeof CpuCompositor>();
  return {
    createCpuCompositor: (size: number): Compositor => {
      const c = real.createCpuCompositor(size);
      const dispose = vi.fn(() => {
        c.dispose();
      });
      disposals.push(dispose);
      return {
        kind: c.kind,
        ok: c.ok,
        draw: (target, passes) => {
          c.draw(target, passes);
        },
        dispose,
      };
    },
  };
});

/*
 * A 256 x 256 painting where a world metre is a frame unit: x east from the
 * centre, y north, and height lifting a point up the picture. Block A of
 * `twoBlocks` covers frame x 128-228, y 28-128.
 */
const painting: Painting = {
  format: "qipu-tiles/1",
  tile: 512,
  width: 256,
  height: 256,
  present: { template: "today/{z}/{x}/{y}.webp", zmax: 3, version: undefined },
  eras: null,
  worldToFrame: (x, y, z) => [128 + x, 128 - y - z],
  attribution: ["Painted by qipu"],
};
const blocks = decodeBlocks(decodeChunk(twoBlocks()), { id: ["A", "B"] }, []);
const ON_A: Point = [178, 48];
const OFF_EVERY_BLOCK: Point = [20, 20];
const latLng = ([x, y]: Point) => L.latLng(-y, x);

const city: CityConfig = SAN_FRANCISCO;

describe("createCityMap", () => {
  let element: HTMLDivElement;
  let coarsePointer: boolean;
  const made: CityMap[] = [];

  beforeEach(() => {
    disposals.length = 0;
    stubCanvas();
    vi.stubGlobal("fetch", fakeFetch({}));
    coarsePointer = false;
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query === "(pointer: coarse)" && coarsePointer }));
    element = document.createElement("div");
    Object.defineProperty(element, "clientWidth", { value: 800 });
    Object.defineProperty(element, "clientHeight", { value: 600 });
    document.body.append(element);
  });

  afterEach(() => {
    for (const m of made.splice(0)) m.destroy();
    element.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function cityMap(overrides: Partial<CityMapOptions> = {}): CityMap {
    const m = createCityMap({
      element,
      city,
      painting,
      year: 2026,
      compositor: "cpu",
      devicePixelRatio: 2,
      onPick: vi.fn(),
      ...overrides,
    });
    made.push(m);
    return m;
  }

  const click = (m: CityMap, at: Point) => m.leaflet.fire("click", { latlng: latLng(at) });

  it("is a flat map of the painting, named for the city", () => {
    const m = cityMap();
    expect(m.leaflet.options.crs).toBe(L.CRS.Simple);
    expect(element).toHaveAttribute("aria-label", "Painted map of San Francisco");
  });

  it("credits the city's sources and the painting", () => {
    cityMap();
    const credit = element.querySelector(".leaflet-control-attribution");
    expect(credit).toHaveTextContent(SAN_FRANCISCO.attribution);
    expect(credit).toHaveTextContent("Painted by qipu");
  });

  it("opens on the view it is given, in frame units", () => {
    const m = cityMap({ view: { x: 100, y: 120, zoom: 2 } });
    expect(m.view()).toEqual({ x: 100, y: 120, zoom: 2 });
  });

  it("opens on the city's starting view when it is given none", () => {
    const m = cityMap({ city: { ...city, start: { x: 60, y: 90, zoom: 2 } } });
    expect(m.view()).toEqual({ x: 60, y: 90, zoom: 2 });
  });

  it("otherwise fits the whole painting", () => {
    const { x, y } = cityMap().view();
    expect(x).toBeCloseTo(128);
    expect(y).toBeCloseTo(128);
  });

  it("reports where the reader moves to", () => {
    const onViewChange = vi.fn();
    const m = cityMap({ onViewChange });
    m.leaflet.setView(latLng([40, 50]), 2);
    expect(onViewChange).toHaveBeenLastCalledWith({ x: 40, y: 50, zoom: 2 });
  });

  it("has zoom buttons, except on a touch screen", () => {
    cityMap();
    expect(element.querySelector(".leaflet-control-zoom")).not.toBeNull();
    made.splice(0).forEach((m) => {
      m.destroy();
    });

    coarsePointer = true;
    cityMap();
    expect(element.querySelector(".leaflet-control-zoom")).toBeNull();
  });

  it("picks nothing until the blocks have arrived", () => {
    const onPick = vi.fn();
    const m = cityMap({ onPick });
    click(m, ON_A);
    expect(onPick).not.toHaveBeenCalled();
  });

  it("picks the block under a click, or none", () => {
    const onPick = vi.fn();
    const m = cityMap({ onPick });
    m.setBlocks(blocks);
    click(m, ON_A);
    expect(onPick).toHaveBeenLastCalledWith(0);
    click(m, OFF_EVERY_BLOCK);
    expect(onPick).toHaveBeenLastCalledWith(null);
  });

  describe("selecting a block", () => {
    const outlines = (m: CityMap) => {
      const found: L.Polygon[] = [];
      m.leaflet.eachLayer((layer) => {
        if (layer instanceof L.Polygon && layer.options.className === "qv-block-outline") found.push(layer);
      });
      return found;
    };

    it("outlines it where the painting shows it, and clears the outline", () => {
      const m = cityMap({ view: { x: 10, y: 10, zoom: 2 } });
      m.setBlocks(blocks);
      m.select(0);
      const [outline, ...more] = outlines(m);
      expect(more).toEqual([]);
      const corners = (outline?.getLatLngs()[0] as L.LatLng[]).map((ll) => [ll.lng, -ll.lat]);
      expect(corners).toEqual([
        [128, 128],
        [228, 128],
        [228, 28],
        [128, 28],
      ]);
      expect(m.view()).toMatchObject({ x: 10, y: 10 });

      m.select(1);
      expect(outlines(m)).toHaveLength(1);
      m.select(null);
      expect(outlines(m)).toEqual([]);
    });

    it("brings it into view when asked", async () => {
      const m = cityMap({ view: { x: 10, y: 10, zoom: 2 } });
      m.setBlocks(blocks);
      m.select(0, true);
      await vi.waitFor(
        () => {
          const { x, y } = m.view();
          expect(x).toBeCloseTo(178);
          expect(y).toBeCloseTo(78);
        },
        { timeout: 2000 },
      );
      expect(m.view().zoom).toBe(2);
    });

    it("does nothing before the blocks have arrived", () => {
      const m = cityMap();
      m.select(0, true);
      expect(outlines(m)).toEqual([]);
    });
  });

  describe("the past", () => {
    const withEras: Painting = { ...painting, eras: parseLiveEras(sfEras, { tile: 512 }) };

    it("has no era layer for a painting without eras", () => {
      const m = cityMap();
      expect(m.compositorKind()).toBe("none");
      m.setYear(1938);
      expect(m.pendingEraTiles()).toBe(0);
    });

    it("draws on the CPU where WebGL is missing", () => {
      expect(cityMap({ painting: withEras, compositor: "auto" }).compositorKind()).toBe("cpu");
    });

    it("releases its compositor when destroyed", () => {
      const m = createCityMap({ element, city, painting: withEras, year: 2026, compositor: "cpu", onPick: vi.fn() });
      expect(disposals).toHaveLength(1);
      m.destroy();
      expect(disposals[0]).toHaveBeenCalledOnce();
    });

    it("counts era tiles in view as pending until a new year is drawn", () => {
      const m = cityMap({ painting: withEras });
      expect(m.pendingEraTiles()).toBe(0);
      m.setYear(1938);
      expect(m.pendingEraTiles()).toBeGreaterThan(0);
    });
  });

  it("removes the map from its element when destroyed", () => {
    const m = createCityMap({ element, city, painting, year: 2026, onPick: vi.fn() });
    expect(element.querySelector(".leaflet-map-pane")).not.toBeNull();
    m.destroy();
    expect(element.querySelector(".leaflet-map-pane")).toBeNull();
  });
});
