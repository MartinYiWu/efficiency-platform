import { test, expect } from './fixtures';
const question = {
  id: 'q1',
  layer: 1,
  title: '请说明项目中的职责边界与取舍',
  purpose: '核验已记录事实',
  answerPoints: ['依据材料说明'],
  followUps: ['哪些决策由您负责？'],
  references: {
    excellent: '给出可核验案例',
    qualified: '说明职责',
    needsVerification: '进一步核实',
  },
  sourceType: 'RESUME_VERIFY',
  sourceIds: ['b1'],
  minutes: 5,
  dimension: null,
};
const template = {
  id: 't1',
  departmentId: null,
  name: '技术研发系统模板',
  family: 'TECHNOLOGY',
  system: true,
  status: 'PUBLISHED',
  weights: { SKILL: 40, EXPERIENCE: 25, PROJECT: 25, EDUCATION: 5, BONUS: 5 },
  hardConditions: [],
  criteria: [],
  version: 1,
  sourceTemplateId: null,
  sourceVersion: null,
};
for (const width of [1440, 1024, 390])
  test(`HR补全页面离线三宽 ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown;
      if (path.includes('/hr/templates')) data = [template];
      else if (path.includes('/interview-assignments/'))
        data = {
          setId: 's1',
          version: 1,
          positionName: '合成验收岗位',
          questions: [question],
          disclaimer: '仅供面试参考',
          totalScore: 99,
          candidatePhone: '13812345678',
        };
      else if (path.endsWith('/preview'))
        data = {
          setId: 's1',
          version: 1,
          positionName: '合成验收岗位',
          questions: [question],
          disclaimer: '仅供面试参考',
        };
      else if (path.includes('/interview-sets/'))
        data = {
          id: 's1',
          candidateId: 'c1',
          positionId: 'p1',
          version: 1,
          status: 'READY',
          targetMinutes: 45,
          estimatedMinutes: 5,
          questions: [question],
          insufficientLayers: [],
          createdAt: '2026-11-11T00:00:00Z',
        };
      else if (path.includes('/hr/candidates'))
        data = {
          items: [
            {
              candidateId: 'c1',
              name: '合成验收候选人',
              education: '本科',
              experienceMonths: 36,
              skills: ['Java'],
              updatedAt: '2026-11-11T00:00:00Z',
              expiresAt: '2027-01-01T00:00:00Z',
              olderThan30Days: false,
              expiringWithin30Days: false,
            },
          ],
          total: 1,
          page: 1,
          pageSize: 20,
        };
      else if (path.includes('/audit-events'))
        data = { items: [], total: 0, page: 1, pageSize: 20 };
      else {
        await route.abort();
        return;
      }
      await route.fulfill({ json: { code: 'SUCCESS', data } });
    });
    for (const [url, title] of [
      ['talent', '人才库'],
      ['positions/templates', '岗位模板库'],
      ['interviews/questions?questionSetId=s1', '面试题集'],
      ['interviews/guide?questionSetId=s1', '面试提纲 · A4预览'],
      ['interviews/assigned/a1', '面试官提纲'],
      ['settings/audit', '审计日志'],
    ] as const) {
      await page.goto(`/ai-assistants/hr/${url}`);
      await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
      await expect(page.getByText('演示数据', { exact: false })).toHaveCount(0);
      if (url.includes('assigned')) {
        await expect(page.getByText('合成验收岗位', { exact: true })).toBeVisible();
        await expect(page.getByText('13812345678')).toHaveCount(0);
        await expect(page.getByText('99', { exact: true })).toHaveCount(0);
      }
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
      ).toBe(true);
      await page.screenshot({
        path: `../.local-acceptance/hr-completion-20261111/ui-${url.split(/[/?]/)[0]}-${width}.png`,
        fullPage: true,
      });
    }
  });
