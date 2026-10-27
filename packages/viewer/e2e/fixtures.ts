import { readFileSync } from "node:fs";
import { deflateSync } from "node:zlib";
import type { Page, Route } from "@playwright/test";
import { crc32 } from "../src/data/qct";

/*
 * The end-to-end tests never reach tiles.qipu.org. Its two JSON files are
 * served from real copies in src/test/fixtures, and every tile is a small
 * solid PNG whose colour says which pyramid it came from, so a test can read
 * a pixel and know which year the map is drawing.
 */

export const TILES = "https://tiles.qipu.org/us/sf/city/r20261001";

export const COLOURS = {
  present: [90, 110, 130],
  1915: [200, 120, 40],
  1959: [40, 160, 90],
} as const;

/** The Haight switch map from 1915 to 1959 changes every pixel at 1940.00. */
export const SWITCH_YEAR = 1940;

/** Block 1270, Haight-Ashbury, in the demo's sample: 63 decisions. Frame point of its centre. */
export const HAIGHT_BLOCK = { id: "1270", x: 71.01, y: 49.58 } as const;

const fixture = (name: string) => readFileSync(new URL(`../src/test/fixtures/${name}`, import.meta.url));

export async function serveTiles(page: Page): Promise<{ requested: string[] }> {
  const requested: string[] = [];
  await page.route(`${TILES}/**`, (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.slice(new URL(TILES).pathname.length + 1);
    requested.push(path);
    if (path === "render/index.json") return json(route, fixture("sf-index.json"));
    if (path === "_preview_eras/render-years.json") return json(route, fixture("sf-eras.json"));
    const colour = tileColour(path);
    if (!colour) return route.fulfill({ status: 404, body: "" });
    return route.fulfill({ status: 200, contentType: "image/png", body: solidPng(colour) });
  });
  /* a source link opens the Internet Archive in a new tab; answer it here */
  await page
    .context()
    .route("https://archive.org/**", (route) =>
      route.fulfill({ status: 200, contentType: "text/html", body: "<title>Internet Archive</title>" }),
    );
  return { requested };
}

function tileColour(path: string): readonly number[] | null {
  if (path.startsWith("render/")) return [...COLOURS.present, 255];
  if (path.startsWith("_preview_eras/area/haight/1915/")) return [...COLOURS[1915], 255];
  if (path.startsWith("_preview_eras/area/haight/1959/")) return [...COLOURS[1959], 255];
  if (path.startsWith("_preview_eras/area/haight/switch/1915-1959/")) {
    const code = (SWITCH_YEAR - 1800) * 100;
    return [code >> 8, code & 255, 0, 255];
  }
  return null;
}

function json(route: Route, body: Buffer) {
  return route.fulfill({ status: 200, contentType: "application/json", body });
}

/** An 8 x 8 RGBA PNG of one colour. */
export function solidPng(rgba: readonly number[]): Buffer {
  const size = 8;
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: size }, () => rgba).flat())]);
  const raw = Buffer.concat(Array.from({ length: size }, () => row));
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function chunk(type: string, data: Buffer): Buffer {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

/** The colour the era layer draws at the centre of the map, once it has drawn `year`. */
export async function eraColourAtCentre(page: Page, year: number): Promise<number[]> {
  return page.evaluate(async (want) => {
    const map = document.querySelector(".qv-map");
    if (!map) throw new Error("no map");
    const r = map.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    for (let i = 0; i < 100; i++) {
      for (const c of document.querySelectorAll<HTMLCanvasElement>(".qv-era-layer canvas")) {
        const b = c.getBoundingClientRect();
        if (cx < b.left || cx >= b.right || cy < b.top || cy >= b.bottom || c.dataset.year !== String(want)) continue;
        const x = Math.floor(((cx - b.left) / b.width) * c.width);
        const y = Math.floor(((cy - b.top) / b.height) * c.height);
        return Array.from(c.getContext("2d")?.getImageData(x, y, 1, 1).data ?? []);
      }
      await new Promise((res) => setTimeout(res, 100));
    }
    throw new Error(`the era layer never drew ${want} at the centre`);
  }, year);
}

export function near(actual: readonly number[], expected: readonly number[], tolerance = 3): boolean {
  return expected.every((v, i) => Math.abs((actual[i] ?? -999) - v) <= tolerance);
}
