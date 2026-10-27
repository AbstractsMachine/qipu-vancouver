import { expect, test } from "@playwright/test";
import { gridOptionsFor, tilesForViewport } from "../src/tiles/levels";
import { serveTiles } from "./fixtures";

/*
 * The performance budget, as numbers a test can hold: the first view asks
 * for no more present-day tiles than its viewport needs, no era tile at the
 * present, and is drawn before the 2.5 s mark (served locally, so this is
 * the app's own cost, not the network's).
 */
test("the first view stays inside its tile budget", async ({ page }, info) => {
  const { requested } = await serveTiles(page);
  const started = Date.now();
  await page.goto("/?city=sf");
  await expect(page.locator(".qv-present-layer img.leaflet-tile-loaded").first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  const drawnMs = Date.now() - started;

  const viewport = page.viewportSize() ?? { width: 0, height: 0 };
  const dpr = info.project.use.deviceScaleFactor ?? 1;
  const budget = tilesForViewport(viewport.width, viewport.height, gridOptionsFor(dpr));
  const present = requested.filter((p) => p.startsWith("render/") && !p.endsWith(".json"));
  const eras = requested.filter((p) => p.startsWith("_preview_eras/area/"));

  expect(present.length).toBeGreaterThan(0);
  expect(present.length).toBeLessThanOrEqual(budget);
  expect(eras).toEqual([]);
  expect(drawnMs).toBeLessThan(2500);
});
