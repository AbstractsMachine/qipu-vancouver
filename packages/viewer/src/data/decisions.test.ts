import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { VANCOUVER, withDataBase } from "../config";
import { fakeFetch, twoBlocks } from "../test/builders";
import { decodeBlocks } from "./blocks";
import { loadCityData, neighbourhoodNames } from "./city";
import { parseDecisionsJsonl, placeOnBlocks, projectionOf, toWorld } from "./decisions";
import { decodeChunk } from "./qct";

/* a projection in which a degree is a metre, so the test blocks' metres can be written as lat/lon */
const METRES = { lon0: 0, lat0: 0, mpd: 1, cosl: 1 };

function row(fields: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "19740219:3/1",
    date: "1974-02-19",
    kind: "resolution",
    outcome: "passed",
    summary: "Lane paving approved.",
    quote: "THAT the lane be paved",
    money: [
      { amount: 1200, currency: "CAD" },
      { amount: 8000, currency: "CAD" },
    ],
    places: [{ text: "100 Keefer Street", precision: "address", lat: 50, lon: 50, placed_as: "address" }],
    source: {
      page_url: "https://archive.org/details/19740219/page/n3",
      item_url: "https://archive.org/details/19740219",
    },
    ...fields,
  };
}

const jsonl = (...rows: Record<string, unknown>[]) => rows.map((r) => JSON.stringify(r)).join("\n") + "\n";

describe("reading packages/records' decisions.jsonl", () => {
  it("turns a row into the panel's decision", () => {
    const [placed] = parseDecisionsJsonl(jsonl(row()));
    expect(placed?.decision).toEqual({
      year: 1974,
      date: "02-19",
      kind: "resolution",
      precision: "address",
      amount: 8000,
      printed: "THAT the lane be paved",
      plain: "Lane paving approved.",
      outcome: "decided",
      address: null,
      source: {
        system: "url",
        href: "https://archive.org/details/19740219/page/n3",
        page: 3,
        document: "archive.org",
        approximate: false,
      },
    });
    expect(placed?.points).toEqual([{ lat: 50, lon: 50, precision: "address" }]);
  });

  it("maps every outcome and falls back to the item when the page is unknown", () => {
    const outcomes = ["passed", "pending", "refused", "unknown", "something new"].map(
      (outcome) => parseDecisionsJsonl(jsonl(row({ outcome })))[0]?.decision.outcome,
    );
    expect(outcomes).toEqual(["decided", "pending", "failed", "unrecorded", null]);
    const [placed] = parseDecisionsJsonl(
      jsonl(row({ source: { page_url: null, item_url: "https://archive.org/details/19740219" } })),
    );
    expect(placed?.decision.source).toMatchObject({ href: "https://archive.org/details/19740219", approximate: true });
  });

  it("leaves out undated rows and places that name no block", () => {
    const rows = parseDecisionsJsonl(
      jsonl(
        row({ date: null }),
        row({
          money: [],
          places: [
            { text: "Strathcona", precision: "area", lat: 1, lon: 1, placed_as: "area" },
            { text: "Main and Keefer", precision: "intersection", lat: 2, lon: 2, placed_as: "intersection" },
            { text: "somewhere", precision: "street" },
          ],
        }),
      ),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.decision.amount).toBeNull();
    expect(rows[0]?.decision.precision).toBe("corner");
    expect(rows[0]?.points).toEqual([{ lat: 2, lon: 2, precision: "corner" }]);
  });

  it("names the line of a malformed row", () => {
    expect(() => parseDecisionsJsonl(`${JSON.stringify(row())}\n{oops\n`)).toThrow("decisions.jsonl line 2");
    expect(() => parseDecisionsJsonl(JSON.stringify(row({ quote: 3 })))).toThrow("decisions.jsonl line 1.quote");
  });
});

