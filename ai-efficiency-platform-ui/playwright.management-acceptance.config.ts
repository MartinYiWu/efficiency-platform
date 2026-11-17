import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  testMatch: 'management-journey.spec.ts',
  fullyParallel: true,
  use: { baseURL: 'http://127.0.0.1:5196', serviceWorkers: 'block', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm exec vite --host 127.0.0.1 --port 5196 --strictPort',
    url: 'http://127.0.0.1:5196',
    reuseExistingServer: false,
    env: { VITE_API_BASE_URL: '', VITE_API_PROXY_TARGET: 'http://127.0.0.1:1' },
  },
});
