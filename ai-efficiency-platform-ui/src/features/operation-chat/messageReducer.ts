import {
  parseDeliverableSet,
  type OperationChatStatus,
  type DeliverableSetDto,
  type OperationPhaseProgress,
  type OperationVisiblePhase,
  type StreamEventV1,
  type VisibleOperationPhase,
} from './types';

export interface OperationChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: number;
  frozen?: boolean;
}
export interface OperationChatState {
  status: OperationChatStatus;
  runId: string | null;
  requestId: string | null;
  cancellationRunId: string | null;
  messages: OperationChatMessage[];
  clarification: { question: string; fields: string[] } | null;
  deliverableSets: DeliverableSetDto[];
  visiblePhase: VisibleOperationPhase | null;
  phaseProgress: OperationPhaseProgress | null;
  error: string | null;
  lastEventId: string | null;
  seenEventIds: string[];
}
export type OperationChatEvent =
  | { type: 'submit_started'; requestId: string; content: string }
  | { type: 'run_created'; runId: string; requestId: string }
  | { type: 'sse_event'; event: StreamEventV1 }
  | { type: 'local_failed'; message: string; requestId: string }
  | { type: 'cancel_requested'; runId: string | null; requestId: string | null }
  | { type: 'cancelled'; runId?: string; requestId?: string }
  | { type: 'cancel_failed'; runId: string; requestId: string; message: string }
  | { type: 'reset' };

export function createInitialOperationChatState(): OperationChatState {
  return {
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
  };
}
const phaseLabels: Record<OperationVisiblePhase, string> = {
  understanding_request: '正在理解目标与约束',
  collecting_sources: '正在收集公开来源',
  checking_evidence: '正在去重并核验信息',
  creating_content: '正在生成运营内容',
  checking_delivery: '正在检查来源与格式',
};
const operationStageEvents = new Set<StreamEventV1['event']>([
  'phase_started',
  'research_started',
  'research_completed',
  'content_generation_started',
  'content_generation_completed',
  'quality_checked',
]);

function readVisiblePhase(payload: Record<string, unknown>): {
  visiblePhase: VisibleOperationPhase;
  phaseProgress: OperationPhaseProgress | null;
} | null {
  const phase = payload.phase;
  if (typeof phase !== 'string' || !Object.hasOwn(phaseLabels, phase)) return null;
  const completed = payload.completed;
  const target = payload.target;
  const validCounts =
    typeof completed === 'number' &&
    Number.isSafeInteger(completed) &&
    completed >= 0 &&
    typeof target === 'number' &&
    Number.isSafeInteger(target) &&
    target >= 0 &&
    completed <= target;
  const phaseProgress = validCounts ? { completed, target } : null;
  return {
    visiblePhase: {
      phase: phase as OperationVisiblePhase,
      label: phaseLabels[phase as OperationVisiblePhase],
      ...(phaseProgress ?? {}),
    },
    phaseProgress,
  };
}
function isTerminalStatus(status: OperationChatStatus): boolean {
  return (
    status === 'succeeded' ||
    status === 'degraded_succeeded' ||
    status === 'failed' ||
    status === 'cancelled'
  );
}
function hasActiveRequest(
  state: OperationChatState,
  requestId: string | null | undefined,
): boolean {
  return requestId !== null && requestId !== undefined && state.requestId === requestId;
}
function withAssistantMessage(state: OperationChatState, content: string): OperationChatState {
  const last = state.messages.at(-1);
  if (last?.role === 'assistant')
    return { ...state, messages: [...state.messages.slice(0, -1), { ...last, content }] };
  return {
    ...state,
    messages: [
      ...state.messages,
      { id: `assistant-${Date.now()}`, role: 'assistant', content, createdAt: Date.now() },
    ],
  };
}
function freezeCurrentAssistantMessage(state: OperationChatState): OperationChatState {
  const last = state.messages.at(-1);
  if (last?.role !== 'assistant' || last.frozen) return state;
  return { ...state, messages: [...state.messages.slice(0, -1), { ...last, frozen: true }] };
}