describe("placing rows on blocks", () => {
  const blocks = decodeBlocks(decodeChunk(twoBlocks()), { id: ["A", "B"] }, []);

  it("puts a row on the block its place falls in, or the nearest within a street's width", () => {
    const rows = parseDecisionsJsonl(
      jsonl(
        row({ date: "1970-06-09" }),
        row({ places: [{ text: "x", lat: -50, lon: 50, placed_as: "address" }] }),
        row({ date: "1982-01-05", places: [{ text: "x", lat: 110, lon: 50, placed_as: "intersection" }] }),
        row({ places: [{ text: "x", lat: 500, lon: 50, placed_as: "address" }] }),
      ),
    );
    const { index, records } = placeOnBlocks(rows, blocks, METRES);
    expect(index.ids).toEqual(["A", "B"]);
    expect(index.counts).toEqual([2, 1]);
    expect(index.firstYears).toEqual([1970, 1974]);
    expect(index.lastYears).toEqual([1982, 1974]);
    expect(records.get("A")?.decisions.map((d) => d.year)).toEqual([1982, 1970]);
  });

  it("lists a row once per block however many of its places fall there", () => {
    const places = [
      { text: "a", lat: 10, lon: 10, placed_as: "address" },
      { text: "b", lat: 20, lon: 20, placed_as: "address" },
      { text: "c", lat: -20, lon: 20, placed_as: "address" },
    ];
    const { index } = placeOnBlocks(parseDecisionsJsonl(jsonl(row({ places }))), blocks, METRES);
    expect(index.counts).toEqual([1, 1]);
  });

  it("projects with the city manifest's projection", () => {
    const p = projectionOf({ proj: { lon0: -123.1302, lat0: 49.2565, mpd: 111320, cosl: 0.65 } });
    const [x, y] = toWorld(p, 49.2565 + 1 / 111320, -123.1302 + 2 / (111320 * 0.65));
    expect(x).toBeCloseTo(2, 6);
    expect(y).toBeCloseTo(1, 6);
    expect(projectionOf({ proj: { lon0: 0, lat0: 60, mpd: 1 } }).cosl).toBeCloseTo(0.5, 9);
  });
});

describe("loading a city from a decisions.jsonl", () => {
  const base = "https://data.example/vancouver";
  const decisions = "https://data.example/records/decisions.jsonl";
  const city = { ...withDataBase(VANCOUVER, base), data: { base, decisions } };
  const routes = {
    [`${base}/manifest.json`]: { proj: METRES, chunks: [{ kind: "blocks", hoodNames: ["Strathcona"] }] },
    [`${base}/base/blocks.qc`]: twoBlocks(),
    [`${base}/base/blocks-id.json`]: { id: ["A", "B"] },
    [decisions]: jsonl(row()),
  };

  it("reads the records from it and never asks for the shards", async () => {
    const asked: string[] = [];
    const serve = fakeFetch(routes);
    const data = await loadCityData(city, (url, init) => {
      asked.push(url);
      return serve(url, init);
    });
    expect(data.index.counts).toEqual([1, 0]);
    expect((await data.record(0)).decisions[0]?.printed).toBe("THAT the lane be paved");
    expect(await data.record(1)).toEqual({ blockId: "B", decisions: [], streets: [] });
    expect(asked.some((url) => url.includes("/blocks/"))).toBe(false);
  });

  it("keeps the decisions URL when the data folder moves", () => {
    expect(withDataBase(city, "/sample/vancouver").data).toEqual({ base: "/sample/vancouver", decisions });
  });
});

describe("the demo's records sample", () => {
  /* vitest runs from the package folder */
  const read = (name: string) => readFileSync(join("demo/public/sample/vancouver", name));

  it("places packages/records' Vancouver output on the sample's blocks", () => {
    const manifest = JSON.parse(read("manifest.json").toString("utf8")) as unknown;
    const raw = read("base/blocks.qc");
    const chunk = decodeChunk(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength));
    const blocks = decodeBlocks(
      chunk,
      JSON.parse(read("base/blocks-id.json").toString("utf8")),
      neighbourhoodNames(manifest),
    );
    const rows = parseDecisionsJsonl(read("decisions.jsonl").toString("utf8"));
    const { records } = placeOnBlocks(rows, blocks, projectionOf(manifest));
    const quotes = (id: string) => records.get(id)?.decisions.map((d) => d.printed) ?? [];
    expect(quotes("3054")).toContain("Y.M.C.A. Building at 2617 East Broadway: Use for Travelling Youth and Young Men");
    expect(records.get("4284")?.decisions[0]?.year).toBe(1974);
    expect([...records.keys()].length).toBeGreaterThanOrEqual(6);
  });
});
