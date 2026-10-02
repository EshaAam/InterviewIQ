import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end: a real browser against a real backend.
 *
 * Playwright starts the *production* frontend build (the standalone server), so build
 * first with NEXT_PUBLIC_API_URL pointing at the API — it's baked in at build
 * time. The backend must already be running, on the fake provider:
 *
 *   NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 npm run build
 *   npm run e2e
 *
 * CI does exactly this against docker-compose.prod.yml (see .github/workflows).
 */
export default defineConfig({
  testDir: "e2e",
  // The interview waits on background workers; give each test room.
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.E2E_BASE_URL
    ? undefined // pointing at something already running
    : {
        command: "npm run serve", // the standalone server, as in production
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 60_000,
      },
});
