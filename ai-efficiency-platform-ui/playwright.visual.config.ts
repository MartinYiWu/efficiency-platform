import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  testMatch: 'migration-visual.spec.ts',
  workers: 1,
  timeout: 180_000,
  outputDir: 'test-results/migration-visual',
  reporter: [
    ['list'],
    ['json', { outputFile: '../docs/verification/2026-11-03-vue-migration/visual-results.json' }],
  ],
  use: { baseURL: 'http://127.0.0.1:5191', serviceWorkers: 'block', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm exec vite --host 127.0.0.1 --port 5191 --strictPort',
    url: 'http://127.0.0.1:5191',
    reuseExistingServer: false,
    env: { VITE_API_BASE_URL: '', VITE_API_PROXY_TARGET: 'http://127.0.0.1:1' },
  },
});
