import { expect, test } from '@playwright/test';

test('uses the HR workbench as the sole root entry', async ({ page }) => {
  await page.goto('/');

  await expect(page).toHaveURL(/\/ai-assistants\/hr\/workbench$/);
  await expect(page.getByRole('heading', { name: '工作台' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'AI 人事助手导航' })).toBeVisible();
  await expect(page.getByText('首页概览')).toHaveCount(0);
});

test('keeps the single navigation responsive across desktop, tablet and mobile', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  await expect(page.getByRole('navigation', { name: 'AI 人事助手导航' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: /岗位管理/ })).toBeVisible();
  await expect
    .poll(() =>
      page.locator('main').evaluate((element) => Math.round(element.getBoundingClientRect().width)),
    )
    .toBeGreaterThanOrEqual(1180);

  await page.setViewportSize({ width: 1024, height: 900 });
  await expect(page.getByRole('menuitem', { name: /岗位管理/ })).toBeVisible();
  await page.getByRole('button', { name: '收合左侧导航' }).click();
  await expect(page.getByRole('button', { name: '展开左侧导航' })).toBeVisible();
  await page.getByRole('button', { name: '展开左侧导航' }).click();
  await expect(page.getByRole('menuitem', { name: /岗位管理/ })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: '打开人事助手导航' })).toBeVisible();
  await page.getByRole('button', { name: '打开人事助手导航' }).click();
  await expect(page.getByRole('dialog')).toContainText('AI 人事助手');
});

test('keeps the HR workbench inside the responsive viewport', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 900 });
  await page.goto('/ai-assistants/hr/workbench');

  await expect(page.getByRole('heading', { name: '工作台' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'AI 人事助手导航' })).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator('[aria-label="快捷入口"]')
        .evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(' ').length),
    )
    .toBe(2);
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
});

test('keeps the resume upload workspace compact without a scrolling settings column', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 900 });
  await page.goto('/ai-assistants/hr/resumes/upload');
  await expect.poll(() => page.evaluate(() => window.innerWidth)).toBe(1920);

  const settingsPanel = page.getByRole('complementary', { name: '上传配置' });
  const uploadPanel = page.getByRole('region', { name: '上传方式' });
  const actionBar = page.locator('footer[aria-label="上传操作"]');

  await expect(settingsPanel).toBeVisible();
  await expect(uploadPanel).toBeVisible();
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
    .toBeGreaterThanOrEqual(1050);
  await expect
    .poll(() =>
      actionBar.evaluate((element) => element.getBoundingClientRect().bottom <= window.innerHeight),
    )
    .toBe(true);
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
  await page.getByText('处理设置', { exact: true }).click();
  await expect(page.getByRole('switch', { name: '自动去重' })).toBeVisible();
  await page.waitForTimeout(350);
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
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight))
    .toBe(true);
});

test('uses the available workspace width and renders every position configuration tab', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 900 });
  await page.goto('/ai-assistants/hr/positions/backend');

  const detailPage = page.getByTestId('position-detail-page');
  await expect(detailPage).toBeVisible();
  await expect
    .poll(() => detailPage.evaluate((element) => Math.round(element.getBoundingClientRect().width)))
    .toBeGreaterThanOrEqual(1600);

  await page.getByRole('tab', { name: '硬性条件' }).click();
  await expect(page.getByRole('heading', { name: '一票否决条件' })).toBeVisible();
  await expect(page.getByText('允许人工放行').first()).toBeVisible();

  await page.getByRole('tab', { name: '软性要求' }).click();
  await expect(page.getByRole('heading', { name: '核心技能与重要度' })).toBeVisible();
  await expect(page.getByText('软性要求仅影响得分，不构成否决。')).toBeVisible();

  await page.getByRole('tab', { name: '权重与分档' }).click();
  await expect(page.getByText('合计 100%')).toBeVisible();
  await expect(page.getByRole('heading', { name: '岗位族权重参考' })).toBeVisible();
  await page.getByRole('button', { name: '换一个示例' }).click();
  await expect(page.getByText('76.3', { exact: true })).toBeVisible();

  await page.getByRole('tab', { name: '版本记录' }).click();
  await expect(page.getByRole('heading', { name: '配置版本历史' })).toBeVisible();
  await page.getByRole('button', { name: '查看差异' }).first().click();
  await expect(page.getByRole('dialog', { name: '版本差异' })).toBeVisible();
  await page.getByRole('button', { name: '关闭' }).click();

  await page.setViewportSize({ width: 1280, height: 900 });
  await expect
    .poll(() =>
      page
        .locator('[data-testid="position-detail-page"] aside')
        .first()
        .evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(' ').length),
    )
    .toBe(1);

  await page.setViewportSize({ width: 390, height: 844 });
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
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/ai-assistants/operations/chat');

  const composer = page.locator('footer[aria-label="消息输入"]');
  const input = page.getByRole('textbox', { name: '输入消息' });
  await expect(page.getByRole('heading', { name: 'AI 内容运营助手' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'AI 内容运营助手导航' })).toBeVisible();
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
