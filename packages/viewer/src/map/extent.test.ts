import * as L from "leaflet";
import { describe, expect, it } from "vitest";
import { clipToPainting } from "./extent";

/* 160 x 96 frame: at level 2 that is 2.5 x 1.5 tiles */
const painting = { width: 160, height: 96 };

function clipOf(x: number, y: number, z = 2, zoomOffset = 0): string {
  const layer = new L.GridLayer();
  clipToPainting(layer, painting, zoomOffset);
  const tile = document.createElement("div");
  layer.fire("tileloadstart", { tile, coords: Object.assign(L.point(x, y), { z }) });
  return tile.style.clipPath;
}

describe("clipToPainting", () => {
  it("leaves a tile inside the painting whole", () => {
    expect(clipOf(0, 0)).toBe("");
  });

  it("cuts the last column and row down to the painting", () => {
    expect(clipOf(2, 0)).toBe("inset(0 50% 0% 0)");
    expect(clipOf(0, 1)).toBe("inset(0 0% 50% 0)");
    expect(clipOf(2, 1)).toBe("inset(0 50% 50% 0)");
  });

  it("reads the level from the zoom offset", () => {
    expect(clipOf(2, 0, 1, 1)).toBe("inset(0 50% 0% 0)");
  });
});
