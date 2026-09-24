import { defineConfig, devices } from '@playwright/test';

const livePreviewUrl = process.env.UEC_REAL_PREVIEW_URL;

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? 'line' : 'list',
  timeout: 30_000,
  use: { baseURL: livePreviewUrl ?? 'http://127.0.0.1:4173/v2-preview/', trace: 'retain-on-failure' },
  ...(livePreviewUrl ? {} : { webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 4173', url: 'http://127.0.0.1:4173/v2-preview/', timeout: 30_000, reuseExistingServer: false } }),
  projects: livePreviewUrl ? [
    { name: 'chromium-live-preview', use: { ...devices['Desktop Chrome'] } },
  ] : [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
