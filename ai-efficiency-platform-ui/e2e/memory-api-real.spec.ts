import { expect, test, type BrowserContext, type Page, type Response } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const enabled = process.env.MEMORY_UI_INTEGRATION_ENABLED === '1';
test.skip(!enabled, 'Explicit isolated Java/MySQL integration gate is required');

interface Preference {
  id: string;
  fieldKey: string;
  value: string;
  revision: number;
  versionId: string;
}
interface Envelope<T> {
  code: string;
  data: T;
}
const fields = [
  {
    key: 'response.language',
    label: '回复语言',
    value: 'en-US',
    text: '英语',
  },
  {
    key: 'response.detail_level',
    label: '详细程度',
    value: 'detailed',
    text: '详细',
  },
  {
    key: 'response.format',
    label: '回复格式',
    value: 'table',
    text: '表格',
  },
] as const;
const apiPaths =
  /^\/api\/aihub\/(memories(?:\/[^/]+(?:\/corrections)?)?|memory-deletions(?:\/[^/]+)?|memory-suppressions\/[^/]+\/reauthorizations)$/;

test('actual browser private preferences persist across sessions, isolate actors and stop at real pending deletion', async ({
  browser,
  baseURL,
  request,
}) => {
  if (!baseURL) throw new Error('Memory UI integration base URL is required');
  const evidence = resolve('../.local-acceptance/agent-memory-implementation/green/D14API-browser');
  const rejected: string[] = [];
  const requests: { method: string; path: string }[] = [];
  const contexts: BrowserContext[] = [];
  const results: {
    topAgent: string;
    items: { id: string; fieldKey: string; revision: number; versionId: string }[];
    jobId: string;
    deletionStatus: string;
  }[] = [];
  async function actorContext(token: string) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    contexts.push(context);
    await context.addInitScript((accessToken) => {
      window.__memoryAcceptanceToken = accessToken;
    }, token);
    await context.route('**/*', async (route) => {
      const request = route.request(),
        target = new URL(request.url());
      const allowed =
        target.origin === baseURL &&
        (!target.pathname.startsWith('/api/') || apiPaths.test(target.pathname));
      if (!allowed) {
        rejected.push(`${request.method()} ${target.pathname}`);
        await route.abort('blockedbyclient');
        return;
      }
      if (target.pathname.startsWith('/api/'))
        requests.push({ method: request.method(), path: target.pathname });
      await route.continue();
    });
    return context;
  }
  function responseFor(page: Page, method: string, path: string) {
    return page.waitForResponse(
      (response) =>
        response.request().method() === method && new URL(response.url()).pathname === path,
    );
  }
  async function accepted<T>(response: Response): Promise<T> {
    expect(response.status()).toBe(200);
    const envelope = (await response.json()) as Envelope<T>;
    expect(envelope.code).toBe('SUCCESS');
    return envelope.data;
  }
  async function select(page: Page, id: string, text: string) {
    await page
      .locator('.ant-select')
      .filter({ has: page.locator(`#${id}`) })
      .click();
    await page
      .locator('.ant-select-dropdown:visible .ant-select-item-option')
      .filter({ hasText: new RegExp(`^${text}$`) })
      .click();
  }
  function centerUrl(agent: string, sessionId: string) {
    return `/e2e/memory-api-host.html?${new URLSearchParams({ topAgent: agent, sessionId })}`;
  }
  try {
    await mkdir(evidence, { recursive: true });
    const actorA = await actorContext(process.env.MEMORY_UI_ACCESS_TOKEN!);
    const actorB = await actorContext(process.env.MEMORY_UI_OTHER_ACCESS_TOKEN!);
    const page = await actorA.newPage();
    const other = await actorB.newPage();
    for (const [agent, session, nextSession] of [
      [
        'operations',
        process.env.MEMORY_UI_OPERATIONS_SESSION_ID!,
        process.env.MEMORY_UI_OPERATIONS_NEW_SESSION_ID!,
      ],
      [
        'customer-service',
        process.env.MEMORY_UI_CUSTOMER_SERVICE_SESSION_ID!,
        process.env.MEMORY_UI_CUSTOMER_SERVICE_NEW_SESSION_ID!,
      ],
    ]) {
      let read = responseFor(page, 'GET', '/api/aihub/memories');
      await page.goto(centerUrl(agent!, session!));
      const initial = await accepted<{ items: Preference[] }>(await read);
      expect(initial.items.length).toBe(0);
      const created: Preference[] = [];
      for (const field of fields) {
        const cancel = page.getByRole('button', { name: '取消更正' });
        if (await cancel.count()) await cancel.click();
        await select(page, 'memory-field', field.label);
        await select(page, 'memory-value', field.text);
        const write = responseFor(page, 'POST', '/api/aihub/memories');
        await page.getByRole('button', { name: '保存偏好', exact: true }).click();
        const saved = await accepted<Preference>(await write);
        expect(saved.fieldKey).toBe(field.key);
        expect(saved.value).toBe(field.value);
        created.push(saved);
        await expect(
          page
            .locator('tr')
            .filter({ hasText: field.label })
            .getByText(field.text, { exact: true }),
        ).toBeVisible();
      }
      read = responseFor(page, 'GET', '/api/aihub/memories');
      await page.reload();
      const reloaded = await accepted<{ items: Preference[] }>(await read);
      expect(reloaded.items.map((entry) => [entry.fieldKey, entry.value]).sort()).toEqual(
        fields.map((field) => [field.key, field.value]).sort(),
      );
      read = responseFor(page, 'GET', '/api/aihub/memories');
      await page.goto(centerUrl(agent!, nextSession!));
      const acrossSessions = await accepted<{ items: Preference[] }>(await read);
      expect(acrossSessions.items.map((entry) => entry.id).sort()).toEqual(
        created.map((entry) => entry.id).sort(),
      );
      const forbidden = responseFor(other, 'GET', '/api/aihub/memories');
      await other.goto(centerUrl(agent!, session!));
      expect((await forbidden).status()).toBe(403);
      await expect(other.getByText('无权查看当前记忆或来源')).toBeVisible();
      await expect(other.getByRole('button', { name: '更正', exact: true })).toHaveCount(0);
      const privateRead = responseFor(other, 'GET', '/api/aihub/memories');
      await other.goto(`/e2e/memory-api-host.html?topAgent=${agent}`);
      expect((await accepted<{ items: Preference[] }>(await privateRead)).items.length).toBe(0);
      const language = created.find((entry) => entry.fieldKey === 'response.language')!;
      const row = page.locator('tr').filter({ hasText: '回复语言' });
      await row.getByRole('button', { name: /^更\s*正$/ }).click();
      await select(page, 'memory-value', '简体中文');
      const correction = responseFor(
        page,
        'POST',
        `/api/aihub/memories/${language.id}/corrections`,
      );
      await page.getByRole('button', { name: '保存更正' }).click();
      const corrected = await accepted<Preference>(await correction);
      expect(corrected.revision).toBe(language.revision + 1);
      expect(corrected.value).toBe('zh-CN');
      const detailRead = responseFor(page, 'GET', `/api/aihub/memories/${language.id}`);
      await row.getByRole('link', { name: '详情与来源' }).click();
      const detail = await accepted<{ preference: Preference; history: Preference[] }>(
        await detailRead,
      );
      expect(detail.preference.value).toBe('zh-CN');
      expect(detail.history.map((version) => version.value)).toContain('en-US');
      await expect(page.getByRole('heading', { name: '版本记录' })).toBeVisible();
      await page.screenshot({
        path: resolve(evidence, `${agent}-actual-history.png`),
        fullPage: true,
      });
      await page.getByRole('button', { name: /^忘\s*记$/ }).click();
      const forget = responseFor(page, 'POST', '/api/aihub/memory-deletions');
      await page.getByRole('button', { name: '确认忘记' }).click();
      const task = await accepted<{
        jobId: string;
        status: string;
        jobStatus: string;
        completedTargets: number;
        requiredTargets: number;
      }>(await forget);
      expect(task.status).toBe('DELETE_PENDING');
      expect(task.jobStatus).not.toBe('SUCCEEDED');
      expect(task.completedTargets).toBeLessThan(task.requiredTargets);
      await expect(page.getByRole('heading', { name: '版本记录' })).toHaveCount(0);
      await expect(page.getByText('简体中文', { exact: true })).toHaveCount(0);
      await expect(page.getByRole('button', { name: '重新允许记住', exact: true })).toHaveCount(0);
      const postsBefore = requests.filter((entry) => entry.method === 'POST').length;
      const jobRead = responseFor(page, 'GET', `/api/aihub/memory-deletions/${task.jobId}`);
      await page.getByRole('button', { name: '刷新清理状态' }).click();
      const currentTask = await accepted<typeof task>(await jobRead);
      expect(currentTask.status).toBe('DELETE_PENDING');
      expect(currentTask.jobStatus).not.toBe('SUCCEEDED');
      expect(requests.filter((entry) => entry.method === 'POST').length).toBe(postsBefore);
      await page.screenshot({
        path: resolve(evidence, `${agent}-actual-pending.png`),
        fullPage: true,
      });
      results.push({
        topAgent: agent!,
        items: created.map(({ id, fieldKey, revision, versionId }) => ({
          id,
          fieldKey,
          revision,
          versionId,
        })),
        jobId: task.jobId,
        deletionStatus: currentTask.status,
      });
    }
    const beforeRevocation = responseFor(page, 'GET', '/api/aihub/memories');
    await page.goto(
      `${centerUrl('operations', process.env.MEMORY_UI_OPERATIONS_NEW_SESSION_ID!)}&jobId=${encodeURIComponent(results[0]!.jobId)}`,
    );
    expect((await accepted<{ items: Preference[] }>(await beforeRevocation)).items.length).toBe(2);
    await expect(page.getByRole('region', { name: '偏好遗忘任务' })).toBeVisible();
    await page
      .locator('tr')
      .filter({ hasText: '详细程度' })
      .getByRole('button', { name: /^更\s*正$/ })
      .click();
    await select(page, 'memory-value', '简洁');
    const revocation = await request.post(
      new URL('/__memory-ui/revoke', process.env.MEMORY_UI_API_BASE_URL!).href,
      { headers: { Authorization: `Bearer ${process.env.MEMORY_UI_ACCESS_TOKEN}` } },
    );
    expect([200, 204]).toContain(revocation.status());
    const expired = responseFor(page, 'GET', '/api/aihub/memories');
    await page.getByRole('button', { name: '重新加载', exact: true }).click();
    expect((await expired).status()).toBe(401);
    await expect(page.getByText('请先登录后管理记忆')).toBeVisible();
    await expect(page.getByRole('region', { name: '偏好遗忘任务' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '取消更正' })).toHaveCount(0);
    await expect(page.getByText('用户明确设置', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^更\s*正$/ })).toHaveCount(0);
    await page.screenshot({
      path: resolve(evidence, 'actual-revoked-credential.png'),
      fullPage: true,
    });
    expect(
      await page.evaluate(() => Object.keys(localStorage).filter((key) => /memory/i.test(key))),
    ).toEqual([]);
    expect(rejected).toEqual([]);
    await writeFile(
      resolve(evidence, 'browser-result.json'),
      JSON.stringify(
        {
          verificationLayer: 'actual browser HTTP to isolated Java/MySQL; pending cleanup only',
          actors: 2,
          agents: results,
          credentialRevocationVerified: true,
          browserStorageEmpty: true,
          blockedRequests: rejected.length,
          requestCounts: {
            get: requests.filter((entry) => entry.method === 'GET').length,
            post: requests.filter((entry) => entry.method === 'POST').length,
          },
          fullAgentCleanupVerified: false,
          productionLoginHostDelivered: false,
        },
        null,
        2,
      ),
    );
  } finally {
    await Promise.allSettled(contexts.map((context) => context.close()));
  }
});
