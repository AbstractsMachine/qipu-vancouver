import { describe, expect, it } from "vitest";
import { SAN_FRANCISCO, withDataBase } from "../config";
import { encodeChunk, fakeFetch, twoBlocks } from "../test/builders";
import { blockIndexOf, decodeBlocks, ringCentre } from "./blocks";
import { assertSameBlocks, loadCityData, neighbourhoodNames } from "./city";
import { HttpError, fetchJson, fetchOptionalJson, memo } from "./fetch";
import { crc32, decodeChunk } from "./qct";
import { parseBlockIndex, parseBlockRecord, parseDecision, parseMoneyFile, shardFile } from "./records";
import { sourceOf } from "./sources";

describe("QCT1 chunks", () => {
  it("decodes fields as typed arrays", () => {
    const chunk = decodeChunk(
      encodeChunk("k/1", "demo", { a: new Uint16Array([1, 2, 3]), b: new Float32Array([0.5]) }),
    );
    expect(chunk.key).toBe("k/1");
    expect(chunk.kind).toBe("demo");
    expect(Array.from(chunk.fields.get("a") ?? [])).toEqual([1, 2, 3]);
    expect(chunk.fields.get("b")?.[0]).toBe(0.5);
  });

  it("refuses an HTML error page", () => {
    const html = new TextEncoder().encode("<!DOCTYPE html><html>not found</html>").buffer;
    expect(() => decodeChunk(html)).toThrow('the magic "QCT1"');
    expect(() => decodeChunk(new ArrayBuffer(4))).toThrow("at least 16 bytes");
  });

  it("refuses a corrupted or truncated payload", () => {
    const bytes = new Uint8Array(encodeChunk("k", "demo", { a: new Uint32Array([7, 8]) }));
    const flipped = bytes.slice();
    flipped[flipped.length - 1] = (flipped[flipped.length - 1] ?? 0) ^ 1;
    expect(() => decodeChunk(flipped.buffer)).toThrow("matching its CRC-32");
    expect(() => decodeChunk(bytes.slice(0, bytes.length - 2).buffer)).toThrow("a complete payload");
  });

  it("computes the standard CRC-32", () => {
    expect(crc32(new TextEncoder().encode("123456789"))).toBe(0xcbf43926);
  });
});

describe("decodeBlocks", () => {
  const blocks = decodeBlocks(decodeChunk(twoBlocks()), { id: ["A", "B"] }, ["Mission"]);

  it("rebuilds rings in metres from the quantised offsets", () => {
    expect(blocks.count).toBe(2);
    expect(Array.from(blocks.offsets)).toEqual([0, 4, 8]);
    expect(Array.from(blocks.xs.slice(0, 4))).toEqual([0, 100, 100, 0]);
    expect(Array.from(blocks.ys.slice(4, 8))).toEqual([-100, -100, 0, 0]);
    expect(ringCentre(blocks, 0)).toEqual([50, 50]);
  });

  it("reads elevation in metres and neighbourhoods by index", () => {
    expect(Array.from(blocks.elevation)).toEqual([0, 30]);
    expect(Array.from(blocks.hood)).toEqual([0, -1]);
    expect(blockIndexOf(blocks, "B")).toBe(1);
  });

  it("refuses ids that do not match the rings", () => {
    expect(() => decodeBlocks(decodeChunk(twoBlocks()), { id: ["A"] }, [])).toThrow("2 ids, one per ring");
    const noZ = decodeChunk(encodeChunk("b", "blocks", { cnt: new Uint16Array([0]) }));
    expect(() => decodeBlocks(noZ, { id: ["A"] }, [])).toThrow("blocks.sc");
  });
});

