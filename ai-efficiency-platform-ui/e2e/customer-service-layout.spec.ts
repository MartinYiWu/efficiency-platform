import { writeFile } from 'node:fs/promises';

import { expect, test } from './fixtures';

const now = '2026-10-27T00:00:00Z';
const longContent = Array.from(
  { length: 24 },
  (_, index) =>
    `### 第 ${index + 1} 项\n\n这是用于验证消息布局的通用说明。${'长内容应只在消息区滚动。'.repeat(8)}`,
).join('\n\n');

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 1024, height: 420 },
  { width: 390, height: 420 },
]) {
  test(`long conversation keeps composer visible at ${viewport.width}x${viewport.height}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = [];
      if (path === '/api/customer-service/conversations')
        data = {
          items: Array.from({ length: 50 }, (_, index) => ({
            id: `c${index}`,
            tenantId: 't',
            userId: 'u',
            title: `布局验收会话 ${index}`,
            status: 'ACTIVE',
            lastMessageAt: now,
            createdAt: now,
            updatedAt: now,
          })),
          page: 1,
          pageSize: 50,
          total: 50,
        };
      if (path.endsWith('/messages'))
        data = Array.from({ length: 6 }, (_, index) => ({
          message: {
            id: `m${index}`,
            conversationId: 'c0',
            tenantId: 't',
            role: index % 2 === 0 ? 'USER' : 'ASSISTANT',
            content: index % 2 === 0 ? '布局验收问题' : longContent,
            status: 'COMPLETED',
            answerMode: index % 2 === 0 ? null : 'GENERAL_ADVICE',
            runId: null,
            clientRequestId: null,
            createdAt: now,
          },
          citations: [],
        }));
      await route.fulfill({ json: { code: 'SUCCESS', data } });
    });
    await page.goto('/ai-assistants/customer-service/chat');
    const log = page.getByRole('log');
    await expect(log.getByRole('heading', { name: '第 24 项', exact: true })).toHaveCount(3);
    const input = page.getByRole('textbox', { name: '输入问题' });
    await input.fill('多行输入\n'.repeat(7));
    await input.focus();
    await expect
      .poll(() => input.evaluate((element) => element.getBoundingClientRect().height))
      .toBeGreaterThan(60);
    if (viewport.height <= 500)
      expect(
        await input.evaluate((element) => element.getBoundingClientRect().height),
      ).toBeLessThanOrEqual(64);
    const measure = () =>
      page.evaluate(() => {
        const log = document.querySelector('[role="log"]')!;
        const form = document.querySelector('[role="form"]')!;
        const textarea = document.querySelector('textarea')!;
        const rect = form.getBoundingClientRect();
        return {
          pageHeight: document.documentElement.scrollHeight,
          height: innerHeight,
          width: innerWidth,
          pageWidth: document.documentElement.scrollWidth,
          composerTop: rect.top,
          composerBottom: rect.bottom,
          inputBottom: textarea.getBoundingClientRect().bottom,
          messageHeight: log.clientHeight,
          messageContent: log.scrollHeight,
        };
      });
    await expect
      .poll(async () => (await measure()).composerBottom)
      .toBeLessThanOrEqual(viewport.height + 1);
    let metrics = await measure();
    expect(metrics.pageHeight).toBeLessThanOrEqual(metrics.height + 1);
    expect(metrics.pageWidth).toBeLessThanOrEqual(metrics.width);
    expect(metrics.inputBottom).toBeLessThanOrEqual(metrics.composerBottom);
    expect(metrics.composerTop).toBeGreaterThan(100);
    expect(metrics.messageHeight).toBeGreaterThan(0);
    expect(metrics.messageContent).toBeGreaterThan(metrics.messageHeight);
    await log.evaluate((element) => {
      element.scrollTop = 0;
    });
    await expect(page.getByRole('button', { name: '回到最新消息' })).toBeVisible();
    await page.getByRole('button', { name: '回到最新消息' }).click();
    await expect
      .poll(() =>
        log.evaluate((element) => element.scrollHeight - element.clientHeight - element.scrollTop),
      )
      .toBeLessThan(2);
    if (viewport.width >= 640) {
      const history = page.getByRole('navigation', { name: '历史会话', exact: true });
      expect(await history.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(
        true,
      );
      const messageTop = await log.evaluate((element) => element.scrollTop);
      await history.evaluate((element) => {
        element.scrollTop = element.scrollHeight;
      });
      expect(await log.evaluate((element) => element.scrollTop)).toBe(messageTop);
    }
    await testInfo.attach('layout-metrics', {
      body: JSON.stringify(metrics),
      contentType: 'application/json',
    });
    await writeFile(testInfo.outputPath('layout-metrics.json'), JSON.stringify(metrics, null, 2));
    await testInfo.attach('long-conversation', {
      body: await page.screenshot({ path: testInfo.outputPath('long-conversation.png') }),
      contentType: 'image/png',
    });
    await page.setViewportSize({ width: viewport.width, height: Math.min(viewport.height, 360) });
    await expect.poll(async () => (await measure()).composerBottom).toBeLessThanOrEqual(361);
    await expect
      .poll(() => input.evaluate((element) => element.getBoundingClientRect().height))
      .toBeLessThanOrEqual(64);
    metrics = await measure();
    expect(metrics.messageHeight).toBeGreaterThan(0);
    expect(metrics.pageHeight).toBeLessThanOrEqual(metrics.height + 1);
  });
}
