import { expect, test } from '@playwright/test';

const agentBaseUrl = process.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8080';

test('运营助手通过真实 Agent HTTP 与 SSE 完成身份问答', async ({ page }, testInfo) => {
  test.setTimeout(60_000);

  const agentOrigin = new URL(agentBaseUrl).origin;
  const apiRequests: Array<{ method: string; path: string }> = [];
  const consoleIssues: string[] = [];

  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on('request', (request) => {
    const target = new URL(request.url());
    if (target.origin !== agentOrigin) return;
    apiRequests.push({
      method: request.method(),
      path: target.pathname
        .replace(/\/conversations\/[^/]+/, '/conversations/{conversation_id}')
        .replace(/\/runs\/[^/]+/, '/runs/{run_id}'),
    });
  });

  await page.goto('/ai-assistants/operations/chat');
  await page.getByLabel('输入消息').fill('你是谁');

  const submitResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).origin === agentOrigin &&
      /\/v1\/conversations\/[^/]+\/messages$/.test(new URL(response.url()).pathname),
  );
  const streamResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'GET' &&
      new URL(response.url()).origin === agentOrigin &&
      /\/v1\/runs\/[^/]+\/events$/.test(new URL(response.url()).pathname),
  );

  await page.getByRole('button', { name: '发送消息' }).click();
  const [submitResponse, streamResponse] = await Promise.all([
    submitResponsePromise,
    streamResponsePromise,
  ]);
  const submission = (await submitResponse.json()) as {
    contract_version?: string;
    run_id?: string;
    status?: string;
  };

  expect(submitResponse.status()).toBe(201);
  expect(submission).toMatchObject({
    contract_version: 'conversation/1',
    status: 'queued',
  });
  expect(submission.run_id).toEqual(expect.any(String));
  expect(streamResponse.status()).toBe(200);
  expect(streamResponse.headers()['content-type']).toContain('text/event-stream');

  await expect(
    page.getByText('我是你的 AI 内容运营助手，可以协助完成内容与运营相关工作。'),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: '发送消息' })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(apiRequests.filter(({ method }) => method === 'POST' || method === 'GET')).toEqual([
    { method: 'POST', path: '/v1/conversations/{conversation_id}/messages' },
    { method: 'GET', path: '/v1/runs/{run_id}/events' },
  ]);
  expect(consoleIssues).toEqual([]);

  await testInfo.attach('真实 Agent 脱敏网络摘要', {
    body: Buffer.from(JSON.stringify(apiRequests, null, 2)),
    contentType: 'application/json',
  });
});
