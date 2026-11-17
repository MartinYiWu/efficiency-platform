import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

const referenceRoot = process.env.UI_REFERENCE_ROOT ?? resolve('e2e/reference-ui');
const evidenceRoot = resolve('../docs/verification/2026-11-03-ui-style-parity');
const properties = [
  'color',
  'backgroundColor',
  'backgroundImage',
  'borderTopColor',
  'borderTopWidth',
  'borderTopStyle',
  'borderRadius',
  'boxShadow',
  'fontFamily',
  'fontSize',
  'fontWeight',
  'lineHeight',
  'paddingTop',
  'paddingRight',
  'paddingBottom',
  'paddingLeft',
  'height',
  'opacity',
  'cursor',
  'outlineColor',
  'outlineStyle',
  'outlineWidth',
  'backdropFilter',
];
const selectors = [
  'body',
  '#primary-control',
  '#default-control',
  '#dashed-control',
  '#text-control',
  '#disabled-control',
  '#danger-control',
  '#small-control',
  '#input-control',
  '#select-control .ant-select-selector',
  '#number-control .ant-input-number',
  '#checkbox-control .ant-checkbox-inner',
  '#switch-control',
  '#radio-control .ant-radio-inner',
  '#tag-control',
  '#tag-blue-control',
  '#tag-success-control',
  '#card-control',
  '#card-control .ant-card-head',
  '#card-control .ant-card-head-title',
  '#card-control .ant-card-body',
  '#section-control',
  '#metric-control',
  '#metric-control .v1-metric-icon',
  '#table-control .ant-table',
  '#table-control th',
  '#table-control td',
  '#tabs-control .ant-tabs-tab-active .ant-tabs-tab-btn',
];
async function installReference(page: Page) {
  for (const file of ['design-system.css', 'v1-tokens.css', 'v1-layout.css', 'v1-components.css'])
    await page.addStyleTag({
      content: await readFile(resolve(referenceRoot, 'src/styles', file), 'utf8'),
    });
  const index = await readFile(resolve(referenceRoot, 'src/styles/index.css'), 'utf8');
  await page.addStyleTag({ content: index.replace(/^@import[^;]+;|^@tailwind[^;]+;/gm, '') });
}
async function styles(page: Page, targets = selectors) {
  return page.evaluate(
    ({ targets, properties }) =>
      Object.fromEntries(
        targets.map((selector) => {
          const element = document.querySelector(selector);
          if (!element) throw new Error(`Missing specimen ${selector}`);
          const style = getComputedStyle(element);
          return [
            selector,
            Object.fromEntries(
              properties.map((property) => [
                property,
                style.getPropertyValue(
                  property.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`),
                ),
              ]),
            ),
          ];
        }),
      ),
    { targets, properties },
  );
}

test('按钮、输入、标签、卡片、表格、弹窗及状态与旧版实际设计相同', async ({
  page,
  context,
  baseURL,
}) => {
  test.setTimeout(90_000);
  const reference = await context.newPage();
  await reference.setViewportSize({ width: 1440, height: 1200 });
  await page.setViewportSize({ width: 1440, height: 1200 });
  await reference.goto(`${baseURL}/e2e/theme-specimen.html?reference=1`);
  await expect(reference.locator('html')).toHaveAttribute('data-specimen-ready', 'true');
  await installReference(reference);
  await page.goto('/e2e/theme-specimen.html');
  await expect(page.locator('html')).toHaveAttribute('data-specimen-ready', 'true');
  await mkdir(evidenceRoot, { recursive: true });
  const before = { reference: await styles(reference), candidate: await styles(page) };
  await writeFile(resolve(evidenceRoot, 'computed-controls.json'), JSON.stringify(before, null, 2));
  for (const selector of selectors)
    expect.soft(before.candidate[selector], selector).toEqual(before.reference[selector]);
  for (const target of [
    '#primary-control',
    '#default-control',
    '#card-control',
    '#table-control td',
  ]) {
    await reference.locator(target).first().hover();
    await page.locator(target).first().hover();
    await page.waitForTimeout(350);
    expect
      .soft((await styles(page, [target]))[target], `${target}:hover`)
      .toEqual((await styles(reference, [target]))[target]);
  }
  await reference.locator('#input-control').focus();
  await page.locator('#input-control').focus();
  await page.waitForTimeout(250);
  expect
    .soft((await styles(page, ['#input-control']))['#input-control'], '输入焦点')
    .toEqual((await styles(reference, ['#input-control']))['#input-control']);
  await reference.getByRole('button', { name: '打开弹窗' }).click();
  await page.getByRole('button', { name: '打开弹窗' }).click();
  await page.waitForTimeout(350);
  const modalSelectors = [
    '.ant-modal-content',
    '.ant-modal-header',
    '.ant-modal-title',
    '.ant-modal-body',
    '.ant-modal-footer .ant-btn-primary',
  ];
  const modalReference = await styles(reference, modalSelectors),
    modalCandidate = await styles(page, modalSelectors);
  for (const selector of modalSelectors)
    expect.soft(modalCandidate[selector], selector).toEqual(modalReference[selector]);
  await reference.screenshot({ path: resolve(evidenceRoot, 'reference-modal.png') });
  await page.screenshot({ path: resolve(evidenceRoot, 'candidate-modal.png') });
  await reference.getByRole('button', { name: /取\s*消/ }).click();
  await page.getByRole('button', { name: /取\s*消/ }).click();
  await page.waitForTimeout(350);
  await reference
    .locator('#theme-specimen')
    .screenshot({ path: resolve(evidenceRoot, 'reference-controls.png') });
  await page
    .locator('#theme-specimen')
    .screenshot({ path: resolve(evidenceRoot, 'candidate-controls.png') });
  const dashedReference = await styles(reference, ['#dashed-control']);
  await page.route('**/api/hr/positions/theme-parity/draft', (route) =>
    route.fulfill({
      json: {
        code: 'SUCCESS',
        data: {
          positionId: 'theme-parity',
          name: '主题对照岗位',
          family: 'TECHNOLOGY',
          departmentId: 'offline',
          level: 'P6',
          jdText: '',
          lastStep: 'SOFT_REQUIREMENTS',
          scoring: null,
          draftScoring: null,
          hardConditions: [],
          criteria: [],
          version: 1,
        },
      },
    }),
  );
  await page.goto('/ai-assistants/hr/positions/new/soft-requirements?positionId=theme-parity');
  await expect(
    page.getByRole('heading', { name: '软性要求', level: 1, exact: true }),
  ).toBeVisible();
  const customButton = page.getByRole('button', { name: /添加评分要求$/ });
  const customStyle = await customButton.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      color: style.color,
      borderTopColor: style.borderTopColor,
      borderRadius: style.borderRadius,
      backgroundColor: style.backgroundColor,
    };
  });
  for (const property of ['color', 'borderTopColor', 'borderRadius', 'backgroundColor'])
    expect
      .soft(customStyle[property as keyof typeof customStyle], `业务添加技能按钮 ${property}`)
      .toBe(dashedReference['#dashed-control'][property]);
  await writeFile(
    resolve(evidenceRoot, 'comparison-summary.json'),
    JSON.stringify(
      {
        referenceRoot,
        defaultTargets: selectors.length,
        propertiesPerTarget: properties.length,
        statePropertyComparisons:
          selectors.length * properties.length +
          4 * properties.length +
          properties.length +
          modalSelectors.length * properties.length +
          4,
        modes: ['default', 'hover', 'focus', 'disabled', 'modal', 'actual-business-dashed-button'],
        actualBusinessButton: customStyle,
        referenceBusinessButton: dashedReference['#dashed-control'],
      },
      null,
      2,
    ),
  );
  await reference.close();
});
