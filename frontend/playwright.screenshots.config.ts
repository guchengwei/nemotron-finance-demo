import { defineConfig } from '@playwright/test'

// Screenshots config: identical to playwright.config.ts but points to the
// system Chromium binary so it works without a network download.
export default defineConfig({
  testDir: './e2e',
  timeout: 120000,
  use: {
    baseURL: 'http://127.0.0.1:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
        launchOptions: {
          executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
        },
      },
    },
  ],
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 3000',
    port: 3000,
    reuseExistingServer: true,
    timeout: 120000,
  },
})
