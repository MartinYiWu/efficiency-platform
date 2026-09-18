import { act, render, screen } from '@testing-library/react';
import type { DeliverableSetV2 } from '../../../entities/operation-deliverable';
import type { OperationChatState } from '../../../features/operation-chat';
import { MemoryRouter } from 'react-router';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { OperationsChatPage } from './OperationsChatPage';

const useOperationChatMock = vi.hoisted(() => vi.fn());

vi.mock('../../../features/operation-chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../features/operation-chat')>()),
  useOperationChat: useOperationChatMock,
}));

const baseState = (overrides: Partial<OperationChatState>): OperationChatState => ({
  status: 'idle',
  runId: null,
  requestId: null,
  cancellationRunId: null,
  messages: [],
  clarification: null,
  deliverableSets: [],
  visiblePhase: null,
  phaseProgress: null,
  error: null,
  lastEventId: null,
  seenEventIds: [],
  ...overrides,
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <OperationsChatPage />
    </MemoryRouter>,
  );

function rankedDigestSet(): DeliverableSetV2 {
  return {
    contract_version: 'deliverable-set/2' as const,
    run_id: 'run-v2-digest',
    intent_revision: 1,
    summary: { message: '已核验 9 条行业动态', result_count: 1, complete: true },
    deliverables: [
      {
        contract_version: 'deliverable/2' as const,
        deliverable_id: 'digest-1',
        deliverable_kind: 'ranked_digest' as const,
        platform: '通用',
        title: 'AI 行业热点',
        lead: '面向运营团队的热点交付。',
        citations: [
          {
            citation_id: 'citation-1',
            url: 'https://news.example.test/meta',
            title: '官方公告',
            source: 'Meta',
            published_at: '2026-09-17T00:00:00Z',
            source_type: 'official' as const,
            source_tier: 'primary' as const,
            verification_status: 'verified' as const,
            supports_item_ids: ['item-1'],
            independent_source_group: 'meta',
          },
        ],
        copy_text: '1. Meta 发布新模型',
        warnings: [],
        content: {
          kind: 'ranked_digest' as const,
          selection_summary: '按重要性与新近性排序。',
          ranking_basis: 'mixed' as const,
          items: [
            {
              item_id: 'item-1',
              rank: 1,
              title: 'Meta 发布新模型',
              occurred_at: '2026-09-17T00:00:00Z',
              summary: '发布新的 AI 模型。',
              why_it_matters: '影响内容生产效率。',
              content_angles: ['生产效率'],
              metrics: [],
              source_refs: ['citation-1'],
              confidence: 'high' as const,
              verification_status: 'verified' as const,
            },
          ],
        },
      },
    ],
    next_actions: [],
    provenance: {
      source_count: 1,
      verified_source_count: 1,
      candidate_count: 9,
      merged_event_count: 9,
      retained_count: 9,
      eliminated_count: 0,
      collection_window_start: '2026-09-16T00:00:00Z',
      collection_window_end: '2026-09-17T00:00:00Z',
      ranking_basis: 'mixed' as const,
    },
    degraded: false,
    warnings: [],
  };
}

function platformContentSet(): DeliverableSetV2 {
  const value = rankedDigestSet();
  value.summary = { message: '已生成平台文案', result_count: 1, complete: true };
  value.deliverables = [
    {
      contract_version: 'deliverable/2',
      deliverable_id: 'platform-1',
      deliverable_kind: 'platform_content',
      platform: '小红书',
      title: '小红书发布稿',
      lead: '可直接交付的运营文案。',
      citations: [],
      copy_text: 'Agent 原样 copyText\n<script>不得执行</script>',
      warnings: [],
      content: {
        kind: 'platform_content',
        body_markdown: '## 页面正文\n这是渲染内容，不是复制内容。',
        hashtags: ['AI运营'],
        format_notes: [],
      },
    },
  ];
  value.provenance = null;
  return value;
}

describe('OperationsChatPage', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it('首个非空 delta 到达后立即移除三点思考动效', () => {
    useOperationChatMock.mockReturnValue({
      state: baseState({ status: 'streaming', requestId: 'request-1' }),
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      isBusy: true,
    });
    const { rerender } = renderPage();

    expect(screen.getByLabelText('助手正在思考')).toBeInTheDocument();
    useOperationChatMock.mockReturnValue({
      state: baseState({
        status: 'streaming',
        requestId: 'request-1',
        messages: [{ id: 'assistant-1', role: 'assistant', content: '首个正文', createdAt: 1 }],
      }),
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      isBusy: true,
    });
    rerender(
      <MemoryRouter>
        <OperationsChatPage />
      </MemoryRouter>,
    );

    expect(screen.queryByLabelText('助手正在思考')).not.toBeInTheDocument();
  });

  it('冻结消息在新一轮提交后不恢复打字机', async () => {
    vi.useFakeTimers();
    const assistant = {
      id: 'assistant-1',
      role: 'assistant' as const,
      content: '完整正文',
      createdAt: 1,
    };
    useOperationChatMock.mockReturnValue({
      state: baseState({ status: 'streaming', runId: 'run-1', messages: [assistant] }),
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      isBusy: true,
    });
    const { rerender } = renderPage();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(24);
    });
    expect(screen.getByLabelText('助手回复')).toHaveTextContent(/^完$/);

    useOperationChatMock.mockReturnValue({
      state: baseState({
        status: 'submitting',
        requestId: 'request-2',
        messages: [
          { ...assistant, frozen: true },
          { id: 'user-2', role: 'user', content: '第二轮', createdAt: 2 },
        ],
      }),
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      isBusy: true,
    });
    rerender(
      <MemoryRouter>
        <OperationsChatPage />
      </MemoryRouter>,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(240);
    });

    expect(screen.getByLabelText('助手回复')).toHaveTextContent(/^完$/);
  });

  it('仅将 V1 安全 HTTPS 来源渲染为链接，保留不安全来源的原始文本', async () => {
    const user = userEvent.setup();
    useOperationChatMock.mockReturnValue({
      state: baseState({
        deliverableSets: [
          {
            contract_version: 'deliverable-set/1',
            summary: '来源校验',
            degraded: false,
            deliverables: [
              {
                contract_version: 'deliverable/1',
                platform: '微信公众号',
                title: '测试交付',
                body: '正文',
                hashtags: [],
                format_notes: [],
                citations: [
                  { url: 'https://news.example.test/brief', title: '安全来源', source: null },
                  { url: 'javascript:alert(1)', title: null, source: null },
                  {
                    url: 'https://editor:secret@news.example.test/private',
                    title: null,
                    source: null,
                  },
                ],
                warnings: [],
              },
            ],
          },
        ],
      }),
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      isBusy: false,
    });

    renderPage();

    await user.click(screen.getByRole('button', { name: '来源（3 条）' }));

    expect(screen.getByRole('link', { name: '来源：安全来源' })).toHaveAttribute(
      'href',
      'https://news.example.test/brief',
    );
    expect(
      screen.queryByRole('link', { name: '来源：javascript:alert(1)' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', {
        name: '来源：https://editor:secret@news.example.test/private',
      }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('来源：javascript:alert(1)').closest('a')).toBeNull();
    expect(
      screen.getByText('来源：https://editor:secret@news.example.test/private').closest('a'),
    ).toBeNull();
  });

  it('V2 热点交付不再渲染为一整段通用卡片', () => {
    useOperationChatMock.mockReturnValue({
      state: baseState({ deliverableSets: [rankedDigestSet()] }),
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      isBusy: false,
    });

    renderPage();

    expect(screen.getByText('已核验 9 条行业动态')).toBeVisible();
    expect(screen.getByRole('heading', { name: '1. Meta 发布新模型' })).toBeVisible();
    expect(screen.getByRole('button', { name: /来源与采集依据/ })).toBeVisible();
  });

  it('用户点击后续动作时沿用当前会话发送', async () => {
    const user = userEvent.setup();
    const sendMessage = vi.fn();
    const value = rankedDigestSet();
    value.next_actions = [
      {
        action_id: 'rewrite-1',
        action_type: 'rewrite_for_platform',
        label: '生成公众号版本',
        target_deliverable_id: 'digest-1',
        target_item_ids: ['item-1'],
        intent_patch: { platform: '微信公众号' },
        requires_user_input: false,
      },
    ];
    useOperationChatMock.mockReturnValue({
      state: baseState({ deliverableSets: [value] }),
      sendMessage,
      cancel: vi.fn(),
      isBusy: false,
    });

    renderPage();
    await user.click(screen.getByRole('button', { name: '生成公众号版本' }));

    expect(sendMessage).toHaveBeenCalledWith('生成公众号版本');
  });

  it('show_sources 在真实 Widget 中只展开本地来源，不发送消息或读取 intent_patch', async () => {
    const user = userEvent.setup();
    const sendMessage = vi.fn();
    const value = rankedDigestSet();
    const showSourcesAction = {
      action_id: 'show-sources-1',
      action_type: 'show_sources' as const,
      label: '查看本次来源',
      target_deliverable_id: null,
      target_item_ids: [],
      intent_patch: {},
      requires_user_input: false,
    };
    const intentPatchRead = vi.fn(() => {
      throw new Error('show_sources 不得读取 intent_patch');
    });
    Object.defineProperty(showSourcesAction, 'intent_patch', {
      configurable: true,
      enumerable: true,
      get: intentPatchRead,
    });
    value.next_actions = [showSourcesAction];
    useOperationChatMock.mockReturnValue({
      state: baseState({ deliverableSets: [value] }),
      sendMessage,
      cancel: vi.fn(),
      isBusy: false,
    });

    renderPage();

    const action = screen.getByRole('button', { name: '查看本次来源' });
    expect(action).toBeEnabled();
    expect(screen.queryByRole('link', { name: '官方公告' })).not.toBeInTheDocument();
    await user.click(action);

    expect(screen.getByRole('link', { name: '官方公告' })).toBeVisible();
    expect(screen.getByRole('button', { name: /来源与采集依据/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(sendMessage).not.toHaveBeenCalled();
    expect(intentPatchRead).not.toHaveBeenCalled();
  });

  it('V2 provenance 未提供时明确显示未知，不宣称已核验 0 条', async () => {
    const user = userEvent.setup();
    const value = rankedDigestSet();
    value.provenance = null;
    useOperationChatMock.mockReturnValue({
      state: baseState({ deliverableSets: [value] }),
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      isBusy: false,
    });

    renderPage();
    await user.click(screen.getByRole('button', { name: /来源与采集依据/ }));

    expect(screen.getByText('核验统计未提供')).toBeVisible();
    expect(screen.queryByText(/已核验 0 条/)).not.toBeInTheDocument();
  });

  it('真实运营页面把 Agent 原样 copyText 交给安全复制机制', async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    useOperationChatMock.mockReturnValue({
      state: baseState({ deliverableSets: [platformContentSet()] }),
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      isBusy: false,
    });

    renderPage();
    await user.click(screen.getByRole('button', { name: '复制全文' }));

    expect(writeText).toHaveBeenCalledWith('Agent 原样 copyText\n<script>不得执行</script>');
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status')).toHaveTextContent('已复制');
  });

  it('复制失败时提供可访问反馈且页面保持可用', async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('permission denied'));
    useOperationChatMock.mockReturnValue({
      state: baseState({ deliverableSets: [platformContentSet()] }),
      sendMessage: vi.fn(),
      cancel: vi.fn(),
      isBusy: false,
    });

    renderPage();
    await user.click(screen.getByRole('button', { name: '复制全文' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('复制失败，请手动复制');
    expect(screen.getByRole('button', { name: '复制全文' })).toBeEnabled();
  });
});
