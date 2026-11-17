import { render, screen, cleanup, waitFor } from '@testing-library/vue';
import { afterEach, expect, it, vi } from 'vitest';
import { createRouter, createMemoryHistory } from 'vue-router';
import TalentSearchPage from './talent/TalentSearchPage.vue';
import PositionTemplateLibraryPage from './positions/PositionTemplateLibraryPage.vue';
import AuditPage from './settings/AuditPage.vue';
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it.each([
  [TalentSearchPage, '暂无符合条件的授权人才。', { items: [], total: 0, page: 1, pageSize: 20 }],
  [PositionTemplateLibraryPage, '暂无可访问模板。', []],
  [AuditPage, '暂无可访问的审计事件。', { items: [], total: 0, page: 1, pageSize: 20 }],
] as const)('真实空响应不显示演示招聘数据', async (component, empty, data) => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data }))),
  );
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component }],
  });
  await router.push('/');
  render(component, { global: { plugins: [router] } });
  await waitFor(() => expect(screen.getByText(empty)).toBeInTheDocument());
  expect(screen.queryByText(/演示数据/)).not.toBeInTheDocument();
});
import { fireEvent } from '@testing-library/vue';
import SkillSynonymPage from './settings/SkillSynonymPage.vue';
import InterviewAssignedPage from './interviews/InterviewAssignedPage.vue';
import InterviewGeneratePage from './interviews/InterviewGeneratePage.vue';
import HrTrialPanel from '../../features/hr-trials/HrTrialPanel.vue';
import { criterionSchema } from '../../features/hr-position-draft/model';
it('词典版本冲突不弹保存成功且保留输入', async () => {
  const fetcher = vi.fn().mockImplementation((_url: string, init?: RequestInit) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          init?.method === 'PUT'
            ? { code: 'HR_VERSION_CONFLICT', message: '版本冲突，请重新读取' }
            : {
                code: 'SUCCESS',
                data: { departmentId: 'd1', version: 3, status: 'DRAFT', entries: [] },
              },
        ),
        { status: init?.method === 'PUT' ? 409 : 200 },
      ),
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: SkillSynonymPage }],
  });
  await router.push('/');
  render(SkillSynonymPage, { global: { plugins: [router] } });
  await fireEvent.update(screen.getByLabelText('配置部门ID'), 'd1');
  await fireEvent.click(screen.getByRole('button', { name: '读取配置' }));
  await screen.findByText('暂无词条，请添加或导入并预检。');
  await fireEvent.click(screen.getByRole('button', { name: '新增词条' }));
  await fireEvent.update(screen.getByLabelText('标准名'), '离线技能');
  await fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() => expect(screen.getByText('版本冲突，请重新读取')).toBeInTheDocument());
  expect(screen.getByLabelText('标准名')).toHaveValue('离线技能');
  expect(screen.queryByText('草稿已保存。')).not.toBeInTheDocument();
  expect(JSON.parse(fetcher.mock.calls.at(-1)![1]!.body as string).expectedVersion).toBe(3);
});
it('面试官视图丢弃额外评分和联系字段且只GET指派', async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        code: 'SUCCESS',
        data: {
          setId: 's1',
          version: 1,
          positionName: '测试岗位',
          questions: [],
          disclaimer: '仅供面试参考',
          totalScore: 99,
          candidatePhone: '13812345678',
          band: '强烈推荐',
        },
      }),
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/assigned/:assignmentId', component: InterviewAssignedPage }],
  });
  await router.push('/assigned/a1');
  render(InterviewAssignedPage, { global: { plugins: [router] } });
  await waitFor(() => expect(screen.getByText('测试岗位')).toBeInTheDocument());
  expect(document.body.textContent).not.toContain('13812345678');
  expect(document.body.textContent).not.toContain('强烈推荐');
  expect(fetcher.mock.calls[0]![0]).toBe('/api/hr/interview-assignments/a1/view');
  expect(fetcher.mock.calls[0]![1]?.method).toBeUndefined();
});
it('面试生成参数缺失时不调用付费接口', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: InterviewGeneratePage }],
  });
  await router.push('/');
  render(InterviewGeneratePage, { global: { plugins: [router] } });
  expect(screen.getByRole('button', { name: '确认参数并生成' })).toBeDisabled();
  expect(fetcher).not.toHaveBeenCalled();
});
it('盲标前系统标签不泄漏且不展示虚构一致率', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: [
            {
              id: 't1',
              positionId: 'p1',
              departmentId: 'd1',
              sampleSize: 10,
              actualSize: 1,
              seed: 1,
              snapshotHash: 'h',
              version: 1,
              status: 'WAITING_LABELS',
              results: [
                { candidateId: 'c1', status: 'SCORED', label: null, score: null, coverage: null },
              ],
              labels: [],
              diagnosis: null,
              agreement: null,
              verified: false,
            },
          ],
        }),
      ),
    ),
  );
  render(HrTrialPanel, { props: { positionId: 'p1', positionVersion: 1 } });
  await fireEvent.click(await screen.findByRole('button', { name: 't1 · WAITING_LABELS' }));
  expect(screen.getByText('一致率：有效双标样本不足，不计算')).toBeInTheDocument();
  expect(screen.queryByText(/^系统分档 /)).not.toBeInTheDocument();
});
it('确定性子规则通过Zod保留而非保存时丢失', () => {
  const value = criterionSchema.parse({
    id: 'r1',
    label: '月数',
    dimension: 'EXPERIENCE',
    criterion: '要求36个月',
    strongAnchor: '',
    matchAnchor: '',
    partialAnchor: '',
    notMetAnchor: '',
    critical: false,
    calculation: {
      type: 'EXPERIENCE_MONTHS',
      minimum: 36,
      maximum: null,
      expected: 36,
      metric: null,
      unit: 'MONTH',
    },
  });
  expect(value.calculation?.expected).toBe(36);
});
import InterviewQuestionSetPage from './interviews/InterviewQuestionSetPage.vue';
it('题集编辑保存新版本携带expectedVersion且不触发重新生成', async () => {
  const set = {
    id: 's1',
    candidateId: 'c1',
    positionId: 'p1',
    version: 2,
    status: 'READY',
    targetMinutes: 45,
    estimatedMinutes: 0,
    questions: [],
    insufficientLayers: [],
    createdAt: '2026-11-11T00:00:00Z',
  };
  const fetcher = vi.fn().mockImplementation((_url: string, init?: RequestInit) =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data:
            init?.method === 'PUT'
              ? { ...set, version: 3, questions: JSON.parse(init.body as string).questions }
              : set,
        }),
      ),
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: InterviewQuestionSetPage }],
  });
  await router.push('/?questionSetId=s1');
  render(InterviewQuestionSetPage, { global: { plugins: [router] } });
  await screen.findByText('题集暂无问题。');
  await fireEvent.click(screen.getByRole('button', { name: '新增人工题目' }));
  await fireEvent.update(screen.getByLabelText('题目内容'), '请说明一次方案取舍');
  await fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));
  await waitFor(() =>
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(true),
  );
  const call = fetcher.mock.calls.find(([, init]) => init?.method === 'PUT')!;
  expect(JSON.parse(call[1]!.body as string).expectedVersion).toBe(2);
  expect(fetcher.mock.calls.some(([url]) => String(url).includes('regenerations'))).toBe(false);
});
import ResumeCorrectionPage from './resumes/ResumeCorrectionPage.vue';
it('明确不适用组必须显式确认且发送服务端版本', async () => {
  const facts = {
    candidateId: 'c1',
    resumeVersionId: 'r1',
    filename: '合成.txt',
    pageCount: 0,
    qualityScore: 85,
    status: 'PARSE_REVIEW',
    profile: { name: null, education: null, experienceMonths: null, targetPosition: null },
    blocks: [],
    fields: [],
    skills: [],
    confirmedCount: 0,
    totalCount: 0,
    version: 4,
    structuredFacts: [],
    notApplicableGroups: [],
  };
  const fetcher = vi.fn().mockImplementation((_url: string, init?: RequestInit) =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data:
            init?.method === 'POST'
              ? { ...facts, version: 5, notApplicableGroups: ['employment'] }
              : facts,
        }),
      ),
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:candidateId', component: ResumeCorrectionPage }],
  });
  await router.push('/c1');
  render(ResumeCorrectionPage, { global: { plugins: [router] } });
  await screen.findByText('明确不适用组（仅在材料与人工核实支持时确认）');
  expect(screen.getByRole('button', { name: '明确确认所选组不适用' })).toBeDisabled();
  await fireEvent.click(screen.getByRole('checkbox', { name: '工作经历不适用' }));
  await fireEvent.click(screen.getByRole('button', { name: '明确确认所选组不适用' }));
  await waitFor(() =>
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true),
  );
  const write = fetcher.mock.calls.find(([, init]) => init?.method === 'POST')!;
  expect(JSON.parse(write[1]!.body as string)).toEqual({
    expectedVersion: 4,
    fieldIds: [],
    notApplicableGroups: ['employment'],
  });
});
import HrInterviewBatchPanel from '../../features/hr-interview-batch/HrInterviewBatchPanel.vue';
it('批量面试必须逐对象显式勾选并确认才可提交', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  render(HrInterviewBatchPanel, { props: { candidateIds: ['c1', 'c2'], positionId: 'p1' } });
  expect(screen.getByRole('button', { name: '一次提交所选批次' })).toBeDisabled();
  expect(
    screen.getAllByRole('checkbox').filter((input) => (input as HTMLInputElement).checked),
  ).toHaveLength(0);
  expect(fetcher).not.toHaveBeenCalled();
});

