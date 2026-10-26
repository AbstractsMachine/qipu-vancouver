import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SAN_FRANCISCO, VANCOUVER } from "../config";
import type { CityMap, CityMapOptions } from "../map/city-map";
import type { Painting } from "../tiles/painting";
import { type CityMapHookOptions, useCityMap } from "./use-city-map";

const made = vi.hoisted(() => [] as { options: CityMapOptions; destroy: () => void }[]);

vi.mock("../map/city-map", () => ({
  createCityMap: (options: CityMapOptions) => {
    const map = { options, destroy: vi.fn() };
    made.push(map);
    return map as unknown as CityMap;
  },
}));

/* the hook only hands the painting on to the map, so its contents do not matter here */
const painting = { eras: null } as unknown as Painting;

function options(overrides: Partial<CityMapHookOptions> = {}): CityMapHookOptions {
  return {
    container: { current: document.createElement("div") },
    city: SAN_FRANCISCO,
    painting,
    initialYear: 1938,
    initialView: { x: 10, y: 20, zoom: 3 },
    compositor: "cpu",
    onPick: vi.fn(),
    onViewChange: vi.fn(),
    ...overrides,
  };
}

describe("useCityMap", () => {
  beforeEach(() => {
    made.length = 0;
  });

  it("waits for the painting before making a map", () => {
    const { result, rerender } = renderHook((o: CityMapHookOptions) => useCityMap(o), {
      initialProps: options({ painting: null }),
    });
    expect(result.current).toBeNull();
    expect(made).toHaveLength(0);

    rerender(options());
    expect(made).toHaveLength(1);
    expect(result.current).toBe(made[0]);
  });

  it("makes no map without a container element", () => {
    const { result } = renderHook(() => useCityMap(options({ container: { current: null } })));
    expect(result.current).toBeNull();
    expect(made).toHaveLength(0);
  });

  it("opens the map on the initial year and view in the given element", () => {
    const o = options();
    renderHook(() => useCityMap(o));
    expect(made[0]?.options).toMatchObject({
      element: o.container.current,
      city: SAN_FRANCISCO,
      year: 1938,
      view: { x: 10, y: 20, zoom: 3 },
      compositor: "cpu",
    });
  });

  it("keeps the same map when only the year, view or callbacks change", () => {
    const first = options();
    const { rerender } = renderHook((o: CityMapHookOptions) => useCityMap(o), { initialProps: first });
    rerender({ ...first, initialYear: 1959, initialView: { x: 0, y: 0, zoom: 1 }, onPick: vi.fn() });
    expect(made).toHaveLength(1);
  });

  it("passes picks and view changes to the latest callbacks", () => {
    const firstOnPick = vi.fn();
    const first = options({ onPick: firstOnPick });
    const { rerender } = renderHook((o: CityMapHookOptions) => useCityMap(o), { initialProps: first });
    const onPick = vi.fn();
    const onViewChange = vi.fn();
    rerender({ ...first, onPick, onViewChange });

    made[0]?.options.onPick(4);
    made[0]?.options.onViewChange?.({ x: 1, y: 2, zoom: 3 });
    expect(onPick).toHaveBeenCalledWith(4);
    expect(onViewChange).toHaveBeenCalledWith({ x: 1, y: 2, zoom: 3 });
    expect(firstOnPick).not.toHaveBeenCalled();
  });

  it("replaces the map when the city changes", () => {
    const first = options();
    const { result, rerender } = renderHook((o: CityMapHookOptions) => useCityMap(o), { initialProps: first });
    rerender({ ...first, city: VANCOUVER });
    expect(made).toHaveLength(2);
    expect(made[0]?.destroy).toHaveBeenCalledOnce();
    expect(made[1]?.destroy).not.toHaveBeenCalled();
    expect(result.current).toBe(made[1]);
  });

  it("destroys the map on unmount", () => {
    const o = options();
    const { unmount } = renderHook(() => useCityMap(o));
    unmount();
    expect(made[0]?.destroy).toHaveBeenCalledOnce();
  });
});
