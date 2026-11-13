import { defineConfig } from "@playwright/test";

// E2E runs against an isolated backend (port 8001, separate SQLite file) and a Vite dev server on 5174.
const E2E_DB = "sqlite:///" + new URL("../backend/data/e2e.db", import.meta.url).pathname;

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [["list"], ["json", { outputFile: "e2e-results.json" }]],
  use: { baseURL: "http://127.0.0.1:5174", trace: "retain-on-failure", viewport: { width: 1440, height: 900 } },
  webServer: [
    {
      command: `rm -f data/e2e.db data/e2e.db-wal data/e2e.db-shm && RACKOPS_DATABASE_URL=${E2E_DB} uv run alembic upgrade head && RACKOPS_DATABASE_URL=${E2E_DB} uv run python -m app.seed && RACKOPS_DATABASE_URL=${E2E_DB} RACKOPS_FRONTEND_ORIGIN=http://127.0.0.1:5174 uv run uvicorn app.main:app --host 127.0.0.1 --port 8001`,
      cwd: "../backend",
      url: "http://127.0.0.1:8001/api/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "RACKOPS_API_URL=http://127.0.0.1:8001 npx vite --host 127.0.0.1 --port 5174 --strictPort",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
