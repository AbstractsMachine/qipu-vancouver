import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { CITIES, type CityConfig, Viewer, readViewState, withDataBase } from "../src";
import "./demo.css";

/*
 * The demo reads painted tiles from tiles.qipu.org and block records from the
 * sample in demo/public/sample (qipu.org's data folders send no CORS headers).
 * With QIPU_DATA_ORIGIN=https://www.qipu.org, `npm run demo` proxies /data
 * to the live folders and VITE_QIPU_DATA=live switches to them.
 */
const live = import.meta.env.VITE_QIPU_DATA === "live";

const SAMPLE_NOTES: Readonly<Record<string, string>> = {
  sf: "Demo records: the Mission, Haight-Ashbury and Chinatown. The rest of the city is on qipu.org.",
  vancouver: "Demo records: Strathcona and Mount Pleasant. The rest of the city is on qipu.org.",
};

function noticeFor(city: CityConfig): string {
  if (city.data.decisions) return "Records read from a packages/records decisions.jsonl, placed on the blocks here.";
  return SAMPLE_NOTES[city.id] ?? "";
}

function dataFor(city: CityConfig): CityConfig {
  const path = new URL(city.data.base).pathname;
  return withDataBase(city, live ? path : `${import.meta.env.BASE_URL}sample/${city.id}`);
}

/* with no link the demo opens where the README shows it: Strathcona in 1972, one block's decisions open */
const linked = readViewState(window.location.search);
const initial = Object.keys(linked).length > 0 ? linked : { city: "vancouver", year: 1972, block: "3565" };

/* ?tiles=<release folder> opens a qipu-tiles/1 release written by packages/map-pipeline, over Vancouver's records */
const release = new URLSearchParams(window.location.search).get("tiles");
/*
 * ?decisions=<url> reads Vancouver's records from a decisions.jsonl written by packages/records instead of the
 * qipu.org shards; ?decisions=sample opens the copy of `make -C packages/records demo` bundled with the demo
 */
const decisionsParam = new URLSearchParams(window.location.search).get("decisions");
const decisions =
  decisionsParam === "sample" ? `${import.meta.env.BASE_URL}sample/vancouver/decisions.jsonl` : decisionsParam;
const cities: readonly CityConfig[] = CITIES.map((c) => {
  if (c.id !== "vancouver") return c;
  return {
    ...c,
    ...(release ? { tiles: { format: "qipu-tiles/1" as const, base: release } } : {}),
    ...(decisions ? { data: { ...c.data, decisions } } : {}),
  };
});

function App() {
  const [cityId, setCityId] = useState(initial.city ?? "vancouver");
  const city = cities.find((c) => c.id === cityId) ?? cities[0];
  if (!city) return null;
  return (
    <div className="demo">
      <nav className="demo-cities" aria-label="City">
        {cities.map((c) => (
          <button
            key={c.id}
            type="button"
            aria-pressed={c.id === city.id}
            onClick={() => {
              window.history.replaceState(
                null,
                "",
                `?city=${c.id}${release ? `&tiles=${encodeURIComponent(release)}` : ""}${
                  decisionsParam ? `&decisions=${encodeURIComponent(decisionsParam)}` : ""
                }`,
              );
              setCityId(c.id);
            }}
          >
            {c.name}
          </button>
        ))}
      </nav>
      <main className="demo-map">
        <Viewer
          key={city.id}
          city={dataFor(city)}
          initial={city.id === initial.city || (!initial.city && city.id === "vancouver") ? initial : {}}
          syncUrl
          {...(live ? {} : { notice: noticeFor(city) })}
          {...(new URLSearchParams(window.location.search).get("gl") === "0" ? { compositor: "cpu" as const } : {})}
        />
      </main>
    </div>
  );
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
