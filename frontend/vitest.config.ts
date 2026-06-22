import { defineConfig } from "vitest/config";
import solid from "vite-plugin-solid";
import { resolve } from "node:path";

const here = import.meta.dirname; // frontend/
const repoRoot = resolve(here, "..");

// Convert Windows backslashes to forward slashes for glob patterns.
const fwd = (p: string) => p.replace(/\\/g, "/");

export default defineConfig({
  plugins: [solid()],
  resolve: {
    // Use browser-side solid-js (not server bundle) in tests.
    conditions: ["browser"],
    alias: {
      "@": resolve(here, "src"),
      // When test files live outside the Vite root they cannot resolve
      // node_modules relative to their own directory — anchor them here.
      "@solidjs/testing-library": resolve(here, "node_modules/@solidjs/testing-library"),
      "@testing-library/jest-dom": resolve(here, "node_modules/@testing-library/jest-dom"),
    },
  },
  // Test files live outside the Vite root (frontend/) — allow serving them.
  server: { fs: { allow: [here, repoRoot] } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [resolve(here, "vitest.setup.ts")],
    include: [
      `${fwd(repoRoot)}/tests/unit/frontend/**/*.{test,spec}.{ts,tsx}`,
      `${fwd(repoRoot)}/tests/integration/frontend/**/*.{test,spec}.{ts,tsx}`,
    ],
    coverage: {
      provider: "v8",
      reportsDirectory: resolve(here, "coverage"),
      include: ["src/**"],
    },
  },
});
