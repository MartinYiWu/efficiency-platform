import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import {
  cancelRun,
  createConversation,
  listConversationArtifacts,
  submitConversationMessage,
} from './api';
import { createInitialOperationChatState, operationChatReducer } from './messageReducer';
import { connectRunStream } from './sseClient';
import type { OperationArtifactSummary } from './types';

export interface UseOperationChatOptions {
  baseUrl?: string;
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
  const [artifacts, setArtifacts] = useState<OperationArtifactSummary[]>([]);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const activeRunRef = useRef<{ requestId: string; runId: string } | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const cancelRequestedRef = useRef(false);
  const generationRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const baseUrl = options.baseUrl ?? defaultBaseUrl();
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
      let conversationId = conversationIdRef.current;
      cancelRequestedRef.current = false;
      setArtifacts([]);
      setArtifactError(null);
      dispatch({ type: 'submit_started', requestId, content: message });
      try {
        if (!conversationId) {
          const conversation = await createConversation({
            baseUrl,
            fetcher: options.fetcher,
            signal: controller.signal,
          });
          conversationId = conversation.conversationId;
          conversationIdRef.current = conversationId;
        }
        const submitted = await submitConversationMessage(
          { conversationId, message, clientRequestId: requestId },
          { baseUrl, fetcher: options.fetcher, signal: controller.signal },
        );
        if (!isCurrent()) return;
        activeRunRef.current = { requestId, runId: submitted.runId };
        dispatch({ type: 'run_created', runId: submitted.runId, requestId });
        if (cancelRequestedRef.current) {
          try {
            const result = await cancelRun(submitted.runId, {
              baseUrl,
              fetcher: options.fetcher,
            });
            if (!isCurrent()) return;
            if (result.status === 'cancelled') {
              dispatch({ type: 'cancelled', runId: submitted.runId, requestId });
              return;
            }
          } catch (error) {
            if (isCurrent())
              dispatch({
                type: 'cancel_failed',
                runId: submitted.runId,
                requestId,
                message: error instanceof Error ? error.message : '停止请求失败，请稍后重试。',
              });
          }
        }
        for await (const event of connectRunStream(submitted.runId, {
          baseUrl,
          fetcher: options.fetcher,
          signal: controller.signal,
        })) {
          if (!isCurrent()) break;
          dispatch({ type: 'sse_event', event });
          if (event.event === 'clarification_required') break;
          if (
            event.event === 'stream_done' &&
            (event.payload.status === 'succeeded' || event.payload.status === 'degraded_succeeded')
          ) {
            try {
              setArtifacts(
                await listConversationArtifacts(conversationId, {
                  baseUrl,
                  fetcher: options.fetcher,
                  signal: controller.signal,
                }),
              );
            } catch {
              setArtifactError('成稿已生成，但复制、预览和下载操作加载失败，请稍后重试。');
            }
          }
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
    [baseUrl, options.fetcher, state.status],
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
      const result = await cancelRun(runId, { baseUrl, fetcher: options.fetcher });
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
  }, [baseUrl, options.fetcher, state.requestId, state.runId]);
  return {
    state,
    sendMessage,
    cancel,
    artifacts,
    artifactError,
    baseUrl,
    isBusy:
      state.status === 'submitting' ||
      state.status === 'streaming' ||
      state.status === 'cancelling',
  };
}
