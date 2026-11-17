import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, expect } from './fixtures';
import { installMigrationFixture } from './migration-fixture';
import { routes as appRoutes } from '../src/app/router/routes';
const routes = appRoutes
  .filter((route) => 'component' in route && !route.path.includes('pathMatch'))
  .map((route) => route.path);
const sample = (path: string) =>
  path
    .replace(':baseId', 'kb')
    .replace(':documentId', 'd')
    .replace(':agentId', 'a')
    .replace(':datasetId', 'ds')
    .replace(':runId', path.includes('rag-evaluations') ? 'er' : 'r')
    .replace(':candidateId', 'candidate-1')
    .replace(':batchId', 'batch-1')
    .replace(':positionId', 'position-1')
    .replace(':assignmentId', 'assignment-1');
const screenshots = resolve('../docs/verification/2026-11-03-vue-migration/screenshots');
const representatives: Record<string, string> = {
  '/knowledge-center/knowledge-bases': 'knowledge-list',
  '/knowledge-center/knowledge-bases/:baseId': 'knowledge-detail',
  '/knowledge-center/documents/:documentId': 'knowledge-document',
  '/ai-center/agents': 'ai-agents',
  '/ai-center/rag-evaluations/:datasetId': 'ai-evaluations',
  '/ai-assistants/hr/workbench': 'hr-workbench',
  '/ai-assistants/hr/positions/new': 'hr-position',
  '/ai-assistants/operations/chat': 'operations-chat',
  '/ai-assistants/customer-service/chat': 'customer-service',
};
for (const width of [1440, 1024, 390]) {
  test(`全部45页面离线视觉与响应式 ${width}px`, async ({ page, baseURL }) => {
    test.setTimeout(180_000);
    expect(routes).toHaveLength(45);
    expect(routes.filter((route) => !route.includes('/interviews/assigned/'))).toHaveLength(44);
    expect(routes).toContain('/ai-assistants/hr/interviews/assigned/:assignmentId');
    mkdirSync(screenshots, { recursive: true });
    await page.setViewportSize({ width, height: 1000 });
    const unknown = await installMigrationFixture(page, baseURL!);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    for (const route of routes) {
      await test.step(sample(route), async () => {
        await page.goto(sample(route));
        await page.waitForLoadState('networkidle');
        const main = page.locator('main.platform-content');
        await expect(main).toBeVisible();
        await expect(main).not.toBeEmpty();
        await expect(main.locator('h1,h2,h3').first()).toBeVisible();
        const metrics = await page.evaluate(() => ({
          client: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth,
          mainClient: document.querySelector('main.platform-content')?.clientWidth ?? 0,
          mainScroll: document.querySelector('main.platform-content')?.scrollWidth ?? 0,
          text: document.querySelector('main')?.textContent ?? '',
        }));
        expect.soft(metrics.scroll, `${route}整体横向溢出`).toBeLessThanOrEqual(metrics.client + 1);
        expect
          .soft(metrics.mainScroll, `${route}主体不可依靠外壳裁切内容`)
          .toBeLessThanOrEqual(metrics.mainClient + 1);
        expect
          .soft(metrics.text, `${route}不应加载失败/契约异常`)
          .not.toMatch(/服务端响应不符合|正在加载知识库|正在加载文档|OFFLINE_FIXTURE_MISSING/);
        expect.soft(errors, `${route}运行时异常`).toEqual([]);
        const primaryLabels: Record<string, string> = {
          '/knowledge-center/knowledge-bases': '新建知识库',
          '/knowledge-center/knowledge-bases/:baseId': '上传文档',
          '/knowledge-center/knowledge-bases/:baseId/imports': '选择文件并导入',
          '/knowledge-center/documents/:documentId': '上传版本',
          '/ai-assistants/hr/workbench': '新建岗位',
        };
        if (primaryLabels[route])
          await expect(
            main.getByRole('button', { name: new RegExp(primaryLabels[route]! + '$') }),
          ).toBeVisible();
        if (route.endsWith('/chat')) await expect(main.locator('textarea').last()).toBeInViewport();
        if (representatives[route])
          await page.screenshot({
            path: resolve(screenshots, `${representatives[route]}-${width}.png`),
            fullPage: true,
          });
      });
    }
    expect(unknown, '所有API/外源请求必须显式离线fixture').toEqual([]);
  });
}
