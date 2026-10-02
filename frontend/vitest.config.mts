import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

// Unit tests live next to the code they test (`*.test.ts[x]` under src/).
// End-to-end tests are Playwright's, in e2e/, and are excluded here.
export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
    restoreMocks: true,
  },
});