import ResumeProgressPage from './resumes/ResumeProgressPage.vue';
it('失败条目重试必须选择新材料、填写原因并确认原批预算', async () => {
  const batch = {
    id: 'b1',
    positionId: null,
    mode: 'STORE_ONLY',
    status: 'FAILED',
    version: 2,
    items: [
      {
        id: 'i1',
        filename: '旧.txt',
        status: 'FAILED',
        stage: null,
        candidateId: null,
        errorCode: 'INVALID',
        message: '材料失败',
        progress: 0,
        contentHash: 'oldhash',
      },
    ],
    createdAt: '2026-11-11T00:00:00Z',
    completedCount: 0,
    failedCount: 1,
    reviewCount: 0,
    totalCount: 1,
  };
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: batch })));
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:batchId', component: ResumeProgressPage }],
  });
  await router.push('/b1');
  render(ResumeProgressPage, { global: { plugins: [router] } });
  await fireEvent.click(await screen.findByRole('button', { name: '修正材料后重试' }));
  expect(await screen.findByRole('dialog')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '确认原批额度内重试' })).toBeDisabled();
  expect(fetcher.mock.calls.every(([, init]) => !init?.method)).toBe(true);
});
it('人才普通读取不自动提交有费用语义检索', async () => {
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
    routes: [{ path: '/', component: TalentSearchPage }],
  });
  await router.push('/');
  render(TalentSearchPage, { global: { plugins: [router] } });
  await waitFor(() => expect(screen.getByText('暂无符合条件的授权人才。')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: '语义检索（需模型预算）' })).toBeDisabled();
  expect(fetcher.mock.calls.every(([, init]) => !init?.method)).toBe(true);
});

