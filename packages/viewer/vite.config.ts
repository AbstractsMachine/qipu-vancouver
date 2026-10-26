import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { defineConfig } from "vite";

/*
 * Two builds from one config: `vite` / `vite build --mode demo` serve and build
 * the demo app in demo/; `vite build` (library mode) builds src/ for other apps.
 * QIPU_DATA_ORIGIN proxies /data to a live qipu.org data folder during `npm run demo`.
 */
export default defineConfig(({ mode }) => {
  const dataOrigin = process.env.QIPU_DATA_ORIGIN;
  if (mode === "demo" || mode === "development") {
    return {
      root: "demo",
      base: "./",
      plugins: [react()],
      build: { outDir: "../demo-dist", emptyOutDir: true },
      server: {
        port: 5173,
        strictPort: true,
        ...(dataOrigin ? { proxy: { "/data": { target: dataOrigin, changeOrigin: true } } } : {}),
      },
      preview: { port: 4173, strictPort: true },
    };
  }
  return {
    plugins: [react()],
    build: {
      lib: { entry: resolve(__dirname, "src/index.ts"), formats: ["es"], fileName: "index", cssFileName: "viewer" },
      rolldownOptions: { external: ["react", "react-dom", "react/jsx-runtime", "leaflet"] },
      sourcemap: true,
    },
  };
});
