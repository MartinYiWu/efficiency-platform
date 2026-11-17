import { computed, shallowRef, ref, onMounted, onBeforeUnmount } from 'vue';
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
  const state = shallowRef(createInitialOperationChatState());
  const dispatch = (event: Parameters<typeof operationChatReducer>[1]) => {
    state.value = operationChatReducer(state.value, event);
  };
  const artifacts = shallowRef<OperationArtifactSummary[]>([]);
  const setArtifacts = (
    value: typeof artifacts.value | ((current: typeof artifacts.value) => typeof artifacts.value),
  ) => {
    artifacts.value = typeof value === 'function' ? value(artifacts.value) : value;
  };
  const artifactError = shallowRef<string | null>(null);
  const setArtifactError = (
    value:
      | typeof artifactError.value
      | ((current: typeof artifactError.value) => typeof artifactError.value),
  ) => {
    artifactError.value = typeof value === 'function' ? value(artifactError.value) : value;
  };
  const isRestoring = shallowRef(true);
  const setIsRestoring = (
    value:
      typeof isRestoring.value | ((current: typeof isRestoring.value) => typeof isRestoring.value),
  ) => {
    isRestoring.value = typeof value === 'function' ? value(isRestoring.value) : value;
  };
  const activeRunRef = ref<{ requestId: string; runId: string } | null>(null);
  const conversationIdRef = ref<string | null>(null);
  const cancelRequestedRef = ref(false);
  const generationRef = ref(0);
  const requestControllerRef = ref<AbortController | null>(null);
  const baseUrl = options.baseUrl ?? defaultBaseUrl();

  const reloadArtifacts = async (conversationId: string, signal?: AbortSignal) => {
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
  };

  const consumeRun = async (
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
      if (generationRef.value !== generation) break;
      dispatch({ type: 'sse_event', event });
      if (event.event === 'clarification_required') break;
      if (
        event.event === 'stream_done' &&
        (event.payload.status === 'succeeded' || event.payload.status === 'degraded_succeeded')
      ) {
        await reloadArtifacts(conversationId, controller.signal);
      }
    }
    if (activeRunRef.value?.requestId === requestId) activeRunRef.value = null;
  };

  (() => {
    let cleanup0: (() => void) | undefined;
    onMounted(() => {
      cleanup0 = (() => {
        const controller = new AbortController();
        requestControllerRef.value = controller;
        const generation = ++generationRef.value;
        const isCurrent = () => generationRef.value === generation && !controller.signal.aborted;

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
              conversationIdRef.value = conversationId;
              replaceConversationId(conversationId);
              dispatch({ type: 'history_loaded', messages: [], run: null });
              return;
            }

            conversationIdRef.value = conversationId;
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
            setIsRestoring(false);
            if (isRunning(run)) {
              const requestId = `restored:${run.runId}`;
              activeRunRef.value = { requestId, runId: run.runId };
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
          generationRef.value += 1;
          requestControllerRef.value?.abort();
          controller.abort();
          if (requestControllerRef.value === controller) requestControllerRef.value = null;
          activeRunRef.value = null;
        };
      })();
    });
    onBeforeUnmount(() => cleanup0?.());
  })();

  const sendMessage = async (content: string) => {
    const message = content.trim();
    if (
      !message ||
      isRestoring.value ||
      state.value.status === 'submitting' ||
      state.value.status === 'streaming' ||
      state.value.status === 'cancelling'
    )
      return;
    requestControllerRef.value?.abort();
    const controller = new AbortController();
    requestControllerRef.value = controller;
    const requestId = crypto.randomUUID();
    const generation = ++generationRef.value;
    const isCurrent = () => generationRef.value === generation;
    activeRunRef.value = null;
    let conversationId = conversationIdRef.value;
    cancelRequestedRef.value = false;
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
        conversationIdRef.value = conversationId;
        replaceConversationId(conversationId);
      }
      const submitted = await submitConversationMessage(
        { conversationId, message, clientRequestId: requestId },
        { baseUrl, fetcher: options.fetcher, signal: controller.signal },
      );
      if (!isCurrent()) return;
      activeRunRef.value = { requestId, runId: submitted.runId };
      dispatch({ type: 'run_created', runId: submitted.runId, requestId });
      if (cancelRequestedRef.value) {
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
      if (isCurrent() && activeRunRef.value?.requestId === requestId) {
        activeRunRef.value = null;
        cancelRequestedRef.value = false;
      }
      if (requestControllerRef.value === controller) requestControllerRef.value = null;
    }
  };

  const cancel = async () => {
    cancelRequestedRef.value = true;
    const requestId = state.value.requestId;
    const activeRun = activeRunRef.value?.requestId === requestId ? activeRunRef.value : null;
    const runId = activeRun?.runId ?? state.value.runId;
    dispatch({ type: 'cancel_requested', runId, requestId });
    if (!runId) return;
    const generation = generationRef.value;
    try {
      const result = await cancelRun(runId, { baseUrl, fetcher: options.fetcher });
      if (generation !== generationRef.value) return;
      if (result.status === 'cancelled') {
        dispatch({ type: 'cancelled', runId, requestId: requestId ?? undefined });
        requestControllerRef.value?.abort();
      }
    } catch (error) {
      if (generation === generationRef.value)
        dispatch({
          type: 'cancel_failed',
          runId,
          requestId: requestId ?? '',
          message: error instanceof Error ? error.message : '停止请求失败，请稍后重试。',
        });
    }
  };

  return {
    state,
    sendMessage,
    cancel,
    artifacts,
    artifactError,
    baseUrl,
    isRestoring,
    isBusy: computed(
      () =>
        isRestoring.value ||
        state.value.status === 'submitting' ||
        state.value.status === 'streaming' ||
        state.value.status === 'cancelling',
    ),
  };
}
