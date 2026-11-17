import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e',
  outputDir: 'test-results/knowledge',
  testMatch: 'knowledge-journey.spec.ts',
  use: { baseURL: 'http://127.0.0.1:5195', serviceWorkers: 'block' },
  webServer: {
    command: 'pnpm exec vite --host 127.0.0.1 --port 5195 --strictPort',
    url: 'http://127.0.0.1:5195',
    reuseExistingServer: false,
    env: { VITE_API_BASE_URL: '', VITE_API_PROXY_TARGET: 'http://127.0.0.1:1' },
  },
});
