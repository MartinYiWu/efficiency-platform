import { expect, type Page, test } from '@playwright/test';

type Deliverable = {
  platform: string;
  title: string;
  body: string;
  hashtags?: string[];
  formatNotes?: string[];
  citations?: Array<{ url: string; title: string | null; source: string | null }>;
  warnings?: string[];
};

type DeliverableKindV2 =
  'ranked_digest' | 'platform_content' | 'action_plan' | 'diagnosis' | 'retrospective';

type DeliverableV2Fixture = {
  contract_version: 'deliverable/2';
  deliverable_id: string;
  deliverable_kind: DeliverableKindV2;
  platform: string;
  title: string;
  lead: string;
  content: Record<string, unknown>;
  citations: Array<Record<string, unknown>>;
  copy_text: string;
  warnings: Array<{ code: string; message: string }>;
};

const frame = (runId: string, sequence: number, event: string, payload: Record<string, unknown>) =>
  `id: ${sequence}\nevent: ${event}\ndata: ${JSON.stringify({ contract_version: 'run.stream.event/1', event, run_id: runId, sequence, payload })}\n\n`;

const deliverableSet = (deliverables: Deliverable[], degraded = false) => ({
  contract_version: 'deliverable-set/1',
  summary: degraded ? '部分能力降级，已保留可用成品' : '运营成品已生成',
  degraded,
  deliverables: deliverables.map((item) => ({
    contract_version: 'deliverable/1',
    platform: item.platform,
    title: item.title,
    body: item.body,
    hashtags: item.hashtags ?? [],
    format_notes: item.formatNotes ?? [],
    citations: item.citations ?? [],
    warnings: item.warnings ?? [],
  })),
});

const deliverableSetV2 = (
  deliverables: DeliverableV2Fixture[],
  options: {
    degraded?: boolean;
    nextActions?: Array<Record<string, unknown>>;
    provenance?: Record<string, unknown> | null;
    warnings?: Array<{ code: string; message: string }>;
  } = {},
) => ({
  contract_version: 'deliverable-set/2',
  run_id: 'run-1',
  intent_revision: 1,
  summary: {
    message: options.degraded ? '部分能力降级，已保留可用成品' : '运营成品已生成',
    result_count: deliverables.length,
    complete: !options.degraded,
  },
  deliverables,
  next_actions: options.nextActions ?? [],
  provenance: options.provenance ?? null,
  degraded: options.degraded ?? false,
  warnings: options.warnings ?? [],
});

const v2Deliverable = (
  kind: DeliverableKindV2,
  title: string,
  content: Record<string, unknown>,
): DeliverableV2Fixture => ({
  contract_version: 'deliverable/2',
  deliverable_id: `${kind}-1`,
  deliverable_kind: kind,
  platform: '通用',
  title,
  lead: `${title}的可执行摘要。`,
  content,
  citations: [],
  copy_text: `${title}可复制正文`,
  warnings: [],
});

async function installConversation(
  page: Page,
  stream: (runId: string) => string | Promise<string>,
) {
  await page.route('**/v1/conversations/*/messages', async (route) => {
    const conversationId = new URL(route.request().url()).pathname.split('/').at(-2);
    await route.fulfill({
      json: {
        contract_version: 'conversation/1',
        conversation_id: decodeURIComponent(conversationId ?? ''),
        turn_id: 'turn-1',
        run_id: 'run-1',
        status: 'queued',
      },
    });
  });
  await page.route('**/v1/runs/run-1/events', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: await stream('run-1'),
    });
  });
}

async function submit(page: Page, message: string) {
  await page.goto('/ai-assistants/operations/chat');
  await page.getByLabel('输入消息').fill(message);
  await page.getByRole('button', { name: '发送消息' }).click();
}

const successfulStream = (runId: string, items: Deliverable[], degraded = false) =>
  frame(runId, 1, 'run_started', { status: 'running' }) +
  frame(runId, 2, 'deliverable', {
    deliverable_set: deliverableSet(items, degraded),
  }) +
  frame(runId, 3, 'stream_done', {
    status: 'succeeded',
    degraded,
  });

