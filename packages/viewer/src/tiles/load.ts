import type { CityConfig } from "../config";
import { type Fetch, fetchJson } from "../data/fetch";
import { parseLiveEras } from "./live-eras";
import { livePainting, parsePyramidIndex } from "./live-index";
import type { Painting } from "./painting";
import { parseQipuTiles } from "./qipu-tiles";
import { trimSlash } from "./urls";

/** The small JSON files the map needs before its first tile. */
export async function loadPainting(city: CityConfig, fetcher: Fetch = fetch): Promise<Painting> {
  const base = trimSlash(city.tiles.base);
  const tiles = city.tiles;
  if (tiles.format === "qipu-tiles/1") {
    return parseQipuTiles(await fetchJson(`${base}/${tiles.manifest ?? "manifest.json"}`, fetcher));
  }
  const [indexJson, erasJson] = await Promise.all([
    fetchJson(`${base}/${tiles.present}/index.json`, fetcher),
    tiles.eras ? fetchJson(`${base}/${tiles.eras}`, fetcher) : Promise.resolve(null),
  ]);
  const index = parsePyramidIndex(indexJson);
  return livePainting(index, tiles.present, erasJson === null ? null : parseLiveEras(erasJson, { tile: index.tile }));
}