describe("records", () => {
  const indexJson = { meta: { shards: 4 }, b: ["A", "B"], n: [2, 0], y0: [1906, 0], y1: [1990, 0] };

  it("reads the block index and finds a block's shard", () => {
    const index = parseBlockIndex(indexJson);
    expect(index.ids).toEqual(["A", "B"]);
    expect(shardFile(1, index)).toBe("block-01.json");
    expect(shardFile(6, index)).toBe("block-02.json");
    expect(() => parseBlockIndex({ ...indexJson, n: [1] })).toThrow("block-index.n: expected 2 entries");
    expect(() => parseBlockIndex({ ...indexJson, meta: { shards: 0 } })).toThrow("positive shard count");
  });

  it("parses a decision into readable fields", () => {
    const d = parseDecision(
      {
        y: 1976,
        d: "11-17",
        k: "R",
        p: 3,
        a: 0,
        u: "journalseptdecofproceed71sanfrich/292",
        t: "Hearings sought",
        pl: "Proposed: hearings",
        hp: "n",
      },
      "row",
    );
    expect(d).toMatchObject({
      year: 1976,
      date: "11-17",
      kind: "R",
      precision: "address",
      amount: null,
      plain: "Proposed: hearings",
      outcome: "pending",
      address: null,
    });
    expect(d.source.href).toBe("https://archive.org/details/journalseptdecofproceed71sanfrich/page/n292/mode/1up");
  });

  it("keeps unknown codes out rather than guessing", () => {
    const d = parseDecision({ y: 1916, d: "", k: "W", p: 9, u: "v/1", t: "x", hp: "?" }, "row");
    expect(d.date).toBeNull();
    expect(d.precision).toBeNull();
    expect(d.outcome).toBeNull();
    expect(() => parseDecision({ y: "1916", k: "W", u: "v/1", t: "x" }, "row")).toThrow("row.y");
  });

  it("reads a block out of its shard, newest first", () => {
    const shard = {
      A: {
        d: [
          { y: 1950, d: "01-02", k: "R", u: "v/1", t: "older" },
          { y: 1990, d: "", k: "O", u: "v/2", t: "newer", a: 5000 },
        ],
        s: ["PINE|ST"],
      },
    };
    const rec = parseBlockRecord(shard, "A");
    expect(rec.decisions.map((d) => d.printed)).toEqual(["newer", "older"]);
    expect(rec.decisions[0]?.amount).toBe(5000);
    expect(rec.streets).toEqual(["PINE|ST"]);
    expect(parseBlockRecord(shard, "Z")).toEqual({ blockId: "Z", decisions: [], streets: [] });
  });

  it("reads places and their money, dropping zero figures", () => {
    const money = parseMoneyFile({
      href: "/places/place/{slug}",
      b: {
        A: [
          {
            slug: "lib",
            name: "Library",
            kind: "library",
            agreed_usd: 4000000,
            paid_usd: null,
            n_contracts: 1,
          },
        ],
        B: [{ slug: "park", name: "Park", agreed_usd: 0 }],
      },
    });
    expect(money.placePath).toBe("/places/place/{slug}");
    expect(money.byBlock.get("A")?.[0]).toEqual({
      slug: "lib",
      name: "Library",
      kind: "library",
      agreed: 4000000,
      paid: null,
      contracts: 1,
    });
    expect(money.byBlock.get("B")?.[0]?.agreed).toBeNull();
  });
});

describe("sourceOf", () => {
  it("links a scanned volume page on the Internet Archive", () => {
    expect(sourceOf({ u: "journal22/2161", c: undefined, approx: true })).toEqual({
      system: "archive",
      href: "https://archive.org/details/journal22/page/n2161/mode/1up",
      page: 2161,
      document: "journal22",
      approximate: true,
    });
  });

  it("links the Clerk's PDF at its page", () => {
    expect(sourceOf({ u: "bag100725/22", c: "b", approx: false }).href).toBe(
      "https://sfbos.org/sites/default/files/bag100725_minutes.pdf#page=22",
    );
  });

  it("links a Legistar meeting with both halves of its id", () => {
    const s = sourceOf({ u: "1408633~BD01A20F/12", c: "l", approx: false });
    expect(s.href).toBe("https://sfgov.legistar.com/View.ashx?M=M&ID=1408633&GUID=BD01A20F#page=12");
    expect(s.page).toBe(12);
  });

  it("uses a row's own URL and reads its page", () => {
    const s = sourceOf({ u: "https://archive.org/details/19740730/page/n6", c: "x", approx: false });
    expect(s).toMatchObject({ system: "url", document: "archive.org", page: 6 });
    expect(sourceOf({ u: "https://www.example.org/a", c: "x", approx: false }).document).toBe("example.org");
    expect(sourceOf({ u: "not a url", c: "x", approx: false }).document).toBe("not a url");
  });

  it("handles a citation with no page", () => {
    expect(sourceOf({ u: "volume", c: undefined, approx: false }).href).toBe("https://archive.org/details/volume");
  });
});

