import { writeFile } from 'node:fs/promises';
import { test, expect, type Page } from './fixtures';
import {
  managementFixture,
  draftInput,
  importedCase,
  frozenInput,
} from './management-journey-fixture';
const evidence = '../docs/verification/2026-11-03-ui-delivery';
async function fillVersion(page: Page) {
  for (const [label, value] of [
    ['版本号', draftInput.semanticVersion],
    ['Graph Key', draftInput.graphKey],
    ['Graph 版本', draftInput.graphVersion],
    ['变更说明', draftInput.changeSummary],
  ])
    await page.getByLabel(label, { exact: true }).fill(value!);
}
async function dataset(page: Page) {
  await page.goto('/ai-center/rag-evaluations');
  await page.getByRole('button', { name: '新建数据集' }).click();
  await page.getByLabel('名称', { exact: true }).fill('离线事务数据集');
  await page.getByLabel('说明', { exact: true }).fill('有状态模拟');
  await expect(page.getByRole('button', { name: /^创\s*建$/ })).toBeInViewport();
  await expect(
    page.getByRole('dialog').getByRole('button', { name: /Cancel|取\s*消/ }),
  ).toBeInViewport();
  await page.getByRole('button', { name: /^创\s*建$/ }).click();
  await page.getByRole('button', { name: '查看用例' }).click();
  await page.getByRole('button', { name: '批量导入' }).click();
  await page.getByLabel('JSON 用例', { exact: true }).fill('invalid');
  await page.getByRole('button', { name: /^导\s*入$/ }).click();
  await expect(page.getByLabel('JSON 用例', { exact: true })).toHaveValue('invalid');
  await page.getByLabel('JSON 用例', { exact: true }).fill(JSON.stringify([importedCase]));
  await page.getByRole('button', { name: /^导\s*入$/ }).click();
  await expect(page.getByText(importedCase.question, { exact: true })).toBeVisible();
}
async function select(page: Page, label: string, option: string) {
  await page.getByLabel(label, { exact: true }).click();
  await page.locator('.ant-select-item-option-content').getByText(option, { exact: true }).click();
}
async function prepareRun(page: Page) {
  await page.getByRole('button', { name: '发起评测', exact: true }).click();
  await select(page, 'ACTIVE Agent 版本', 'av · dev');
  await select(page, 'PUBLISHED RAG 策略', 'offline-rag · 1');
  await select(page, '知识库 1', '离线制度库');
  await select(page, '索引发布版本', '1 · PUBLISHED');
}
test('Agent 草稿创建、审核与刷新持久化；预算拒绝保留输入', async ({ page }) => {
  const state = await managementFixture(page);
  await page.goto('/ai-center/agents/a');
  await page.getByRole('button', { name: '新建版本' }).click();
  await fillVersion(page);
  state.rejectVersion = true;
  await page.getByRole('button', { name: /^确\s*定$/ }).click();
  await expect(page.getByText('离线预算拒绝：未授权')).toBeVisible();
  await expect(page.getByLabel('版本号', { exact: true })).toHaveValue('1.0.1');
  await expect.poll(() => state.writes.length).toBe(1);
  state.rejectVersion = false;
  await page.getByRole('button', { name: /^确\s*定$/ }).click();
  await page.getByRole('button', { name: '提交审核' }).click();
  await expect(page.getByRole('row').filter({ hasText: '1.0.1' })).toContainText('READY');
  await page.reload();
  await expect(page.getByRole('row').filter({ hasText: '1.0.1' })).toContainText('READY');
  expect(state.writes).toHaveLength(3);
  await writeFile(
    `${evidence}/management-agent-requests.json`,
    JSON.stringify(state.writes, null, 2),
  );
  await page.screenshot({ path: `${evidence}/management-agent.png`, fullPage: true });
});
test('Prompt 指定 USER 编辑保留 SYSTEM/ASSISTANT 与变量，重新读取持久内容', async ({ page }) => {
  const state = await managementFixture(page);
  await page.goto('/ai-center/prompts?agentId=a');
  await page.getByRole('button', { name: '创建草稿并编辑' }).click();
  await select(page, '消息角色', '用户提示词（USER）');
  await page.getByLabel('消息正文').fill('USER 已编辑 {{question}}');
  await page.getByRole('button', { name: '保存草稿' }).click();
  await expect(page.getByText('Prompt 草稿已保存')).toBeVisible();
  expect(state.messages.map((m) => m.contentTemplate)).toEqual([
    'SYSTEM 原始 {{question}}',
    'USER 已编辑 {{question}}',
    'ASSISTANT 原始 {{question}}',
  ]);
  expect(state.variables).toHaveLength(1);
  await page.reload();
  await expect(page.getByText('选择 Prompt 后创建独立草稿版本')).toBeVisible();
  const persisted = await page.evaluate(
    async () => (await (await fetch('/api/aihub/prompts/versions/pv')).json()).data,
  );
  expect(persisted.messages).toEqual(state.messages);
  expect(persisted.variables).toEqual(state.variables);
  expect(state.writes.filter((w) => w.method === 'PUT')).toHaveLength(1);
  await writeFile(
    `${evidence}/management-prompt-requests.json`,
    JSON.stringify({ writes: state.writes, persisted }, null, 2),
  );
});
test('数据集导入、事实等价绑定编辑、冻结版本模拟评测至终态与引用', async ({ page }) => {
  const state = await managementFixture(page);
  await dataset(page);
  await page.getByRole('button', { name: /^编\s*辑$/ }).click();
  await page.getByLabel('必须事实（每行一条）').fill('保留事实\n新增事实');
  await page.getByRole('button', { name: /^保\s*存$/ }).click();
  await expect(page.getByLabel('必须事实（每行一条）')).not.toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: /^编\s*辑$/ }).click();
  await expect(page.getByLabel('必须事实（每行一条）')).toHaveValue('保留事实\n新增事实');
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  expect(state.cases[0]!.expectedFactAlternatives).toEqual({ 保留事实: ['保留同义'] });
  await prepareRun(page);
  await page.getByRole('button', { name: /^开\s*始$/ }).click();
  await expect(page).toHaveURL(/\/runs\/run$/);
  await expect(page.getByRole('button', { name: '查看事实' })).toBeVisible();
  expect(state.runReads).toBeGreaterThanOrEqual(2);
  expect(state.run).toMatchObject({ ...frozenInput, status: 'SUCCEEDED', passedCount: 1 });
  await page.reload();
  await expect(page.getByText('kb / index', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '查看事实' }).click();
  await expect(page.getByText('离线模拟回答', { exact: true })).toBeVisible();
  await expect(page.getByText('离线冻结引文', { exact: true })).toBeVisible();
  await writeFile(
    `${evidence}/management-evaluation-requests.json`,
    JSON.stringify(
      { writes: state.writes, cases: state.cases, run: state.run, runReads: state.runReads },
      null,
      2,
    ),
  );
  await page.screenshot({ path: `${evidence}/management-result.png`, fullPage: true });
});
test('390px Modal/Drawer 操作可达，评测预算拒绝不重复提交并保留冻结参数', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await managementFixture(page);
  await dataset(page);
  await page.getByRole('button', { name: '新增用例' }).click();
  await expect(
    page.locator('.ant-drawer-content:visible').getByRole('button', { name: /^保\s*存$/ }),
  ).toBeInViewport();
  await expect(page.getByRole('button', { name: 'Close', exact: true })).toBeInViewport();
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await prepareRun(page);
  state.rejectRun = true;
  await expect(page.getByRole('button', { name: /^开\s*始$/ })).toBeInViewport();
  await page.getByRole('button', { name: /^开\s*始$/ }).click();
  await expect(page.getByText('离线预算拒绝：未授权')).toBeVisible();
  await expect(page.locator('.ant-drawer-content:visible')).toContainText('av · dev');
  await expect(page.locator('.ant-drawer-content:visible')).toContainText('offline-rag · 1');
  await page.screenshot({ path: `${evidence}/management-mobile-budget.png`, fullPage: true });
  await page.getByRole('button', { name: 'Close', exact: true }).click();
  await page.reload();
  expect(state.writes.filter((w) => w.path.endsWith('/runs'))).toEqual([
    { method: 'POST', path: '/api/aihub/rag-evaluations/runs', body: frozenInput },
  ]);
  await writeFile(
    `${evidence}/management-budget-requests.json`,
    JSON.stringify(state.writes, null, 2),
  );
});
