import { computed, shallowRef, ref, onMounted, onBeforeUnmount } from 'vue';

import type {
  Conversation,
  MessageView,
  PublicProgress,
} from '../../entities/customer-service/model';
import {
  cancelRun,
  createConversation,
  deleteConversation,
  getRun,
  getTimeline,
  listConversations,
  listMessages,
  renameConversation as saveConversationTitle,
  submitMessage,
} from './api';
import { connectCustomerServiceRun } from './sseClient';

export type ChatStatus = 'IDLE' | 'SUBMITTING' | 'STREAMING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED';
export interface CustomerServiceChatState {
  conversations: Conversation[];
  conversationId?: string;
  messages: MessageView[];
  status: ChatStatus;
  progressByRun: Record<string, PublicProgress[]>;
  runId?: string;
  sequence: number;
  error?: string;
  traceId?: string;
}

const empty: CustomerServiceChatState = {
  conversations: [],
  messages: [],
  status: 'IDLE',
  sequence: 0,
  progressByRun: {},
};

function findAssistantIndex(messages: MessageView[], runId: string) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const item = messages[index];
    if (item.message.role === 'ASSISTANT' && item.message.runId === runId) return index;
  }
  return -1;
}

export function useCustomerServiceChat() {
  const state = shallowRef(empty);
  const setState = (
    value: typeof state.value | ((current: typeof state.value) => typeof state.value),
  ) => {
    state.value = typeof value === 'function' ? value(state.value) : value;
  };
  const abortRef = ref<AbortController | undefined>(undefined);
  const selectedConversationRef = ref<string | undefined>(undefined);
  const conversationListRequestRef = ref(0);
  let generation = 0;
  let disposed = false;
  let activeRequestId: string | undefined;
  let cancelRequestedRequestId: string | undefined;
  onBeforeUnmount(() => {
    disposed = true;
    generation += 1;
    abortRef.value?.abort();
  });
  const busy = computed(
    () => state.value.status === 'SUBMITTING' || state.value.status === 'STREAMING',
  );
  const refreshConversations = async () => {
    const request = ++conversationListRequestRef.value;
    const page = await listConversations();
    if (!disposed && request === conversationListRequestRef.value)
      setState((value) => ({ ...value, conversations: page.items }));
    return page.items;
  };
  const consume = async (runId: string, afterSequence = 0, conversationId?: string) => {
    const currentGeneration = generation;
    abortRef.value?.abort();
    const controller = new AbortController();
    abortRef.value = controller;
    setState((value) => ({ ...value, runId, status: 'STREAMING', sequence: afterSequence }));
    try {
      for await (const event of connectCustomerServiceRun(runId, {
        afterSequence,
        signal: controller.signal,
      })) {
        if (disposed || controller.signal.aborted || generation !== currentGeneration) break;
        if (event.event === 'run.progress' && event.payload.stage === 'conversation_title')
          void refreshConversations().catch(() => undefined);
        setState((current) => {
          if (current.runId !== runId || event.id <= current.sequence) return current;
          if (event.event === 'message.delta') {
            const messages = [...current.messages];
            const index = findAssistantIndex(messages, runId);
            if (index >= 0)
              messages[index] = {
                ...messages[index],
                message: {
                  ...messages[index].message,
                  content: `${messages[index].message.content}${messages[index].message.content ? '\n\n' : ''}${event.payload.delta}`,
                  status: 'STREAMING',
                },
              };
            return { ...current, messages, sequence: event.id };
          }
          if (event.event === 'citation.ready') {
            const messages = [...current.messages];
            const index = findAssistantIndex(messages, runId);
            if (
              index >= 0 &&
              !messages[index].citations.some((item) => item.id === event.payload.id)
            )
              messages[index] = {
                ...messages[index],
                citations: [...messages[index].citations, event.payload],
              };
            return { ...current, messages, sequence: event.id };
          }
          if (event.event === 'run.progress' || event.event === 'run.started') {
            const phase = event.payload.phase;
            if (!phase) return { ...current, sequence: event.id };
            const previous = current.progressByRun[runId] ?? [];
            const step: PublicProgress = {
              sequence: event.id,
              stage: event.payload.stage,
              phase,
              summary: event.payload.summary,
            };
            return {
              ...current,
              sequence: event.id,
              progressByRun: {
                ...current.progressByRun,
                [runId]: [...previous.filter((item) => item.stage !== step.stage), step],
              },
            };
          }
          if (event.event === 'run.completed')
            return {
              ...current,
              sequence: event.id,
              status: 'SUCCEEDED',
              messages: current.messages.map((item) =>
                item.message.runId === runId && item.message.role === 'ASSISTANT'
                  ? {
                      ...item,
                      message: {
                        ...item.message,
                        status: 'COMPLETED',
                        answerMode: event.payload.answerMode,
                      },
                    }
                  : item,
              ),
            };
          if (event.event === 'run.cancelled')
            return {
              ...current,
              sequence: event.id,
              status: 'CANCELLED',
              messages: current.messages.map((item) =>
                item.message.runId === runId && item.message.role === 'ASSISTANT'
                  ? {
                      ...item,
                      message: { ...item.message, status: 'CANCELLED', answerMode: null },
                    }
                  : item,
              ),
            };
          return {
            ...current,
            sequence: event.id,
            status: 'FAILED',
            error: `${event.payload.errorMessage}（${event.payload.errorCode}）`,
            messages: current.messages.map((item) =>
              item.message.runId === runId && item.message.role === 'ASSISTANT'
                ? { ...item, message: { ...item.message, status: 'FAILED', answerMode: null } }
                : item,
            ),
          };
        });
      }
    } catch (error) {
      if (!disposed && !controller.signal.aborted && generation === currentGeneration)
        setState((value) => ({
          ...value,
          status: 'FAILED',
          error: error instanceof Error ? error.message : '流式连接失败',
        }));
    } finally {
      if (!controller.signal.aborted) {
        const currentRun = await getRun(runId).catch(() => null);
        if (conversationId) {
          const persisted = await listMessages(conversationId).catch(() => null);
          if (
            persisted &&
            !disposed &&
            !controller.signal.aborted &&
            generation === currentGeneration &&
            state.value.conversationId === conversationId &&
            state.value.runId === runId
          )
            setState((value) => ({
              ...value,
              messages: persisted,
              status: currentRun?.status === 'SUCCEEDED' ? 'SUCCEEDED' : value.status,
            }));
        }
      }
    }
  };
  const selectConversation = async (conversationId: string) => {
    const currentGeneration = ++generation;
    selectedConversationRef.value = conversationId;
    abortRef.value?.abort();
    const messages = await listMessages(conversationId);
    if (
      disposed ||
      generation !== currentGeneration ||
      selectedConversationRef.value !== conversationId
    )
      return;
    const pending = messages.find(
      (item) =>
        item.message.role === 'ASSISTANT' && ['PENDING', 'STREAMING'].includes(item.message.status),
    );
    setState((value) => ({
      ...value,
      conversationId,
      messages,
      status: pending ? 'STREAMING' : 'IDLE',
      runId: pending?.message.runId ?? undefined,
      sequence: 0,
      progressByRun: {},
      error: undefined,
    }));
    const runIds = [
      ...new Set(
        messages.flatMap((item) =>
          item.message.role === 'ASSISTANT' && item.message.runId ? [item.message.runId] : [],
        ),
      ),
    ];
    const timelines = await Promise.all(
      runIds.map((runId) => getTimeline(runId).catch(() => null)),
    );
    if (
      disposed ||
      generation !== currentGeneration ||
      selectedConversationRef.value !== conversationId
    )
      return;
    setState((value) => {
      if (value.conversationId !== conversationId) return value;
      const updated = [...value.messages];
      const progressByRun = { ...value.progressByRun };
      for (const timeline of timelines) {
        if (!timeline) continue;
        progressByRun[timeline.runId] = timeline.steps;
        const index = findAssistantIndex(updated, timeline.runId);
        if (index >= 0) updated[index] = timeline.assistant;
      }
      return { ...value, messages: updated, progressByRun };
    });
    const active = timelines.find(
      (timeline) => timeline && ['PENDING', 'RUNNING'].includes(timeline.status),
    );
    if (active) void consume(active.runId, active.lastEventSequence, conversationId);
  };
  (() => {
    let cleanup0: (() => void) | undefined;
    onMounted(() => {
      cleanup0 = (() => {
        let active = true;
        const timer = window.setTimeout(() => {
          void refreshConversations()
            .then(async (items) => {
              if (!active) return;
              if (active && items[0]) await selectConversation(items[0].id);
            })
            .catch((error: Error & { traceId?: string }) =>
              setState((value) => ({
                ...value,
                status: 'FAILED',
                error: error.message,
                traceId: error.traceId,
              })),
            );
        }, 0);
        return () => {
          active = false;
          window.clearTimeout(timer);
          abortRef.value?.abort();
        };
      })();
    });
    onBeforeUnmount(() => cleanup0?.());
  })();
  const newConversation = async () => {
    if (busy.value) return;
    generation += 1;
    selectedConversationRef.value = undefined;
    abortRef.value?.abort();
    setState((value) => ({
      ...value,
      conversationId: undefined,
      messages: [],
      status: 'IDLE',
      runId: undefined,
      sequence: 0,
      progressByRun: {},
      error: undefined,
    }));
  };
  const removeConversation = async (id: string) => {
    if (busy.value) return;
    try {
      await deleteConversation(id);
      const remaining = await refreshConversations();
      if (state.value.conversationId !== id) return;
      if (remaining[0]) await selectConversation(remaining[0].id);
      else await newConversation();
    } catch (error) {
      setState((value) => ({
        ...value,
        error: error instanceof Error ? error.message : '删除会话失败',
      }));
    }
  };
  const renameConversation = async (id: string, title: string) => {
    const conversation = await saveConversationTitle(id, title);
    conversationListRequestRef.value += 1;
    setState((value) => ({
      ...value,
      conversations: value.conversations.map((item) => (item.id === id ? conversation : item)),
    }));
  };
  const send = async (text: string) => {
    if (busy.value || !text.trim()) return;
    const requestId = crypto.randomUUID();
    const currentGeneration = ++generation;
    activeRequestId = requestId;
    cancelRequestedRequestId = undefined;
    abortRef.value?.abort();
    const now = new Date().toISOString();
    setState((value) => ({ ...value, runId: undefined, status: 'SUBMITTING', error: undefined }));
    let conversationId = state.value.conversationId;
    try {
      if (!conversationId) {
        const conversation = await createConversation('');
        if (disposed || generation !== currentGeneration) return;
        conversationId = conversation.id;
        selectedConversationRef.value = conversation.id;
        setState((value) => ({ ...value, conversationId: conversation.id }));
        await refreshConversations();
        if (disposed || generation !== currentGeneration) return;
      }
      const activeConversationId = conversationId;
      const user: MessageView = {
        message: {
          id: `local-user-${requestId}`,
          conversationId: activeConversationId,
          tenantId: 'dev',
          role: 'USER',
          content: text.trim(),
          status: 'COMPLETED',
          answerMode: null,
          runId: null,
          clientRequestId: requestId,
          createdAt: now,
        },
        citations: [],
      };
      setState((value) => ({
        ...value,
        messages: [
          ...value.messages,
          user,
          {
            message: {
              id: `local-assistant-${requestId}`,
              conversationId: activeConversationId,
              tenantId: 'dev',
              role: 'ASSISTANT',
              content: '',
              status: 'PENDING',
              answerMode: null,
              runId: null,
              clientRequestId: null,
              createdAt: now,
            },
            citations: [],
          },
        ],
      }));
      const submitted = await submitMessage(activeConversationId, text.trim(), requestId);
      if (disposed || generation !== currentGeneration) return;
      setState((value) => ({
        ...value,
        messages: value.messages.map((item) =>
          item.message.id === `local-assistant-${requestId}`
            ? { ...item, message: { ...item.message, runId: submitted.runId, status: 'STREAMING' } }
            : item,
        ),
        runId: submitted.runId,
      }));
      if (cancelRequestedRequestId === requestId) {
        await cancel();
        if (state.value.status === 'CANCELLED' || disposed || generation !== currentGeneration)
          return;
      }
      await consume(submitted.runId, 0, activeConversationId);
      await refreshConversations().catch(() => undefined);
    } catch (error) {
      if (disposed || generation !== currentGeneration) return;
      const value = error as Error & { traceId?: string };
      setState((current) => ({
        ...current,
        messages: current.messages.filter(
          (item) => item.message.id !== `local-assistant-${requestId}`,
        ),
        status: 'FAILED',
        error: value.message,
        traceId: value.traceId,
      }));
    }
  };
  const cancel = async () => {
    if (!busy.value) return;
    if (state.value.status === 'SUBMITTING' && !state.value.runId) {
      cancelRequestedRequestId = activeRequestId;
      return;
    }
    if (!state.value.runId) return;
    const cancellingRunId = state.value.runId;
    const controller = abortRef.value;
    const cancelled = await cancelRun(cancellingRunId);
    if (cancelled.status !== 'CANCELLED') return;
    controller?.abort();
    setState((value) =>
      value.runId !== cancellingRunId
        ? value
        : {
            ...value,
            status: 'CANCELLED',
            messages: value.messages.map((item) =>
              item.message.runId === cancellingRunId && item.message.role === 'ASSISTANT'
                ? { ...item, message: { ...item.message, status: 'CANCELLED', answerMode: null } }
                : item,
            ),
          },
    );
  };
  return {
    state,
    busy,
    send,
    cancel,
    selectConversation,
    newConversation,
    removeConversation,
    renameConversation,
  };
}
