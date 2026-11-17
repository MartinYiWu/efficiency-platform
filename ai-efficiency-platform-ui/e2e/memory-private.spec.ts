import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { test, expect } from './fixtures';

const evidence = resolve('../.local-acceptance/agent-memory-implementation/green/D14F-layout');
const preference = {
  id: 'offline-memory',
  versionId: 'offline-v1',
  topAgent: 'operations',
  fieldKey: 'response.language',
  value: 'zh-CN',
  revision: 1,
  status: 'ACTIVE',
  sourceType: 'USER_PREFERENCE_DECISION',
  sourceRef: 'offline-decision',
  expiresAt: '2026-12-01T00:00:00Z',
};
for (const width of [1440, 1024, 390]) {
  test(`离线HTTP Fixture记忆中心与详情 ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const writes: string[] = [];
    let currentPreference = preference;
    let reads = 0;
    const deletionCalls: string[] = [];
    const deletion = {
      jobId: 'offline-job',
      itemId: 'offline-memory',
      status: 'DELETE_PENDING',
      jobStatus: 'BLOCKED',
      revision: 2,
      deletionEpoch: 1,
      suppressionId: 'offline-suppression',
      suppressionRevision: 1,
      requiredTargets: 6,
      completedTargets: 0,
    };
    await page.route('**/api/aihub/memory-deletions**', async (route) => {
      const method = route.request().method();
      deletionCalls.push(method);
      const data =
        method === 'GET' && currentPreference.revision === 3
          ? {
              ...deletion,
              status: 'LIVE',
              jobStatus: 'SUCCEEDED',
              completedTargets: 6,
              revision: 3,
            }
          : method === 'GET' && ++reads >= 2
            ? { ...deletion, status: 'DELETED', jobStatus: 'SUCCEEDED', completedTargets: 6 }
            : deletion;
      await route.fulfill({ json: { code: 'SUCCESS', data } });
    });
    await page.route('**/api/aihub/memory-suppressions/**', async (route) => {
      expect(route.request().method()).toBe('POST');
      expect(route.request().postDataJSON()).toMatchObject({
        confirmation: 'ALLOW_REMEMBER',
        expectedRevision: 2,
        expected_suppression_revision: 1,
        fieldKey: 'response.language',
        value: 'en-US',
      });
      currentPreference = {
        ...preference,
        versionId: 'new-version',
        revision: 3,
        value: 'en-US',
        sourceRef: 'offline-new-decision',
      };
      await route.fulfill({ json: { code: 'SUCCESS', data: currentPreference } });
    });
    await page.route('**/api/aihub/memories**', async (route) => {
      const request = route.request(),
        url = new URL(request.url());
      expect(request.headers().authorization).toBe('Bearer offline-layout-fixture');
      if (request.method() !== 'GET') {
        writes.push(request.method());
        await route.fulfill({
          status: 409,
          json: { code: 'MEMORY_REVISION_CONFLICT', data: null, traceId: 'offline-409' },
        });
        return;
      }
      const topAgent = url.searchParams.get('topAgent');
      const detail = url.pathname.endsWith('/offline-memory');
      await route.fulfill({
        json: {
          code: 'SUCCESS',
          data: detail
            ? { preference: currentPreference, history: [currentPreference] }
            : {
                items: topAgent === 'operations' ? [currentPreference] : [],
                total: topAgent === 'operations' ? 1 : 0,
                page: 1,
                pageSize: 20,
              },
          traceId: 'offline-layout',
        },
      });
    });
    await page.goto(
      '/e2e/memory-fixture.html?topAgent=operations&sessionId=offline-business-session',
    );
    await expect(page.getByRole('heading', { name: '记忆中心', exact: true })).toBeVisible();
    await expect(page.getByText('版本 1', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '跨 Agent 共享' })).toBeDisabled();
    await expect(page.getByRole('button', { name: /忘\s*记/ })).toBeEnabled();
    await page.getByRole('button', { name: /更\s*正/, exact: true }).click();
    await page.getByRole('button', { name: '保存更正' }).click();
    await expect(page.getByText(/版本冲突/)).toBeVisible();
    await expect(page.getByText('偏好已保存')).toHaveCount(0);
    for (const text of ['回复语言', '用户明确设置', '版本 1']) {
      const item = page.getByText(text, { exact: text !== '用户明确设置' }).first();
      await item.scrollIntoViewIfNeeded();
      await expect(item).toBeInViewport();
    }
    await page.getByRole('heading', { name: '记忆中心', exact: true }).scrollIntoViewIfNeeded();
    await expect(page.getByRole('heading', { name: '记忆中心', exact: true })).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await mkdir(evidence, { recursive: true });
    await page.screenshot({ path: resolve(evidence, `center-${width}.png`), fullPage: true });
    if (width === 390)
      await page.locator('aside.ui-card').screenshot({ path: resolve(evidence, 'form-390.png') });
    await page.getByRole('link', { name: '详情与来源' }).click();
    await expect(page.getByText('offline-decision', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '版本记录' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: resolve(evidence, `detail-${width}.png`), fullPage: true });
    expect(writes).toEqual(['POST']);
    await page.getByRole('button', { name: /^忘\s*记$/ }).click();
    await expect(page.getByRole('heading', { name: '忘记并停止自动记住此偏好' })).toBeVisible();
    await page.getByRole('button', { name: '确认忘记' }).click();
    const panel = page.getByRole('region', { name: '偏好遗忘任务' });
    await expect(panel.getByText('清理中，尚未全部确认')).toBeVisible();
    await expect(page.getByText('offline-decision', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '重新允许记住', exact: true })).toHaveCount(0);
    await panel.screenshot({ path: resolve(evidence, `pending-${width}.png`) });
    await page.getByRole('button', { name: '刷新清理状态' }).click();
    await expect(panel.getByText('清理暂时受阻，请稍后刷新状态。')).toBeVisible();
    await page.getByRole('button', { name: '刷新清理状态' }).click();
    await expect(panel.getByRole('heading', { name: '已清理', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '重新允许记住', exact: true })).toBeDisabled();
    await page.getByLabel('重新授权的字段').click();
    await page
      .locator('.ant-select-dropdown:visible .ant-select-item-option')
      .filter({ hasText: '回复语言' })
      .click();
    await page
      .locator('.ant-select')
      .filter({ has: page.getByLabel('新的偏好值') })
      .click();
    await page
      .locator('.ant-select-dropdown:visible .ant-select-item-option')
      .filter({ hasText: '英语' })
      .click();
    await panel.getByRole('heading', { name: '重新允许记住', exact: true }).click();
    await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '重新允许记住', exact: true })).toBeEnabled();
    await panel.screenshot({ path: resolve(evidence, `reauthorize-${width}.png`) });
    await page.getByRole('button', { name: '重新允许记住', exact: true }).click();
    await expect(page.getByText('offline-new-decision', { exact: true })).toBeVisible();
    await expect(page.getByText('offline-decision', { exact: true })).toHaveCount(0);
    expect(deletionCalls).toEqual(['POST', 'GET', 'GET']);
    if (width === 390) {
      await page.goto('/e2e/memory-fixture.html?topAgent=operations&jobId=offline-job');
      await expect(page.getByText('该次清理已完成，偏好已重新设置')).toBeVisible();
      await expect(page.getByRole('button', { name: '重新允许记住', exact: true })).toHaveCount(0);
      await page
        .getByRole('region', { name: '偏好遗忘任务' })
        .screenshot({ path: resolve(evidence, 'historical-job-390.png') });
      expect(deletionCalls).toEqual(['POST', 'GET', 'GET', 'GET']);
    }
    expect(
      await page.evaluate(() => Object.keys(localStorage).filter((key) => /memory/i.test(key))),
    ).toEqual([]);
  });
}
test('真实入口无凭据时零发送，并说明HR TASK_ONLY', async ({ page }) => {
  await page.goto('/ai-center/memories?topAgent=hr');
  await expect(page.getByText('请先登录后管理记忆')).toBeVisible();
  await expect(page.getByRole('button', { name: '保存偏好' })).toBeDisabled();
  await expect(page.getByText(/TASK_ONLY/)).toBeVisible();
  await expect(page.getByRole('log')).toHaveCount(0);
  await page.goto('/e2e/memory-api-host.html?topAgent=hr');
  await expect(page.getByText('接口联验宿主 · 非生产登录')).toBeVisible();
  await expect(page.getByText('请先登录后管理记忆')).toBeVisible();
  await expect(page.getByRole('button', { name: '保存偏好' })).toBeDisabled();
});
