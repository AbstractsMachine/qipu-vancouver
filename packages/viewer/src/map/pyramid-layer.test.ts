import * as L from "leaflet";
import { afterEach, describe, expect, it, vi } from "vitest";
import vancouverIndex from "../test/fixtures/vancouver-index.json";
import type { GridOptions } from "../tiles/levels";
import { livePainting, parsePyramidIndex } from "../tiles/live-index";
import { PyramidLayer } from "./pyramid-layer";

const BASE = "https://tiles.test/vancouver";
/* level 4 is 10 x 6 tiles; its mask leaves out (1, 1) and keeps (3, 1) */
const painting = livePainting(parsePyramidIndex(vancouverIndex), "render", null);

const coords = (x: number, y: number, z: number): L.Coords => Object.assign(L.point(x, y), { z });

describe("PyramidLayer", () => {
  let map: L.Map | null = null;

  afterEach(() => {
    map?.remove();
    map = null;
  });

  function layerOnMap(grid: GridOptions = { tileSize: 256, zoomOffset: 0 }): PyramidLayer {
    const bounds = L.latLngBounds([0, 0], [-painting.height, painting.width]);
    const layer = new PyramidLayer({ base: BASE, painting, grid, bounds, attribution: "City of Vancouver" });
    map?.remove();
    map = L.map(document.createElement("div"), { crs: L.CRS.Simple }).setView([-48, 80], 4);
    return layer.addTo(map);
  }

  async function tileAt(layer: PyramidLayer, c: L.Coords) {
    const done = vi.fn();
    const el = layer.createTile(c, done);
    await Promise.resolve();
    return { el, done };
  }

  it("requests a tile the pyramid has", async () => {
    const { el } = await tileAt(layerOnMap(), coords(3, 1, 4));
    expect(el).toBeInstanceOf(HTMLImageElement);
    expect(el.getAttribute("src")).toBe(`${BASE}/render/4/3/1.webp?v=r20261007-10221622`);
  });

  it.each([
    ["masked out of the pyramid", coords(1, 1, 4)],
    ["past the level's last column", coords(10, 0, 4)],
    ["before its first row", coords(0, -1, 4)],
    ["deeper than the pyramid goes", coords(0, 0, 10)],
  ])("gives a tile %s an empty placeholder without a request", async (_, c) => {
    const { el, done } = await tileAt(layerOnMap(), c);
    expect(el).toBeInstanceOf(HTMLDivElement);
    expect(el).not.toHaveAttribute("src");
    expect(done).toHaveBeenCalledWith(undefined, el);
  });

  it("checks the coarser level a 1x screen loads", async () => {
    /* (2, 1) is masked out at level 4 but present at level 3 */
    expect((await tileAt(layerOnMap(), coords(2, 1, 4))).el).toBeInstanceOf(HTMLDivElement);
    const coarse = layerOnMap({ tileSize: 512, zoomOffset: -1 });
    expect((await tileAt(coarse, coords(2, 1, 4))).el).toBeInstanceOf(HTMLImageElement);
  });
});
