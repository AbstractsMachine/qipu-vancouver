import * as L from "leaflet";
import type { CityConfig } from "../config";
import type { Blocks } from "../data/blocks";
import type { EraManifest } from "../eras/manifest";
import { type Frame, type Point, frameOf } from "../tiles/frame";
import { gridOptionsFor } from "../tiles/levels";
import type { PyramidIndex } from "../tiles/pyramid";
import { tileTemplate } from "../tiles/urls";
import type { Compositor } from "./compositor";
import { createCpuCompositor } from "./cpu-compositor";
import { EraLayer } from "./era-layer";
import { createGlCompositor } from "./gl-compositor";
import { type BlockPicker, blockPicker } from "./pick";
import { projection } from "./projection";
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
  readonly index: PyramidIndex;
  readonly eras: EraManifest | null;
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
  readonly frame: Frame;
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

export function createCityMap(options: CityMapOptions): CityMap {
  const { index, city } = options;
  const frame = frameOf(index);
  const grid = gridOptionsFor(options.devicePixelRatio ?? window.devicePixelRatio);
  const bounds = L.latLngBounds(toLatLng([0, 0]), toLatLng([frame.width, frame.height]));
  const proj = projection(index.proj);
  const phone = window.matchMedia("(pointer: coarse)").matches;

  const map = L.map(options.element, {
    crs: L.CRS.Simple,
    minZoom: -1,
    maxZoom: index.zmax + 2,
    zoomSnap: 0.25,
    zoomDelta: 0.5,
    wheelPxPerZoomLevel: 120,
    maxBounds: bounds.pad(0.5),
    maxBoundsViscosity: 0.8,
    attributionControl: true,
    zoomControl: true,
  });
  map.attributionControl.setPrefix(false);
  options.element.setAttribute("aria-label", `Painted map of ${city.name}`);

  new PyramidLayer({
    template: tileTemplate(city.tiles.base, {
      key: city.tiles.present,
      zmax: index.zmax,
      version: index.version,
      ext: "webp",
    }),
    index,
    grid,
    bounds,
    attribution: city.attribution,
  }).addTo(map);

  let compositorKind: "webgl" | "cpu" | "none" = "none";
  const makeCompositor = (): Compositor => {
    const gl = options.compositor === "cpu" ? null : createGlCompositor(index.tile);
    const c = gl ?? createCpuCompositor(index.tile);
    compositorKind = c.kind;
    return c;
  };
  const eraLayer = options.eras
    ? new EraLayer({
        manifest: options.eras,
        base: city.tiles.base,
        images: tileImages(phone ? 64 : 160),
        grid,
        compositor: makeCompositor,
        year: options.year,
        tilePx: index.tile,
        bounds,
        maxNativeZoom: index.zmax - grid.zoomOffset,
      }).addTo(map)
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
    options.onPick(picker.at(frame.toPlane(toFrame(e.latlng))));
  });
  map.on("moveend", () => options.onViewChange?.(view()));

  return {
    leaflet: map,
    frame,
    setYear: (year) => eraLayer?.setYear(year),
    setBlocks(blocks) {
      picker = blockPicker(blocks, proj);
    },
    select(position, fly = false) {
      outline?.remove();
      outline = null;
      if (position === null || !picker) return;
      const ring = picker.outline(position).map((p) => toLatLng(frame.toFrame(p)));
      outline = L.polygon(ring, { className: "qv-block-outline", interactive: false, weight: 2.5 }).addTo(
        map,
      );
      if (fly) {
        const centre = toLatLng(frame.toFrame(picker.centre(position)));
        map.flyTo(centre, Math.max(map.getZoom(), index.zmax - 3), { duration: 0.6 });
      }
    },
    view,
    pendingEraTiles: () => eraLayer?.pending() ?? 0,
    compositorKind: () => compositorKind,
    destroy() {
      map.remove();
    },
  };
}
