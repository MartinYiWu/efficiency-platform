import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { expect, test } from './fixtures';
import { installCustomerJourney, source } from './customer-service-journey-fixture';

const evidence = resolve('../docs/verification/2026-11-03-ui-delivery');
const chat = '/ai-assistants/customer-service/chat';

for (const width of [1440, 390]) {
  test(`客服完整事务与刷新持久化 ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const server = await installCustomerJourney(page);
    await mkdir(evidence, { recursive: true });
    await page.goto(chat);
    await expect(page.getByRole('heading', { name: '有什么可以帮你？' })).toBeVisible();
    expect(server.writes()).toHaveLength(0);
    const input = page.getByRole('textbox', { name: '输入问题' });
    await input.fill('如何申请售后？');
    await input.press('Enter');
    await expect(page.getByRole('button', { name: '回答有帮助' })).toBeVisible();
    await expect(
      page.getByRole('log').getByRole('heading', { name: '服务步骤 18', exact: true }),
    ).toBeVisible();
    await page.getByText('处理过程', { exact: true }).click();
    await expect(page.getByText('已检索到售后规范', { exact: true })).toBeVisible();
    const citation = page.getByRole('button', { name: `[1] ${source.documentTitle}`, exact: true });
    await citation.focus();
    await page.keyboard.press('Enter');
    const drawer = page.getByRole('dialog', { name: '引用来源', exact: true });
    await expect(drawer).toContainText(source.quotedText);
    await expect(drawer).toContainText('版本 V3');
    await page.screenshot({ path: resolve(evidence, `customer-service-${width}-citation.png`) });
    await page.keyboard.press('Escape');
    await expect(drawer).toBeHidden();
    await page.getByRole('button', { name: '回答有帮助' }).click();
    await expect(page.getByText('感谢反馈', { exact: true })).toBeVisible();
    expect(server.feedback()).toEqual({ rating: 'UP', reasonCode: null, comment: null });
    if (width === 390) await page.getByRole('button', { name: '历史会话', exact: true }).click();
    await page
      .getByRole('button', { name: '重命名会话：新对话', exact: true })
      .filter({ visible: true })
      .click();
    const modal = page.getByRole('dialog', { name: '重命名会话', exact: true });
    const title = modal.getByRole('textbox', { name: '会话名称' });
    await title.fill('重复名称');
    await title.press('Enter');
    await expect(modal.getByRole('alert')).toContainText('会话名称已存在');
    await expect(title).toHaveValue('重复名称');
    await page.screenshot({
      path: resolve(evidence, `customer-service-${width}-rename-error.png`),
    });
    expect(server.conversations[0].title).toBe('新对话');
    await title.fill('  售后验收记录  ');
    await title.press('Enter');
    await expect(modal).toBeHidden();
    expect(server.conversations[0].title).toBe('售后验收记录');
    if (width === 390) {
      await page
        .getByRole('navigation', { name: '移动端历史会话' })
        .getByRole('button', { name: '售后验收记录', exact: true })
        .click();
      await expect(page.getByRole('navigation', { name: '移动端历史会话' })).toBeHidden();
    }
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      .toBe(true);
    await mkdir(evidence, { recursive: true });
    await page.screenshot({ path: resolve(evidence, `customer-service-${width}.png`) });
    const writes = structuredClone(server.writes());
    expect(writes.map((r) => [r.method, r.status])).toEqual([
      ['POST', 200],
      ['POST', 200],
      ['PUT', 200],
      ['PATCH', 409],
      ['PATCH', 200],
    ]);
    const beforeReload = server.requests.length;
    await page.reload();
    await expect(page.getByRole('button', { name: '回答有帮助' })).toBeVisible();
    await expect(
      page.getByRole('log').getByRole('heading', { name: '服务步骤 18', exact: true }),
    ).toBeVisible();
    if (width === 390) await page.getByRole('button', { name: '历史会话', exact: true }).click();
    await expect(
      page.getByRole('button', { name: '重命名会话：售后验收记录', exact: true }),
    ).toHaveCount(1);
    expect(server.writes()).toEqual(writes);
    expect(server.requests.slice(beforeReload).every((r) => r.method === 'GET')).toBe(true);
    expect(server.requests.slice(beforeReload).map((r) => r.path)).toContain(
      '/api/customer-service/runs/run-1/timeline',
    );
    expect(server.requests.filter((r) => r.path.endsWith('/events'))).toHaveLength(1);
    expect(server.messages).toHaveLength(2);
    expect(server.unknown).toEqual([]);
    await writeFile(
      resolve(evidence, `customer-service-${width}-requests.json`),
      JSON.stringify(server.requests, null, 2),
    );
    await testInfo.attach('request-counts', {
      body: JSON.stringify(server.requests),
      contentType: 'application/json',
    });
  });
}

for (const mode of ['budget', 'stop', 'missing-citation'] as const) {
  test(`客服边界 ${mode} 不假成功不重复提交`, async ({ page }, testInfo) => {
    const server = await installCustomerJourney(page, mode);
    await page.goto(chat);
    await expect(page.getByRole('heading', { name: '有什么可以帮你？' })).toBeVisible();
    await page.getByRole('textbox', { name: '输入问题' }).fill('如何申请售后？');
    await page.getByRole('textbox', { name: '输入问题' }).press('Enter');
    if (mode === 'budget') {
      await expect(page.getByRole('alert')).toContainText('未授权真实预算，已拒绝提交');
      await expect(page.getByRole('button', { name: '回答有帮助' })).toHaveCount(0);
      expect(server.messages).toHaveLength(0);
    } else if (mode === 'stop') {
      await page.getByRole('button', { name: /停止$/ }).click();
      await expect(page.getByText('已停止生成', { exact: true })).toBeVisible();
      expect(server.run.status).toBe('CANCELLED');
      await expect(page.getByRole('button', { name: '回答有帮助' })).toHaveCount(0);
    } else {
      await expect(page.getByRole('button', { name: '回答有帮助' })).toBeVisible();
      await expect(page.getByText(/参考来源/)).toHaveCount(0);
      expect(server.messages[1].citations).toEqual([]);
    }
    const writes = structuredClone(server.writes());
    await page.reload();
    if (mode === 'budget')
      await expect(page.getByRole('heading', { name: '有什么可以帮你？' })).toBeVisible();
    else if (mode === 'stop')
      await expect(page.getByText('已停止生成', { exact: true })).toBeVisible();
    else await expect(page.getByRole('button', { name: '回答有帮助' })).toBeVisible();
    expect(server.writes()).toEqual(writes);
    expect(
      server.requests.filter((r) => r.method === 'POST' && r.path.endsWith('/messages')),
    ).toHaveLength(1);
    expect(server.requests.filter((r) => r.path.endsWith('/cancel'))).toHaveLength(
      mode === 'stop' ? 1 : 0,
    );
    expect(server.unknown).toEqual([]);
    await mkdir(evidence, { recursive: true });
    await writeFile(
      resolve(evidence, `customer-service-${mode}-requests.json`),
      JSON.stringify(server.requests, null, 2),
    );
    await testInfo.attach('requests', {
      body: JSON.stringify(server.requests),
      contentType: 'application/json',
    });
  });
}
