/**
 * The viewer's shareable state, read from and written to the URL's query:
 *
 *   ?city=sf&year=1938&at=812.4,1290.0,6.5&block=0572
 *
 * `at` is the view centre in frame units and the zoom. Every field is
 * optional and a malformed one is dropped rather than failing the page, so
 * a hand-edited or truncated link still opens something sensible.
 */
export interface ViewState {
  readonly city?: string;
  readonly year?: number;
  readonly at?: { readonly x: number; readonly y: number; readonly zoom: number };
  readonly block?: string;
}

const CITY = /^[a-z][a-z0-9-]{0,31}$/;
const BLOCK = /^[A-Za-z0-9_.-]{1,24}$/;

export function readViewState(search: string): ViewState {
  const q = new URLSearchParams(search);
  const state: { -readonly [K in keyof ViewState]: ViewState[K] } = {};
  const city = q.get("city");
  if (city && CITY.test(city)) state.city = city;
  const year = Number(q.get("year"));
  if (q.has("year") && Number.isInteger(year) && year >= 1000 && year <= 9999) state.year = year;
  const at = (q.get("at") ?? "").split(",").map(Number);
  if (at.length === 3 && at.every(Number.isFinite)) {
    const [x, y, zoom] = at as [number, number, number];
    if (zoom >= -4 && zoom <= 24) state.at = { x, y, zoom };
  }
  const block = q.get("block");
  if (block && BLOCK.test(block)) state.block = block;
  return state;
}

/** The query string for a state, keeping parameters the viewer does not own. */
export function writeViewState(state: ViewState, existing = ""): string {
  const q = new URLSearchParams(existing);
  for (const key of ["city", "year", "at", "block"]) q.delete(key);
  if (state.city) q.set("city", state.city);
  if (state.year !== undefined) q.set("year", String(state.year));
  if (state.at) q.set("at", [round(state.at.x, 1), round(state.at.y, 1), round(state.at.zoom, 2)].join(","));
  if (state.block) q.set("block", state.block);
  const s = q.toString().replace(/%2C/g, ",");
  return s ? `?${s}` : "";
}

const round = (v: number, digits: number): string => String(Number(v.toFixed(digits)));
