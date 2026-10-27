import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/*
 * The bundled demo data must follow this repository's privacy rule (docs/privacy.md, qipu_records.verify.privacy):
 * a name is withheld everywhere in a record or nowhere. A name masked in one field and printed in another is a mask
 * that protects no one and hides a public name, as the SF cut once did for a contractor ("Dr. Bach-Y-Rita",
 * sf block rows 3532/3533) and an organisation ("Colonial Dames", row 0175).
 */
const SAMPLE = join(__dirname, "../../demo/public/sample");
const WITHHELD = "[name withheld]";

type Row = Record<string, unknown>;

function blockRows(city: string): Row[] {
  const folder = join(SAMPLE, city, "blocks");
  return readdirSync(folder)
    .filter((name) => /^block-\d+\.json$/.test(name))
    .flatMap((name) => {
      const shard = JSON.parse(readFileSync(join(folder, name), "utf8")) as Record<string, { d?: Row[] }>;
      return Object.values(shard).flatMap((block) => block.d ?? []);
    });
}

function recordRows(city: string): Row[] {
  const text = readFileSync(join(SAMPLE, city, "decisions.jsonl"), "utf8");
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as Row);
}

function texts(row: Row): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(row)) {
    out[key] = typeof value === "string" ? value : JSON.stringify(value);
  }
  return out;
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Names a field masks that another field of the same row prints: the words between a mask's neighbours there. */
function shownElsewhere(row: Row): string[] {
  const fields = texts(row);
  const found: string[] = [];
  for (const [key, value] of Object.entries(fields)) {
    if (!value.includes(WITHHELD)) continue;
    const parts = value.split(/(?:\[name withheld\])+/);
    for (let i = 0; i + 1 < parts.length; i++) {
      const before = (parts[i] ?? "").trim().split(/\s+/).slice(-1).join(" ");
      const after = (parts[i + 1] ?? "").trim().split(/\s+/).slice(0, 2).join(" ");
      if (!before || !after) continue;
      const between = new RegExp(`${escape(before)}\\s*(.+?)\\s*${escape(after)}`);
      for (const [other, text] of Object.entries(fields)) {
        if (other === key) continue;
        const name = between.exec(text)?.[1]?.trim();
        if (name && !name.includes(WITHHELD)) found.push(`${key} masks "${name}", ${other} prints it`);
      }
    }
  }
  return found;
}

describe("the bundled sample follows the privacy rule", () => {
  it("finds a name masked in one field and printed in another", () => {
    const row = {
      t: "Sheriff to hire Dr. Bach-Y-Rita to screen deputy applicants",
      pl: "the Sheriff hiring Dr. [name withheld][name withheld] to screen deputy applicants",
    };
    expect(shownElsewhere(row)).toEqual(['pl masks "Bach-Y-Rita", t prints it']);
    expect(shownElsewhere({ t: "Claim of [name withheld] paid", pl: "A claim by [name withheld] was paid" })).toEqual(
      [],
    );
  });

  for (const [city, rows] of [
    ["sf", blockRows("sf")],
    ["vancouver", blockRows("vancouver")],
    ["vancouver decisions.jsonl", recordRows("vancouver")],
  ] as const) {
    it(`never masks a name in one field of ${city} and prints it in another`, () => {
      expect(rows.length).toBeGreaterThan(0);
      const problems = rows.flatMap((row) => shownElsewhere(row).map((p) => `${String(row.id ?? row.u)}: ${p}`));
      expect(problems).toEqual([]);
    });
  }
});
