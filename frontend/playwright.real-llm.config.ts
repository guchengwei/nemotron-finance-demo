import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e/real-llm',
  fullyParallel: false,
  workers: 1,
  timeout: 10 * 60 * 1000,
  expect: {
    timeout: 30_000,
  },
  retries: process.env.CI ? 1 : 0,
  globalSetup: './e2e/real-llm/global.setup.ts',
  use: {
    baseURL: 'http://127.0.0.1:3100',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  webServer: [
    {
      command: "rm -f ../data/e2e-history.db ../data/e2e-history.db-shm ../data/e2e-history.db-wal && cd ../backend && MOCK_LLM=false E2E_MODE=true BACKEND_PORT=8180 HISTORY_DB_PATH=./data/e2e-history.db python3 -m uvicorn main:app --host 127.0.0.1 --port 8180 --env-file ../.env",
      port: 8180,
      reuseExistingServer: false,
      timeout: 10 * 60 * 1000,
    },
    {
      command: 'VITE_API_PROXY_TARGET=http://127.0.0.1:8180 npm run build && VITE_API_PROXY_TARGET=http://127.0.0.1:8180 npm run preview -- --host 127.0.0.1 --port 3100',
      port: 3100,
      reuseExistingServer: false,
      timeout: 5 * 60 * 1000,
    },
  ],
})
