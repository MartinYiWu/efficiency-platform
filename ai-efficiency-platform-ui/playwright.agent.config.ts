import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'operations-chat-live-fake-agent.spec.ts',
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report-agent', open: 'never' }],
    [
      'json',
      {
        outputFile:
          '../efficiency-platform-agent/docs/superpowers/acceptance/evidence/operation-live-fake-agent-playwright.json',
      },
    ],
  ],
  use: {
    baseURL: 'http://127.0.0.1:5190',
    trace: 'on',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command:
        'uv run python scripts/local_fake_operation_agent_server.py --host 127.0.0.1 --port 8080',
      cwd: '../efficiency-platform-agent',
      url: 'http://127.0.0.1:8080/health/live',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: 'pnpm exec vite --host 127.0.0.1 --port 5190',
      url: 'http://127.0.0.1:5190',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
