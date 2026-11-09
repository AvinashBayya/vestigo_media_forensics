import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// A browser-equivalent run: real HTTP to the live dev server, no msw, no CSS pipeline.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost:5180/" } },
    css: false,
    setupFiles: ["./src/test/jsdom-only-setup.ts"],
    include: ["browser-acceptance.test.tsx"],
    testTimeout: 120000,
    hookTimeout: 60000,
    fileParallelism: false,
  },
});
