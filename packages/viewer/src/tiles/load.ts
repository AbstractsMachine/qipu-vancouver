import type { CityConfig } from "../config";
import { type Fetch, fetchJson } from "../data/fetch";
import { type EraManifest, parseEraManifest } from "../eras/manifest";
import { type PyramidIndex, parsePyramidIndex } from "./pyramid";
import { trimSlash } from "./urls";

export interface Painting {
  readonly index: PyramidIndex;
  /** null for a city with no eras: the map then has no year slider */
  readonly eras: EraManifest | null;
}

/** The two small JSON files the map needs before its first tile. */
export async function loadPainting(city: CityConfig, fetcher: Fetch = fetch): Promise<Painting> {
  const base = trimSlash(city.tiles.base);
  const [index, eras] = await Promise.all([
    fetchJson(`${base}/${city.tiles.present}/index.json`, fetcher).then(parsePyramidIndex),
    city.tiles.eras ? fetchJson(`${base}/${city.tiles.eras}`, fetcher) : Promise.resolve(null),
  ]);
  return { index, eras: eras === null ? null : parseEraManifest(eras, { tile: index.tile }) };
}
