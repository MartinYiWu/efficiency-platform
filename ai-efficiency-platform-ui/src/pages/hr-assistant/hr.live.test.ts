import { render, screen, cleanup, fireEvent, within } from '@testing-library/vue';
import { createRouter, createMemoryHistory } from 'vue-router';
import { afterEach, expect, it, vi } from 'vitest';
import ResumeCorrectionPage from './resumes/ResumeCorrectionPage.vue';
import MatchDetailPage from './matching/MatchDetailPage.vue';
import PositionListPage from './positions/PositionListPage.vue';
import MatchResultsPage from './matching/MatchResultsPage.vue';
import HrWorkbenchPage from './workbench/HrWorkbenchPage.vue';
import ResumeUploadPage from './resumes/ResumeUploadPage.vue';
import ResumeProgressPage from './resumes/ResumeProgressPage.vue';
import PositionWizardPage from './positions/PositionWizardPage.vue';
import PositionHardConditionsPage from './positions/PositionHardConditionsPage.vue';
import PositionWeightsPage from './positions/PositionWeightsPage.vue';
import PositionPreviewPage from './positions/PositionPreviewPage.vue';
import PositionDetailPage from './positions/PositionDetailPage.vue';
import FilteredResumesPage from './matching/FilteredResumesPage.vue';
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('失败批次不提供会重置费用计数的无条件重试', async () => {
  const batch = {
    id: 'b1',
    positionId: null,
    mode: 'STORE_ONLY',
    status: 'FAILED',
    version: 2,
    items: [
      {
        id: 'i1',
        filename: '简历.txt',
        status: 'FAILED',
        stage: null,
        candidateId: null,
        errorCode: 'HR_FILE_INVALID',
        message: '材料不可读',
        progress: 0,
      },
    ],
    createdAt: '2026-11-11T00:00:00Z',
    completedCount: 0,
    failedCount: 1,
    reviewCount: 0,
    totalCount: 1,
  };
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: batch }))),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/b/:batchId', component: ResumeProgressPage }],
  });
  await router.push('/b/b1');
  render(ResumeProgressPage, { global: { plugins: [router] } });
  expect(await screen.findByRole('button', { name: '修正材料后重试' })).toBeDisabled();
  expect(
    screen.getByText('只允许修正材料后在原批次额度内重试；原消费与截止时间不会清零。'),
  ).toBeInTheDocument();
});
it('真实放行必须勾选可放行条件并填理由，不可放行项保持锁定', async () => {
  const item = {
    resultId: 'm1',
    candidateId: 'c1',
    candidateName: '候选人',
    positionId: 'p1',
    positionName: '岗位',
    factSnapshotId: 'f1',
    configVersion: 'v1',
    contextVersion: 'v1',
    semanticSnapshotId: null,
    asOfDate: '2026-11-11',
    businessStatus: 'FILTERED',
    scoreStatus: 'NONE',
    totalScore: null,
    referenceScore: null,
    evidenceCoverage: 100,
    band: null,
    reasonCodes: [],
    dimensions: [],
    hardConditions: [
      {
        id: 'r1',
        label: '工作经验',
        status: 'FAIL',
        expected: '36个月',
        actual: '24个月',
        overridable: true,
      },
      {
        id: 'r2',
        label: '必要证书',
        status: 'FAIL',
        expected: '证书',
        actual: '明确无',
        overridable: false,
      },
    ],
    overrides: [],
    snapshotHash: 'hash1',
    createdAt: '2026-11-11T00:00:00Z',
    supersededBy: null,
    highlights: [],
    reviewPoints: [],
    thresholds: [80, 65, 50],
    pageCount: 1,
    blocks: [],
  };
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: { items: [item], total: 1, page: 1, pageSize: 20 },
        }),
      ),
    ),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: FilteredResumesPage }],
  });
  await router.push('/');
  render(FilteredResumesPage, { global: { plugins: [router] } });
  await fireEvent.click(await screen.findByRole('button', { name: '人工放行条件' }));
  const dialog = within(screen.getByRole('dialog'));
  expect(dialog.getByRole('checkbox', { name: '必要证书' })).toBeDisabled();
  const confirm = dialog.getByRole('button', { name: '确认放行并生成新结果' });
  expect(confirm).toBeDisabled();
  await fireEvent.click(dialog.getByRole('checkbox', { name: '工作经验' }));
  await fireEvent.update(dialog.getByLabelText('放行理由'), '已复核相邻领域经历');
  expect(confirm).toBeEnabled();
});
it('被过滤列表仅展示真实快照，不预置失败原因或候选人', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ code: 'SUCCESS', data: { items: [], total: 0, page: 1, pageSize: 20 } }),
        ),
      ),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: FilteredResumesPage }],
  });
  await router.push('/');
  render(FilteredResumesPage, { global: { plugins: [router] } });
  expect(await screen.findByText('当前范围没有被硬条件过滤的简历。')).toBeInTheDocument();
  expect(screen.queryByText('吴磊')).not.toBeInTheDocument();
});
it('岗位详情缺少岗位ID时不能冒用演示配置或历史快照', async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: PositionDetailPage }],
  });
  await router.push('/');
  render(PositionDetailPage, { global: { plugins: [router] } });
  expect(screen.getByText('请从岗位列表选择真实岗位。')).toBeInTheDocument();
  expect(screen.queryByText('Python')).not.toBeInTheDocument();
});
it.each([PositionWizardPage, PositionHardConditionsPage, PositionWeightsPage, PositionPreviewPage])(
  '配置步骤没有岗位草稿时不展示固定技能或预演分数',
  async (component) => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component }],
    });
    await router.push('/');
    render(component, { global: { plugins: [router] } });
    expect(screen.getByText('请先创建岗位，或从岗位列表恢复已有草稿。')).toBeInTheDocument();
    expect(screen.queryByText('Python')).not.toBeInTheDocument();
  },
);
it('恢复runId只GET查询，不POST重发；完成后跳转结果快照', async () => {
  const fetcher = vi.fn().mockImplementation((url: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: url.includes('/matching-runs/')
            ? { runId: 'r1', status: 'SUCCEEDED', resultId: 'm1', failureCode: null }
            : { items: [], total: 0, page: 1, pageSize: 20 },
        }),
      ),
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: MatchResultsPage },
      {
        path: '/ai-assistants/hr/matching/:candidateId',
        component: { template: '<p>结果已定位</p>' },
      },
    ],
  });
  await router.push('/?runId=r1');
  render(MatchResultsPage, { global: { plugins: [router] } });
  await screen.findByText('岗位匹配结果');
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(router.currentRoute.value.query.resultId).toBe('m1');
  expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === 'GET')).toBe(true);
});
it('没有批次ID时不虚构处理进度或触发后台任务', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: ResumeProgressPage }],
  });
  await router.push('/');
  render(ResumeProgressPage, { global: { plugins: [router] } });
  expect(
    screen.getByText('请选择已创建的上传批次，页面不会自动创建或重发任务。'),
  ).toBeInTheDocument();
  expect(fetcher).not.toHaveBeenCalled();
});
it('上传未选文件与未授权时不启动真实批次，也不预置虚构简历', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            code: 'SUCCESS',
            data: url.includes('upload-policy')
              ? {
                  policyVersionId: 'v1',
                  authorizationText: '已取得候选人合法授权',
                  formats: [{ extension: 'txt', available: true, reason: null }],
                }
              : { items: [], total: 0, page: 1, pageSize: 100 },
          }),
        ),
      ),
    ),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: ResumeUploadPage }],
  });
  await router.push('/');
  render(ResumeUploadPage, { global: { plugins: [router] } });
  expect(await screen.findByText('已取得候选人合法授权')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '开始解析' })).toBeDisabled();
  expect(screen.queryByText('张伟_后端开发工程师.pdf')).not.toBeInTheDocument();
});
it('工作台空响应不显示虚构人数或问候身份', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: { metrics: [], todos: [], positions: [], activities: [] },
        }),
      ),
    ),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: HrWorkbenchPage }],
  });
  await router.push('/');
  render(HrWorkbenchPage, { global: { plugins: [router] } });
  expect(await screen.findByText('还没有岗位进展，请先配置并发布岗位。')).toBeInTheDocument();
  expect(screen.queryByText('47')).not.toBeInTheDocument();
});
it('匹配列表空响应不伪造候选人或已匹配统计', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ code: 'SUCCESS', data: { items: [], total: 0, page: 1, pageSize: 20 } }),
        ),
      ),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: MatchResultsPage }],
  });
  await router.push('/');
  render(MatchResultsPage, { global: { plugins: [router] } });
  expect(
    await screen.findByText('暂无匹配结果，请先选择已发布岗位并完成解析。'),
  ).toBeInTheDocument();
  expect(screen.queryByText('张伟')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '调整权重重算' })).toBeDisabled();
});
it('岗位列表读取分页HTTP，空数据不展示示例岗位统计', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      new Response(
        JSON.stringify({ code: 'SUCCESS', data: { items: [], total: 0, page: 1, pageSize: 20 } }),
      ),
    );
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: PositionListPage }],
  });
  await router.push('/');
  render(PositionListPage, { global: { plugins: [router] } });
  expect(await screen.findByText('暂无岗位，请新建岗位并完成规则配置。')).toBeInTheDocument();
  expect(screen.queryByText('后端开发工程师')).not.toBeInTheDocument();
  expect(fetcher).toHaveBeenCalled();
});
it.each([ResumeCorrectionPage, MatchDetailPage])(
  '没有目标对象时明确空态，不呈现虚构招聘信息',
  async (component) => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component }],
    });
    await router.push('/');
    render(component, { global: { plugins: [router] } });
    expect(screen.getByText(/请选择/)).toBeInTheDocument();
    expect(screen.queryByText('张伟')).not.toBeInTheDocument();
  },
);
it('解析事实来自HTTP并按原文块定位，确认必须等待后端响应', async () => {
  const facts = {
    candidateId: 'c1',
    resumeVersionId: 'r1',
    filename: '真实.pdf',
    pageCount: 3,
    qualityScore: 90,
    status: 'PARSE_REVIEW',
    profile: {
      name: '陈知远',
      education: '本科',
      experienceMonths: 72,
      targetPosition: 'Java后端工程师',
    },
    blocks: [
      { id: 'B014', page: 2, text: '负责支付模块重构，日订单量300万。', section: '项目经历' },
    ],
    fields: [
      {
        id: 'scope',
        label: '项目职责边界',
        value: '负责支付模块重构',
        status: 'NEEDS_REVIEW',
        reason: '负责未说明具体边界',
        evidenceIds: ['B014'],
      },
    ],
    skills: [],
    confirmedCount: 26,
    totalCount: 28,
    version: 1,
  };
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: facts })));
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/c/:candidateId', component: ResumeCorrectionPage }],
  });
  await router.push('/c/c1');
  render(ResumeCorrectionPage, { global: { plugins: [router] } });
  expect(await screen.findByText('陈知远', { selector: 'h2' })).toBeInTheDocument();
  expect(fetcher.mock.calls[0][0]).toBe('/api/hr/candidates/c1/facts');
  expect(screen.getAllByRole('button', { name: '确认并继续匹配' })[0]).toBeDisabled();
  await fireEvent.click(screen.getByRole('button', { name: '在原文中定位 ↗' }));
  expect(document.getElementById('source-B014')).toHaveClass('selected');
});
it('匹配详情按真实快照展示83.5五维公式、100覆盖和4项硬通过', async () => {
  const result = {
    resultId: 'm1',
    candidateId: 'c1',
    candidateName: '陈知远',
    positionId: 'p1',
    positionName: 'Java后端工程师（P6）',
    factSnapshotId: 'f2',
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
      ['skills', '技能匹配', 80, 40],
      ['experience', '经验匹配', 90, 25],
      ['projects', '项目匹配', 80, 25],
      ['education', '学历匹配', 80, 5],
      ['bonus', '加分项', 100, 5],
    ].map(([id, label, score, weight]) => ({
      id,
      label,
      score,
      weight,
      evidenceCoverage: 100,
      requirements: [],
    })),
    hardConditions: ['本科以上', '3年相关经验', 'Java项目经验', '工作地域已确认'].map(
      (label, index) => ({
        id: String(index),
        label,
        status: 'PASS',
        actual: '通过',
        expected: '满足',
        overridable: false,
      }),
    ),
    overrides: [],
    snapshotHash: 'sha256:abc',
    createdAt: '2026-11-11T02:32:00Z',
    supersededBy: null,
    highlights: [],
    reviewPoints: ['服务治理方案的边界'],
    thresholds: [80, 65, 50],
    pageCount: 3,
    blocks: [],
  };
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: result }))),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/m/:candidateId', component: MatchDetailPage }],
  });
  await router.push('/m/c1?resultId=m1');
  render(MatchDetailPage, { global: { plugins: [router] } });
  expect(await screen.findByText('陈知远 · 岗位匹配分析')).toBeInTheDocument();
  expect(screen.getByText('83.5', { selector: '.score strong' })).toBeInTheDocument();
  expect(screen.getByText('4 / 4')).toBeInTheDocument();
  expect(screen.getByText('强烈推荐面试')).toBeInTheDocument();
  expect(screen.queryByText('sha256:abc')).not.toBeInTheDocument();
});
