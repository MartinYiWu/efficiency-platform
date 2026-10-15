import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import {
  cancelRun,
  createConversation,
  getConversation,
  getRun,
  listConversationArtifacts,
  listConversationMessages,
  OperationApiError,
  submitConversationMessage,
} from './api';
import { createInitialOperationChatState, operationChatReducer } from './messageReducer';
import { connectRunStream } from './sseClient';
import type { OperationArtifactSummary, OperationMessageView, OperationRunView } from './types';

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

function conversationIdFromUrl(): string | null {
  const value = new URLSearchParams(window.location.search).get('conversationId');
  return value?.trim() || null;
}

function replaceConversationId(conversationId: string | null): void {
  const current = new URL(window.location.href);
  if (conversationId) current.searchParams.set('conversationId', conversationId);
  else current.searchParams.delete('conversationId');
  window.history.replaceState(window.history.state, '', current);
}

function latestRunId(messages: OperationMessageView[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const runId = messages[index]?.runId;
    if (runId) return runId;
  }
  return null;
}

function isRunning(run: OperationRunView | null): run is OperationRunView {
  return !!run && ['submitting', 'queued', 'running'].includes(run.status);
}

export function useOperationChat(options: UseOperationChatOptions = {}) {
  const [state, dispatch] = useReducer(
    operationChatReducer,
    undefined,
    createInitialOperationChatState,
  );
  const [artifacts, setArtifacts] = useState<OperationArtifactSummary[]>([]);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [isRestoring, setIsRestoring] = useState(true);
  const activeRunRef = useRef<{ requestId: string; runId: string } | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const cancelRequestedRef = useRef(false);
  const generationRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const baseUrl = options.baseUrl ?? defaultBaseUrl();

  const reloadArtifacts = useCallback(
    async (conversationId: string, signal?: AbortSignal) => {
      try {
        setArtifacts(
          await listConversationArtifacts(conversationId, {
            baseUrl,
            fetcher: options.fetcher,
            signal,
          }),
        );
        setArtifactError(null);
      } catch {
        setArtifactError('成稿已生成，但复制、预览和下载操作加载失败，请稍后重试。');
      }
    },
    [baseUrl, options.fetcher],
  );

  const consumeRun = useCallback(
    async (
      runId: string,
      requestId: string,
      conversationId: string,
      controller: AbortController,
      generation: number,
      lastEventId?: string | null,
    ) => {
      for await (const event of connectRunStream(runId, {
        baseUrl,
        fetcher: options.fetcher,
        signal: controller.signal,
        lastEventId,
      })) {
        if (generationRef.current !== generation) break;
        dispatch({ type: 'sse_event', event });
        if (event.event === 'clarification_required') break;
        if (
          event.event === 'stream_done' &&
          (event.payload.status === 'succeeded' || event.payload.status === 'degraded_succeeded')
        ) {
          await reloadArtifacts(conversationId, controller.signal);
        }
      }
      if (activeRunRef.current?.requestId === requestId) activeRunRef.current = null;
    },
    [baseUrl, options.fetcher, reloadArtifacts],
  );

  useEffect(() => {
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const generation = ++generationRef.current;
    const isCurrent = () => generationRef.current === generation && !controller.signal.aborted;

    const restore = async () => {
      let conversationId = conversationIdFromUrl();
      try {
        if (conversationId) {
          try {
            await getConversation(conversationId, {
              baseUrl,
              fetcher: options.fetcher,
              signal: controller.signal,
            });
          } catch (error) {
            if (!(error instanceof OperationApiError) || error.status !== 404) throw error;
            conversationId = null;
            replaceConversationId(null);
          }
        }
        if (!conversationId) {
          const created = await createConversation({
            baseUrl,
            fetcher: options.fetcher,
            signal: controller.signal,
          });
          if (!isCurrent()) return;
          conversationId = created.conversationId;
          conversationIdRef.current = conversationId;
          replaceConversationId(conversationId);
          dispatch({ type: 'history_loaded', messages: [], run: null });
          return;
        }

        conversationIdRef.current = conversationId;
        const [messages, restoredArtifacts] = await Promise.all([
          listConversationMessages(conversationId, {
            baseUrl,
            fetcher: options.fetcher,
            signal: controller.signal,
          }),
          listConversationArtifacts(conversationId, {
            baseUrl,
            fetcher: options.fetcher,
            signal: controller.signal,
          }),
        ]);
        const runId = latestRunId(messages);
        const run = runId
          ? await getRun(runId, {
              baseUrl,
              fetcher: options.fetcher,
              signal: controller.signal,
            })
          : null;
        if (!isCurrent()) return;
        setArtifacts(restoredArtifacts);
        dispatch({ type: 'history_loaded', messages, run });
        if (isRunning(run)) {
          const requestId = `restored:${run.runId}`;
          activeRunRef.current = { requestId, runId: run.runId };
          await consumeRun(
            run.runId,
            requestId,
            conversationId,
            controller,
            generation,
            run.lastEventSequence > 0 ? String(run.lastEventSequence) : null,
          );
        }
      } catch (error) {
        if (isCurrent()) {
          setArtifactError(
            error instanceof Error ? error.message : '会话历史加载失败，请刷新后重试。',
          );
        }
      } finally {
        if (isCurrent()) setIsRestoring(false);
      }
    };

    void restore();
    return () => {
      generationRef.current += 1;
      requestControllerRef.current?.abort();
      controller.abort();
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
      activeRunRef.current = null;
    };
  }, [baseUrl, consumeRun, options.fetcher]);

  const sendMessage = useCallback(
    async (content: string) => {
      const message = content.trim();
      if (
        !message ||
        isRestoring ||
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
          replaceConversationId(conversationId);
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
        await consumeRun(submitted.runId, requestId, conversationId, controller, generation);
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
    [baseUrl, consumeRun, isRestoring, options.fetcher, state.status],
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
    isRestoring,
    isBusy:
      isRestoring ||
      state.status === 'submitting' ||
      state.status === 'streaming' ||
      state.status === 'cancelling',
  };
}
