import { useEffect, useEffectEvent, useState } from "react";
import { type ViewState, writeViewState } from "./url";

export type Loaded<T> =
  | { readonly status: "loading" }
  | { readonly status: "error"; readonly message: string }
  | { readonly status: "ready"; readonly value: T };

/**
 * Run an async load whenever `key` changes and keep only the latest answer,
 * so a slow response for a previous city or block can never overwrite the
 * current one.
 */
export function useLoad<T>(key: string | null, load: () => Promise<T>): Loaded<T> {
  const [state, setState] = useState<{ key: string | null; loaded: Loaded<T> }>({
    key: null,
    loaded: { status: "loading" },
  });
  const run = useEffectEvent(load);

  useEffect(() => {
    if (key === null) return;
    let live = true;
    run().then(
      (value) => {
        if (live) setState({ key, loaded: { status: "ready", value } });
      },
      (error: unknown) => {
        if (live) setState({ key, loaded: { status: "error", message: errorMessage(error) } });
      },
    );
    return () => {
      live = false;
    };
  }, [key]);

  return state.key === key ? state.loaded : { status: "loading" };
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Move the year forward while `playing`, about eight years a second, and stop
 * at the present. Calls `onEnd` when it gets there.
 */
export function usePlay(
  playing: boolean,
  year: number,
  present: number,
  setYear: (y: number) => void,
  onEnd: () => void,
  yearsPerSecond = 8,
): void {
  const step = useEffectEvent(() => {
    const next = year + 1;
    if (next >= present) {
      setYear(present);
      onEnd();
    } else setYear(next);
  });
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(step, 1000 / yearsPerSecond);
    return () => {
      window.clearInterval(timer);
    };
  }, [playing, yearsPerSecond]);
}

/** Keep the address bar's query in step with the view, without adding history entries. */
export function useUrlSync(state: ViewState, enabled: boolean, delayMs = 300): void {
  const serialised = writeViewState(state, enabled ? window.location.search : "");
  useEffect(() => {
    if (!enabled) return;
    const timer = window.setTimeout(() => {
      if (serialised === window.location.search) return;
      const url = `${window.location.pathname}${serialised}${window.location.hash}`;
      window.history.replaceState(window.history.state, "", url);
    }, delayMs);
    return () => {
      window.clearTimeout(timer);
    };
  }, [serialised, enabled, delayMs]);
}
