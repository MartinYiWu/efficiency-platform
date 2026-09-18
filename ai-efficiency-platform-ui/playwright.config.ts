import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  // 真实 HTTP Fake Agent 用例由独立配置同时拉起前后端，避免普通 UI 套件误用外部服务。
  testIgnore: 'operations-chat-live-fake-agent.spec.ts',
  fullyParallel: true,
  use: {
    baseURL: 'http://127.0.0.1:5190',
    trace: 'on-first-retry',
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
    command: 'pnpm exec vite --host 127.0.0.1 --port 5190',
    url: 'http://127.0.0.1:5190',
    reuseExistingServer: !process.env.CI,
  },
});
