import { clipToPainting } from "./extent";
import * as L from "leaflet";
import type { CityConfig } from "../config";
import type { Blocks } from "../data/blocks";
import type { Point } from "../tiles/frame";
import { gridOptionsFor } from "../tiles/levels";
import type { Painting } from "../tiles/painting";
import type { Compositor } from "./compositor";
import { createCpuCompositor } from "./cpu-compositor";
import { EraLayer } from "./era-layer";
import { createGlCompositor } from "./gl-compositor";
import { type BlockPicker, blockPicker } from "./pick";
import { PyramidLayer } from "./pyramid-layer";
import { tileImages } from "./tile-images";

export interface MapView {
  /** centre in frame units (level-0 CSS pixels) */
  readonly x: number;
  readonly y: number;
  readonly zoom: number;
}

export interface CityMapOptions {
  readonly element: HTMLElement;
  readonly city: CityConfig;
  readonly painting: Painting;
  readonly year: number;
  readonly view?: MapView | undefined;
  /** "cpu" skips WebGL, for browsers or tests where it is unreliable */
  readonly compositor?: "auto" | "cpu";
  readonly devicePixelRatio?: number;
  /** a click on the map: the block under it, or null for none */
  onPick(position: number | null): void;
  onViewChange?(view: MapView): void;
}

export interface CityMap {
  readonly leaflet: L.Map;
  setYear(year: number): void;
  /** blocks arrive after the tiles; until then a click picks nothing */
  setBlocks(blocks: Blocks): void;
  /** outline a block, or clear the outline; `fly` also brings it into view */
  select(position: number | null, fly?: boolean): void;
  view(): MapView;
  /** era tiles in view still loading for the current year */
  pendingEraTiles(): number;
  compositorKind(): "webgl" | "cpu" | "none";
  destroy(): void;
}

/** Frame units to Leaflet's CRS.Simple, where lat runs up and frame y runs down. */
const toLatLng = ([x, y]: Point): L.LatLng => L.latLng(-y, x);
const toFrame = (ll: L.LatLng): Point => [ll.lng, -ll.lat];

/**
 * The Leaflet map of one painting in a container: today's tiles, the era layer for the year on the slider, and the
 * block outlines. Returns a handle to drive it; call `destroy()` before removing the container.
 */
export function createCityMap(options: CityMapOptions): CityMap {
  const { painting, city } = options;
  const zmax = painting.present.zmax;
  const grid = gridOptionsFor(options.devicePixelRatio ?? window.devicePixelRatio);
  const bounds = L.latLngBounds(toLatLng([0, 0]), toLatLng([painting.width, painting.height]));
  const phone = window.matchMedia("(pointer: coarse)").matches;

  const map = L.map(options.element, {
    crs: L.CRS.Simple,
    minZoom: -1,
    maxZoom: zmax + 2,
    zoomSnap: 0.25,
    zoomDelta: 0.5,
    wheelPxPerZoomLevel: 120,
    maxBounds: bounds.pad(0.5),
    maxBoundsViscosity: 0.8,
    attributionControl: true,
    /* phones pinch; the +/- buttons would sit under a thumb and a notice */
    zoomControl: !phone,
  });
  map.attributionControl.setPrefix(false);
  options.element.setAttribute("aria-label", `Painted map of ${city.name}`);

  new PyramidLayer({
    base: city.tiles.base,
    painting,
    grid,
    bounds,
    attribution: [city.attribution, ...painting.attribution].join(" · "),
  }).addTo(map);

  let compositorKind: "webgl" | "cpu" | "none" = "none";
  const makeCompositor = (): Compositor => {
    const gl = options.compositor === "cpu" ? null : createGlCompositor(painting.tile);
    const c = gl ?? createCpuCompositor(painting.tile);
    compositorKind = c.kind;
    return c;
  };
  const clipped = (layer: EraLayer): EraLayer => {
    clipToPainting(layer, painting, grid.zoomOffset);
    return layer;
  };
  const images = tileImages({ capacity: phone ? 160 : 400 });
  const eraLayer = painting.eras
    ? clipped(
        new EraLayer({
          manifest: painting.eras,
          base: city.tiles.base,
          images,
          grid,
          compositor: makeCompositor,
          year: options.year,
          tilePx: painting.tile,
          bounds,
          maxNativeZoom: zmax - grid.zoomOffset,
        }),
      ).addTo(map)
    : null;

  if (options.view) map.setView(toLatLng([options.view.x, options.view.y]), options.view.zoom);
  else if (city.start) map.setView(toLatLng([city.start.x, city.start.y]), city.start.zoom);
  else map.fitBounds(bounds);

  let picker: BlockPicker | null = null;
  let outline: L.Polygon | null = null;

  const view = (): MapView => {
    const [x, y] = toFrame(map.getCenter());
    return { x, y, zoom: map.getZoom() };
  };

  map.on("click", (e: L.LeafletMouseEvent) => {
    if (!picker) return;
    options.onPick(picker.at(toFrame(e.latlng)));
  });
  map.on("moveend", () => options.onViewChange?.(view()));

  return {
    leaflet: map,
    setYear: (year) => eraLayer?.setYear(year),
    setBlocks(blocks) {
      picker = blockPicker(blocks, painting.worldToFrame);
    },
    select(position, fly = false) {
      outline?.remove();
      outline = null;
      if (position === null || !picker) return;
      const ring = picker.outline(position).map(toLatLng);
      outline = L.polygon(ring, { className: "qv-block-outline", interactive: false, weight: 2.5 }).addTo(map);
      if (fly) {
        map.flyTo(toLatLng(picker.centre(position)), Math.max(map.getZoom(), zmax - 3), { duration: 0.6 });
      }
    },
    view,
    pendingEraTiles: () => eraLayer?.pending() ?? 0,
    compositorKind: () => compositorKind,
    destroy() {
      /* removing the map removes the era layer, which disposes its compositor */
      map.remove();
      images.clear();
    },
  };
}
