import { test, expect } from './fixtures';
import { fileName, fileText, installKnowledgeJourney } from './knowledge-journey-fixture';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

for (const width of [1440, 390]) {
  test(`知识中心完整上传发布与索引回滚事务 ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const state = await installKnowledgeJourney(page);
    await page.goto('/knowledge-center/knowledge-bases');
    await page.getByRole('button', { name: /新建知识库$/ }).click();
    const drawer = page.locator('.ant-drawer-content').filter({ hasText: '新建知识库' });
    await expect(drawer.getByRole('button', { name: 'Close' })).toBeInViewport();
    await drawer.getByRole('button', { name: /^创\s*建$/ }).click();
    await expect(drawer.getByText('请输入名称')).toBeVisible();
    expect(state.requests.filter((x) => x === 'POST /api/knowledge/bases')).toHaveLength(0);
    await drawer.getByRole('textbox', { name: '名称' }).fill('事务验收产品库');
    await drawer.getByRole('textbox', { name: '编码' }).fill('journey');
    await drawer.getByLabel('描述', { exact: true }).fill('完整业务事务离线验收');
    await drawer.locator('.ant-select-selector').click();
    await page.getByTitle('产品文档', { exact: true }).click();
    await drawer.getByRole('button', { name: /^创\s*建$/ }).click();
    await expect(page).toHaveURL(/knowledge-bases\/journey$/);
    await expect(page.getByRole('heading', { name: '事务验收产品库' })).toBeVisible();
    await expect(page.getByRole('button', { name: '上传文档', exact: true })).toBeDisabled();
    await page.getByRole('button', { name: '启用知识库' }).click();
    await expect(page.getByRole('button', { name: '上传文档', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: '新建目录', exact: true }).click();
    const modal = page.getByRole('dialog', { name: '新建目录' });
    await modal.getByLabel('目录名称').fill('产品说明');
    await modal.getByRole('button', { name: '确 定' }).click();
    await expect(page.getByText('目录冲突，请确认后重试')).toBeVisible();
    await expect(modal.getByLabel('目录名称')).toHaveValue('产品说明');
    await expect(modal.getByRole('button', { name: '确 定' })).toBeEnabled();
    expect(
      state.requests.filter((x) => x === 'POST /api/knowledge/bases/journey/directories'),
    ).toHaveLength(1);
    await modal.getByRole('button', { name: '确 定' }).click();
    await expect(modal).not.toBeVisible();
    await page.getByRole('button', { name: '上传文档', exact: true }).click();
    const upload = page.locator('.ant-drawer-content').filter({ hasText: '上传文档' });
    await expect(upload.getByRole('button', { name: 'Close' })).toBeInViewport();
    await upload.locator('.evidence-mode .ant-select-selector').click();
    await page.getByTitle('允许叙述性原文节选', { exact: true }).click();
    await upload.locator('.ant-select-selector').nth(1).click();
    await page.getByTitle('/产品说明', { exact: true }).click();
    await upload.locator('.ant-drawer-title').click();
    await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);
    const chooser = page.waitForEvent('filechooser');
    await upload.getByText('拖拽文件到这里，或点击选择').click();
    await (
      await chooser
    ).setFiles({ name: fileName, mimeType: 'text/markdown', buffer: Buffer.from(fileText) });
    await expect(upload.getByTitle(fileName, { exact: true })).toBeVisible();
    await expect(upload.locator('.ant-upload-list-item')).toHaveCSS('opacity', '1');
    const evidenceDir = resolve('../docs/verification/2026-11-03-ui-delivery');
    await mkdir(evidenceDir, { recursive: true });
    await page.screenshot({
      path: resolve(evidenceDir, `knowledge-upload-${width}.png`),
      fullPage: true,
    });
    await upload.getByRole('button', { name: '开始处理' }).click();
    const batch = page.getByRole('dialog', { name: '批量导入' });
    await expect(batch.getByRole('button', { name: /^关\s*闭$/ })).toBeInViewport();
    await expect(batch.getByText('RUNNING', { exact: true })).toBeVisible();
    await expect(batch.getByText('成功 1，失败 0，共 1')).toBeVisible();
    await batch.getByRole('button', { name: /^关\s*闭$/ }).click();
    await page.getByRole('button', { name: /^查\s*看$/ }).click();
    await expect(page.getByText('冻结证据模式：允许叙述性原文节选')).toBeVisible();
    await expect(page.getByText('待发布', { exact: true }).first()).toBeVisible();
    await page.getByRole('button', { name: '处理任务 100%' }).click();
    const task = page.locator('.ant-drawer-content').filter({ hasText: '执行次数' });
    await expect(task.getByText('SUCCEEDED', { exact: true })).toBeVisible();
    await expect(task.getByRole('button', { name: 'Close' })).toBeInViewport();
    await task.getByRole('button', { name: 'Close' }).click();
    await page.getByRole('button', { name: /^发\s*布$/ }).click();
    await expect(page.getByRole('button', { name: /^发\s*布$/ })).toHaveCount(0);
    await page.reload();
    await expect(page.getByText('已发布', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('冻结证据模式：允许叙述性原文节选')).toBeVisible();
    expect(state.getDocument()?.currentPublishedVersionId).toBe('version-1');
    await page.screenshot({
      path: resolve(evidenceDir, `knowledge-published-${width}.png`),
      fullPage: true,
    });
    await page.getByRole('button', { name: '返回知识库', exact: true }).click();
    await expect(page.getByText('release-2', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '回滚到此版本' }).click();
    await expect(page.getByText('release-1', { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText('release-1', { exact: true })).toBeVisible();
    expect(state.getBase()?.currentIndexReleaseId).toBe('release-1');
    expect(state.unexpected).toEqual([]);
    expect(state.requests.filter((x) => x.startsWith('POST'))).toHaveLength(6);
  });
}
