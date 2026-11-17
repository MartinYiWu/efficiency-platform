import type { Page } from '@playwright/test';
export function hrFixtureResponse(path: string) {
  if (path === '/api/hr/workbench')
    return {
      metrics: ['新增简历', '完成匹配', '生成面试题', '待处理事项'].map((label, i) => ({
        key: String(i),
        label,
        value: 0,
        comparisonText: '离线受控数据',
      })),
      todos: [],
      positions: [],
      activities: [],
    };
  if (path === '/api/hr/templates' || path === '/api/hr/interview-templates') return [];
  if (path === '/api/hr/candidates' || path === '/api/hr/audit-events')
    return { items: [], total: 0, page: 1, pageSize: 20 };
  if (path === '/api/hr/interview-assignments/assignment-1/view')
    return {
      setId: 'offline-set',
      version: 1,
      positionName: '离线面试岗位',
      questions: [],
      resumeSections: [],
      disclaimer: '仅供面试参考',
    };
  if (path === '/api/hr/positions' || path === '/api/hr/matching-results')
    return { items: [], total: 0, page: 1, pageSize: 20 };
  if (path === '/api/hr/settings/upload-policy')
    return {
      policyVersionId: 'offline-policy',
      authorizationText: '离线测试采集政策',
      formats: [{ extension: 'txt', available: true, reason: null }],
    };
  if (path === '/api/hr/positions/backend' || path === '/api/hr/positions/position-1')
    return {
      id: 'backend',
      tenantId: 'test',
      name: '离线岗位',
      family: 'TECHNOLOGY',
      departmentId: 'd1',
      level: 'P6',
      code: 'TEST',
      status: 'DRAFT',
      configVersion: null,
      contextVersion: 'v1',
      createdBy: 'fixture',
      createdAt: '2026-11-11T00:00:00Z',
      version: 1,
    };
  return undefined;
}
export async function installHrEmptyFixture(page: Page) {
  await page.route('**/api/hr/**', async (route) => {
    const data = hrFixtureResponse(new URL(route.request().url()).pathname);
    await route.fulfill(
      data === undefined
        ? { status: 404, json: { code: 'HR_NOT_FOUND', message: '离线测试未创建此业务对象' } }
        : { json: { code: 'SUCCESS', data } },
    );
  });
}
