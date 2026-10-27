import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/index.ts", "src/map/gl-*.ts"],
      reporter: ["text-summary", "text", "json-summary"],
      thresholds: { lines: 85, functions: 85, branches: 75, statements: 85 },
    },
  },
});
