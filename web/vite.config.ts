import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The browser talks only to Vite; /api requests are proxied to the FastAPI backend.
const backend = process.env.VESTIGO_BACKEND_URL ?? "http://localhost:8400";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5180,
    strictPort: true,
    proxy: { "/api": backend },
  },
  preview: {
    host: true,
    port: 5180,
    strictPort: true,
    proxy: { "/api": backend },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
