import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'node:path';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'release.spec.ts',
  workers: 1,
  timeout: 30_000,
  outputDir: 'test-results/release',
  use: { baseURL: 'http://127.0.0.1:5193', serviceWorkers: 'block' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: 'node e2e/release-backend.mjs',
      url: 'http://127.0.0.1:5194/health',
      reuseExistingServer: false,
    },
    {
      command: 'node scripts/serve-dist.mjs',
      url: 'http://127.0.0.1:5193',
      reuseExistingServer: false,
      env: {
        RELEASE_PORT: '5193',
        RELEASE_API_TARGET: 'http://127.0.0.1:5194',
        RELEASE_ASSETS_DIR: resolve(
          '../.local-acceptance/ui-delivery-20261103/probe-shared-assets',
        ),
      },
    },
    {
      command: 'node scripts/serve-dist.mjs',
      url: 'http://127.0.0.1:5198',
      reuseExistingServer: false,
      env: { RELEASE_PORT: '5198', RELEASE_API_TARGET: '' },
    },
  ],
});
