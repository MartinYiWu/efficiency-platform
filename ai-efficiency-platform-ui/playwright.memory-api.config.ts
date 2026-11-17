import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'node:path';

const enabled = process.env.MEMORY_UI_INTEGRATION_ENABLED === '1';
let apiBase: string | undefined;
let uiPort: number | undefined;
if (enabled) {
  const required = [
    'MEMORY_UI_API_BASE_URL',
    'MEMORY_UI_PORT',
    'MEMORY_UI_ACCESS_TOKEN',
    'MEMORY_UI_OTHER_ACCESS_TOKEN',
    'MEMORY_UI_OPERATIONS_SESSION_ID',
    'MEMORY_UI_OPERATIONS_NEW_SESSION_ID',
    'MEMORY_UI_CUSTOMER_SERVICE_SESSION_ID',
    'MEMORY_UI_CUSTOMER_SERVICE_NEW_SESSION_ID',
  ];
  if (required.some((name) => !process.env[name]))
    throw new Error('Memory UI integration requires explicit fixture configuration');
  let parsed: URL;
  try {
    parsed = new URL(process.env.MEMORY_UI_API_BASE_URL!);
  } catch {
    throw new Error('Memory UI API must be an explicit HTTP loopback origin');
  }
  if (
    parsed.protocol !== 'http:' ||
    !['127.0.0.1', 'localhost'].includes(parsed.hostname) ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== '/' ||
    parsed.search ||
    parsed.hash
  )
    throw new Error('Memory UI API must be an explicit HTTP loopback origin');
  apiBase = parsed.origin;
  uiPort = Number(process.env.MEMORY_UI_PORT);
  if (
    !Number.isInteger(uiPort) ||
    uiPort < 1024 ||
    uiPort > 65535 ||
    uiPort === Number(parsed.port || 80)
  )
    throw new Error('Memory UI requires a distinct explicit unprivileged task port');
  if (process.env.MEMORY_UI_ACCESS_TOKEN === process.env.MEMORY_UI_OTHER_ACCESS_TOKEN)
    throw new Error('Memory UI integration requires distinct authenticated actors');
}

export default defineConfig({
  testDir: './e2e',
  testMatch: 'memory-api-real.spec.ts',
  workers: 1,
  retries: 0,
  timeout: 120_000,
  reporter: [['line']],
  outputDir: resolve('../.local-acceptance/agent-memory-implementation/green/D14API-browser'),
  use: {
    baseURL: enabled ? `http://127.0.0.1:${uiPort}` : undefined,
    serviceWorkers: 'block',
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: enabled
    ? {
        command: `pnpm exec vite --host 127.0.0.1 --port ${uiPort} --strictPort`,
        url: `http://127.0.0.1:${uiPort}`,
        reuseExistingServer: false,
        env: { VITE_API_BASE_URL: '', VITE_API_PROXY_TARGET: apiBase! },
      }
    : undefined,
});
