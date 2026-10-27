import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { YearSlider } from "./YearSlider";

/* jsdom has no ResizeObserver; this one reports whatever width the test sets */
class FakeResizeObserver {
  static readonly live = new Set<FakeResizeObserver>();
  static width = 600;
  private readonly callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(): void {
    FakeResizeObserver.live.add(this);
    this.report();
  }

  disconnect(): void {
    FakeResizeObserver.live.delete(this);
  }

  report(): void {
    const entry = { contentRect: { width: FakeResizeObserver.width } } as ResizeObserverEntry;
    this.callback([entry], this as unknown as ResizeObserver);
  }

  static resize(width: number): void {
    FakeResizeObserver.width = width;
    for (const o of FakeResizeObserver.live) o.report();
  }
}

const keyYears = [1906, 1915, 1925, 1938, 1946, 1959, 1970, 1985, 1995, 2006, 2026];

function ticks(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("datalist option"), (o) => o.getAttribute("value") ?? "");
}

describe("YearSlider tick marks", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    FakeResizeObserver.width = 600;
  });

  const slider = () => <YearSlider first={1906} present={2026} value={1938} keyYears={keyYears} onChange={vi.fn()} />;

  it("shows every key year on a wide slider", () => {
    FakeResizeObserver.width = 1200;
    const { container } = render(slider());
    expect(ticks(container)).toEqual(keyYears.map(String));
  });

  it("thins the key years on a narrow slider, keeping the first and the present", () => {
    FakeResizeObserver.width = 300;
    const { container } = render(slider());
    expect(ticks(container)).toEqual(["1906", "1925", "1946", "1970", "1995", "2026"]);
  });

  it("follows the slider as it is resized", () => {
    FakeResizeObserver.width = 1200;
    const { container } = render(slider());
    act(() => {
      FakeResizeObserver.resize(300);
    });
    expect(ticks(container)).toHaveLength(6);
  });

  it("stops watching the width once unmounted", () => {
    const { unmount } = render(slider());
    expect(FakeResizeObserver.live.size).toBe(1);
    unmount();
    expect(FakeResizeObserver.live.size).toBe(0);
  });
});