describe("loadCityData", () => {
  const base = "https://data.example/sf";
  const city = withDataBase(SAN_FRANCISCO, `${base}/`);
  const routes = {
    [`${base}/manifest.json`]: { chunks: [{ kind: "terrain" }, { kind: "blocks", hoodNames: ["Mission"] }] },
    [`${base}/base/blocks.qc`]: twoBlocks(),
    [`${base}/base/blocks-id.json`]: { id: ["A", "B"] },
    [`${base}/blocks/block-index.json`]: {
      meta: { shards: 2 },
      b: ["A", "B"],
      n: [1, 0],
      y0: [1950, 0],
      y1: [1950, 0],
    },
    [`${base}/blocks/block-00.json`]: { A: { d: [{ y: 1950, d: "", k: "R", u: "v/1", t: "paving" }] } },
    [`${base}/blocks/block-money.json`]: { href: "/p/{slug}", b: { A: [{ slug: "s", name: "School" }] } },
  };

  it("loads blocks, the index and a block's record", async () => {
    const data = await loadCityData(city, fakeFetch(routes));
    expect(data.blocks.neighbourhoods).toEqual(["Mission"]);
    expect((await data.record(0)).decisions[0]?.printed).toBe("paving");
    expect(await data.record(1)).toEqual({ blockId: "B", decisions: [], streets: [] });
    await expect(data.record(5)).rejects.toThrow(RangeError);
    expect((await data.places("A"))[0]?.name).toBe("School");
    expect(await data.places("B")).toEqual([]);
    expect(await data.placePath()).toBe("/p/{slug}");
  });

  it("works without a money file", async () => {
    const rest = Object.fromEntries(Object.entries(routes).filter(([url]) => !url.endsWith("block-money.json")));
    const data = await loadCityData(city, fakeFetch(rest));
    expect(await data.places("A")).toEqual([]);
    expect(await data.placePath()).toBeNull();
  });

  it("refuses geometry and index that disagree", async () => {
    const swapped = {
      ...routes,
      [`${base}/blocks/block-index.json`]: {
        meta: { shards: 1 },
        b: ["B", "A"],
        n: [0, 0],
        y0: [0, 0],
        y1: [0, 0],
      },
    };
    await expect(loadCityData(city, fakeFetch(swapped))).rejects.toThrow('block-index.b[0]: expected "A"');
  });

  it("reports a missing file with its URL", async () => {
    await expect(loadCityData(city, fakeFetch({}))).rejects.toThrow(HttpError);
  });

  it("checks the join length too", () => {
    const blocks = decodeBlocks(decodeChunk(twoBlocks()), { id: ["A", "B"] }, []);
    expect(() => {
      assertSameBlocks(blocks, parseBlockIndex({ meta: { shards: 1 }, b: ["A"], n: [0], y0: [0], y1: [0] }));
    }).toThrow("2 blocks, as in the geometry");
  });

  it("finds neighbourhood names, or none", () => {
    expect(neighbourhoodNames({ chunks: [] })).toEqual([]);
    expect(() => neighbourhoodNames([])).toThrow("manifest");
  });
});

describe("fetch helpers", () => {
  it("returns null for an optional file that is missing", async () => {
    expect(await fetchOptionalJson("x", fakeFetch({}))).toBeNull();
    expect(await fetchOptionalJson("x", fakeFetch({ x: { a: 1 } }))).toEqual({ a: 1 });
    const failing = (() => Promise.resolve(new Response("", { status: 500 }))) as typeof fetch;
    await expect(fetchOptionalJson("x", failing)).rejects.toThrow("x: HTTP 500");
    await expect(fetchJson("y", fakeFetch({}))).rejects.toThrow("y: HTTP 404");
  });

  it("memoises loads and forgets failures", async () => {
    let calls = 0;
    const load = memo((k: string) => {
      calls++;
      return k === "bad" ? Promise.reject(new Error("no")) : Promise.resolve(k.length);
    });
    expect(await load("abc")).toBe(3);
    expect(await load("abc")).toBe(3);
    await expect(load("bad")).rejects.toThrow("no");
    await expect(load("bad")).rejects.toThrow("no");
    expect(calls).toBe(3);
  });
});
