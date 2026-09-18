import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react-swc';

export default defineConfig({
  plugins: [react()],
  test: {
    // Node 线程池在当前 Windows 环境会偶发长时间无输出；使用子进程池保证本地与 CI 的回归结果可重复。
    pool: 'forks',
    // 该项目的页面测试会加载完整 Ant Design 运行时；并发 JSDOM 会争抢 CPU 并触发错误超时。
    maxWorkers: 1,
    testTimeout: 20_000,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
});
