import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SAN_FRANCISCO, VANCOUVER } from "../config";
import { type Decision, parseDecision } from "../data/records";
import { DecisionItem } from "./DecisionItem";

const streetArtists = parseDecision(
  {
    y: 1976,
    d: "11-17",
    k: "R",
    p: 3,
    a: 0,
    u: "journalseptdecofproceed71sanfrich/292",
    t: "Hearings sought to drop two street-artist selling spots near Beach Street",
    pl: "Proposed: dropping two street-artist selling spots near Beach Street",
    hp: "n",
  },
  "sf",
);

const bonds = parseDecision(
  {
    y: 2025,
    d: "10-07",
    k: "R",
    p: 3,
    a: 60000000,
    u: "bag100725/22",
    c: "b",
    t: "$60,000,000 in bonds sought for 136 flats at 2970 16th Street",
    hp: "u",
  },
  "sf",
);

function renderItem(decision: Decision, city = SAN_FRANCISCO) {
  render(
    <ul>
      <DecisionItem decision={decision} kinds={city.record.kinds} currency={city.record.currency} />
    </ul>,
  );
  return screen.getByRole("listitem");
}

describe("DecisionItem", () => {
  it("shows the date, series and outcome", () => {
    const item = renderItem(streetArtists);
    expect(within(item).getByText("17 Nov 1976")).toHaveAttribute("datetime", "1976-11-17");
    expect(within(item).getByText("Resolution")).toBeInTheDocument();
    expect(within(item).getByText("Pending")).toBeInTheDocument();
  });

  it("leads with qipu's summary and keeps the printed words one click away", async () => {
    const user = userEvent.setup();
    const item = renderItem(streetArtists);
    expect(within(item).getByText(/^Proposed: dropping/)).toBeVisible();
    expect(within(item).getByText("qipu's summary")).toBeInTheDocument();
    const printed = within(item).getByText(/^Hearings sought/);
    expect(printed).not.toBeVisible();
    await user.click(within(item).getByText("As printed"));
    expect(printed).toBeVisible();
    expect(printed.tagName).toBe("BLOCKQUOTE");
  });

  it("shows the printed words alone when there is no summary", () => {
    const item = renderItem(bonds);
    expect(within(item).getByText(/^\$60,000,000 in bonds/)).toBeVisible();
    expect(within(item).queryByText("As printed")).not.toBeInTheDocument();
    expect(within(item).queryByText("qipu's summary")).not.toBeInTheDocument();
  });

  it("says where on the block the row sits and what it is worth", () => {
    const item = renderItem(bonds);
    expect(within(item).getByText("at an address on this block · $60,000,000")).toBeInTheDocument();
    expect(within(item).queryByText(/Decided|Pending|Failed/)).not.toBeInTheDocument();
  });

  it("formats Vancouver amounts in Canadian dollars and writes the address", () => {
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
    const item = renderItem(permit, VANCOUVER);
    expect(within(item).getByText("Building permit")).toBeInTheDocument();
    expect(
      within(item).getByText("at an address on this block · 3122 SE Marine Dr · CA$4,000,000"),
    ).toBeInTheDocument();
  });

  it("falls back to the year and the row code", () => {
    const undated = parseDecision({ y: 1938, k: "Z", u: "journal1938/4", t: "Street lights for Pine Street" }, "sf");
    const item = renderItem(undated);
    expect(within(item).getByText("1938")).toHaveAttribute("datetime", "1938");
    expect(within(item).getByText("Z")).toBeInTheDocument();
    expect(item.querySelector(".qv-decision__where")).toBeNull();
  });
});
