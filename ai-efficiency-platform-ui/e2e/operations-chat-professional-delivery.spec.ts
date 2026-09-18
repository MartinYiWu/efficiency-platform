import { expect, type Locator, type Page, test } from '@playwright/test';

type RankedDigestOptions = {
  degraded?: boolean;
  setWarnings?: Array<{ code: string; message: string }>;
  deliverableWarnings?: Array<{ code: string; message: string }>;
};

const frame = (runId: string, sequence: number, event: string, payload: Record<string, unknown>) =>
  `id: ${sequence}\nevent: ${event}\ndata: ${JSON.stringify({ contract_version: 'run.stream.event/1', event, run_id: runId, sequence, payload })}\n\n`;

const citation = {
  citation_id: 'citation-official',
  url: 'https://example.test/official-announcement',
  title: '官方公告',
  source: '示例官方站点',
  published_at: '2026-09-16T08:30:00Z',
  source_type: 'official',
  source_tier: 'primary',
  verification_status: 'verified',
  supports_item_ids: Array.from({ length: 9 }, (_, index) => `hotspot-${index + 1}`),
  independent_source_group: 'official-example',
} as const;

function deliverableSetV2(options: RankedDigestOptions = {}) {
  const items = Array.from({ length: 9 }, (_, index) => ({
    item_id: `hotspot-${index + 1}`,
    rank: index + 1,
    title: `AI 行业动态 ${index + 1}`,
    occurred_at: `2026-09-16T${String(index + 1).padStart(2, '0')}:00:00Z`,
    summary: `第 ${index + 1} 条已核验行业动态摘要。`,
    why_it_matters: `第 ${index + 1} 条动态会影响内容团队的生产判断。`,
    content_angles: [`动态 ${index + 1} 的运营解读`],
    metrics: [`指标 ${index + 1}`],
    source_refs: ['citation-official'],
    confidence: 'high',
    verification_status: 'verified',
  }));
  return {
    contract_version: 'deliverable-set/2',
    run_id: 'run-1',
    intent_revision: 2,
    summary: {
      message: options.degraded ? '部分数据源暂不可用，以下结果仍可使用' : '已核验 9 条行业动态',
      result_count: 1,
      complete: !options.degraded,
    },
    deliverables: [
      {
        contract_version: 'deliverable/2',
        deliverable_id: 'digest-1',
        deliverable_kind: 'ranked_digest',
        platform: '通用',
        title: '昨日 AI 行业热点榜',
        lead: '先展示九条核心结果，完整来源按需展开。',
        content: {
          kind: 'ranked_digest',
          selection_summary: '按重要性、新近性与热度综合排序。',
          ranking_basis: 'mixed',
          items,
        },
        citations: [citation],
        copy_text: items.map((item) => `${item.rank}. ${item.title}`).join('\n'),
        warnings: options.deliverableWarnings ?? [],
      },
    ],
    next_actions: [
      {
        action_id: 'show-sources',
        action_type: 'show_sources',
        label: '查看完整来源',
        target_deliverable_id: null,
        target_item_ids: [],
        intent_patch: {},
        requires_user_input: false,
      },
      {
        action_id: 'rewrite-wechat',
        action_type: 'rewrite_for_platform',
        label: '生成公众号版本',
        target_deliverable_id: 'digest-1',
        target_item_ids: ['hotspot-1'],
        intent_patch: { platform: 'wechat_official_account' },
        requires_user_input: false,
      },
    ],
    provenance: {
      source_count: 1,
      verified_source_count: 1,
      candidate_count: 15,
      merged_event_count: 12,
      retained_count: 9,
      eliminated_count: 3,
      collection_window_start: '2026-09-16T00:00:00Z',
      collection_window_end: '2026-09-17T00:00:00Z',
      ranking_basis: 'mixed',
    },
    degraded: options.degraded ?? false,
    warnings: options.setWarnings ?? [],
  };
}

function platformFollowUpSet(runId: string) {
  return {
    contract_version: 'deliverable-set/2',
    run_id: runId,
    intent_revision: 3,
    summary: { message: '公众号版本已生成', result_count: 1, complete: true },
    deliverables: [
      {
        contract_version: 'deliverable/2',
        deliverable_id: 'platform-1',
        deliverable_kind: 'platform_content',
        platform: '微信公众号',
        title: '公众号深度解读',
        lead: '沿用本轮热点上下文生成。',
        content: {
          kind: 'platform_content',
          body_markdown: '## 正文\n同一会话中的公众号后续成品。',
          hashtags: ['#AI行业'],
          format_notes: ['保留来源说明'],
        },
        citations: [],
        copy_text: '同一会话中的公众号后续成品。',
        warnings: [],
      },
    ],
    next_actions: [],
    provenance: null,
    degraded: false,
    warnings: [],
  };
}

