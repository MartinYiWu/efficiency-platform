import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, expect } from './fixtures';
const blocks = [
  {
    id: 'B014',
    page: 2,
    text: '2020.07—2026.06 · 某科技公司\n参与交易平台研发，负责订单与支付模块。',
    section: '工作经历',
  },
  {
    id: 'B018',
    page: 2,
    text: '完成服务限流与降级改造，通过链路追踪定位问题。',
    section: '交易平台服务治理',
  },
  { id: 'B020', page: 2, text: '平台日订单量300万，负责支付模块方案与落地。', section: null },
  {
    id: 'B021',
    page: 2,
    text: '协同6人项目组完成性能优化，推动团队完成稳定性复盘。',
    section: null,
  },
];
const facts = {
  candidateId: 'c1',
  resumeVersionId: 'r2',
  filename: '陈知远_Java后端.pdf',
  pageCount: 3,
  qualityScore: 94,
  status: 'PARSE_REVIEW',
  profile: {
    name: '陈知远',
    education: '本科',
    experienceMonths: 72,
    targetPosition: 'Java后端工程师（P6）',
  },
  blocks,
  fields: [
    {
      id: 'work',
      label: '工作经历',
      value: '2020.07—2026.06 · 某科技公司',
      status: 'CONFIRMED',
      reason: null,
      evidenceIds: ['B014'],
    },
    {
      id: 'scope',
      label: '项目职责边界',
      value: '负责支付模块重构',
      status: 'NEEDS_REVIEW',
      reason: '“负责”未说明方案决策与执行边界。',
      evidenceIds: ['B020'],
    },
    {
      id: 'team',
      label: '团队规模',
      value: '6人',
      status: 'NEEDS_REVIEW',
      reason: '原文为“协同6人项目组”，不能据此认定管理6人。',
      evidenceIds: ['B021'],
    },
  ],
  skills: [
    ['Java', 'STRONG', 4],
    ['Spring Boot', 'STRONG', 3],
    ['MySQL', 'MEDIUM', 2],
    ['Redis', 'MEDIUM', 1],
  ].map(([name, strength, evidenceCount]) => ({
    name,
    strength,
    evidenceCount,
    evidenceIds: ['B014'],
  })),
  confirmedCount: 26,
  totalCount: 28,
  version: 2,
};
const result = {
  resultId: 'm1',
  candidateId: 'c1',
  candidateName: '陈知远',
  positionId: 'p1',
  positionName: 'Java后端工程师（P6）',
  factSnapshotId: 'v2',
  configVersion: 'v1.2',
  contextVersion: 'v2',
  semanticSnapshotId: 's1',
  asOfDate: '2026-11-11',
  businessStatus: 'SCORED',
  scoreStatus: 'FINAL',
  totalScore: 83.5,
  referenceScore: null,
  evidenceCoverage: 100,
  band: 'STRONG_RECOMMEND',
  reasonCodes: [],
  dimensions: [
    ['skills', '技能匹配', 80, 40, 'Java独立交付', 'MATCH', '负责订单与支付模块研发', 'B014'],
    ['experience', '经验匹配', 90, 25, '服务治理经验', 'MATCH', '完成限流与降级改造', 'B018'],
    ['projects', '项目匹配', 80, 25, '业务规模', 'STRONG_MATCH', '日订单量300万', 'B020'],
    ['education', '学历匹配', 80, 5, '项目职责', 'MATCH', '负责支付模块方案与落地', 'B020'],
    ['bonus', '加分项', 100, 5],
  ].map(([id, label, score, weight, requirement, judgment, quote, evidence]) => ({
    id,
    label,
    score,
    weight,
    evidenceCoverage: 100,
    requirements: requirement
      ? [{ id: String(id), label: requirement, judgment, quote, evidenceIds: [evidence] }]
      : [],
  })),
  hardConditions: ['本科及以上', '≥3年相关经验', 'Java项目经验', '工作地域已确认'].map(
    (label, i) => ({
      id: String(i),
      label,
      status: 'PASS',
      expected: '满足',
      actual: '通过',
      overridable: false,
    }),
  ),
  overrides: [],
  snapshotHash: 'sha256:frozen-snapshot',
  createdAt: '2026-11-11T02:32:00Z',
  supersededBy: null,
  highlights: ['核心技术和服务治理经验有原文支持'],
  reviewPoints: [
    '服务治理方案的取舍与降级边界',
    '团队协作中的具体分工与个人贡献',
    '跨服务故障的定位与复盘过程',
  ],
  thresholds: [80, 65, 50],
  pageCount: 3,
  blocks,
};
for (const width of [1440, 1024, 390])
  test(`HR真实合同离线双页 ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1024 });
    await page.route('**/api/hr/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      const data = path.endsWith('/facts')
        ? facts
        : path.endsWith('/matching-results/m1')
          ? result
          : undefined;
      if (data) await route.fulfill({ json: { code: 'SUCCESS', data } });
      else
        await route.fulfill({
          status: 404,
          json: { code: 'HR_NOT_FOUND', message: '离线用例无此对象' },
        });
    });
    const dir = resolve('../docs/verification/2026-11-11-hr/screenshots');
    mkdirSync(dir, { recursive: true });
    await page.goto('/ai-assistants/hr/resumes/candidates/c1/confirm');
    await expect(page.getByRole('heading', { name: '核对解析结果', exact: true })).toBeVisible();
    const resumeTrigger = page.getByRole('button', { name: '在原文中定位 ↗' }).last();
    if (width > 700) await expect(page.getByText('陈知远', { exact: true })).toBeVisible();
    await resumeTrigger.click();
    if (width === 390) {
      const drawer = page.getByRole('dialog', { name: '原文证据' });
      await expect(drawer).toBeVisible();
      await expect(drawer.locator('#evidence-B021')).toHaveClass(/selected/);
      await expect(
        drawer.getByText('协同6人项目组完成性能优化，推动团队完成稳定性复盘。', { exact: true }),
      ).toBeVisible();
      await page.screenshot({ path: resolve(dir, `resume-evidence-${width}.png`), fullPage: true });
      await drawer.getByRole('button', { name: '关闭原文' }).click();
      await expect(drawer).not.toBeVisible();
      await expect(resumeTrigger).toBeFocused();
    } else await expect(page.locator('#source-B021')).toHaveClass(/selected/);
    await expect(page.getByRole('button', { name: '确认并继续匹配' }).first()).toBeDisabled();
    await page.locator('.platform-content').evaluate((element) => element.scrollTo(0, 0));
    await page.screenshot({ path: resolve(dir, `resume-${width}.png`), fullPage: true });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.goto('/ai-assistants/hr/matching/c1?resultId=m1');
    await expect(page.getByText('83.5', { exact: true })).toBeVisible();
    await expect(page.getByText('4 / 4', { exact: true })).toBeVisible();
    const matchTrigger = page.getByRole('button', { name: 'B020 ↗' }).first();
    await matchTrigger.click();
    if (width === 390) {
      const drawer = page.getByRole('dialog', { name: '原文证据' });
      await expect(drawer).toBeVisible();
      await expect(drawer.locator('#evidence-B020')).toHaveClass(/selected/);
      await expect(
        drawer.getByText('平台日订单量300万，负责支付模块方案与落地。', { exact: true }),
      ).toBeVisible();
      await page.screenshot({ path: resolve(dir, `match-evidence-${width}.png`), fullPage: true });
      await drawer.getByRole('button', { name: '关闭原文' }).click();
      await expect(drawer).not.toBeVisible();
      await expect(matchTrigger).toBeFocused();
    } else await expect(page.locator('#match-source-B020')).toHaveClass(/selected/);
    await page.locator('.platform-content').evaluate((element) => element.scrollTo(0, 0));
    await page.screenshot({ path: resolve(dir, `match-${width}.png`), fullPage: true });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  });
