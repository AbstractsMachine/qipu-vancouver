import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, type Mock, vi } from "vitest";
import { VANCOUVER, withDataBase } from "./config";
import type { CityMapOptions, MapView } from "./map/city-map";
import { fakeFetch, twoBlocks } from "./test/builders";
import vancouverEras from "./test/fixtures/vancouver-eras.json";
import vancouverIndex from "./test/fixtures/vancouver-index.json";
import { Viewer, type ViewerProps } from "./Viewer";

/* The map itself is Leaflet and WebGL; here it is a recorder the test can also click through. */
interface FakeMap {
  readonly options: CityMapOptions;
  readonly setYear: Mock<(year: number) => void>;
  readonly setBlocks: Mock;
  readonly select: Mock<(position: number | null, fly?: boolean) => void>;
  readonly destroy: Mock;
}

const maps = vi.hoisted(() => [] as FakeMap[]);

vi.mock("./map/city-map", () => ({
  createCityMap: (options: CityMapOptions) => {
    const map = {
      options,
      setYear: vi.fn(),
      setBlocks: vi.fn(),
      select: vi.fn(),
      destroy: vi.fn(),
      compositorKind: () => "cpu",
      pendingEraTiles: () => 0,
    };
    maps.push(map);
    return map;
  },
}));

const TILES = VANCOUVER.tiles.base;
const DATA = "https://data.test/vancouver";
const city = withDataBase(VANCOUVER, DATA);

const paintingRoutes = {
  [`${TILES}/render/index.json`]: vancouverIndex,
  [`${TILES}/_preview_eras/render-years.json`]: vancouverEras,
};

function dataRoutes(): Record<string, unknown> {
  return {
    [`${DATA}/manifest.json`]: { chunks: [{ kind: "blocks", hoodNames: ["Strathcona"] }] },
    [`${DATA}/base/blocks.qc`]: twoBlocks(),
    [`${DATA}/base/blocks-id.json`]: { id: ["A", "B"] },
    [`${DATA}/blocks/block-index.json`]: {
      meta: { shards: 2 },
      b: ["A", "B"],
      n: [2, 0],
      y0: [1938, 0],
      y1: [1951, 0],
    },
    [`${DATA}/blocks/block-00.json`]: {
      A: {
        d: [
          {
            y: 1938,
            d: "06-13",
            k: "N",
            u: "https://archive.org/details/CVAN_1938-06-13/page/n4",
            c: "x",
            t: "Sewer in Keefer Street",
          },
          {
            y: 1951,
            d: "05-02",
            k: "N",
            u: "https://archive.org/details/CVAN_1951-05-02/page/n12",
            c: "x",
            t: "Paving of Hawks Avenue",
          },
        ],
        s: ["KEEFER|ST"],
      },
    },
    [`${DATA}/blocks/block-money.json`]: {
      href: "/places/{slug}",
      b: { A: [{ slug: "strathcona-library", name: "Strathcona Branch Library" }] },
    },
  };
}

function serve(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(fakeFetch(routes)));
}

function renderViewer(props: Partial<ViewerProps> = {}) {
  return render(<Viewer city={city} compositor="cpu" {...props} />);
}

function theMap(): FakeMap {
  const map = maps.at(-1);
  if (!map) throw new Error("no map was made");
  return map;
}

/** The map exists and has its blocks, so clicks can pick. */
async function mapWithBlocks(): Promise<FakeMap> {
  await waitFor(() => {
    expect(theMap().setBlocks).toHaveBeenCalled();
  });
  return theMap();
}

function pick(position: number | null) {
  act(() => {
    theMap().options.onPick(position);
  });
}

function moveView(view: MapView) {
  act(() => {
    theMap().options.onViewChange?.(view);
  });
}

const yearSlider = () => screen.findByRole("slider", { name: "Year" });
const playButton = () => screen.getByRole("button", { name: "Play through the years" });

