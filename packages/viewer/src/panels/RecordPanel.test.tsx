import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { VANCOUVER } from "../config";
import { type BlockRecord, type Decision, type Place, parseDecision } from "../data/records";
import { type RecordLoad, RecordPanel, type RecordPanelProps } from "./RecordPanel";

function row(year: number): Decision {
  return parseDecision(
    { y: year, d: "03-01", k: "C", u: `https://archive.org/details/CVAN_${year}`, c: "x", t: `Vote of ${year}` },
    "test",
  );
}

const record: BlockRecord = {
  blockId: "3565",
  decisions: [row(2016), row(1976), row(1912)],
  streets: ["KEEFER|ST", "HAWKS|AV"],
};

const library: Place = {
  slug: "strathcona-branch-library",
  name: "Strathcona Branch Library",
  kind: "library",
  agreed: 12_500_000,
  paid: null,
  contracts: 2,
};

function ready(r: BlockRecord, places: readonly Place[] = []): RecordLoad {
  return { status: "ready", record: r, places, placeHref: (slug) => `/places/${slug}` };
}

function renderPanel(overrides: Partial<RecordPanelProps> = {}) {
  const props: RecordPanelProps = {
    city: VANCOUVER,
    block: { id: "3565", neighbourhood: "Strathcona" },
    load: ready(record),
    year: 1976,
    shareUrl: "https://www.qipu.org/en/canada/vancouver/the-city?block=3565",
    onClose: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<RecordPanel {...props} />) };
}

describe("RecordPanel", () => {
  it("is a landmark named by the neighbourhood and block", () => {
    renderPanel();
    expect(screen.getByRole("complementary", { name: "Strathcona Block 3565" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Strathcona Block 3565");
  });

  it("names the block alone when it has no neighbourhood", () => {
    renderPanel({ block: { id: "77", neighbourhood: null } });
    expect(screen.getByRole("complementary", { name: "Block 77" })).toBeInTheDocument();
  });

  it("announces loading politely", () => {
    renderPanel({ load: { status: "loading" } });
    expect(screen.getByText("Loading this block's record…")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("explains a failed load", () => {
    renderPanel({ load: { status: "error", message: "HTTP 503 for block-07.json" } });
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("This block's record could not be loaded.");
    expect(alert).toHaveTextContent("HTTP 503 for block-07.json");
  });

  it("says when a block has no decisions yet", () => {
    renderPanel({ load: ready({ blockId: "3565", decisions: [], streets: [] }) });
    expect(screen.getByText("No decisions are placed on this block yet.")).toBeInTheDocument();
    expect(screen.getByText(VANCOUVER.record.scope)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
  });

  it("summarises the record and lists it by decade", () => {
    renderPanel();
    expect(screen.getByText("3 decisions, 1912–2016")).toBeInTheDocument();
    expect(screen.getByText("On Keefer St · Hawks Av")).toBeInTheDocument();
    expect(screen.getByText(VANCOUVER.record.scope)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /^1970s/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.queryByRole("heading", { name: "Places on this block" })).not.toBeInTheDocument();
  });

  it("lists the places on the block when there are any", () => {
    renderPanel({ load: ready(record, [library]) });
    expect(screen.getByRole("heading", { name: "Places on this block" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Strathcona Branch Library" })).toHaveAttribute(
      "href",
      "/places/strathcona-branch-library",
    );
    expect(screen.getByText("CA$12,500,000 agreed · 2 contracts")).toBeInTheDocument();
  });

  it("offers a share button", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: "Share" })).toBeInTheDocument();
  });

  it("moves focus to the close button when it opens and when the block changes", () => {
    const { props, rerender } = renderPanel();
    const close = screen.getByRole("button", { name: "Close" });
    expect(close).toHaveFocus();

    close.blur();
    rerender(<RecordPanel {...props} block={{ id: "3566", neighbourhood: "Strathcona" }} />);
    expect(close).toHaveFocus();
  });

  it("closes from the close button", async () => {
    const user = userEvent.setup();
    const { props } = renderPanel();
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape from inside the panel", async () => {
    const user = userEvent.setup();
    const { props } = renderPanel();
    await user.keyboard("{Escape}");
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores Escape pressed elsewhere on the page", async () => {
    const user = userEvent.setup();
    const { props } = renderPanel();
    screen.getByRole("button", { name: "Close" }).blur();
    await user.keyboard("{Escape}");
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it("gives focus back to what opened it", () => {
    const opener = document.createElement("button");
    opener.textContent = "Block 3565 on the map";
    document.body.append(opener);
    opener.focus();
    const { unmount } = renderPanel();
    expect(opener).not.toHaveFocus();
    unmount();
    expect(opener).toHaveFocus();
    opener.remove();
  });
});
