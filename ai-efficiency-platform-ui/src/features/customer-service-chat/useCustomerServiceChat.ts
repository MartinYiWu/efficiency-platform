import { useCallback, useEffect, useRef, useState } from 'react';

import type { Conversation, MessageView } from '../../entities/customer-service/model';
import {
  cancelRun,
  createConversation,
  getRun,
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
  stage?: string;
  summary?: string;
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
                  content: `${messages[index].message.content}${event.payload.delta}`,
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
          if (event.event === 'run.progress' || event.event === 'run.started')
            return {
              ...current,
              sequence: event.id,
              stage: event.payload.stage,
              summary: event.payload.summary,
            };
          if (event.event === 'run.completed')
            return {
              ...current,
              sequence: event.id,
              status: 'SUCCEEDED',
              stage: undefined,
              summary: undefined,
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
              stage: undefined,
              summary: undefined,
            };
          return {
            ...current,
            sequence: event.id,
            status: 'FAILED',
            error: `${event.payload.errorMessage}（${event.payload.errorCode}）`,
            stage: undefined,
            summary: undefined,
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
      abortRef.current?.abort();
      const messages = await listMessages(conversationId);
      setState((value) => ({
        ...value,
        conversationId,
        messages,
        status: 'IDLE',
        runId: undefined,
        sequence: 0,
        error: undefined,
      }));
      const last = messages.at(-1)?.message;
      if (
        last?.role === 'ASSISTANT' &&
        last.runId &&
        ['PENDING', 'STREAMING'].includes(last.status)
      ) {
        const run = await getRun(last.runId);
        if (!['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(run.status))
          void consume(run.id, run.lastEventSequence, conversationId);
      }
    },
    [consume],
  );
  useEffect(() => {
    let active = true;
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
    return () => {
      active = false;
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
      messages: [...value.messages, user],
      status: 'SUBMITTING',
      error: undefined,
    }));
    try {
      const submitted = await submitMessage(conversationId, text.trim(), requestId);
      const assistant: MessageView = {
        message: {
          id: `local-assistant-${requestId}`,
          conversationId,
          tenantId: 'dev',
          role: 'ASSISTANT',
          content: '',
          status: 'STREAMING',
          answerMode: null,
          runId: submitted.runId,
          clientRequestId: null,
          createdAt: now,
        },
        citations: [],
      };
      setState((value) => ({
        ...value,
        messages: [...value.messages, assistant],
        runId: submitted.runId,
      }));
      await consume(submitted.runId, 0, conversationId);
      await refreshConversations();
    } catch (error) {
      const value = error as Error & { traceId?: string };
      setState((current) => ({
        ...current,
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
