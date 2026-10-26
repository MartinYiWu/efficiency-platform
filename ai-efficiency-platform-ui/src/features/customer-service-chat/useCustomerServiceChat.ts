import { useCallback, useEffect, useRef, useState } from 'react';

import type { Conversation, MessageView, PublicProgress } from '../../entities/customer-service/model';
import {
  cancelRun,
  createConversation,
  getRun,
  getTimeline,
  listConversations,
  listMessages,
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
  const [state, setState] = useState(empty);
  const abortRef = useRef<AbortController | undefined>(undefined);
  const selectedConversationRef = useRef<string | undefined>(undefined);
  const busy = state.status === 'SUBMITTING' || state.status === 'STREAMING';
  const refreshConversations = useCallback(async () => {
    const page = await listConversations();
    setState((value) => ({ ...value, conversations: page.items }));
    return page.items;
  }, []);
  const consume = useCallback(async (runId: string, afterSequence = 0, conversationId?: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState((value) => ({ ...value, runId, status: 'STREAMING', sequence: afterSequence }));
    try {
      for await (const event of connectCustomerServiceRun(runId, {
        afterSequence,
        signal: controller.signal,
      })) {
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
            };
          return {
            ...current,
            sequence: event.id,
            status: 'FAILED',
            error: `${event.payload.errorMessage}（${event.payload.errorCode}）`,
          };
        });
      }
    } catch (error) {
      if (!controller.signal.aborted)
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
          if (persisted)
            setState((value) => ({
              ...value,
              messages: persisted,
              status: currentRun?.status === 'SUCCEEDED' ? 'SUCCEEDED' : value.status,
            }));
        }
      }
    }
  }, []);
  const selectConversation = useCallback(
    async (conversationId: string) => {
      selectedConversationRef.current = conversationId;
      abortRef.current?.abort();
      const messages = await listMessages(conversationId);
      if (selectedConversationRef.current !== conversationId) return;
      const pending = messages.find((item) =>
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
      const runIds = [...new Set(messages.flatMap((item) =>
        item.message.role === 'ASSISTANT' && item.message.runId ? [item.message.runId] : [],
      ))];
      const timelines = await Promise.all(runIds.map((runId) => getTimeline(runId).catch(() => null)));
      if (selectedConversationRef.current !== conversationId) return;
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
      const active = timelines.find((timeline) =>
        timeline && ['PENDING', 'RUNNING'].includes(timeline.status),
      );
      if (active) void consume(active.runId, active.lastEventSequence, conversationId);
    },
    [consume],
  );
  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      void refreshConversations()
        .then(async (items) => {
          if (!active) return;
          let first = items[0];
          if (!first) first = await createConversation('新对话');
          if (active) await selectConversation(first.id);
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
      abortRef.current?.abort();
    };
  }, [refreshConversations, selectConversation]);
  const newConversation = async () => {
    if (busy) return;
    const conversation = await createConversation('新对话');
    await refreshConversations();
    await selectConversation(conversation.id);
  };
  const send = async (text: string) => {
    if (busy || !state.conversationId || !text.trim()) return;
    const conversationId = state.conversationId;
    const requestId = crypto.randomUUID();
    const now = new Date().toISOString();
    const user: MessageView = {
      message: {
        id: `local-user-${requestId}`,
        conversationId,
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
      messages: [...value.messages, user, {
        message: {
          id: `local-assistant-${requestId}`,
          conversationId,
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
      }],
      status: 'SUBMITTING',
      error: undefined,
    }));
    try {
      const submitted = await submitMessage(conversationId, text.trim(), requestId);
      setState((value) => ({
        ...value,
        messages: value.messages.map((item) =>
          item.message.id === `local-assistant-${requestId}`
            ? { ...item, message: { ...item.message, runId: submitted.runId, status: 'STREAMING' } }
            : item,
        ),
        runId: submitted.runId,
      }));
      await consume(submitted.runId, 0, conversationId);
      await refreshConversations();
    } catch (error) {
      const value = error as Error & { traceId?: string };
      setState((current) => ({
        ...current,
        messages: current.messages.filter((item) => item.message.id !== `local-assistant-${requestId}`),
        status: 'FAILED',
        error: value.message,
        traceId: value.traceId,
      }));
    }
  };
  const cancel = async () => {
    if (!state.runId || !busy) return;
    await cancelRun(state.runId);
    abortRef.current?.abort();
    setState((value) => ({ ...value, status: 'CANCELLED' }));
  };
  return { state, busy, send, cancel, selectConversation, newConversation };
}
