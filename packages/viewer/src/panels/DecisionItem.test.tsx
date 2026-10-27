import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { VANCOUVER } from "../config";
import { type Decision, parseDecision } from "../data/records";
import { DecisionItem } from "./DecisionItem";

const leases = parseDecision(
  {
    y: 1979,
    d: "03-13",
    k: "N",
    p: 2,
    a: 0,
    u: "https://archive.org/details/CVAN_1979-03-13/page/n11",
    c: "x",
    t: "THAT clause 1 in this report be received for information and the recommendations of the City Manager be approved.",
    pl: "City land lease, 275 East 8th encroachment and Barclay Manor rent review approved",
    hp: "n",
  },
  "van",
);

const housing = parseDecision(
  {
    y: 2017,
    d: "10-17",
    k: "C",
    p: 3,
    a: 60000000,
    u: "https://opendata.vancouver.ca/explore/dataset/council-voting-records/table/?q=%221.%20REZONING%22",
    c: "x",
    t: "$60,000,000 for 145 social housing homes at 2221-2223 Main Street",
    hp: "u",
  },
  "van",
);

function renderItem(decision: Decision, city = VANCOUVER) {
  render(
    <ul>
      <DecisionItem decision={decision} kinds={city.record.kinds} currency={city.record.currency} />
    </ul>,
  );
  return screen.getByRole("listitem");
}

describe("DecisionItem", () => {
  it("shows the date, series and outcome", () => {
    const item = renderItem(leases);
    expect(within(item).getByText("13 Mar 1979")).toHaveAttribute("datetime", "1979-03-13");
    expect(within(item).getByText("Council minutes")).toBeInTheDocument();
    expect(within(item).getByText("Pending")).toBeInTheDocument();
  });

  it("leads with qipu's summary and keeps the printed words one click away", async () => {
    const user = userEvent.setup();
    const item = renderItem(leases);
    expect(within(item).getByText(/^City land lease/)).toBeVisible();
    expect(within(item).getByText("qipu's summary")).toBeInTheDocument();
    const printed = within(item).getByText(/^THAT clause 1/);
    expect(printed).not.toBeVisible();
    await user.click(within(item).getByText("As printed"));
    expect(printed).toBeVisible();
    expect(printed.tagName).toBe("BLOCKQUOTE");
  });

  it("shows the printed words alone when there is no summary", () => {
    const item = renderItem(housing);
    expect(within(item).getByText(/^\$60,000,000 for 145 social housing homes/)).toBeVisible();
    expect(within(item).queryByText("As printed")).not.toBeInTheDocument();
    expect(within(item).queryByText("qipu's summary")).not.toBeInTheDocument();
  });

  it("says where on the block the row sits and what it is worth", () => {
    const item = renderItem(housing);
    expect(within(item).getByText("at an address on this block · CA$60,000,000")).toBeInTheDocument();
    expect(within(item).queryByText(/Decided|Pending|Failed/)).not.toBeInTheDocument();
  });

  it("writes a building permit's address and amount", () => {
    const permit = parseDecision(
      {
        y: 2022,
        d: "06-13",
        k: "P",
        p: 3,
        a: 4000000,
        c: "x",
        u: "https://opendata.vancouver.ca/explore/dataset/issued-building-permits/table/?q=%22BP-2021-06799%22",
        t: "Demolition / Deconstruction — 3122 SE MARINE DRIVE",
        ad: "3122 SE|MARINE|DR",
      },
      "van",
    );
    const item = renderItem(permit);
    expect(within(item).getByText("Building permit")).toBeInTheDocument();
    expect(
      within(item).getByText("at an address on this block · 3122 SE Marine Dr · CA$4,000,000"),
    ).toBeInTheDocument();
  });

  it("falls back to the year and the row code", () => {
    const undated = parseDecision(
      { y: 1938, k: "Z", u: "https://archive.org/details/CVAN_1938", c: "x", t: "Street lights for Main Street" },
      "van",
    );
    const item = renderItem(undated);
    expect(within(item).getByText("1938")).toHaveAttribute("datetime", "1938");
    expect(within(item).getByText("Z")).toBeInTheDocument();
    expect(item.querySelector(".qv-decision__where")).toBeNull();
  });
});
