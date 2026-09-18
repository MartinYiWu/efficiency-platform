import { expect, test } from '@playwright/test';

test('运营助手通过真实 HTTP 和 SSE 连接确定性 Agent', async ({ page }, testInfo) => {
  const network: Array<{
    method: string;
    origin: string;
    path: string;
    hasSensitiveHeader: boolean;
  }> = [];
  const consoleIssues: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      consoleIssues.push(message.type());
    }
  });
  page.on('request', (request) => {
    const target = new URL(request.url());
    const headers = request.headers();
    network.push({
      method: request.method(),
      origin: target.origin,
      path: target.pathname
        .replace(/\/conversations\/[^/]+/, '/conversations/{conversation_id}')
        .replace(/\/runs\/[^/]+/, '/runs/{run_id}'),
      hasSensitiveHeader:
        'authorization' in headers || 'x-api-key' in headers || 'api-key' in headers,
    });
  });

  await page.goto('/ai-assistants/operations/chat');
  await page.getByLabel('输入消息').fill('生成环保水杯的小红书新品内容');
  await page.getByRole('button', { name: '发送消息' }).click();

  await expect(page.getByText('通勤补水新搭子')).toBeVisible();
  await expect(page.getByText('轻巧环保的水杯，让每天通勤补水更简单。')).toBeVisible();
  await expect(page.getByText('平台：xiaohongshu')).toBeVisible();
  await expect(page.getByRole('button', { name: '发送消息' })).toBeDisabled();

  const apiRequests = network.filter((item) => item.origin === 'http://127.0.0.1:8080');
  expect(apiRequests.map((item) => `${item.method} ${item.path}`)).toEqual([
    'POST /v1/conversations/{conversation_id}/messages',
    'GET /v1/runs/{run_id}/events',
  ]);
  expect(
    network.every((item) =>
      ['http://127.0.0.1:5190', 'http://127.0.0.1:8080'].includes(item.origin),
    ),
  ).toBe(true);
  expect(network.some((item) => item.hasSensitiveHeader)).toBe(false);
  expect(consoleIssues).toEqual([]);

  await testInfo.attach('脱敏网络摘要', {
    body: Buffer.from(JSON.stringify(apiRequests, null, 2)),
    contentType: 'application/json',
  });
  await testInfo.attach('运营助手成品截图', {
    body: await page.screenshot(),
    contentType: 'image/png',
  });
});
