import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In production Django serves the built assets from /static/ (WhiteNoise),
// so the whole app is one deployable service on one origin.
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/static/" : "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 700 },
}));
