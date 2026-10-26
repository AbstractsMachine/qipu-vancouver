import { defineConfig, devices } from "@playwright/test";

const PORT = 5199;

/*
 * The demo, driven in Chromium on a desktop and a phone. Tiles are served by
 * e2e/fixtures.ts, so nothing here touches tiles.qipu.org. Chromium draws the
 * WebGL compositor with SwiftShader; the `gl=0` test covers the CPU path.
 */
export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  /* two browsers at most: the suite shares a laptop with other work */
  workers: 2,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `npx vite --mode demo --port ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
