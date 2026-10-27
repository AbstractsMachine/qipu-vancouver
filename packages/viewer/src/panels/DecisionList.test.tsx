import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VANCOUVER } from "../config";
import { type Decision, parseDecision } from "../data/records";
import { DecisionList } from "./DecisionList";

function row(year: number, text = `Decision of ${year}`): Decision {
  return parseDecision({ y: year, k: "C", u: `https://archive.org/details/CVAN_${year}`, c: "x", t: text }, "test");
}

const { kinds, currency } = VANCOUVER.record;

function renderList(decisions: readonly Decision[], year: number) {
  return render(<DecisionList decisions={decisions} year={year} kinds={kinds} currency={currency} />);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DecisionList", () => {
  const decisions = [row(2016), row(2011), row(1979), row(1976), row(1912)];

  it("groups decisions by decade, newest first, with a count", () => {
    renderList(decisions, 1950);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["2010s 2 decisions", "1970s 2 decisions", "1910s 1 decision"]);
    const seventies = screen.getByRole("region", { name: /^1970s/ });
    expect(within(seventies).getAllByRole("listitem")).toHaveLength(2);
  });

  it("marks the decade holding the slider's year", () => {
    const { rerender } = renderList(decisions, 1976);
    const seventies = screen.getByRole("region", { name: /^1970s/ });
    expect(seventies).toHaveAttribute("aria-current", "true");
    expect(within(seventies).getByText("map year")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /^2010s/ })).not.toHaveAttribute("aria-current");

    rerender(<DecisionList decisions={decisions} year={2012} kinds={kinds} currency={currency} />);
    expect(screen.getByRole("region", { name: /^2010s/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("region", { name: /^1970s/ })).not.toHaveAttribute("aria-current");
  });

  it("opens on the summary and scrolls to the marked decade when the decade changes", () => {
    const scroll = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { value: scroll, configurable: true });
    try {
      const { rerender } = renderList(decisions, 1976);
      expect(scroll).not.toHaveBeenCalled();

      rerender(<DecisionList decisions={decisions} year={1979} kinds={kinds} currency={currency} />);
      expect(scroll).not.toHaveBeenCalled();

      rerender(<DecisionList decisions={decisions} year={2016} kinds={kinds} currency={currency} />);
      expect(scroll).toHaveBeenCalledTimes(1);
      expect(scroll.mock.contexts[0]).toBe(screen.getByRole("region", { name: /^2010s/ }));

      rerender(<DecisionList decisions={decisions} year={1975} kinds={kinds} currency={currency} />);
      expect(scroll).toHaveBeenCalledTimes(2);
      expect(scroll.mock.contexts[1]).toBe(screen.getByRole("region", { name: /^1970s/ }));
    } finally {
      Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
    }
  });

  it("shows the first 30 rows of a long decade until asked for all", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 45 }, (_, i) => row(1979 - (i % 10), `Row ${i + 1}`));
    renderList(many, 1975);
    const decade = screen.getByRole("region", { name: /^1970s/ });
    expect(within(decade).getAllByRole("listitem")).toHaveLength(30);

    await user.click(within(decade).getByRole("button", { name: "Show all 45 decisions" }));
    expect(within(decade).getAllByRole("listitem")).toHaveLength(45);
    expect(within(decade).queryByRole("button", { name: /Show all/ })).not.toBeInTheDocument();
    expect(within(decade).getAllByRole("listitem")[30]).toHaveFocus();
  });

  it("offers no button for a short decade", () => {
    renderList(decisions, 1976);
    expect(screen.queryByRole("button", { name: /Show all/ })).not.toBeInTheDocument();
  });
});