const successfulStream = (runId: string, set: ReturnType<typeof deliverableSetV2> | object) =>
  frame(runId, 1, 'run_started', { status: 'running' }) +
  frame(runId, 2, 'deliverable', {
    deliverable_set: { ...set, run_id: runId },
  }) +
  frame(runId, 3, 'stream_done', {
    status: 'succeeded',
    degraded: 'degraded' in set && set.degraded === true,
  });

const failedStream = (runId: string) =>
  frame(runId, 1, 'run_started', { status: 'running' }) +
  frame(runId, 2, 'stream_error', { safe_message: '后续版本生成失败，请重新尝试。' });

async function installV2Conversation(
  page: Page,
  streamForRun: (runId: string, submitCount: number) => string | Promise<string>,
) {
  let submitCount = 0;
  const conversationIds: string[] = [];
  await page.route('**/v1/conversations/*/messages', async (route) => {
    submitCount += 1;
    const conversationId = decodeURIComponent(
      new URL(route.request().url()).pathname.split('/').at(-2) ?? '',
    );
    conversationIds.push(conversationId);
    await route.fulfill({
      json: {
        contract_version: 'conversation/1',
        conversation_id: conversationId,
        turn_id: `turn-${submitCount}`,
        run_id: `run-${submitCount}`,
        status: 'queued',
      },
    });
  });
  await page.route('**/v1/runs/*/events', async (route) => {
    const runId = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
    const runNumber = Number(runId.split('-').at(-1));
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: await streamForRun(runId, Number.isFinite(runNumber) ? runNumber : submitCount),
    });
  });
  return { conversationIds, submitCount: () => submitCount };
}

async function keepEventStreamOpen(page: Page, runId: string, body: string) {
  await page.addInitScript(
    ({ eventBody, targetRunId }) => {
      const originalFetch = window.fetch.bind(window);
      window.fetch = async (input, init) => {
        const requestUrl =
          typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (
          new URL(requestUrl, window.location.origin).pathname === `/v1/runs/${targetRunId}/events`
        ) {
          return new Response(
            new ReadableStream({
              start(controller) {
                controller.enqueue(new TextEncoder().encode(eventBody));
              },
            }),
            { headers: { 'Content-Type': 'text/event-stream' }, status: 200 },
          );
        }
        return originalFetch(input, init);
      };
    },
    { eventBody: body, targetRunId: runId },
  );
}

async function submit(page: Page, message = '收集昨天的 9 条 AI 行业动态') {
  await page.goto('/ai-assistants/operations/chat');
  await page.getByLabel('输入消息').fill(message);
  await page.getByRole('button', { name: '发送消息' }).click();
}

async function tabTo(page: Page, target: Locator, limit = 12) {
  for (let index = 0; index < limit; index += 1) {
    if (await target.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target).toBeFocused();
}

test('热点榜先展示 9 条核心结果，来源默认折叠并可展开', async ({ page }) => {
  await installV2Conversation(page, (runId) => successfulStream(runId, deliverableSetV2()));

  await submit(page);

  await expect(page.getByRole('heading', { name: /^1\. AI 行业动态 1$/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: /^9\. AI 行业动态 9$/ })).toBeVisible();
  await expect(page.getByRole('link', { name: '官方公告' })).toBeHidden();
  const sources = page.getByRole('button', { name: /来源与采集依据/ });
  await expect(sources).toHaveAttribute('aria-expanded', 'false');
  await sources.click();
  await expect(sources).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('link', { name: '官方公告' })).toBeVisible();
});

test('部分降级保留可用结果并显示可访问告警', async ({ page }) => {
  const set = deliverableSetV2({
    degraded: true,
    setWarnings: [{ code: 'SOURCE_PARTIAL', message: '社区来源暂不可用' }],
    deliverableWarnings: [{ code: 'ITEM_PARTIAL', message: '第九条仅完成单源核验' }],
  });
  await installV2Conversation(page, (runId) => successfulStream(runId, set));

  await submit(page);

  await expect(page.getByRole('heading', { name: /^1\. AI 行业动态 1$/ })).toBeVisible();
  await expect(page.getByText('部分内容已降级，请确认后使用。')).toBeVisible();
  await expect(page.getByRole('alert').filter({ hasText: '社区来源暂不可用' })).toBeVisible();
  await expect(page.getByRole('alert').filter({ hasText: '第九条仅完成单源核验' })).toBeVisible();
});

test('非法 V2 失败关闭且不渲染半结构化原始内容', async ({ page }) => {
  const invalidSet = {
    ...deliverableSetV2(),
    unexpected_debug_payload: '不得展示的内部字段',
  };
  await installV2Conversation(page, (runId) => successfulStream(runId, invalidSet));

  await submit(page, '验证非法 V2');

  await expect(page.getByRole('heading', { name: '昨日 AI 行业热点榜' })).toHaveCount(0);
  await expect(page.getByText('不得展示的内部字段')).toHaveCount(0);
  await expect(page.getByRole('region', { name: '运营交付' })).toHaveCount(0);
});