export function operationChatReducer(
  state: OperationChatState,
  action: OperationChatEvent,
): OperationChatState {
  if (action.type === 'reset') return createInitialOperationChatState();
  if (action.type === 'submit_started')
    return {
      ...state,
      status: 'submitting',
      runId: null,
      requestId: action.requestId,
      cancellationRunId: null,
      error: null,
      clarification: null,
      deliverableSets: [],
      visiblePhase: null,
      phaseProgress: null,
      messages: [
        ...state.messages,
        {
          id: `user-${action.requestId}`,
          role: 'user',
          content: action.content,
          createdAt: Date.now(),
        },
      ],
    };
  if (action.type === 'run_created') {
    if (
      !hasActiveRequest(state, action.requestId) ||
      state.runId !== null ||
      (state.status !== 'submitting' && state.status !== 'cancelling')
    )
      return state;
    const cancellationPending = state.status === 'cancelling';
    return {
      ...state,
      runId: action.runId,
      status: cancellationPending ? 'cancelling' : 'streaming',
      cancellationRunId: cancellationPending ? action.runId : state.cancellationRunId,
    };
  }
  if (action.type === 'local_failed')
    return !hasActiveRequest(state, action.requestId) ||
      (state.status !== 'submitting' &&
        state.status !== 'streaming' &&
        !(state.status === 'cancelling' && state.runId === null))
      ? state
      : { ...freezeCurrentAssistantMessage(state), status: 'failed', error: action.message };
  if (action.type === 'cancel_requested') {
    const validSubmitting =
      state.status === 'submitting' && state.runId === null && action.runId === null;
    const validStreaming =
      state.status === 'streaming' && state.runId !== null && state.runId === action.runId;
    return !hasActiveRequest(state, action.requestId) || (!validSubmitting && !validStreaming)
      ? state
      : { ...state, status: 'cancelling', cancellationRunId: action.runId, error: null };
  }
  if (action.type === 'cancelled') {
    if (
      state.status !== 'cancelling' ||
      !hasActiveRequest(state, action.requestId) ||
      action.runId === undefined ||
      (state.runId !== null && state.runId !== action.runId)
    )
      return state;
    return {
      ...freezeCurrentAssistantMessage(state),
      runId: action.runId,
      status: 'cancelled',
      cancellationRunId: null,
    };
  }
  if (action.type === 'cancel_failed')
    return state.requestId !== action.requestId ||
      state.runId !== action.runId ||
      state.status !== 'cancelling'
      ? state
      : { ...state, status: 'streaming', error: action.message, cancellationRunId: null };
  const { event } = action;
  // SSE 只能驱动当前已由 POST 结果绑定的 Run；不能让 reset/idle 或旧轮事件重建界面。
  if (
    state.runId === null ||
    state.runId !== event.run_id ||
    state.status === 'idle' ||
    state.status === 'submitting'
  )
    return state;
  if (isTerminalStatus(state.status)) return state;
  // 取消请求尚未得到确认时，不展示可能已经失效的阶段或交付；取消失败后会恢复 streaming。
  if (
    state.status === 'cancelling' &&
    (operationStageEvents.has(event.event) || event.event === 'deliverable')
  )
    return state;
  if (
    state.status === 'waiting_input' &&
    (event.event === 'assistant_delta' ||
      event.event === 'assistant_started' ||
      operationStageEvents.has(event.event))
  )
    return state;
  const eventKey = `${event.run_id}:${event.sequence}`;
  if (state.seenEventIds.includes(eventKey)) return state;
  const base = {
    ...state,
    lastEventId: String(event.sequence),
    seenEventIds: [...state.seenEventIds, eventKey].slice(-200),
  };
  switch (event.event) {
    case 'run_started':
    case 'assistant_started':
    case 'intent_detected':
    case 'usage_update':
      return {
        ...base,
        status:
          base.status === 'waiting_input' || base.status === 'cancelling'
            ? base.status
            : 'streaming',
      };
    case 'phase_started':
    case 'research_started':
    case 'research_completed':
    case 'content_generation_started':
    case 'content_generation_completed':
    case 'quality_checked': {
      const progress = readVisiblePhase(event.payload);
      return {
        ...base,
        ...(progress ?? {}),
        status:
          base.status === 'waiting_input' || base.status === 'cancelling'
            ? base.status
            : 'streaming',
      };
    }
    case 'assistant_delta': {
      const delta = typeof event.payload.delta === 'string' ? event.payload.delta : '';
      const previous =
        base.messages.at(-1)?.role === 'assistant' ? (base.messages.at(-1)?.content ?? '') : '';
      return withAssistantMessage(
        { ...base, status: base.status === 'waiting_input' ? 'waiting_input' : 'streaming' },
        previous + delta,
      );
    }
    case 'clarification_required':
      return {
        ...freezeCurrentAssistantMessage(base),
        status: 'waiting_input',
        clarification: {
          question:
            typeof event.payload.question === 'string'
              ? event.payload.question
              : '请补充更多信息。',
          fields: Array.isArray(event.payload.fields)
            ? event.payload.fields.filter((field): field is string => typeof field === 'string')
            : [],
        },
      };
    case 'deliverable': {
      const set = parseDeliverableSet(event.payload.deliverable_set ?? event.payload);
      if (set?.contract_version === 'deliverable-set/2' && set.run_id !== event.run_id) return base;
      return set ? { ...base, deliverableSets: [...base.deliverableSets, set] } : base;
    }
    case 'stream_error':
      return {
        ...freezeCurrentAssistantMessage(base),
        status: 'failed',
        error:
          typeof event.payload.safe_message === 'string'
            ? event.payload.safe_message
            : '运营助手暂时无法完成请求。',
      };
    case 'stream_done': {
      const status = event.payload.status;
      const degraded = event.payload.degraded === true;
      const nextStatus: OperationChatStatus =
        status === 'cancelled'
          ? 'cancelled'
          : status === 'succeeded' && degraded
            ? 'degraded_succeeded'
            : status === 'succeeded'
              ? 'succeeded'
              : 'failed';
      const nextState: OperationChatState = {
        ...base,
        cancellationRunId: null,
        status: nextStatus,
      };
      return nextState.status === 'succeeded' || nextState.status === 'degraded_succeeded'
        ? nextState
        : freezeCurrentAssistantMessage(nextState);
    }
  }
}
