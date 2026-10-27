import { expect, test } from "@playwright/test";
import { COLOURS, HAIGHT_BLOCK, SWITCH_YEAR, eraColourAtCentre, near, serveTiles } from "./fixtures";

const HAIGHT = `at=${HAIGHT_BLOCK.x},${HAIGHT_BLOCK.y},7`;

test.describe("the painted map", () => {
  test("loads the present and offers the eras", async ({ page }) => {
    const { requested } = await serveTiles(page);
    await page.goto("/?city=sf");
    await expect(page.getByLabel("Painted map of San Francisco")).toBeVisible();
    await expect(page.locator(".qv-present-layer img.leaflet-tile-loaded").first()).toBeVisible();
    const slider = page.getByRole("slider", { name: "Year" });
    await expect(slider).toHaveAttribute("min", "1887");
    await expect(slider).toHaveAttribute("max", "2026");
    await expect(slider).toHaveAttribute("aria-valuetext", "2026, today");
    expect(requested).toContain("render/index.json");
  });

  test("redraws a quarter pixel by pixel as the year moves", async ({ page }) => {
    await serveTiles(page);
    await page.goto(`/?city=sf&year=1938&${HAIGHT}`);
    expect(near(await eraColourAtCentre(page, 1938), COLOURS[1915])).toBe(true);

    const slider = page.getByRole("slider", { name: "Year" });
    await slider.focus();
    for (let y = 1938; y < SWITCH_YEAR; y++) await page.keyboard.press("ArrowRight");
    await expect(page.locator("output")).toHaveText(String(SWITCH_YEAR));
    expect(near(await eraColourAtCentre(page, SWITCH_YEAR), COLOURS[1959])).toBe(true);
    await expect(page).toHaveURL(new RegExp(`year=${SWITCH_YEAR}`));

    await page.keyboard.press("End");
    await expect(slider).toHaveAttribute("aria-valuetext", "2026, today");
  });

  test("draws the same eras without WebGL", async ({ page }) => {
    await serveTiles(page);
    await page.goto(`/?city=sf&year=1938&${HAIGHT}&gl=0`);
    await expect(page.locator(".qv-viewer")).toHaveAttribute("data-compositor", "cpu");
    expect(near(await eraColourAtCentre(page, 1938), COLOURS[1915])).toBe(true);
  });

  test("plays through the years and stops at the present", async ({ page }) => {
    await serveTiles(page);
    await page.goto("/?city=sf&year=2015");
    await page.getByRole("button", { name: "Play through the years" }).click();
    await expect(page.locator("output")).toHaveText("2026", { timeout: 5000 });
    await expect(page.getByRole("button", { name: "Play through the years" })).toHaveAttribute("aria-pressed", "false");
  });
});

test.describe("a block's record", () => {
  test("opens on a click or tap, follows a source to the archive, and closes", async ({ page }, info) => {
    await serveTiles(page);
    await page.goto(`/?city=sf&${HAIGHT}`);
    const map = page.locator(".qv-map");
    await expect(page.locator(".qv-present-layer img.leaflet-tile-loaded").first()).toBeVisible();
    if (info.project.name === "phone") await map.tap();
    else await map.click();

    const panel = page.getByRole("complementary", { name: /Haight Ashbury/ });
    await expect(panel).toBeVisible();
    await expect(panel.getByText(`Block ${HAIGHT_BLOCK.id}`)).toBeVisible();
    await expect(panel.getByText(/63 decisions/)).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`block=${HAIGHT_BLOCK.id}`));
    await expect(page.locator(".qv-block-outline")).toHaveCount(1);

    const source = panel.getByRole("link", { name: /Internet Archive/ }).first();
    await expect(source).toHaveAttribute("href", /^https:\/\/archive\.org\/details\/.+\/page\/n\d+/);
    const [tab] = await Promise.all([page.waitForEvent("popup"), source.click()]);
    await expect(tab).toHaveURL(/archive\.org\/details\//);
    await tab.close();

    await panel.getByRole("button", { name: /close/i }).click();
    await expect(panel).toBeHidden();
    await expect(page.locator(".qv-block-outline")).toHaveCount(0);
  });

  test("opens from a shared link", async ({ page }) => {
    await serveTiles(page);
    await page.goto(`/?city=sf&block=${HAIGHT_BLOCK.id}`);
    await expect(page.getByRole("complementary", { name: /Haight Ashbury/ })).toBeVisible();
    await expect(page.locator(".qv-block-outline")).toHaveCount(1);
  });

  test("says when a block has no records in the sample", async ({ page }) => {
    await serveTiles(page);
    await page.goto("/?city=sf&block=0001");
    await expect(page.getByText("No decisions are placed on this block yet.")).toBeVisible();
  });
});

test.describe("failures", () => {
  test("says so when the painting cannot load", async ({ page }) => {
    await page.route("https://tiles.qipu.org/**", (route) => route.fulfill({ status: 503, body: "" }));
    await page.goto("/?city=sf");
    await expect(page.getByRole("alert")).toContainText("The map could not load");
  });
});