test('后续动作沿用同一 conversation id', async ({ page }) => {
  const requests = await installV2Conversation(page, (runId, submitCount) =>
    submitCount === 1
      ? successfulStream(runId, deliverableSetV2())
      : successfulStream(runId, platformFollowUpSet(runId)),
  );
  await submit(page);

  await page.getByRole('button', { name: '生成公众号版本' }).click();

  await expect(page.getByRole('heading', { name: '公众号深度解读' })).toBeVisible();
  await expect.poll(() => requests.submitCount()).toBe(2);
  expect(requests.conversationIds).toHaveLength(2);
  expect(requests.conversationIds[1]).toBe(requests.conversationIds[0]);
});

test('Space 触发后续动作且第二轮立即成功时焦点进入新交付操作区', async ({ page }) => {
  const requests = await installV2Conversation(page, (runId, submitCount) =>
    submitCount === 1
      ? successfulStream(runId, deliverableSetV2())
      : successfulStream(runId, platformFollowUpSet(runId)),
  );
  await submit(page);

  const action = page.getByRole('button', { name: '生成公众号版本' });
  await action.focus();
  await page.keyboard.press('Space');

  await expect.poll(() => requests.submitCount()).toBe(2);
  await expect(page.getByRole('heading', { name: '公众号深度解读' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName)).not.toBe('BODY');
  await expect(page.getByRole('button', { name: '复制全文' })).toBeFocused();
});

test('Space 触发后续动作且第二轮立即失败时焦点回到输入框', async ({ page }) => {
  const requests = await installV2Conversation(page, (runId, submitCount) =>
    submitCount === 1 ? successfulStream(runId, deliverableSetV2()) : failedStream(runId),
  );
  await submit(page);

  const action = page.getByRole('button', { name: '生成公众号版本' });
  await action.focus();
  await page.keyboard.press('Space');

  await expect.poll(() => requests.submitCount()).toBe(2);
  await expect(page.getByRole('alert')).toContainText('后续版本生成失败，请重新尝试。');
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName)).not.toBe('BODY');
  await expect(page.getByLabel('输入消息')).toBeFocused();
});

test('真实阶段进度使用 polite live region', async ({ page }) => {
  await keepEventStreamOpen(
    page,
    'run-1',
    frame('run-1', 1, 'phase_started', {
      phase: 'collecting_sources',
      completed: 3,
      target: 9,
    }),
  );
  await installV2Conversation(page, () => '');

  await submit(page);

  const progress = page.getByRole('status');
  await expect(progress).toHaveAttribute('aria-live', 'polite');
  await expect(progress).toContainText('正在收集公开来源');
  await expect(progress).toContainText('3/9');
});

for (const viewport of [
  { width: 1440, height: 1024 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
]) {
  test(`${viewport.width}x${viewport.height} 无水平溢出且输入、来源和动作可达`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await installV2Conversation(page, (runId) => successfulStream(runId, deliverableSetV2()));

    await submit(page);

    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      )
      .toBe(true);
    const composer = page.locator('footer[aria-label="消息输入"]');
    await expect(composer).toBeVisible();
    await expect
      .poll(() =>
        composer.evaluate(
          (element) => element.getBoundingClientRect().bottom <= window.innerHeight,
        ),
      )
      .toBe(true);
    const sources = page.getByRole('button', { name: /来源与采集依据/ });
    const action = page.getByRole('button', { name: '生成公众号版本' });
    await sources.scrollIntoViewIfNeeded();
    await expect(sources).toBeVisible();
    await action.scrollIntoViewIfNeeded();
    await expect(action).toBeVisible();
  });
}

test('Tab 后可用 Enter 展开来源、Space 触发动作且焦点转移到可操作控件', async ({ page }) => {
  await keepEventStreamOpen(
    page,
    'run-2',
    frame('run-2', 1, 'phase_started', {
      phase: 'creating_content',
      completed: 1,
      target: 2,
    }),
  );
  const requests = await installV2Conversation(page, (runId, submitCount) =>
    submitCount === 1 ? successfulStream(runId, deliverableSetV2()) : '',
  );
  await submit(page);

  const copyButton = page.getByRole('button', { name: '复制热点榜' });
  const sources = page.getByRole('button', { name: /来源与采集依据/ });
  await copyButton.focus();
  await page.keyboard.press('Tab');
  await expect(sources).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(sources).toHaveAttribute('aria-expanded', 'true');
  await expect(sources).toBeFocused();

  const action = page.getByRole('button', { name: '生成公众号版本' });
  await tabTo(page, action);
  await expect(action).toBeFocused();
  await page.keyboard.press('Space');

  await expect.poll(() => requests.submitCount()).toBe(2);
  await expect(page.getByRole('button', { name: '停止生成' })).toBeFocused();
});
