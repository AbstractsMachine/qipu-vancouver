import type * as L from "leaflet";

/**
 * At fractional zooms the browser rounds each tile's edges on its own and a
 * hairline of background shows between neighbours. Drawing every tile one
 * CSS pixel larger than its slot covers the gap; the overlap is a pixel of
 * the same painting.
 */
export function closeSeams(layer: L.GridLayer, tileSize: number): void {
  layer.on("tileloadstart", (e: L.TileEvent) => {
    e.tile.style.width = `${tileSize + 1}px`;
    e.tile.style.height = `${tileSize + 1}px`;
  });
}
