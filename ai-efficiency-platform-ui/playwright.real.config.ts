import { defineConfig, devices } from '@playwright/test';

// 显式连接操作者已启动的真实 Java → Agent 环境，不创建或停止任何服务。
export default defineConfig({
  testDir: './e2e',
  testMatch: 'operations-chat-real-agent.spec.ts',
  workers: 1,
  outputDir: 'test-results-real',
  use: {
    baseURL: process.env.PLAYWRIGHT_REAL_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'on',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
