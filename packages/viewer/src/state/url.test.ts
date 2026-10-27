import { describe, expect, it } from "vitest";
import { readViewState, writeViewState } from "./url";

describe("view state in the URL", () => {
  it("round-trips every field", () => {
    const state = { city: "sf", year: 1938, at: { x: 812.44, y: 1290, zoom: 6.5 }, block: "0572" };
    const search = writeViewState(state);
    expect(search).toBe("?city=sf&year=1938&at=812.4,1290,6.5&block=0572");
    expect(readViewState(search)).toEqual({ ...state, at: { x: 812.4, y: 1290, zoom: 6.5 } });
  });

  it("drops malformed fields and keeps the rest", () => {
    expect(readViewState("?city=SF!&year=19x8&at=1,2&block=a b&zoom=3")).toEqual({});
    expect(readViewState("?year=1938&at=1,2,99")).toEqual({ year: 1938 });
    expect(readViewState("?year=938")).toEqual({});
  });

  it("keeps query parameters it does not own", () => {
    expect(writeViewState({ year: 1906 }, "?utm_source=talk&year=2000")).toBe("?utm_source=talk&year=1906");
    expect(writeViewState({})).toBe("");
  });
});
