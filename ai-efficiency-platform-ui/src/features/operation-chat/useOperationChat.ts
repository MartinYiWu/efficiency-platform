import { useCallback, useEffect, useReducer, useRef } from 'react';
import { cancelRun, submitConversationMessage } from './api';
import { createInitialOperationChatState, operationChatReducer } from './messageReducer';
import { connectRunStream } from './sseClient';

export interface UseOperationChatOptions {
  baseUrl?: string;
  tenantId?: string;
  userId?: string;
  fetcher?: typeof fetch;
}
const defaultBaseUrl = (): string => {
  const configured = import.meta.env.VITE_API_BASE_URL;
  return typeof configured === 'string' && configured.length > 0
    ? configured
    : window.location.origin;
};

export function useOperationChat(options: UseOperationChatOptions = {}) {
  const [state, dispatch] = useReducer(
    operationChatReducer,
    undefined,
    createInitialOperationChatState,
  );
  const activeRunRef = useRef<{ requestId: string; runId: string } | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const cancelRequestedRef = useRef(false);
  const generationRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const baseUrl = options.baseUrl ?? defaultBaseUrl();
  const tenantId = options.tenantId ?? 'tenant-demo';
  const userId = options.userId ?? 'web-user';
  useEffect(
    () => () => {
      generationRef.current += 1;
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
      activeRunRef.current = null;
    },
    [],
  );
  const sendMessage = useCallback(
    async (content: string) => {
      const message = content.trim();
      if (
        !message ||
        state.status === 'submitting' ||
        state.status === 'streaming' ||
        state.status === 'cancelling'
      )
        return;
      requestControllerRef.current?.abort();
      const controller = new AbortController();
      requestControllerRef.current = controller;
      const requestId = crypto.randomUUID();
      const generation = ++generationRef.current;
      const isCurrent = () => generationRef.current === generation;
      activeRunRef.current = null;
      const conversationId = conversationIdRef.current ?? crypto.randomUUID();
      conversationIdRef.current = conversationId;
      cancelRequestedRef.current = false;
      dispatch({ type: 'submit_started', requestId, content: message });
      try {
        const submitted = await submitConversationMessage(
          { conversationId, message, requestId, userId },
          { baseUrl, tenantId, fetcher: options.fetcher, signal: controller.signal },
        );
        if (!isCurrent()) return;
        activeRunRef.current = { requestId, runId: submitted.run_id };
        dispatch({ type: 'run_created', runId: submitted.run_id, requestId });
        if (cancelRequestedRef.current) {
          try {
            const result = await cancelRun(submitted.run_id, {
              baseUrl,
              tenantId,
              fetcher: options.fetcher,
            });
            if (!isCurrent()) return;
            if (result.status === 'cancelled') {
              dispatch({ type: 'cancelled', runId: submitted.run_id, requestId });
              return;
            }
          } catch (error) {
            if (isCurrent())
              dispatch({
                type: 'cancel_failed',
                runId: submitted.run_id,
                requestId,
                message: error instanceof Error ? error.message : '停止请求失败，请稍后重试。',
              });
          }
        }
        for await (const event of connectRunStream(submitted.run_id, {
          baseUrl,
          tenantId,
          fetcher: options.fetcher,
          signal: controller.signal,
        })) {
          if (!isCurrent()) break;
          dispatch({ type: 'sse_event', event });
          if (event.event === 'clarification_required') break;
        }
      } catch (error) {
        if (isCurrent())
          dispatch({
            type: 'local_failed',
            requestId,
            message:
              error instanceof Error
                ? error.message === 'SSE_RECONNECT_EXHAUSTED'
                  ? '连接已断开，请重试。'
                  : error.message
                : '请求失败，请稍后重试。',
          });
      } finally {
        if (isCurrent() && activeRunRef.current?.requestId === requestId) {
          activeRunRef.current = null;
          cancelRequestedRef.current = false;
        }
        if (requestControllerRef.current === controller) requestControllerRef.current = null;
      }
    },
    [baseUrl, options.fetcher, state.status, tenantId, userId],
  );
  const cancel = useCallback(async () => {
    cancelRequestedRef.current = true;
    const requestId = state.requestId;
    const activeRun = activeRunRef.current?.requestId === requestId ? activeRunRef.current : null;
    const runId = activeRun?.runId ?? state.runId;
    dispatch({ type: 'cancel_requested', runId, requestId });
    if (!runId) return;
    const generation = generationRef.current;
    try {
      const result = await cancelRun(runId, { baseUrl, tenantId, fetcher: options.fetcher });
      if (generation !== generationRef.current) return;
      if (result.status === 'cancelled') {
        dispatch({ type: 'cancelled', runId, requestId: requestId ?? undefined });
        requestControllerRef.current?.abort();
      }
    } catch (error) {
      if (generation === generationRef.current)
        dispatch({
          type: 'cancel_failed',
          runId,
          requestId: requestId ?? '',
          message: error instanceof Error ? error.message : '停止请求失败，请稍后重试。',
        });
    }
  }, [baseUrl, options.fetcher, state.requestId, state.runId, tenantId]);
  return {
    state,
    sendMessage,
    cancel,
    isBusy:
      state.status === 'submitting' ||
      state.status === 'streaming' ||
      state.status === 'cancelling',
  };
}
