import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue';
import { MemoryApiError, memoryErrorMessage } from '../../entities/memory/api';
import { fieldValues } from '../../entities/memory/schemas';
import type {
  ForgetMemoryCommand,
  MemoryDeletionApi,
  MemoryDeletionTask,
  MemoryField,
  MemoryPreference,
  MemoryReauthorizationCommand,
  MemoryScope,
} from '../../entities/memory/model';

export function useMemoryDeletion(
  scope: Readonly<Ref<MemoryScope>>,
  api: MemoryDeletionApi,
  authority: () => string | undefined,
  revoked?: (itemId: string, jobId: string) => void,
  restored?: (item: MemoryPreference) => void,
  authorizationDenied?: () => void,
) {
  const task = ref<MemoryDeletionTask>(),
    target = ref<{ itemId: string; expectedRevision: number }>();
  const busy = ref(false),
    error = ref(''),
    success = ref('');
  const relearnField = ref<MemoryField>(),
    relearnValue = ref('');
  const complete = computed(
    () =>
      task.value?.status === 'DELETED' &&
      task.value.jobStatus === 'SUCCEEDED' &&
      task.value.completedTargets === task.value.requiredTargets,
  );
  let generation = 0,
    controller: AbortController | undefined,
    forgetCommand: ForgetMemoryCommand | undefined,
    relearnCommand: MemoryReauthorizationCommand | undefined;
  function reset() {
    generation++;
    controller?.abort();
    controller = undefined;
    task.value = undefined;
    target.value = undefined;
    relearnField.value = undefined;
    relearnValue.value = '';
    forgetCommand = undefined;
    relearnCommand = undefined;
    error.value = '';
    success.value = '';
    busy.value = false;
  }
  function choose(item: MemoryPreference) {
    reset();
    if (item.topAgent !== scope.value.topAgent) {
      error.value = '无法操作其他 Agent 的偏好';
      return;
    }
    target.value = { itemId: item.id, expectedRevision: item.revision };
  }
  function cancel() {
    if (!busy.value) {
      target.value = undefined;
      forgetCommand = undefined;
      error.value = '';
    }
  }
  function begin() {
    controller?.abort();
    controller = new AbortController();
    busy.value = true;
    error.value = '';
    success.value = '';
    return ++generation;
  }
  function fail(reason: unknown, current: number) {
    if (current !== generation) return;
    if (reason instanceof MemoryApiError && [401, 403, 404].includes(reason.status)) {
      reset();
      authorizationDenied?.();
    }
    error.value = memoryErrorMessage(reason);
  }
  function accept(result: MemoryDeletionTask) {
    task.value = result;
    target.value = undefined;
    if (['DELETE_PENDING', 'DELETED'].includes(result.status))
      revoked?.(result.itemId, result.jobId);
  }
  async function forget() {
    if (!target.value || busy.value) return;
    forgetCommand ??= {
      ...target.value,
      idempotencyKey: crypto.randomUUID(),
      mode: 'FORGET_AND_SUPPRESS',
    };
    const command = forgetCommand,
      current = begin();
    try {
      if (!authority()) throw new MemoryApiError(401, 'MEMORY_IDENTITY_REQUIRED');
      const result = await api.forget(scope.value, command, controller!.signal);
      if (current !== generation) return;
      if (result.itemId !== command.itemId) throw new Error('Scope mismatch');
      accept(result);
    } catch (reason) {
      fail(reason, current);
    } finally {
      if (current === generation) busy.value = false;
    }
  }
  async function refresh(jobId = task.value?.jobId) {
    if (!jobId || busy.value) return;
    const current = begin();
    try {
      if (!authority()) throw new MemoryApiError(401, 'MEMORY_IDENTITY_REQUIRED');
      const result = await api.deletion(jobId, scope.value, controller!.signal);
      if (current !== generation) return;
      if (result.jobId !== jobId) throw new Error('Scope mismatch');
      accept(result);
    } catch (reason) {
      fail(reason, current);
    } finally {
      if (current === generation) busy.value = false;
    }
  }
  watch(
    relearnField,
    (field) => {
      relearnValue.value = field ? fieldValues[field][0] : '';
      relearnCommand = undefined;
    },
    { flush: 'sync' },
  );
  async function reauthorize() {
    if (!complete.value || !task.value || !relearnField.value || !relearnValue.value || busy.value)
      return;
    const job = task.value;
    const content = {
      itemId: job.itemId,
      fieldKey: relearnField.value,
      value: relearnValue.value,
      expectedRevision: job.revision,
      expected_suppression_revision: job.suppressionRevision,
      confirmation: 'ALLOW_REMEMBER' as const,
    };
    if (
      !relearnCommand ||
      Object.entries(content).some(
        ([key, value]) => relearnCommand![key as keyof MemoryReauthorizationCommand] !== value,
      )
    )
      relearnCommand = { ...content, idempotencyKey: crypto.randomUUID() };
    const current = begin();
    try {
      if (!authority()) throw new MemoryApiError(401, 'MEMORY_IDENTITY_REQUIRED');
      const result = await api.reauthorize(
        job.suppressionId,
        scope.value,
        relearnCommand,
        controller!.signal,
      );
      if (current !== generation) return;
      if (
        result.id !== job.itemId ||
        result.topAgent !== scope.value.topAgent ||
        result.fieldKey !== content.fieldKey
      )
        throw new Error('Scope mismatch');
      task.value = undefined;
      relearnField.value = undefined;
      relearnValue.value = '';
      relearnCommand = undefined;
      success.value = '已重新允许记住，并保存了新的偏好';
      restored?.(result);
    } catch (reason) {
      fail(reason, current);
    } finally {
      if (current === generation) busy.value = false;
    }
  }
  watch([() => scope.value.topAgent, () => scope.value.sessionId, authority], reset, {
    flush: 'sync',
  });
  onBeforeUnmount(reset);
  return {
    task,
    target,
    busy,
    error,
    success,
    complete,
    relearnField,
    relearnValue,
    choose,
    cancel,
    forget,
    refresh,
    reauthorize,
    reset,
  };
}
