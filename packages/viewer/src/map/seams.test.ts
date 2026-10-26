import * as L from "leaflet";
import { describe, expect, it } from "vitest";
import { closeSeams } from "./seams";

describe("closeSeams", () => {
  it("draws every tile one CSS pixel larger than its slot", () => {
    const layer = new L.GridLayer({ tileSize: 256 });
    closeSeams(layer, 256);
    const tile = document.createElement("div");
    layer.fire("tileloadstart", { tile, coords: Object.assign(L.point(0, 0), { z: 0 }) });
    expect(tile.style.width).toBe("257px");
    expect(tile.style.height).toBe("257px");
  });
});
