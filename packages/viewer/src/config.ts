/**
 * Everything the viewer needs to know about a city, and where to fetch it.
 * Nothing in `src/` names a city; the two qipu.org serves are defined here as
 * data, with the public endpoints they are read from.
 */
export interface CityConfig {
  readonly id: string;
  readonly name: string;
  readonly tiles: {
    /** release folder holding the pyramids, e.g. https://tiles.qipu.org/us/sf/city/r20261001 */
    readonly base: string;
    /** key of the present-day pyramid under `base` */
    readonly present: string;
    /** eras manifest under `base`; omit for a map with no year slider */
    readonly eras?: string;
  };
  /** city data folder: manifest.json, base/blocks.qc, base/blocks-id.json, blocks/ */
  readonly data: { readonly base: string };
  readonly record: {
    /** record series by row code, as a reader should see them */
    readonly kinds: Readonly<Record<string, string>>;
    readonly currency: "USD" | "CAD";
    /** what the record covers, one sentence under the panel's title */
    readonly scope: string;
  };
  /** qipu.org, for "open on qipu.org" links; omit to show none */
  readonly site?: { readonly base: string; readonly cityPath: string };
  /** where the map opens: a frame point (level-0 CSS px) and a zoom; omit to fit the city */
  readonly start?: { readonly x: number; readonly y: number; readonly zoom: number };
  /** credit line shown on the map */
  readonly attribution: string;
}

export const SAN_FRANCISCO: CityConfig = {
  id: "sf",
  name: "San Francisco",
  tiles: {
    base: "https://tiles.qipu.org/us/sf/city/r20261001",
    present: "render",
    eras: "_preview_eras/render-years.json",
  },
  data: { base: "https://www.qipu.org/data/us/sf/city" },
  record: {
    kinds: { R: "Resolution", O: "Ordinance", M: "Motion", W: "Departmental report" },
    currency: "USD",
    scope: "Board of Supervisors decisions, 1906 to today, placed on the block they name.",
  },
  site: { base: "https://www.qipu.org/en", cityPath: "/usa/san-francisco/the-city" },
  attribution:
    "Painted by qipu from DataSF and USGS data · Records: SF Board of Supervisors via the Internet Archive",
};

export const VANCOUVER: CityConfig = {
  id: "vancouver",
  name: "Vancouver",
  tiles: {
    base: "https://tiles.qipu.org/ca/vancouver/city/r20261007",
    present: "render",
    eras: "_preview_eras/render-years.json",
  },
  data: { base: "https://www.qipu.org/data/ca/vancouver/city" },
  record: {
    kinds: { C: "Council vote", N: "Council minutes", W: "Council minutes", P: "Building permit" },
    currency: "CAD",
    scope: "Council votes and minutes, and building permits, placed on the block they name.",
  },
  site: { base: "https://www.qipu.org/en", cityPath: "/canada/vancouver/the-city" },
  attribution:
    "Painted by qipu from City of Vancouver open data · Records: City of Vancouver (CC BY 3.0, OGL-Vancouver)",
};

export const CITIES: readonly CityConfig[] = [SAN_FRANCISCO, VANCOUVER];

/** A city config with its data folder moved, for a local sample or a mirror. */
export function withDataBase(city: CityConfig, base: string): CityConfig {
  return { ...city, data: { base } };
}
