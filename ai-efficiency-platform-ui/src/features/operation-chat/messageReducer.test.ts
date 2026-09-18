import { describe, expect, it } from 'vitest';
import {
  createInitialOperationChatState,
  operationChatReducer,
  type OperationChatEvent,
} from './messageReducer';
import type { StreamEventV1 } from './types';
const event = (
  sequence: number,
  name: StreamEventV1['event'],
  payload: Record<string, unknown>,
): OperationChatEvent => ({
  type: 'sse_event',
  event: {
    id: String(sequence),
    contract_version: 'run.stream.event/1',
    event: name,
    run_id: 'run-1',
    sequence,
    payload,
  },
});
const reduce = (events: OperationChatEvent[]) =>
  events.reduce(operationChatReducer, {
    ...createInitialOperationChatState(),
    status: 'streaming',
    runId: 'run-1',
    requestId: 'request-1',
  });

const deliverableSetV2 = () => ({
  contract_version: 'deliverable-set/2',
  run_id: 'run-1',
  intent_revision: 0,
  summary: { message: '已核验 1 条行业动态。', result_count: 1, complete: true },
  deliverables: [
    {
      contract_version: 'deliverable/2',
      deliverable_id: 'digest-1',
      deliverable_kind: 'ranked_digest',
      platform: '通用',
      title: '今日 AI 热点',
      lead: '以下为已核验的行业动态。',
      citations: [],
      copy_text: '可复制正文',
      warnings: [],
      content: {
        kind: 'ranked_digest',
        selection_summary: '按重要性排序。',
        ranking_basis: 'importance',
        items: [
          {
            item_id: 'item-1',
            rank: 1,
            title: '示例模型发布',
            occurred_at: null,
            summary: '发布了新模型。',
            why_it_matters: '影响内容生产效率。',
            content_angles: [],
            metrics: [],
            source_refs: [],
            confidence: 'high',
            verification_status: 'verified',
          },
        ],
      },
    },
  ],
  next_actions: [],
  provenance: null,
  degraded: false,
  warnings: [],
});
describe('operationChatReducer', () => {
  it('从真实 envelope 读取 delta 并严格按 sequence 去重', () => {
    const state = reduce([
      { type: 'submit_started', requestId: 'r', content: '你好' },
      { type: 'run_created', runId: 'run-1', requestId: 'r' },
      event(1, 'assistant_delta', { delta: '第一' }),
      event(1, 'assistant_delta', { delta: '第一' }),
      event(2, 'assistant_delta', { delta: '段' }),
      event(3, 'stream_done', { status: 'succeeded', degraded: false }),
    ]);
    expect(state.status).toBe('succeeded');
    expect(state.lastEventId).toBe('3');
    expect(state.messages.at(-1)?.content).toBe('第一段');
    expect(state.seenEventIds).toEqual(['run-1:1', 'run-1:2', 'run-1:3']);
  });
  it('处理澄清、多个独立交付物和降级成功', () => {
    const set = {
      contract_version: 'deliverable-set/1',
      summary: '已完成',
      degraded: true,
      deliverables: [
        {
          contract_version: 'deliverable/1',
          platform: '小红书',
          title: '标题 1',
          body: '正文 1',
          hashtags: ['#新品'],
          format_notes: [],
          citations: [],
          warnings: [],
        },
        {
          contract_version: 'deliverable/1',
          platform: '公众号',
          title: '标题 2',
          body: '正文 2',
          hashtags: [],
          format_notes: ['长文'],
          citations: [{ url: 'https://example.test', title: '来源', source: '站点' }],
          warnings: ['需复核'],
        },
      ],
    };
    const state = reduce([
      event(1, 'clarification_required', { question: '目标平台是什么？', fields: ['platform'] }),
      event(2, 'deliverable', set),
      event(3, 'stream_done', { status: 'succeeded', degraded: true }),
    ]);
    expect(state.clarification?.question).toBe('目标平台是什么？');
    expect(state.deliverableSets[0]?.deliverables).toHaveLength(2);
    expect(state.status).toBe('degraded_succeeded');
  });
  it('错误保留已生成内容，迟到取消不会覆盖失败终态', () => {
    const failed = reduce([
      event(1, 'assistant_delta', { delta: '部分结果' }),
      event(2, 'stream_error', { safe_message: '服务暂时不可用' }),
    ]);
    expect(failed.status).toBe('failed');
    expect(failed.messages.at(-1)?.content).toBe('部分结果');
    expect(operationChatReducer(failed, { type: 'cancelled' })).toEqual(failed);
  });
  it('取消失败只恢复当前 Run 的取消中状态，不能覆盖已确认终态', () => {
    const done = reduce([event(1, 'stream_done', { status: 'succeeded', degraded: false })]);
    expect(
      operationChatReducer(
        { ...done, runId: 'run-1', requestId: 'r' },
        { type: 'cancel_requested', runId: 'run-1', requestId: 'r' },
      ),
    ).toEqual({ ...done, runId: 'run-1', requestId: 'r' });
    const cancelling = {
      ...createInitialOperationChatState(),
      status: 'cancelling' as const,
      runId: 'run-1',
      requestId: 'r',
      cancellationRunId: 'run-1',
    };
    expect(
      operationChatReducer(cancelling, {
        type: 'cancel_failed',
        runId: 'other',
        requestId: 'r',
        message: '取消失败',
      }),
    ).toEqual(cancelling);
    expect(
      operationChatReducer(cancelling, {
        type: 'cancel_failed',
        runId: 'run-1',
        requestId: 'r',
        message: '取消失败',
      }),
    ).toMatchObject({ status: 'streaming', error: '取消失败', cancellationRunId: null });
  });
  it('本地异常独立于服务端 sequence，并支持 POST 返回后原子绑定取消态', () => {
    const submitting = operationChatReducer(createInitialOperationChatState(), {
      type: 'submit_started',
      requestId: 'r',
      content: '测试',
    });
    const afterFailure = operationChatReducer(submitting, {
      type: 'local_failed',
      requestId: 'r',
      message: '连接已断开，请重试。',
    });
    expect(afterFailure.status).toBe('failed');
    expect(afterFailure.seenEventIds).toEqual([]);
    const cancelling = operationChatReducer(
      { ...createInitialOperationChatState(), status: 'submitting', requestId: 'r' },
      { type: 'cancel_requested', runId: null, requestId: 'r' },
    );
    const cancelled = operationChatReducer(cancelling, {
      type: 'cancelled',
      runId: 'run-late',
      requestId: 'r',
    });
    expect(cancelled.runId).toBe('run-late');
    expect(cancelled.status).toBe('cancelled');
  });
  it('两轮 run 的 sequence 可以从 1 重新开始，且澄清后生命周期事件不覆盖等待输入', () => {
    const first = reduce([
      event(1, 'deliverable', {
        contract_version: 'deliverable-set/1',
        deliverables: [],
        summary: 'x',
        degraded: false,
      }),
    ]);
    const secondEvent = event(1, 'run_started', { status: 'running' });
    if (secondEvent.type !== 'sse_event') throw new Error('test setup');
    const state = operationChatReducer(
      { ...first, runId: 'run-2', status: 'waiting_input' },
      { type: 'sse_event', event: { ...secondEvent.event, run_id: 'run-2' } },
    );
    expect(state.status).toBe('waiting_input');
    expect(state.seenEventIds).toContain('run-2:1');
  });
  it('新一轮提交后忽略旧轮的 run 创建与事件', () => {
    const state = operationChatReducer(
      { ...createInitialOperationChatState(), requestId: 'new', status: 'submitting' },
      { type: 'run_created', runId: 'old-run', requestId: 'old' },
    );
    expect(state.runId).toBeNull();
    const eventState = operationChatReducer(
      { ...state, runId: 'new-run' },
      event(1, 'assistant_delta', { delta: '旧轮' }),
    );
    expect(eventState.messages).toHaveLength(0);
  });
  it('新一轮提交尚未绑定 Run 时拒绝旧 Run 的迟到事件', () => {
    const next = operationChatReducer(
      {
        ...createInitialOperationChatState(),
        status: 'succeeded',
        runId: 'old-run',
        requestId: 'old-request',
      },
      { type: 'submit_started', requestId: 'new-request', content: '新一轮' },
    );
    const oldEvent = event(1, 'assistant_delta', { delta: '旧轮迟到正文' });
    if (oldEvent.type !== 'sse_event') throw new Error('test setup');
    const polluted = operationChatReducer(next, {
      type: 'sse_event',
      event: { ...oldEvent.event, run_id: 'old-run' },
    });

    expect(polluted.status).toBe('submitting');
    expect(polluted.messages).toHaveLength(1);
    expect(polluted.messages[0]?.content).toBe('新一轮');
    expect(polluted.lastEventId).toBeNull();
  });
  it('终态后忽略迟到的正文和生命周期事件，避免状态回退', () => {
    const done = reduce([
      event(1, 'assistant_delta', { delta: '已完成的正文' }),
      event(2, 'stream_done', { status: 'succeeded', degraded: false }),
    ]);
    const delayed = [
      event(3, 'assistant_delta', { delta: '迟到正文' }),
      event(4, 'phase_started', { phase: 'research' }),
      event(5, 'assistant_started', {}),
    ].reduce(operationChatReducer, done);

    expect(delayed.status).toBe('succeeded');
    expect(delayed.messages.at(-1)?.content).toBe('已完成的正文');
    expect(delayed.lastEventId).toBe('2');
  });
  it('澄清后忽略同一 Run 的迟到正文和助手生命周期事件', () => {
    const state = reduce([
      event(1, 'assistant_delta', { delta: '已展示部分' }),
      event(2, 'clarification_required', { question: '还需要目标平台吗？', fields: ['platform'] }),
      event(3, 'assistant_delta', { delta: '迟到正文' }),
      event(4, 'assistant_started', {}),
      event(5, 'phase_started', { phase: 'research' }),
    ]);

    expect(state.status).toBe('waiting_input');
    expect(state.messages.at(-1)?.content).toBe('已展示部分');
    expect(state.messages.at(-1)?.frozen).toBe(true);
    expect(state.lastEventId).toBe('2');
  });

  it('失败冻结的助手消息在新一轮提交后保留自身冻结状态', () => {
    const failed = reduce([
      { type: 'submit_started', requestId: 'first', content: '第一轮' },
      { type: 'run_created', runId: 'run-1', requestId: 'first' },
      event(1, 'assistant_delta', { delta: '部分正文' }),
      event(2, 'stream_error', { safe_message: '服务暂时不可用' }),
    ]);
    const next = operationChatReducer(failed, {
      type: 'submit_started',
      requestId: 'second',
      content: '第二轮',
    });

    expect(next.messages.at(-2)).toMatchObject({
      role: 'assistant',
      content: '部分正文',
      frozen: true,
    });
  });

  it('新一轮提交会清除上一轮交付物，避免结果归属混淆', () => {
    const previous = {
      ...createInitialOperationChatState(),
      status: 'succeeded' as const,
      deliverableSets: [
        {
          contract_version: 'deliverable-set/1' as const,
          summary: '上一轮',
          degraded: false,
          deliverables: [],
        },
      ],
    };

    const next = operationChatReducer(previous, {
      type: 'submit_started',
      requestId: 'next',
      content: '新的问题',
    });

    expect(next.deliverableSets).toEqual([]);
  });

  it('保存 V2 集合并将真实安全阶段映射为用户文案', () => {
    const state = reduce([
      event(1, 'research_started', { phase: 'collecting_sources', completed: 4, target: 9 }),
      event(2, 'deliverable', { deliverable_set: deliverableSetV2() }),
    ]);

    expect(state.visiblePhase).toEqual({
      phase: 'collecting_sources',
      label: '正在收集公开来源',
      completed: 4,
      target: 9,
    });
    expect(state.phaseProgress).toEqual({ completed: 4, target: 9 });
    expect(state.deliverableSets[0]?.contract_version).toBe('deliverable-set/2');
  });

  it('拒绝无效 V2 且不将原始 JSON 作为消息显示', () => {
    const invalidV2 = { ...deliverableSetV2(), unexpected: true };
    const state = reduce([event(1, 'deliverable', { deliverable_set: invalidV2 })]);

    expect(state.deliverableSets).toEqual([]);
    expect(state.messages).toEqual([]);
  });

  it('忽略未知阶段和无效计数，但仍记录权威事件序号', () => {
    const state = reduce([
      event(1, 'phase_started', { phase: 'collecting_sources', completed: 1, target: 2 }),
      event(2, 'quality_checked', { phase: 'private_reasoning', completed: 2, target: 2 }),
      event(3, 'content_generation_started', {
        phase: 'creating_content',
        completed: -1,
        target: 2,
      }),
    ]);

    expect(state.visiblePhase).toEqual({ phase: 'creating_content', label: '正在生成运营内容' });
    expect(state.phaseProgress).toBeNull();
    expect(state.lastEventId).toBe('3');
  });

  it('拒绝对象原型上的伪阶段名', () => {
    const state = reduce([event(1, 'phase_started', { phase: 'toString' })]);

    expect(state.visiblePhase).toBeNull();
    expect(state.phaseProgress).toBeNull();
    expect(state.lastEventId).toBe('1');
  });

  it('在提交、失败、取消和终态时清理或冻结真实阶段', () => {
    const started = reduce([
      event(1, 'phase_started', { phase: 'collecting_sources', completed: 1, target: 2 }),
    ]);
    const submitted = operationChatReducer(started, {
      type: 'submit_started',
      requestId: 'next',
      content: '下一轮',
    });
    expect(submitted.visiblePhase).toBeNull();
    expect(submitted.phaseProgress).toBeNull();

    const active = { ...started, requestId: 'r' };
    const failed = operationChatReducer(active, {
      type: 'local_failed',
      requestId: 'r',
      message: '失败',
    });
    expect(failed.visiblePhase).toEqual(started.visiblePhase);
    expect(failed.phaseProgress).toEqual(started.phaseProgress);

    const cancelled = operationChatReducer(started, { type: 'cancelled' });
    expect(cancelled.visiblePhase).toEqual(started.visiblePhase);
    expect(cancelled.phaseProgress).toEqual(started.phaseProgress);

    const done = operationChatReducer(
      started,
      event(2, 'stream_done', { status: 'succeeded', degraded: false }),
    );
    expect(done.visiblePhase).toEqual(started.visiblePhase);
    expect(done.phaseProgress).toEqual(started.phaseProgress);
  });

  it('仅接受已绑定且仍活跃 Run 的 SSE，reset 后的 V1/V2 阶段和交付都不能复活界面', () => {
    const v1 = {
      contract_version: 'deliverable-set/1',
      summary: '旧交付',
      degraded: false,
      deliverables: [],
    };
    const v2 = deliverableSetV2();
    const active = operationChatReducer(
      operationChatReducer(createInitialOperationChatState(), {
        type: 'submit_started',
        requestId: 'request-1',
        content: '收集热点',
      }),
      { type: 'run_created', runId: 'run-1', requestId: 'request-1' },
    );
    const mismatchedV2 = event(1, 'deliverable', {
      deliverable_set: { ...v2, run_id: 'another-run' },
    });
    const afterMismatchedV2 = operationChatReducer(active, mismatchedV2);
    expect(afterMismatchedV2.deliverableSets).toEqual([]);

    const reset = operationChatReducer(afterMismatchedV2, { type: 'reset' });
    const lateEvents = [
      event(2, 'phase_started', { phase: 'collecting_sources', completed: 1, target: 2 }),
      event(3, 'deliverable', v1),
      event(4, 'deliverable', { deliverable_set: v2 }),
    ].reduce(operationChatReducer, reset);
    expect(lateEvents).toEqual(reset);
  });

  it('取消中冻结阶段和交付，取消失败恢复 streaming 后才能接收当前 Run 的阶段', () => {
    const started = reduce([
      event(1, 'phase_started', { phase: 'collecting_sources', completed: 1, target: 3 }),
    ]);
    const cancelling = operationChatReducer(
      { ...started, requestId: 'request-1' },
      { type: 'cancel_requested', runId: 'run-1', requestId: 'request-1' },
    );
    const frozen = [
      event(2, 'phase_started', { phase: 'creating_content', completed: 2, target: 3 }),
      event(3, 'deliverable', { deliverable_set: deliverableSetV2() }),
    ].reduce(operationChatReducer, cancelling);
    expect(frozen.status).toBe('cancelling');
    expect(frozen.visiblePhase).toEqual(started.visiblePhase);
    expect(frozen.phaseProgress).toEqual(started.phaseProgress);
    expect(frozen.deliverableSets).toEqual([]);

    const resumed = operationChatReducer(frozen, {
      type: 'cancel_failed',
      runId: 'run-1',
      requestId: 'request-1',
      message: '取消失败',
    });
    const progressed = operationChatReducer(
      resumed,
      event(4, 'phase_started', { phase: 'creating_content', completed: 2, target: 3 }),
    );
    expect(progressed.status).toBe('streaming');
    expect(progressed.visiblePhase).toMatchObject({ phase: 'creating_content' });
  });

  it('reset 与终态后忽略迟到的本地生命周期动作，不能重建或回退会话', () => {
    const reset = operationChatReducer(
      operationChatReducer(createInitialOperationChatState(), {
        type: 'submit_started',
        requestId: 'request-1',
        content: '收集热点',
      }),
      { type: 'reset' },
    );
    const staleAfterReset = [
      { type: 'run_created', runId: 'run-1', requestId: 'request-1' } as const,
      { type: 'cancel_requested', runId: null, requestId: null } as const,
      { type: 'cancelled' } as const,
      { type: 'local_failed', requestId: 'request-1', message: '旧请求失败' } as const,
    ].reduce(operationChatReducer, reset);
    expect(staleAfterReset).toEqual(reset);

    const terminal = reduce([event(1, 'stream_done', { status: 'succeeded', degraded: false })]);
    const staleActions: OperationChatEvent[] = [
      { type: 'run_created', runId: 'run-2', requestId: 'request-1' },
      { type: 'cancel_requested', runId: 'run-1', requestId: 'request-1' },
      { type: 'cancelled', runId: 'run-1', requestId: 'request-1' },
      { type: 'local_failed', requestId: 'request-1', message: '迟到失败' },
    ];
    staleActions.forEach((staleAction) => {
      expect(operationChatReducer(terminal, staleAction)).toEqual(terminal);
    });
  });
});
