#!/usr/bin/env node
/**
 * Cut the demo's sample out of a city's published data folder (what
 * qipu.org serves under /data/<country>/<city>/city). Geometry and the
 * block index are kept whole, so the map, the picker and the deep links
 * behave as on the site; decisions are kept only for the named
 * neighbourhoods, and every other block's count is set to zero.
 *
 *   node scripts/build-sample.mjs --from <data folder> --to demo/public/sample/vancouver \
 *     --hoods "Strathcona,Mount Pleasant" --currency CAD --note "..."
 *
 * The money file is written with currency-neutral field names (`agreed`, `paid`) and the `currency` it is in;
 * qipu.org's files call them `agreed_usd` and `paid_usd` whatever the city's currency.
 */
import { mkdirSync, readFileSync, writeFileSync, copyFileSync } from "node:fs";
import { join } from "node:path";
import { parseArgs } from "node:util";

const { values } = parseArgs({
  options: {
    from: { type: "string" },
    to: { type: "string" },
    hoods: { type: "string" },
    note: { type: "string", default: "" },
    currency: { type: "string" },
  },
});
if (!values.from || !values.to || !values.hoods || !/^[A-Z]{3}$/.test(values.currency ?? "")) {
  console.error(
    "usage: build-sample.mjs --from <data folder> --to <sample folder> --hoods <a,b,c> --currency <ISO code> [--note <text>]",
  );
  process.exit(2);
}
const from = values.from;
const to = values.to;
const wanted = new Set(values.hoods.split(",").map((s) => s.trim()));

const readJson = (p) => JSON.parse(readFileSync(join(from, p), "utf8"));
const writeJson = (p, v) => {
  mkdirSync(join(to, p, ".."), { recursive: true });
  writeFileSync(join(to, p), JSON.stringify(v));
};

/* the manifest, cut to what the viewer reads: the projection and the blocks chunk's neighbourhood names */
const manifest = readJson("manifest.json");
const blocksEntry = manifest.chunks.find((c) => c.kind === "blocks");
writeJson("manifest.json", { format: manifest.format, proj: manifest.proj, chunks: [blocksEntry] });

mkdirSync(join(to, "base"), { recursive: true });
copyFileSync(join(from, "base/blocks.qc"), join(to, "base/blocks.qc"));
copyFileSync(join(from, "base/blocks-id.json"), join(to, "base/blocks-id.json"));

/* which blocks are in the chosen neighbourhoods: the hood byte of the blocks chunk */
const chunk = readFileSync(join(from, "base/blocks.qc"));
const headerLength = chunk.readUInt32LE(4);
const header = JSON.parse(chunk.subarray(16, 16 + headerLength).toString("utf8"));
const payload = (16 + headerLength + 7) & ~7;
const hoodField = header.fields.find((f) => f.n === "hood");
const names = blocksEntry.hoodNames;
const inSample = (i) => wanted.has(names[chunk[payload + hoodField.o + i]]);

const index = readJson("blocks/block-index.json");
const keep = new Set();
index.b.forEach((id, i) => {
  if (inSample(i) && index.n[i] > 0) keep.add(id);
  else index.n[i] = 0;
});
index.meta = {
  ...index.meta,
  sample: { neighbourhoods: [...wanted], blocks: keep.size, note: values.note },
};
writeJson("blocks/block-index.json", index);

let decisions = 0;
for (let s = 0; s < index.meta.shards; s++) {
  const file = `blocks/block-${String(s).padStart(2, "0")}.json`;
  const shard = readJson(file);
  const out = {};
  for (const [id, entry] of Object.entries(shard)) {
    if (!keep.has(id)) continue;
    out[id] = entry;
    decisions += entry.d.length;
  }
  if (Object.keys(out).length) writeJson(file, out);
}

try {
  const money = readJson("blocks/block-money.json");
  money.currency = values.currency;
  money.b = Object.fromEntries(
    Object.entries(money.b)
      .filter(([id]) => keep.has(id))
      .map(([id, places]) => [id, places.map(neutralMoney)]),
  );
  writeJson("blocks/block-money.json", money);
} catch {
  /* a city may publish no money file */
}

function neutralMoney(place) {
  const { agreed_usd: agreed, paid_usd: paid, payees_paid_usd: payeesPaid, ...rest } = place;
  return { ...rest, agreed, paid, payees_paid: payeesPaid };
}

console.log(`${to}: ${keep.size} blocks, ${decisions} decisions from ${[...wanted].join(", ")}`);
