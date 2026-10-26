import type { CityConfig } from "../config";
import { type Blocks, decodeBlocks } from "./blocks";
import { type Fetch, fetchBuffer, fetchJson, fetchOptionalJson, memo } from "./fetch";
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

export async function loadCityData(city: CityConfig, fetcher: Fetch = fetch): Promise<CityData> {
  const base = city.data.base.replace(/\/$/, "");
  const [manifest, chunk, ids, indexJson] = await Promise.all([
    fetchJson(`${base}/manifest.json`, fetcher),
    fetchBuffer(`${base}/base/blocks.qc`, fetcher),
    fetchJson(`${base}/base/blocks-id.json`, fetcher),
    fetchJson(`${base}/blocks/block-index.json`, fetcher),
  ]);
  const blocks = decodeBlocks(decodeChunk(chunk), ids, neighbourhoodNames(manifest));
  const index = parseBlockIndex(indexJson);
  assertSameBlocks(blocks, index);

  const shard = memo((file: string) => fetchJson(`${base}/blocks/${file}`, fetcher));
  const money = memo(async (): Promise<MoneyFile | null> => {
    const json = await fetchOptionalJson(`${base}/blocks/block-money.json`, fetcher);
    return json === null ? null : parseMoneyFile(json);
  });
  return {
    blocks,
    index,
    async record(position) {
      const id = index.ids[position];
      if (id === undefined) throw new RangeError(`no block at position ${position}`);
      if ((index.counts[position] ?? 0) === 0) return { blockId: id, decisions: [], streets: [] };
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
    throw new FormatError(
      "block-index.b",
      `${blocks.ids.length} blocks, as in the geometry (got ${index.ids.length})`,
    );
  }
  const at = blocks.ids.findIndex((id, i) => id !== index.ids[i]);
  if (at >= 0) throw new FormatError(`block-index.b[${at}]`, `"${blocks.ids[at]}", as in the geometry`);
}
