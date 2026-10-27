import { describe, expect, it } from "vitest";
import { decodeBlocks } from "../data/blocks";
import { decodeChunk } from "../data/qct";
import { twoBlocks } from "../test/builders";
import { blockPicker } from "./pick";
import { projection } from "../tiles/projection";

const proj = projection({ sA: 0.42, zex: 1 });
const blocks = decodeBlocks(decodeChunk(twoBlocks()), { id: ["A", "B"] }, []);
const picker = blockPicker(blocks, (x, y, z) => proj.toPlane(x, y, z));

describe("projection", () => {
  it("is north-up: x from x alone, y from y and height", () => {
    const [x, y] = proj.toPlane(100, 100, 0);
    expect(x).toBeCloseTo(Math.SQRT2 * Math.cos(Math.PI / 6) * 100, 10);
    expect(y).toBeCloseTo(Math.SQRT2 * 0.42 * 100, 10);
    expect(proj.toPlane(100, 100, 10)[1]).toBeCloseTo(y + 10, 10);
  });

  it("inverts at a given height", () => {
    const [px, py] = proj.toPlane(-321, 654, 42);
    const [x, y] = proj.toWorld(px, py, 42);
    expect(x).toBeCloseTo(-321, 9);
    expect(y).toBeCloseTo(654, 9);
  });
});

describe("blockPicker", () => {
  const at = (x: number, y: number, z = 0) => picker.at(proj.toPlane(x, y, z));

  it("finds the block under a ground point", () => {
    expect(at(50, 80)).toBe(0);
    expect(at(50, -80, 30)).toBe(1);
  });

  it("returns null off every block", () => {
    expect(at(500, 500)).toBeNull();
    expect(at(-5, 50)).toBeNull();
  });

  it("lets raised ground in front hide the block behind it", () => {
    /* on the plane the rise to the south covers the south edge of the flat block */
    const plane = proj.toPlane(50, 20, 0);
    expect(picker.at(plane)).toBe(1);
  });

  it("outlines a block where the painting shows it", () => {
    const ring = picker.outline(1);
    expect(ring).toHaveLength(4);
    expect(ring[0]?.[1]).toBeCloseTo(proj.toPlane(0, -100, 30)[1], 4);
    const [cx, cy] = picker.centre(0);
    expect(cx).toBeCloseTo(proj.toPlane(50, 0, 0)[0], 4);
    expect(cy).toBeCloseTo(proj.toPlane(0, 50, 0)[1], 4);
  });
});
