// A map of decision records: reads the GeoJSON written by `qipu-records build` and lists what is on the map.
// The data file comes from ?data=<url>, by default the output of `make demo`.

const DATA = new URLSearchParams(location.search).get("data") || "../build/demo/decisions.geojson";
const BASEMAP = "https://tiles.openfreemap.org/styles/positron";
const COLOURS = { passed: "#1f7a4d", refused: "#b3261e", pending: "#8a6d00" };

const map = new maplibregl.Map({ container: "map", style: BASEMAP, center: [-123.1, 49.26], zoom: 11.5 });
map.addControl(new maplibregl.NavigationControl(), "top-right");

const list = document.getElementById("list");
const yearInput = document.getElementById("year");
const yearOut = document.getElementById("year-out");

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => (key === "class" ? (node.className = value) : node.setAttribute(key, value)));
  children.filter((c) => c !== null && c !== undefined).forEach((c) => node.append(c));
  return node;
}

function money(p) {
  // map layers hand back array properties as JSON text
  const amounts = typeof p.amounts === "string" ? JSON.parse(p.amounts) : p.amounts;
  if (!amounts || !amounts.length) return null;
  const fmt = new Intl.NumberFormat("en-CA", { style: "currency", currency: p.currency || "CAD" });
  return el("div", { class: "meta" }, amounts.map((a) => fmt.format(a)).join(", "));
}

// The data file can come from any URL (?data=), so only links to archive.org pages are made clickable.
function archiveLink(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && parsed.hostname === "archive.org" ? parsed.href : null;
  } catch {
    return null;
  }
}

function card(p) {
  const link = p.page_url ? archiveLink(p.page_url) : null;
  return el(
    "div",
    {},
    el("div", { class: "meta" }, `${p.date || "undated"} · ${p.kind} · `, el("span", { class: `outcome ${p.outcome}` }, p.outcome)),
    el("div", {}, p.summary),
    el("div", { class: "meta" }, `${p.place} (${p.placed_as})`),
    money(p),
    el("blockquote", {}, `“${p.quote}”`),
    link ? el("a", { href: link, target: "_blank", rel: "noopener" }, "See the page on archive.org") : null,
  );
}

function showPopup(feature) {
  new maplibregl.Popup({ offset: 10 }).setLngLat(feature.geometry.coordinates).setDOMContent(card(feature.properties)).addTo(map);
}

function render(features, upTo) {
  const shown = features.filter((f) => !f.properties.date || Number(f.properties.date.slice(0, 4)) <= upTo);
  map.getSource("decisions")?.setData({ type: "FeatureCollection", features: shown });
  list.replaceChildren(
    ...shown.map((f) => {
      const item = el("li", { tabindex: "0" }, card(f.properties));
      item.querySelector("a")?.addEventListener("click", (event) => event.stopPropagation());
      item.addEventListener("click", () => showPopup(f));
      item.addEventListener("keydown", (event) => event.key === "Enter" && showPopup(f));
      return item;
    }),
  );
  yearOut.textContent = upTo;
  document.getElementById("caption").textContent = `${shown.length} of ${features.length} placed decisions`;
}

function addLayer() {
  map.addSource("decisions", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: "decisions",
    type: "circle",
    source: "decisions",
    paint: {
      "circle-radius": 7,
      "circle-color": ["match", ["get", "outcome"], "passed", COLOURS.passed, "refused", COLOURS.refused, "pending", COLOURS.pending, "#6b6f76"],
      "circle-stroke-width": 1.5,
      "circle-stroke-color": "#ffffff",
    },
  });
  map.on("click", "decisions", (event) => showPopup(event.features[0]));
  map.on("mouseenter", "decisions", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "decisions", () => (map.getCanvas().style.cursor = ""));
}

async function start() {
  const mapReady = new Promise((resolve) => map.once("load", resolve));
  const response = await fetch(DATA);
  if (!response.ok) throw new Error(`could not load ${DATA} (${response.status}); run "make demo" first`);
  const data = await response.json();
  const features = data.features.sort((a, b) => (a.properties.date || "").localeCompare(b.properties.date || ""));
  const years = features.map((f) => Number((f.properties.date || "0").slice(0, 4))).filter(Boolean);
  const [first, last] = [Math.min(...years), Math.max(...years)];
  Object.assign(yearInput, { min: first, max: last, value: last, step: 1 });
  yearInput.addEventListener("input", () => render(features, Number(yearInput.value)));
  render(features, last);
  await mapReady;
  addLayer();
  render(features, Number(yearInput.value));
  // Tells tests, and any page embedding this one, that the points are drawn.
  map.once("idle", () => (window.mapReady = true));
}

start().catch((error) => (document.getElementById("caption").textContent = error.message));
