/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

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
	test: {
		environment: "jsdom",
		setupFiles: ["./src/test/setup.ts"],
		css: false,
		coverage: {
			provider: "v8",
			reporter: ["text", "html"],
			include: ["src/**/*.{ts,tsx}"],
			// Report-only at first; ratchet a `thresholds` gate up later, mirroring
			// the Python side's coverage.fail_under approach.
			exclude: [
				"src/**/*.test.{ts,tsx}",
				"src/test/**",
				"src/**/*.d.ts",
				"src/main.tsx",
			],
		},
	},
});