import { draftSchema } from '../../features/hr-position-draft/model';
import { matchingSchema } from '../../entities/hr';
it('展示标记开关持久化为空时不重置默认五项', () => {
  const value = draftSchema.parse({
    positionId: 'p1',
    name: '岗位',
    family: 'TECHNOLOGY',
    departmentId: 'd1',
    level: 'P6',
    jdText: '',
    lastStep: 'WEIGHTS',
    scoring: null,
    hardConditions: [],
    criteria: [],
    version: 1,
    visibleMarks: [],
  });
  expect(value.visibleMarks).toEqual([]);
});
it('匹配标记结构保留服务端active与visible独立判断', () => {
  const field = matchingSchema.shape.specialMarks;
  expect(
    field.parse([{ key: 'BORDERLINE', active: true, visible: false, reason: '临界区间' }]),
  ).toEqual([{ key: 'BORDERLINE', active: true, visible: false, reason: '临界区间' }]);
});
import MatchResultsPage from './matching/MatchResultsPage.vue';
it('统计使用同岗位版本真实全量分母而不采用当前页或搜索结果数', async () => {
  const fetcher = vi.fn().mockImplementation((url: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: url.includes('/statistics?')
            ? {
                total: 100,
                strongRecommend: 20,
                recommend: 30,
                review: 10,
                notRecommend: 15,
                filtered: 15,
                reviewRequired: 10,
              }
            : { items: [], total: 3, page: 1, pageSize: 20 },
        }),
      ),
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: MatchResultsPage }],
  });
  await router.push('/?positionId=p1&configVersionId=v1');
  render(MatchResultsPage, { global: { plugins: [router] } });
  await waitFor(() => expect(screen.getByText('授权范围分母 100')).toBeInTheDocument());
  await fireEvent.update(screen.getByPlaceholderText('搜索候选人'), '局部姓名');
  await fireEvent.click(screen.getByRole('button', { name: /查\s*询/ }));
  await waitFor(() =>
    expect(
      fetcher.mock.calls.filter(([url]) => String(url).includes('/statistics?')).length,
    ).toBeGreaterThan(1),
  );
  const urls = fetcher.mock.calls
    .filter(([url]) => String(url).includes('/statistics?'))
    .map(([url]) => String(url));
  expect(
    urls.every(
      (url) =>
        url.includes('positionId=p1') &&
        url.includes('configVersionId=v1') &&
        !url.includes('keyword') &&
        !url.includes('page='),
    ),
  ).toBe(true);
  expect(screen.getByText('授权范围分母 100')).toBeInTheDocument();
});
it('模板初次查询省略空部门与岗位族参数', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValue(new Response(JSON.stringify({ code: 'SUCCESS', data: [] })));
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: PositionTemplateLibraryPage }],
  });
  await router.push('/');
  render(PositionTemplateLibraryPage, { global: { plugins: [router] } });
  await waitFor(() => expect(screen.getByText('暂无可访问模板。')).toBeInTheDocument());
  expect(fetcher.mock.calls[0]![0]).toBe('/api/hr/templates');
});
import MatchDetailPage from './matching/MatchDetailPage.vue';
it('临时权重结果保留真实80分并只读取结果冻结配置快照', async () => {
  const result = {
    resultId: 'm1',
    candidateId: 'c1',
    candidateName: '合成人员',
    positionId: 'p1',
    positionName: '岗位',
    factSnapshotId: 'f1',
    configVersion: 'adhoc-123',
    contextVersion: 'ctx-old',
    semanticSnapshotId: 's1',
    asOfDate: '2026-11-11',
    businessStatus: 'SCORED',
    scoreStatus: 'SCORED',
    totalScore: 80,
    referenceScore: null,
    evidenceCoverage: 100,
    band: 'RECOMMENDED',
    reasonCodes: [],
    dimensions: [],
    hardConditions: [],
    overrides: [],
    snapshotHash: 'h',
    createdAt: '2026-11-11T00:00:00Z',
    supersededBy: null,
    highlights: [],
    reviewPoints: [],
    thresholds: [80, 65, 50],
    pageCount: 0,
    blocks: [],
  };
  const frozen = {
    id: 'cfg',
    positionId: 'p1',
    version: 'adhoc-123',
    contextVersion: 'ctx-old',
    snapshot: {
      positionId: 'p1',
      name: '旧岗位',
      family: 'TECHNOLOGY',
      departmentId: 'd1',
      level: 'P6',
      jdText: '旧JD',
      lastStep: 'WEIGHTS',
      scoring: null,
      hardConditions: [],
      criteria: [],
      version: 1,
    },
    snapshotHash: 'h',
    publishedBy: 'fixture',
    publishedAt: '2026-11-11T00:00:00Z',
    context: {
      positionId: 'p1',
      name: '旧岗位',
      departmentId: 'd1',
      level: 'P6',
      jdText: '冻结JD原文',
      version: 'ctx-old',
    },
  };
  const fetcher = vi.fn().mockImplementation((url: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          code: 'SUCCESS',
          data: url.endsWith('/configuration-snapshot') ? frozen : result,
        }),
      ),
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:candidateId', component: MatchDetailPage }],
  });
  await router.push('/c1?resultId=m1');
  render(MatchDetailPage, { global: { plugins: [router] } });
  await waitFor(() => expect(screen.getByText('80.0')).toBeInTheDocument());
  expect(screen.getByText('临时权重方案，不修改默认')).toBeInTheDocument();
  await fireEvent.click(screen.getByRole('button', { name: '▤ 查看配置快照' }));
  await waitFor(() => expect(screen.getByText('冻结JD原文')).toBeInTheDocument());
  expect(
    fetcher.mock.calls.some(
      ([url]) => url === '/api/hr/matching-results/m1/configuration-snapshot',
    ),
  ).toBe(true);
  expect(fetcher.mock.calls.some(([url]) => String(url).includes('/positions/'))).toBe(false);
});
