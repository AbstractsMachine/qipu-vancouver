import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { sourceOf } from "../data/sources";
import { sourceLabel } from "./format";
import { SourceLink } from "./SourceLink";

describe("sourceLabel", () => {
  it("names each record system", () => {
    expect(sourceLabel(sourceOf({ u: "journalseptdecofproceed71sanfrich/292", c: undefined, approx: false }))).toBe(
      "Scan, page n292 · Internet Archive",
    );
    expect(sourceLabel(sourceOf({ u: "journalseptdecofproceed71sanfrich", c: undefined, approx: false }))).toBe(
      "Scan · Internet Archive",
    );
    expect(sourceLabel(sourceOf({ u: "bag100725/22", c: "b", approx: false }))).toBe("Clerk's minutes PDF, page 22");
    expect(sourceLabel(sourceOf({ u: "bag100725", c: "b", approx: false }))).toBe("Clerk's minutes PDF");
    expect(sourceLabel(sourceOf({ u: "1234~abcd/3", c: "l", approx: false }))).toBe("Legistar minutes, page 3");
    expect(sourceLabel(sourceOf({ u: "1234~abcd", c: "l", approx: false }))).toBe("Legistar minutes");
  });

  it("uses the host for a row's own URL, and treats archive.org as a scan", () => {
    const permit = "https://opendata.vancouver.ca/explore/dataset/issued-building-permits/table/?q=%22BP-2021-06799%22";
    expect(sourceLabel(sourceOf({ u: permit, c: "x", approx: false }))).toBe("opendata.vancouver.ca");
    expect(sourceLabel(sourceOf({ u: "https://archive.org/details/19740730/page/n6", c: "x", approx: false }))).toBe(
      "Scan, page n6 · Internet Archive",
    );
  });
});

describe("SourceLink", () => {
  it("opens the original in a new tab and says so", () => {
    render(<SourceLink source={sourceOf({ u: "bag100725/22", c: "b", approx: false })} />);
    const link = screen.getByRole("link", { name: "Clerk's minutes PDF, page 22 (opens in a new tab)" });
    expect(link).toHaveAttribute("href", "https://sfbos.org/sites/default/files/bag100725_minutes.pdf#page=22");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("warns when the page may be a little off", () => {
    render(<SourceLink source={sourceOf({ u: "journal71/292", c: undefined, approx: true })} />);
    expect(
      screen.getByRole("link", {
        name: "Scan, page n292 · Internet Archive (page may be off by one or two) (opens in a new tab)",
      }),
    ).toBeInTheDocument();
  });

  it("says nothing about the page when there is none", () => {
    render(<SourceLink source={sourceOf({ u: "journal71", c: undefined, approx: true })} />);
    expect(screen.getByRole("link", { name: "Scan · Internet Archive (opens in a new tab)" })).toBeInTheDocument();
  });
});
