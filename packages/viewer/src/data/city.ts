import type { CityConfig } from "../config";
import { type Blocks, decodeBlocks } from "./blocks";
import { parseDecisionsJsonl, placeOnBlocks, projectionOf } from "./decisions";
import { type Fetch, fetchBuffer, fetchJson, fetchOptionalJson, fetchText, memo } from "./fetch";
import { decodeChunk } from "./qct";
import {
  type BlockIndex,
  type BlockRecord,
  type MoneyFile,
  type Place,
  parseBlockIndex,
  parseBlockRecord,
  parseMoneyFile,
  shardFile,
} from "./records";
import { type Json, FormatError, isRecord, list, strings } from "./validate";

/**
 * A city's blocks and their record, loaded in tiers: the geometry and the
 * block index at start (a few hundred kB), one shard per block opened, and
 * the money file only when a panel first asks for it.
 */
export interface CityData {
  readonly blocks: Blocks;
  readonly index: BlockIndex;
  /** the record of the block at a geometry position */
  record(position: number): Promise<BlockRecord>;
  /** named places on a block, with their money */
  places(blockId: string): Promise<readonly Place[]>;
  /** the qipu.org page pattern for a place (`{slug}`), if the city publishes one */
  placePath(): Promise<string | null>;
}

/**
 * A city's block geometry and index, fetched in parallel from its data folder. The index and the records come either
 * from the published shards (blocks/, one shard fetched per block opened) or, when the config names one, from a
 * records `decisions.jsonl` placed on the blocks at load. Rejects with an `HttpError` or a `FormatError` when a file is
 * missing or malformed.
 */
export async function loadCityData(city: CityConfig, fetcher: Fetch = fetch): Promise<CityData> {
  const base = city.data.base.replace(/\/$/, "");
  const decisionsUrl = city.data.decisions;
  const [manifest, chunk, ids, indexJson, decisionsText] = await Promise.all([
    fetchJson(`${base}/manifest.json`, fetcher),
    fetchBuffer(`${base}/base/blocks.qc`, fetcher),
    fetchJson(`${base}/base/blocks-id.json`, fetcher),
    decisionsUrl === undefined ? fetchJson(`${base}/blocks/block-index.json`, fetcher) : null,
    decisionsUrl === undefined ? null : fetchText(decisionsUrl, fetcher),
  ]);
  const blocks = decodeBlocks(decodeChunk(chunk), ids, neighbourhoodNames(manifest));

  /* records' own output: every row placed on its block here, so nothing more is fetched per click */
  const placed =
    decisionsText === null ? null : placeOnBlocks(parseDecisionsJsonl(decisionsText), blocks, projectionOf(manifest));
  const index = placed?.index ?? parseBlockIndex(indexJson);
  assertSameBlocks(blocks, index);

  const shard = memo((file: string) => fetchJson(`${base}/blocks/${file}`, fetcher));
  const money = memo(async (): Promise<MoneyFile | null> => {
    const json = await fetchOptionalJson(`${base}/blocks/block-money.json`, fetcher);
    if (json === null) return null;
    const file = parseMoneyFile(json);
    /* the panel prints amounts in the city's currency, so a file in another one must not be shown as if it were */
    if (file.currency !== null && file.currency !== city.record.currency) {
      throw new FormatError(
        "block-money.currency",
        `${city.record.currency}, the city's currency (got ${file.currency})`,
      );
    }
    return file;
  });
  return {
    blocks,
    index,
    async record(position) {
      const id = index.ids[position];
      if (id === undefined) throw new RangeError(`no block at position ${position}`);
      if ((index.counts[position] ?? 0) === 0) return { blockId: id, decisions: [], streets: [] };
      if (placed) return placed.records.get(id) ?? { blockId: id, decisions: [], streets: [] };
      return parseBlockRecord(await shard(shardFile(position, index)), id);
    },
    async places(blockId) {
      return (await money(undefined))?.byBlock.get(blockId) ?? [];
    },
    async placePath() {
      return (await money(undefined))?.placePath ?? null;
    },
  };
}

/** The neighbourhood names the blocks chunk indexes into, from the city manifest. */
export function neighbourhoodNames(manifest: Json): string[] {
  if (!isRecord(manifest)) throw new FormatError("manifest", "an object");
  const chunks = list(manifest.chunks, "manifest.chunks");
  const entry = chunks.find((c) => isRecord(c) && c.kind === "blocks");
  if (!isRecord(entry) || entry.hoodNames === undefined) return [];
  return strings(entry.hoodNames, "manifest.chunks[blocks].hoodNames");
}

/**
 * The geometry and the record index are two files built separately and joined
 * by position. If they disagree, every decision would be drawn on the wrong
 * block and nothing would fail, so refuse to start instead.
 */
export function assertSameBlocks(blocks: Blocks, index: BlockIndex): void {
  if (blocks.ids.length !== index.ids.length) {
    throw new FormatError("block-index.b", `${blocks.ids.length} blocks, as in the geometry (got ${index.ids.length})`);
  }
  const at = blocks.ids.findIndex((id, i) => id !== index.ids[i]);
  if (at >= 0) throw new FormatError(`block-index.b[${at}]`, `"${blocks.ids[at]}", as in the geometry`);
}