const successfulV2Stream = (runId: string, set: ReturnType<typeof deliverableSetV2>) =>
  frame(runId, 1, 'run_started', { status: 'running' }) +
  frame(runId, 2, 'deliverable', {
    deliverable_set: { ...set, run_id: runId },
  }) +
  frame(runId, 3, 'stream_done', {
    status: 'succeeded',
    degraded: set.degraded,
  });

test('普通内容场景展示一个可复制的独立成品', async ({ page }) => {
  await installConversation(page, (runId) =>
    successfulStream(runId, [
      { platform: '通用内容', title: '秋季新品选题', body: '围绕真实使用场景展开内容。' },
    ]),
  );
  await submit(page, '生成一份秋季新品内容');
  await expect(page.getByText('秋季新品选题')).toBeVisible();
  await expect(page.getByText('围绕真实使用场景展开内容。')).toBeVisible();
});

test('三平台内容场景展示三份独立成品', async ({ page }) => {
  await installConversation(page, (runId) =>
    successfulStream(runId, [
      { platform: 'xiaohongshu', title: '小红书成品', body: '小红书独立正文' },
      { platform: 'wechat_official_account', title: '公众号成品', body: '公众号独立正文' },
      { platform: 'toutiao', title: '今日头条成品', body: '今日头条独立正文' },
    ]),
  );
  await submit(page, '生成三个平台可用的排版标准格式');
  await expect(page.getByText('小红书独立正文')).toBeVisible();
  await expect(page.getByText('公众号独立正文')).toBeVisible();
  await expect(page.getByText('今日头条独立正文')).toBeVisible();
});

test('活动策划场景展示活动方案成品', async ({ page }) => {
  await installConversation(page, (runId) =>
    successfulStream(runId, [
      { platform: '活动策划', title: '新品发布活动方案', body: '预热、发布、复盘三阶段执行。' },
    ]),
  );
  await submit(page, '策划一场新品发布活动');
  await expect(page.getByText('新品发布活动方案')).toBeVisible();
  await expect(page.getByText('预热、发布、复盘三阶段执行。')).toBeVisible();
});

test('行业热点场景展示来源和未核验警告', async ({ page }) => {
  await installConversation(page, (runId) =>
    successfulStream(runId, [
      {
        platform: '行业动态',
        title: '本周行业热点',
        body: '热点信息摘要。',
        citations: [{ url: 'https://example.test/report', title: '行业报告', source: '公开站点' }],
        warnings: ['来源内容尚未完成原文核验'],
      },
    ]),
  );
  await submit(page, '整理本周行业热点');
  await page.getByRole('button', { name: '来源（1 条）' }).click();
  await expect(page.getByRole('link', { name: '来源：行业报告' })).toBeVisible();
  await expect(page.getByText('来源内容尚未完成原文核验')).toBeVisible();
});

test('信息不足场景补充信息后继续生成成品', async ({ page }) => {
  let submitCount = 0;
  await page.route('**/v1/conversations/*/messages', async (route) => {
    submitCount += 1;
    const conversationId = new URL(route.request().url()).pathname.split('/').at(-2);
    await route.fulfill({
      json: {
        contract_version: 'conversation/1',
        conversation_id: decodeURIComponent(conversationId ?? ''),
        turn_id: `turn-${submitCount}`,
        run_id: `run-${submitCount}`,
        status: 'queued',
      },
    });
  });
  await page.route('**/v1/runs/*/events', async (route) => {
    const runId = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
    const body =
      runId === 'run-1'
        ? frame(runId, 1, 'clarification_required', {
            question: '请补充目标平台和产品主题。',
            fields: ['platforms', 'topic'],
          })
        : successfulStream(runId, [
            {
              platform: 'xiaohongshu',
              title: '澄清后的小红书成品',
              body: '已根据补充的平台和新品主题生成独立正文。',
            },
          ]);
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body });
  });
  await submit(page, '帮我做一份运营内容');
  await expect(page.getByLabel('澄清问题')).toBeVisible();
  await expect(page.getByText('请补充目标平台和产品主题。')).toBeVisible();
  await expect(page.getByRole('button', { name: '发送消息' })).toBeDisabled();
  await page.getByLabel('输入消息').fill('小红书，新品发布');
  await expect(page.getByRole('button', { name: '发送消息' })).toBeEnabled();
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect(page.getByText('澄清后的小红书成品')).toBeVisible();
  await expect(page.getByText('已根据补充的平台和新品主题生成独立正文。')).toBeVisible();
  await expect.poll(() => submitCount).toBe(2);
});

