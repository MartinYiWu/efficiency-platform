import { installHrEmptyFixture } from './hr-empty-fixture';
import { envelope, installOperationConversation, queuedRun } from './operations-fixture';
import { expect, test } from './fixtures';

test.beforeEach(async ({ page }) => installHrEmptyFixture(page));

test('uses the HR workbench as the sole root entry', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveURL(/\/ai-assistants\/hr\/workbench$/);
  await expect(page.getByRole('heading', { name: '招聘工作台' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: '平台主导航' })).toBeVisible();
  await expect(page.getByText('首页概览')).toHaveCount(0);
});

test('keeps the single navigation responsive across desktop, tablet and mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  await expect(page.getByRole('navigation', { name: '平台主导航' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: '岗位管理', exact: true })).toBeVisible();
  await expect
    .poll(() =>
      page
        .getByRole('main')
        .evaluate((element) => Math.round(element.getBoundingClientRect().width)),
    )
    .toBeGreaterThanOrEqual(1210);

  await page.setViewportSize({ width: 1024, height: 900 });
  await expect(page.getByRole('button', { name: '折叠侧栏' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: '岗位管理', exact: true })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: '打开平台导航' })).toBeVisible();
  await page.getByRole('button', { name: '打开平台导航' }).click();
  await expect(page.getByRole('dialog')).toContainText('岗位管理');
});

test('keeps the HR workbench inside the responsive viewport', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 900 });
  await page.goto('/ai-assistants/hr/workbench');

  await expect(page.getByRole('heading', { name: '招聘工作台' })).toBeVisible();
  await expect(page.getByRole('button', { name: '打开平台导航' })).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator('[aria-label="招聘概览"]')
        .evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(' ').length),
    )
    .toBe(2);
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
});

test('keeps the resume upload panels readable and the action bar reachable', async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 900 });
  await page.goto('/ai-assistants/hr/resumes/upload');
  await expect.poll(() => page.evaluate(() => window.innerWidth)).toBe(1920);

  const settingsPanel = page.getByRole('complementary', { name: '上传配置' });
  const uploadPanel = page.getByRole('region', { name: '上传方式' });
  const actionBar = page.locator('footer[aria-label="上传操作"]');

  await expect(settingsPanel).toBeVisible();
  await expect(uploadPanel).toBeVisible();
  await actionBar.scrollIntoViewIfNeeded();
  await expect(actionBar).toBeVisible();
  await expect
    .poll(() =>
      settingsPanel.evaluate((element) => {
        const styles = getComputedStyle(element);
        return styles.overflowY === 'hidden' && element.scrollHeight <= element.clientHeight;
      }),
    )
    .toBe(true);
  await expect
    .poll(() =>
      settingsPanel.evaluate((element) => Math.round(element.getBoundingClientRect().width)),
    )
    .toBeGreaterThanOrEqual(570);
  await expect
    .poll(() =>
      uploadPanel.evaluate((element) => Math.round(element.getBoundingClientRect().width)),
    )
    .toBeGreaterThanOrEqual(800);
  await expect(actionBar).toBeInViewport();
  await expect
    .poll(async () => {
      const panelBottom = await settingsPanel.evaluate(
        (element) => element.getBoundingClientRect().bottom,
      );
      const actionBarTop = await actionBar.evaluate(
        (element) => element.getBoundingClientRect().top,
      );
      return panelBottom <= actionBarTop;
    })
    .toBe(true);
  await expect(page.getByRole('button', { name: '开始解析' })).toBeDisabled();
  await expect(page.getByLabel('选择简历文件')).toBeEnabled();
});

test('reads a real position state without inventing published snapshots', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1024 });
  await page.goto('/ai-assistants/hr/positions/backend');
  await expect(page.getByRole('heading', { name: '离线岗位' })).toBeVisible();
  await expect(page.getByText('暂无已发布配置，请继续填写草稿。')).toBeVisible();
  await expect(page.getByRole('button', { name: '编辑岗位草稿' })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
});

test('keeps the HR chat composer visible and sends typed text', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/ai-assistants/hr/chat');

  const composer = page.locator('footer[aria-label="消息输入"]');
  const input = page.getByRole('textbox', { name: '输入消息' });
  await expect(page.getByRole('heading', { name: 'AI 人事助手' })).toBeVisible();
  await expect(composer).toBeVisible();
  await expect
    .poll(() =>
      composer.evaluate((element) => element.getBoundingClientRect().bottom <= window.innerHeight),
    )
    .toBe(true);

  await input.fill('请帮我汇总候选人的项目经历');
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect(page.getByText('请帮我汇总候选人的项目经历')).toBeVisible();
  await expect(page.getByLabel(/语音输入|表情|添加附件/)).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
});

test('keeps the operations chat composer visible and sends typed text', async ({ page }) => {
  await installOperationConversation(page);
  await page.route('**/api/operations/conversations/*/messages', async (route) => {
    await route.fulfill({ json: envelope(queuedRun('conversation-fixture', 'run-1')) });
  });
  await page.route('**/api/operations/runs/run-1/events?*', async (route) => {
    await route.fulfill({
      contentType: 'text/event-stream',
      body: 'id: 1\nevent: stream_done\ndata: {"contract_version":"run.stream.event/1","event":"stream_done","run_id":"run-1","sequence":1,"payload":{"status":"succeeded","degraded":false}}\n\n',
    });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/ai-assistants/operations/chat');

  const composer = page.locator('footer[aria-label="消息输入"]');
  const input = page.getByRole('textbox', { name: '输入消息' });
  await expect(page.getByRole('heading', { name: 'AI 内容运营助手' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: '平台主导航' })).toBeVisible();
  await expect(composer).toBeVisible();
  await expect
    .poll(() =>
      composer.evaluate((element) => element.getBoundingClientRect().bottom <= window.innerHeight),
    )
    .toBe(true);

  await input.fill('请给我三个新品发布选题');
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect(page.getByText('请给我三个新品发布选题')).toBeVisible();
  await expect(page.getByLabel(/语音输入|表情|添加附件/)).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
});

test('shows the not found page for an unknown route', async ({ page }) => {
  await page.goto('/missing');

  await expect(page.getByRole('heading', { name: '页面不存在' })).toBeVisible();
});
