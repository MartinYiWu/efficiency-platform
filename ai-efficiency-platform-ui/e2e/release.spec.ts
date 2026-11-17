import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { test, expect } from '@playwright/test';

test('生产dist深链接刷新、静态资源与404各有正确响应', async ({ request, page }) => {
  const html = await readFile(resolve('dist/index.html'), 'utf8');
  for (const path of [
    '/',
    '/ai-assistants/hr/positions/backend',
    '/ai-assistants/hr/positions/new/preview',
    '/missing-business-page',
  ]) {
    const response = await request.get(path, { headers: { Accept: 'text/html' } });
    expect(response.status()).toBe(200);
    expect(await response.text()).toBe(html);
    expect(response.headers()['cache-control']).toBe('no-cache');
  }
  const asset = html.match(/src="([^"]+\.js)"/)?.[1];
  expect(asset).toBeTruthy();
  const resource = await request.get(asset!);
  expect(resource.status()).toBe(200);
  expect(resource.headers()['content-type']).toContain('javascript');
  expect(resource.headers()['cache-control']).toContain('immutable');
  const head = await request.head(asset!);
  expect(head.status()).toBe(200);
  expect((await head.body()).byteLength).toBe(0);
  expect((await request.get('/assets/not-found.js')).status()).toBe(404);
  expect((await request.get('/missing.json')).status()).toBe(404);
  const retained = await request.get('/assets/previous-release-chunk.js');
  expect(retained.status()).toBe(200);
  expect(await retained.text()).toBe('export const previousRelease = true;\n');
  expect((await request.get('/%2e%2e%2fpackage.json')).status()).toBe(403);
  expect((await request.post('/index.html', { data: 'not allowed' })).status()).toBe(405);
  const errors: string[] = [];
  const external: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:5193' || url.pathname.startsWith('/api/')) {
      external.push(url.pathname);
      await route.abort();
      return;
    }
    await route.continue();
  });
  await page.goto('/ai-assistants/hr/positions/backend');
  await expect(page.getByTestId('position-detail-page')).toBeVisible();
  await page.reload();
  await expect(page.getByTestId('position-detail-page')).toBeVisible();
  await page.goto('/missing-business-page');
  await expect(page.getByRole('heading', { name: '页面不存在' })).toBeVisible();
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('实际HTTP代理保留方法、路径、查询、正文与错误状态', async ({ request }) => {
  const payload = { title: '中文参数', nested: { version: 2 } };
  const response = await request.patch('/api/__release-probe/echo?revision=2&scope=a%2Fb', {
    data: payload,
  });
  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({
    method: 'PATCH',
    path: '/api/__release-probe/echo?revision=2&scope=a%2Fb',
    body: JSON.stringify(payload),
    contentType: 'application/json',
  });
  const error = await request.post('/api/__release-probe/rejected');
  expect(error.status()).toBe(409);
  expect((await error.json()).code).toBe('RELEASE_PROBE_REJECTED');
  const unconfigured = await request.get(
    'http://127.0.0.1:5198/api/customer-service/conversations',
  );
  expect(unconfigured.status()).toBe(503);
  expect((await unconfigured.json()).code).toBe('RELEASE_API_UNCONFIGURED');
});

test('SSE首块不等待终态且下载响应与文件内容完整保留', async ({ page }) => {
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const response = await fetch('/api/__release-probe/events?afterSequence=1', {
      headers: { 'Last-Event-ID': '1' },
    });
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    const first = await reader.read();
    const firstText = decoder.decode(first.value, { stream: true });
    let rest = '';
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      rest += decoder.decode(chunk.value, { stream: true });
    }
    return { firstText, rest, contentType: response.headers.get('content-type') };
  });
  expect(result.contentType).toContain('text/event-stream');
  expect(result.firstText).toContain('"cursor":"1"');
  expect(result.firstText).not.toContain('event: done');
  expect(result.rest).toContain('event: done');
  const download = await page.request.get('/api/__release-probe/download');
  expect(download.headers()['content-disposition']).toContain('release-result.md');
  expect(await download.text()).toBe('# 已验收\n\n生产代理下载内容。\n');
});