test('单个 Specialist 失败时展示降级提示并保留可用成品', async ({ page }) => {
  await installConversation(page, (runId) =>
    successfulStream(
      runId,
      [
        {
          platform: 'xiaohongshu',
          title: '已完成的平台成品',
          body: '其余 Specialist 失败时仍然保留的正文。',
          warnings: ['微信公众号 Specialist 暂不可用'],
        },
      ],
      true,
    ),
  );
  await submit(page, '生成多个平台内容');
  await expect(page.getByText('部分内容已降级，请确认后使用。')).toBeVisible();
  await expect(page.getByText('其余 Specialist 失败时仍然保留的正文。')).toBeVisible();
  await expect(page.getByText('微信公众号 Specialist 暂不可用')).toBeVisible();
});

test('用户停止生成时调用取消接口并恢复可发送状态', async ({ page }) => {
  let releaseStream: (() => void) | undefined;
  const cancelled = new Promise<void>((resolve) => {
    releaseStream = resolve;
  });
  let cancelCount = 0;
  await installConversation(page, async (runId) => {
    await cancelled;
    return frame(runId, 1, 'stream_done', { status: 'cancelled', degraded: false });
  });
  await page.route('**/v1/runs/run-1/cancel', async (route) => {
    cancelCount += 1;
    await route.fulfill({ json: { status: 'cancelled' } });
    releaseStream?.();
  });
  await submit(page, '生成一份长篇活动复盘');
  await page.getByRole('button', { name: '停止生成' }).click();
  await expect.poll(() => cancelCount).toBe(1);
  await expect(page.getByRole('button', { name: '发送消息' })).toBeDisabled();
  await page.getByLabel('输入消息').fill('开始下一项任务');
  await expect(page.getByRole('button', { name: '发送消息' })).toBeEnabled();
});

test('SSE 中断后携带 Last-Event-ID 重连且不重复展示增量', async ({ page }) => {
  let eventRequestCount = 0;
  const replayHeaders: string[] = [];
  await page.route('**/v1/conversations/*/messages', async (route) => {
    const conversationId = new URL(route.request().url()).pathname.split('/').at(-2);
    await route.fulfill({
      json: {
        contract_version: 'conversation/1',
        conversation_id: decodeURIComponent(conversationId ?? ''),
        turn_id: 'turn-1',
        run_id: 'run-1',
        status: 'queued',
      },
    });
  });
  await page.route('**/v1/runs/run-1/events', async (route) => {
    eventRequestCount += 1;
    replayHeaders.push(route.request().headers()['last-event-id'] ?? '');
    const runId = 'run-1';
    const body =
      eventRequestCount === 1
        ? frame(runId, 1, 'assistant_delta', { delta: '只应出现一次的片段' })
        : frame(runId, 1, 'assistant_delta', { delta: '只应出现一次的片段' }) +
          frame(runId, 2, 'deliverable', {
            deliverable_set: deliverableSet([
              { platform: '通用内容', title: '重连完成', body: '重连后的完整成品' },
            ]),
          }) +
          frame(runId, 3, 'stream_done', { status: 'succeeded', degraded: false });
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body });
  });
  await submit(page, '验证断线重连');
  await expect(page.getByText('重连后的完整成品')).toBeVisible();
  await expect.poll(() => eventRequestCount).toBe(2);
  expect(replayHeaders).toEqual(['', '1']);
  await expect(page.getByText('只应出现一次的片段')).toHaveCount(1);
});

