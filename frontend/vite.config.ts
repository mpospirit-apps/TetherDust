import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Single-origin dev: the Vite dev server proxies the API and WebSocket to the
// Django/Daphne backend so the browser only ever talks to one origin (5173).
// This keeps the session cookie first-party and avoids CORS in development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
      "/ws": { target: "ws://localhost:8000", ws: true, changeOrigin: false },
    },
  },
});
