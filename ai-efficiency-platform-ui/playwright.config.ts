import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  // 真实接口用例必须显式选择独立配置，默认套件仅使用浏览器 fixture。
  testIgnore: ['operations-chat-live-fake-agent.spec.ts', 'operations-chat-real-agent.spec.ts'],
  fullyParallel: true,
  use: {
    baseURL: 'http://127.0.0.1:5190',
    trace: 'on-first-retry',
    serviceWorkers: 'block',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
      },
    },
  ],
  webServer: {
    command: 'pnpm exec vite --host 127.0.0.1 --port 5190 --strictPort',
    url: 'http://127.0.0.1:5190',
    reuseExistingServer: false,
    env: { VITE_API_BASE_URL: '', VITE_API_PROXY_TARGET: 'http://127.0.0.1:1' },
  },
});
