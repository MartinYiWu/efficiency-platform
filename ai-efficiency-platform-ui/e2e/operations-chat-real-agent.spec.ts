import { expect, test } from '@playwright/test';

test('运营助手通过真实 Java 与 Agent HTTP/SSE 完成对话并在刷新后恢复', async ({ page }, testInfo) => {
  test.setTimeout(90_000);

  const apiRequests: Array<{ method: string; path: string; status?: number }> = [];
  const consoleIssues: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on('response', (response) => {
    const target = new URL(response.url());
    if (!target.pathname.startsWith('/api/operations/')) return;
    apiRequests.push({
      method: response.request().method(),
      path: target.pathname
        .replace(/\/conversations\/[^/]+/, '/conversations/{conversation_id}')
        .replace(/\/runs\/[^/]+/, '/runs/{run_id}'),
      status: response.status(),
    });
  });

  const createResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === '/api/operations/conversations',
  );
  await page.goto('/ai-assistants/operations/chat');
  const createResponse = await createResponsePromise;
  expect(createResponse.status()).toBe(200);

  await expect
    .poll(() => new URL(page.url()).searchParams.get('conversationId'))
    .not.toBeNull();
  const conversationId = new URL(page.url()).searchParams.get('conversationId');
  await page.getByLabel('输入消息').fill('你是谁');

  const submitResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      /\/api\/operations\/conversations\/[^/]+\/messages$/.test(
        new URL(response.url()).pathname,
      ),
  );
  const streamResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' &&
      /\/api\/operations\/runs\/[^/]+\/events$/.test(new URL(response.url()).pathname),
  );

  await page.getByRole('button', { name: '发送消息' }).click();
  const [submitResponse, streamResponse] = await Promise.all([
    submitResponsePromise,
    streamResponsePromise,
  ]);
  const submission = (await submitResponse.json()) as {
    code?: string;
    data?: { runId?: string; status?: string };
  };
  expect(submitResponse.status()).toBe(202);
  expect(submission).toMatchObject({
    code: 'SUCCESS',
    data: { status: 'queued' },
  });
  expect(submission.data?.runId).toEqual(expect.any(String));
  expect(streamResponse.status()).toBe(200);
  expect(streamResponse.headers()['content-type']).toContain('text/event-stream');

  await expect(
    page.getByText('我是你的 AI 内容运营助手，可以协助完成内容与运营相关工作。'),
  ).toBeVisible();
  await page.reload();
  expect(new URL(page.url()).searchParams.get('conversationId')).toBe(conversationId);
  await expect(page.getByText('你是谁', { exact: true })).toBeVisible();
  await expect(
    page.getByText('我是你的 AI 内容运营助手，可以协助完成内容与运营相关工作。'),
  ).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(consoleIssues).toEqual([]);

  await testInfo.attach('刷新恢复后的真实运营助手页面', {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
  await testInfo.attach('真实 Java-Agent 脱敏网络摘要', {
    body: Buffer.from(JSON.stringify(apiRequests, null, 2)),
    contentType: 'application/json',
  });
});
