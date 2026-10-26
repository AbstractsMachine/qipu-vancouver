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

function dataFor(city: CityConfig): CityConfig {
  const path = new URL(city.data.base).pathname;
  return withDataBase(city, live ? path : `${import.meta.env.BASE_URL}sample/${city.id}`);
}

const initial = readViewState(window.location.search);

/* ?tiles=<release folder> opens a qipu-tiles/1 release written by packages/map-pipeline, over Vancouver's records */
const release = new URLSearchParams(window.location.search).get("tiles");
const cities: readonly CityConfig[] = release
  ? CITIES.map((c) => (c.id === "vancouver" ? { ...c, tiles: { format: "qipu-tiles/1", base: release } } : c))
  : CITIES;

function App() {
  const [cityId, setCityId] = useState(initial.city ?? (release ? "vancouver" : "sf"));
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
                `?city=${c.id}${release ? `&tiles=${encodeURIComponent(release)}` : ""}`,
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
          initial={city.id === initial.city || (!initial.city && city.id === "sf") ? initial : {}}
          syncUrl
          {...(live ? {} : { notice: SAMPLE_NOTES[city.id] ?? "" })}
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
