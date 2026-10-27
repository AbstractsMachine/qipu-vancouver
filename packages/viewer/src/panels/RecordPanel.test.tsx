import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SAN_FRANCISCO } from "../config";
import { type BlockRecord, type Decision, type Place, parseDecision } from "../data/records";
import { type RecordLoad, RecordPanel, type RecordPanelProps } from "./RecordPanel";

function row(year: number): Decision {
  return parseDecision({ y: year, d: "03-01", k: "O", u: `journal${year}/9`, t: `Ordinance of ${year}` }, "test");
}

const record: BlockRecord = {
  blockId: "3547-012",
  decisions: [row(2016), row(1976), row(1912)],
  streets: ["VALENCIA|ST", "16TH|ST"],
};

const library: Place = {
  slug: "mission-branch-library",
  name: "Mission Branch Library",
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
    city: SAN_FRANCISCO,
    block: { id: "3547-012", neighbourhood: "Mission" },
    load: ready(record),
    year: 1976,
    shareUrl: "https://www.qipu.org/en/usa/san-francisco/the-city?block=3547-012",
    onClose: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<RecordPanel {...props} />) };
}

describe("RecordPanel", () => {
  it("is a landmark named by the neighbourhood and block", () => {
    renderPanel();
    expect(screen.getByRole("complementary", { name: "Mission Block 3547-012" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Mission Block 3547-012");
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
    renderPanel({ load: ready({ blockId: "3547-012", decisions: [], streets: [] }) });
    expect(screen.getByText("No decisions are placed on this block yet.")).toBeInTheDocument();
    expect(screen.getByText(SAN_FRANCISCO.record.scope)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 3 })).not.toBeInTheDocument();
  });

  it("summarises the record and lists it by decade", () => {
    renderPanel();
    expect(screen.getByText("3 decisions, 1912–2016")).toBeInTheDocument();
    expect(screen.getByText("On Valencia St · 16th St")).toBeInTheDocument();
    expect(screen.getByText(SAN_FRANCISCO.record.scope)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /^1970s/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.queryByRole("heading", { name: "Places on this block" })).not.toBeInTheDocument();
  });

  it("lists the places on the block when there are any", () => {
    renderPanel({ load: ready(record, [library]) });
    expect(screen.getByRole("heading", { name: "Places on this block" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mission Branch Library" })).toHaveAttribute(
      "href",
      "/places/mission-branch-library",
    );
    expect(screen.getByText("$12,500,000 agreed · 2 contracts")).toBeInTheDocument();
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
    rerender(<RecordPanel {...props} block={{ id: "3547-013", neighbourhood: "Mission" }} />);
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
    opener.textContent = "Block 3547-012 on the map";
    document.body.append(opener);
    opener.focus();
    const { unmount } = renderPanel();
    expect(opener).not.toHaveFocus();
    unmount();
    expect(opener).toHaveFocus();
    opener.remove();
  });
});
