import { configDefaults, defineConfig } from 'vitest/config';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8080' } },
  test: {
    pool: 'forks',
    maxWorkers: 1,
    testTimeout: 20_000,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
});
