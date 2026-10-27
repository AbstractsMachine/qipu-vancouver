import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type ViewState } from "./url";
import { errorMessage, useLoad, usePlay, useUrlSync } from "./hooks";

/** Move fake time on, letting React apply what the timers did. */
function advance(ms: number): void {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("useLoad", () => {
  it("is loading until the load resolves, then ready with its value", async () => {
    const load = deferred<number>();
    const { result } = renderHook(() => useLoad("a", () => load.promise));
    expect(result.current).toEqual({ status: "loading" });
    await act(async () => {
      load.resolve(7);
      await load.promise;
    });
    expect(result.current).toEqual({ status: "ready", value: 7 });
  });

  it("reports a failed load with its message", async () => {
    const { result } = renderHook(() => useLoad("a", () => Promise.reject(new Error("HTTP 503"))));
    await vi.waitFor(() => {
      expect(result.current).toEqual({ status: "error", message: "HTTP 503" });
    });
  });

  it("keeps only the answer for the latest key", async () => {
    const slow = deferred<string>();
    const fast = deferred<string>();
    const loads: Record<string, Promise<string>> = { sf: slow.promise, vancouver: fast.promise };
    const { result, rerender } = renderHook(
      ({ key }) => useLoad(key, () => loads[key] ?? Promise.reject(new Error("no such city"))),
      {
        initialProps: { key: "sf" },
      },
    );
    rerender({ key: "vancouver" });
    await act(async () => {
      fast.resolve("Vancouver");
      await fast.promise;
    });
    await act(async () => {
      slow.resolve("San Francisco");
      await slow.promise;
    });
    expect(result.current).toEqual({ status: "ready", value: "Vancouver" });
  });

  it("goes back to loading as soon as the key changes", async () => {
    const { result, rerender } = renderHook(({ key }) => useLoad(key, () => Promise.resolve(key)), {
      initialProps: { key: "sf" },
    });
    await vi.waitFor(() => {
      expect(result.current).toEqual({ status: "ready", value: "sf" });
    });
    rerender({ key: "vancouver" });
    expect(result.current).toEqual({ status: "loading" });
    await vi.waitFor(() => {
      expect(result.current).toEqual({ status: "ready", value: "vancouver" });
    });
  });

  it("loads nothing for a null key", () => {
    const load = vi.fn(() => Promise.resolve(1));
    const { result } = renderHook(() => useLoad(null, load));
    expect(load).not.toHaveBeenCalled();
    expect(result.current).toEqual({ status: "loading" });
  });
});

describe("errorMessage", () => {
  it("reads an Error's message and stringifies anything else", () => {
    expect(errorMessage(new TypeError("Failed to fetch"))).toBe("Failed to fetch");
    expect(errorMessage("offline")).toBe("offline");
    expect(errorMessage(404)).toBe("404");
  });
});

describe("usePlay", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function play(initial: { playing: boolean; year: number }) {
    const setYear = vi.fn();
    const onEnd = vi.fn();
    const hook = renderHook(
      ({ playing, year }) => {
        usePlay(playing, year, 2026, setYear, onEnd);
      },
      { initialProps: initial },
    );
    return { setYear, onEnd, ...hook };
  }

  it("moves one year forward every eighth of a second", () => {
    const { setYear, onEnd } = play({ playing: true, year: 2000 });
    advance(124);
    expect(setYear).not.toHaveBeenCalled();
    advance(1);
    expect(setYear).toHaveBeenCalledExactlyOnceWith(2001);
    expect(onEnd).not.toHaveBeenCalled();
  });

  it("steps from the year it is given, not the year it started at", () => {
    const { setYear, rerender } = play({ playing: true, year: 2000 });
    rerender({ playing: true, year: 2010 });
    advance(125);
    expect(setYear).toHaveBeenLastCalledWith(2011);
  });

  it("stops at the present and says so", () => {
    const { setYear, onEnd } = play({ playing: true, year: 2025 });
    advance(125);
    expect(setYear).toHaveBeenLastCalledWith(2026);
    expect(onEnd).toHaveBeenCalledOnce();
  });

  it("does nothing while paused, and stops when paused", () => {
    const { setYear, rerender } = play({ playing: false, year: 2000 });
    advance(1000);
    expect(setYear).not.toHaveBeenCalled();

    rerender({ playing: true, year: 2000 });
    advance(125);
    expect(setYear).toHaveBeenCalledTimes(1);
    rerender({ playing: false, year: 2001 });
    advance(1000);
    expect(setYear).toHaveBeenCalledTimes(1);
  });

  it("plays at the speed it is asked for", () => {
    const setYear = vi.fn();
    renderHook(() => {
      usePlay(true, 2000, 2026, setYear, vi.fn(), 2);
    });
    advance(1000);
    expect(setYear).toHaveBeenCalledTimes(2);
  });
});

describe("useUrlSync", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.history.replaceState(null, "", "/map?lang=fr#credits");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  const sync = (state: ViewState, enabled = true) =>
    renderHook(
      ({ s, on }) => {
        useUrlSync(s, on);
      },
      { initialProps: { s: state, on: enabled } },
    );

  it("writes the view into the query after a short pause, keeping other parameters and the hash", () => {
    const historyLength = window.history.length;
    sync({ city: "vancouver", year: 1938, block: "3565" });
    advance(299);
    expect(window.location.search).toBe("?lang=fr");
    advance(1);
    expect(window.location.pathname).toBe("/map");
    expect(window.location.search).toBe("?lang=fr&city=vancouver&year=1938&block=3565");
    expect(window.location.hash).toBe("#credits");
    expect(window.history.length).toBe(historyLength);
  });

  it("writes once for a burst of changes", () => {
    const replace = vi.spyOn(window.history, "replaceState");
    const { rerender } = sync({ city: "vancouver", year: 1938 });
    for (const year of [1939, 1940, 1941]) {
      advance(100);
      rerender({ s: { city: "vancouver", year }, on: true });
    }
    advance(300);
    expect(replace).toHaveBeenCalledOnce();
    expect(window.location.search).toBe("?lang=fr&city=vancouver&year=1941");
  });

  it("leaves the history alone when the address already says the same", () => {
    window.history.replaceState(null, "", "/map?lang=fr&city=vancouver");
    const replace = vi.spyOn(window.history, "replaceState");
    sync({ city: "vancouver" });
    advance(1000);
    expect(replace).not.toHaveBeenCalled();
  });

  it("does nothing when turned off", () => {
    const replace = vi.spyOn(window.history, "replaceState");
    sync({ city: "vancouver", year: 1938 }, false);
    advance(1000);
    expect(replace).not.toHaveBeenCalled();
    expect(window.location.search).toBe("?lang=fr");
  });
});