test('V2 热点榜按连续编号展示核心结果', async ({ page }) => {
  const set = deliverableSetV2([
    v2Deliverable('ranked_digest', 'AI 行业热点榜', {
      kind: 'ranked_digest',
      selection_summary: '按重要性与新近性综合排序。',
      ranking_basis: 'mixed',
      items: [
        {
          item_id: 'hotspot-1',
          rank: 1,
          title: '模型能力持续升级',
          occurred_at: '2026-09-16T08:00:00Z',
          summary: '行业模型能力继续提升。',
          why_it_matters: '内容团队需要更新生产流程。',
          content_angles: ['效率变化'],
          metrics: ['响应速度提升'],
          source_refs: [],
          confidence: 'high',
          verification_status: 'verified',
        },
      ],
    }),
  ]);
  await installConversation(page, (runId) => successfulV2Stream(runId, set));

  await submit(page, '整理 AI 行业热点');

  await expect(page.getByRole('heading', { name: 'AI 行业热点榜' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '1. 模型能力持续升级' })).toBeVisible();
  await expect(page.getByText('内容团队需要更新生产流程。')).toBeVisible();
});

test('V2 平台内容展示安全正文、标签和格式说明', async ({ page }) => {
  const set = deliverableSetV2([
    v2Deliverable('platform_content', '小红书发布稿', {
      kind: 'platform_content',
      body_markdown: '## 正文\n面向真实工作场景的发布正文。',
      hashtags: ['#AI运营'],
      format_notes: ['保持短段落'],
    }),
  ]);
  await installConversation(page, (runId) => successfulV2Stream(runId, set));

  await submit(page, '生成小红书内容');

  await expect(page.getByRole('heading', { name: '小红书发布稿' })).toBeVisible();
  await expect(page.getByText('面向真实工作场景的发布正文。')).toBeVisible();
  await expect(page.getByText('#AI运营')).toBeVisible();
  await expect(page.getByText('保持短段落')).toBeVisible();
});

test('V2 行动计划展示目标、阶段和指标', async ({ page }) => {
  const set = deliverableSetV2([
    v2Deliverable('action_plan', '七日增长行动计划', {
      kind: 'action_plan',
      goal: '提升有效互动率',
      audience: '新关注的内容创作者',
      phases: [
        {
          phase_id: 'phase-1',
          title: '验证阶段',
          actions: ['发布三条候选内容'],
          metrics: ['互动率达到 8%'],
        },
      ],
      metrics: ['有效互动率'],
      assumptions: ['具备日常发布资源'],
    }),
  ]);
  await installConversation(page, (runId) => successfulV2Stream(runId, set));

  await submit(page, '制定七日运营计划');

  await expect(page.getByRole('heading', { name: '七日增长行动计划' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '验证阶段' })).toBeVisible();
  await expect(page.getByText('互动率达到 8%')).toBeVisible();
});

test('V2 诊断展示证据、优先级、建议和数据缺口', async ({ page }) => {
  const set = deliverableSetV2([
    v2Deliverable('diagnosis', '账号运营诊断', {
      kind: 'diagnosis',
      findings: [
        {
          finding_id: 'finding-1',
          title: '首屏价值表达不足',
          evidence: ['近七日首屏跳出率偏高'],
          priority: 'high',
          recommendation: '重写首屏标题与利益点',
        },
      ],
      data_gaps: ['缺少渠道转化数据'],
    }),
  ]);
  await installConversation(page, (runId) => successfulV2Stream(runId, set));

  await submit(page, '诊断账号问题');

  await expect(page.getByRole('heading', { name: '账号运营诊断' })).toBeVisible();
  await expect(page.getByText('近七日首屏跳出率偏高')).toBeVisible();
  await expect(page.getByText('重写首屏标题与利益点')).toBeVisible();
  await expect(page.getByText('缺少渠道转化数据')).toBeVisible();
});

test('V2 复盘展示目标到下一步的完整结构', async ({ page }) => {
  const set = deliverableSetV2([
    v2Deliverable('retrospective', '新品活动复盘', {
      kind: 'retrospective',
      objectives: ['扩大有效触达'],
      outcomes: ['新增 120 位关注者'],
      gaps: ['转化率低于目标'],
      causes: ['首屏信息不够明确'],
      next_steps: ['重写首屏并再次验证'],
    }),
  ]);
  await installConversation(page, (runId) => successfulV2Stream(runId, set));

  await submit(page, '复盘新品活动');

  await expect(page.getByRole('heading', { name: '新品活动复盘' })).toBeVisible();
  await expect(page.getByText('新增 120 位关注者')).toBeVisible();
  await expect(page.getByText('转化率低于目标')).toBeVisible();
  await expect(page.getByText('重写首屏并再次验证')).toBeVisible();
});
