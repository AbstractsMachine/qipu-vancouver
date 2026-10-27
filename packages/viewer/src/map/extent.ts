import type * as L from "leaflet";
import { TILE_CSS } from "../tiles/frame";
import type { Painting } from "../tiles/painting";

/**
 * A pyramid is whole tiles, so the last column and row of a level are only
 * partly picture; the rest is black. Clipping each edge tile to the
 * painting's own size keeps that padding off the map.
 */
export function clipToPainting(
  layer: L.GridLayer,
  painting: Pick<Painting, "width" | "height">,
  zoomOffset: number,
): void {
  layer.on("tileloadstart", (e: L.TileEvent) => {
    const k = 2 ** (e.coords.z + zoomOffset) / TILE_CSS;
    const right = Math.max(0, 1 - (painting.width * k - e.coords.x));
    const bottom = Math.max(0, 1 - (painting.height * k - e.coords.y));
    if (right > 0 || bottom > 0) {
      e.tile.style.clipPath = `inset(0 ${right * 100}% ${bottom * 100}% 0)`;
    }
  });
}
