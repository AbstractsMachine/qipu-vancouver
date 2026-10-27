import { describe, expect, it } from "vitest";
import {
  countOf,
  decadeOf,
  formatDate,
  formatMoney,
  groupByDecade,
  isoDate,
  outcomeWord,
  precisionPhrase,
  recordSummary,
  streetLabel,
} from "./format";

describe("formatDate", () => {
  it("writes day, short month and year", () => {
    expect(formatDate(1976, "11-17")).toBe("17 Nov 1976");
    expect(formatDate(2025, "01-07")).toBe("7 Jan 2025");
  });

  it("falls back to the year without a usable day", () => {
    expect(formatDate(1976, null)).toBe("1976");
    expect(formatDate(1976, "13-01")).toBe("1976");
    expect(formatDate(1976, "00-12")).toBe("1976");
    expect(formatDate(1976, "11-00")).toBe("1976");
    expect(formatDate(1976, "11-32")).toBe("1976");
    expect(formatDate(1976, "1976-11-17")).toBe("1976");
  });
});

describe("isoDate", () => {
  it("matches formatDate", () => {
    expect(isoDate(1976, "11-17")).toBe("1976-11-17");
    expect(isoDate(1976, null)).toBe("1976");
    expect(isoDate(1976, "13-01")).toBe("1976");
  });
});

describe("decades", () => {
  it("rounds a year down to its decade", () => {
    expect(decadeOf(1976)).toBe(1970);
    expect(decadeOf(1970)).toBe(1970);
    expect(decadeOf(2009)).toBe(2000);
  });

  it("groups rows by decade in the order they come", () => {
    const rows = [{ year: 2016 }, { year: 2011 }, { year: 1979 }, { year: 1972 }, { year: 1912 }];
    expect(groupByDecade(rows)).toEqual([
      { decade: 2010, items: [{ year: 2016 }, { year: 2011 }] },
      { decade: 1970, items: [{ year: 1979 }, { year: 1972 }] },
      { decade: 1910, items: [{ year: 1912 }] },
    ]);
    expect(groupByDecade([])).toEqual([]);
  });
});

describe("countOf", () => {
  it("picks singular or plural and groups digits", () => {
    expect(countOf(1, "decision")).toBe("1 decision");
    expect(countOf(0, "decision")).toBe("0 decisions");
    expect(countOf(1204, "contract")).toBe("1,204 contracts");
  });
});

describe("formatMoney", () => {
  it("writes whole dollars in the city's currency", () => {
    expect(formatMoney(60_000_000, "USD")).toBe("$60,000,000");
    expect(formatMoney(4_000_000, "CAD")).toBe("CA$4,000,000");
    expect(formatMoney(49_999.6, "USD")).toBe("$50,000");
  });
});

describe("precisionPhrase", () => {
  it("says how the row was placed", () => {
    expect(precisionPhrase("stated")).toBe("names this block");
    expect(precisionPhrase("address")).toBe("at an address on this block");
    expect(precisionPhrase("segment")).toBe("on a stretch of street along this block");
    expect(precisionPhrase("corner")).toBe("at a corner of this block");
    expect(precisionPhrase("street")).toBe("somewhere on a street this block fronts");
  });
});

describe("outcomeWord", () => {
  it("names stated outcomes and stays silent otherwise", () => {
    expect(outcomeWord("decided")).toBe("Decided");
    expect(outcomeWord("pending")).toBe("Pending");
    expect(outcomeWord("failed")).toBe("Failed");
    expect(outcomeWord("unrecorded")).toBeNull();
    expect(outcomeWord(null)).toBeNull();
  });
});

describe("streetLabel", () => {
  it("writes street keys the way a reader would", () => {
    expect(streetLabel("PINE|ST")).toBe("Pine St");
    expect(streetLabel("SAN BRUNO|AV")).toBe("San Bruno Av");
    expect(streetLabel("O'FARRELL|ST")).toBe("O'Farrell St");
    expect(streetLabel("THE EMBARCADERO|*")).toBe("The Embarcadero");
  });

  it("drops leading zeros from ordinals", () => {
    expect(streetLabel("01ST|AV")).toBe("1st Av");
    expect(streetLabel("22ND|ST")).toBe("22nd St");
  });

  it("keeps compass points and house numbers", () => {
    expect(streetLabel("349 E|6TH|AV")).toBe("349 E 6th Av");
    expect(streetLabel("SE MARINE|DR")).toBe("SE Marine Dr");
  });
});

describe("recordSummary", () => {
  it("counts the rows and spans their years", () => {
    expect(recordSummary([{ year: 2016 }, { year: 1950 }, { year: 1912 }])).toBe("3 decisions, 1912–2016");
    expect(recordSummary([{ year: 1976 }])).toBe("1 decision, 1976");
    expect(recordSummary([{ year: 1976 }, { year: 1976 }])).toBe("2 decisions, 1976");
    expect(recordSummary([])).toBeNull();
  });
});