describe("Viewer", () => {
  beforeEach(() => {
    maps.length = 0;
    window.history.replaceState(null, "", "/");
    serve({ ...paintingRoutes, ...dataRoutes() });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe("the year", () => {
    it("offers the eras' range and opens at the present", async () => {
      renderViewer();
      const slider = await yearSlider();
      expect(slider).toHaveAttribute("min", "1930");
      expect(slider).toHaveAttribute("max", "2026");
      expect(slider).toHaveValue("2026");
      await waitFor(() => {
        expect(theMap().setYear).toHaveBeenLastCalledWith(2026);
      });
    });

    it("opens at the year in the link", async () => {
      renderViewer({ initial: { year: 1938 } });
      expect(await yearSlider()).toHaveValue("1938");
      await waitFor(() => {
        expect(theMap().setYear).toHaveBeenLastCalledWith(1938);
      });
    });

    it("keeps a linked year inside the range the map can show", async () => {
      renderViewer({ initial: { year: 1700 } });
      expect(await yearSlider()).toHaveValue("1930");
    });

    it("moves the map to the year the reader picks", async () => {
      renderViewer();
      fireEvent.change(await yearSlider(), { target: { value: "1938" } });
      expect(theMap().setYear).toHaveBeenLastCalledWith(1938);
      expect(screen.getByRole("slider", { name: "Year" })).toHaveValue("1938");
    });
  });

  describe("playing", () => {
    /*
     * Play steps on a real 125 ms interval. Left real, a slow run (coverage, a busy CI machine) can tick between a click
     * and the next assertion, or take longer than waitFor's second to reach the present. Only the interval is faked, so
     * fetches, waitFor and userEvent keep their own timers, and each test moves the clock itself.
     * waitFor polls with setInterval, so these tests do not use it.
     */
    beforeEach(() => {
      vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    const tick = () => {
      act(() => {
        vi.advanceTimersByTime(125);
      });
    };

    it("advances year by year and stops at the present", async () => {
      const user = userEvent.setup();
      renderViewer({ initial: { year: 2024 } });
      await yearSlider();
      await user.click(playButton());
      expect(playButton()).toHaveAttribute("aria-pressed", "true");

      tick();
      expect(screen.getByRole("slider", { name: "Year" })).toHaveValue("2025");
      expect(playButton()).toHaveAttribute("aria-pressed", "true");
      tick();
      expect(playButton()).toHaveAttribute("aria-pressed", "false");
      expect(screen.getByRole("slider", { name: "Year" })).toHaveValue("2026");
      tick();
      expect(screen.getByRole("slider", { name: "Year" })).toHaveValue("2026");
      expect(theMap().setYear.mock.calls.map(([y]) => y)).toEqual([2024, 2025, 2026]);
    });

    it("starts over from the first year when played at the present, and pauses on a second press", async () => {
      const user = userEvent.setup();
      renderViewer();
      await yearSlider();
      await user.click(playButton());
      expect(screen.getByRole("slider", { name: "Year" })).toHaveValue("1930");
      await user.click(playButton());
      expect(playButton()).toHaveAttribute("aria-pressed", "false");
    });

    it("stops when the reader moves the slider", async () => {
      const user = userEvent.setup();
      renderViewer({ initial: { year: 1900 } });
      await yearSlider();
      await user.click(playButton());
      fireEvent.change(screen.getByRole("slider", { name: "Year" }), { target: { value: "1950" } });
      expect(playButton()).toHaveAttribute("aria-pressed", "false");
      expect(screen.getByRole("slider", { name: "Year" })).toHaveValue("1950");
    });
  });

  describe("a block's record", () => {
    it("opens on a click, named by neighbourhood and block, with its decisions and places", async () => {
      renderViewer({ initial: { year: 1938 } });
      const map = await mapWithBlocks();
      pick(0);

      expect(await screen.findByRole("complementary", { name: "Strathcona Block A" })).toBeInTheDocument();
      expect(await screen.findByText("Paving of Hawks Avenue")).toBeInTheDocument();
      expect(screen.getByText("Sewer in Keefer Street")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Strathcona Branch Library" })).toHaveAttribute(
        "href",
        "https://www.qipu.org/en/places/strathcona-library",
      );
      expect(map.select).toHaveBeenLastCalledWith(0, false);
    });

    it("closes and clears the outline", async () => {
      const user = userEvent.setup();
      renderViewer();
      const map = await mapWithBlocks();
      pick(0);
      await user.click(await screen.findByRole("button", { name: "Close" }));
      expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
      expect(map.select).toHaveBeenLastCalledWith(null, false);
    });

    it("closes when the reader clicks off every block", async () => {
      renderViewer();
      const map = await mapWithBlocks();
      pick(0);
      await screen.findByRole("complementary");
      pick(null);
      expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
      expect(map.select).toHaveBeenLastCalledWith(null, false);
    });

    it("says so when the block's record cannot be loaded", async () => {
      const routes = Object.entries(dataRoutes()).filter(([url]) => !url.endsWith("/block-00.json"));
      serve({ ...paintingRoutes, ...Object.fromEntries(routes) });
      renderViewer();
      await mapWithBlocks();
      pick(0);
      expect(await screen.findByText("This block's record could not be loaded. Try again in a moment.")).toBeVisible();
    });
  });

  describe("a block named in the link", () => {
    it("opens once the blocks arrive, and the map flies to it", async () => {
      renderViewer({ initial: { block: "B" } });
      expect(await screen.findByRole("complementary", { name: "Block B" })).toBeInTheDocument();
      await waitFor(() => {
        expect(theMap().select).toHaveBeenLastCalledWith(1, true);
      });
    });

    it("opens without moving the map when the link also sets the view", async () => {
      renderViewer({ initial: { block: "B", at: { x: 100, y: 80, zoom: 5 } } });
      await screen.findByRole("complementary", { name: "Block B" });
      await waitFor(() => {
        expect(theMap().select).toHaveBeenLastCalledWith(1, false);
      });
      expect(theMap().select).not.toHaveBeenCalledWith(1, true);
    });

    it("is ignored when the city has no such block", async () => {
      renderViewer({ initial: { block: "Z" } });
      const map = await mapWithBlocks();
      expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
      expect(map.select).not.toHaveBeenCalledWith(expect.any(Number), expect.anything());
    });

    it("gives way to the reader's own pick", async () => {
      renderViewer({ initial: { block: "B" } });
      await screen.findByRole("complementary", { name: "Block B" });
      pick(0);
      expect(await screen.findByRole("complementary", { name: "Strathcona Block A" })).toBeInTheDocument();
    });
  });

  describe("the address bar", () => {
    it("is left alone unless asked", async () => {
      renderViewer({ initial: { year: 1938 } });
      await mapWithBlocks();
      pick(0);
      await new Promise((resolve) => setTimeout(resolve, 400));
      expect(window.location.search).toBe("");
    });

    it("follows the year, the view and the open block", async () => {
      renderViewer({ syncUrl: true });
      await mapWithBlocks();
      await waitFor(() => {
        expect(window.location.search).toBe("?city=vancouver");
      });

      fireEvent.change(await yearSlider(), { target: { value: "1938" } });
      moveView({ x: 812.4, y: 1290, zoom: 6.5 });
      pick(0);
      await waitFor(() => {
        expect(window.location.search).toBe("?city=vancouver&year=1938&at=812.4,1290,6.5&block=A");
      });
    });
  });

  describe("failures", () => {
    it("says when the painted map could not load", async () => {
      serve(dataRoutes());
      renderViewer();
      expect(await screen.findByRole("alert")).toHaveTextContent(
        `The map could not load: ${TILES}/render/index.json: HTTP 404`,
      );
      expect(screen.queryByRole("slider")).not.toBeInTheDocument();
      expect(maps).toHaveLength(0);
    });

    it("keeps the map and the slider when the block records are unavailable", async () => {
      serve(paintingRoutes);
      renderViewer();
      expect(await screen.findByText(/^Block records are unavailable: .*manifest\.json: HTTP 404$/)).toBeVisible();
      expect(await yearSlider()).toBeInTheDocument();
      expect(theMap().setBlocks).not.toHaveBeenCalled();
    });
  });

  it("shows the notice it is given", async () => {
    renderViewer({ notice: "Demo records: Strathcona only." });
    expect(screen.getByText("Demo records: Strathcona only.")).toBeVisible();
    await yearSlider();
  });

  it("removes the map when it unmounts", async () => {
    const { unmount } = renderViewer();
    await yearSlider();
    unmount();
    expect(theMap().destroy).toHaveBeenCalledOnce();
  });
});
