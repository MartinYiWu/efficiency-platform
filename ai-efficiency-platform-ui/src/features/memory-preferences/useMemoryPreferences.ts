import { ref, watch, onBeforeUnmount, type Ref } from 'vue';
import type {
  MemoryApi,
  MemoryScope,
  MemoryPreference,
  MemoryField,
} from '../../entities/memory/model';
import { MemoryApiError, memoryErrorMessage } from '../../entities/memory/api';
import { fieldValues } from '../../entities/memory/schemas';
export function useMemoryPreferences(
  scope: Readonly<Ref<MemoryScope>>,
  api: MemoryApi,
  authority?: () => string | undefined,
  authorizationDenied?: () => void,
) {
  const items = ref<MemoryPreference[]>([]),
    total = ref(0),
    page = ref(1),
    loading = ref(false),
    saving = ref(false);
  const draftField = ref<MemoryField>('response.language'),
    draftValue = ref('zh-CN');
  const editing = ref<MemoryPreference>(),
    error = ref(''),
    success = ref('');
  let generation = 0,
    writeGeneration = 0,
    controller: AbortController | undefined,
    writeController: AbortController | undefined,
    writingItemId: string | undefined;
  const revokedIds = new Set<string>();
  async function load(nextPage = 1) {
    controller?.abort();
    controller = new AbortController();
    const current = ++generation;
    loading.value = true;
    error.value = '';
    success.value = '';
    try {
      if (authority && !authority()) throw new MemoryApiError(401, 'MEMORY_IDENTITY_REQUIRED');
      const result = await api.list(scope.value, nextPage, controller.signal);
      if (current !== generation) return;
      if (result.items.some((item) => item.topAgent !== scope.value.topAgent))
        throw new Error('Scope mismatch');
      items.value = result.items.filter((item) => !revokedIds.has(item.id));
      total.value = Math.max(0, result.total - (result.items.length - items.value.length));
      page.value = result.page;
    } catch (reason) {
      if (current === generation) {
        if (reason instanceof MemoryApiError && [401, 403, 404].includes(reason.status)) {
          clearPrivate();
          authorizationDenied?.();
        }
        error.value = memoryErrorMessage(reason);
      }
    } finally {
      if (current === generation) loading.value = false;
    }
  }
  function edit(item: MemoryPreference) {
    if (revokedIds.has(item.id)) return;
    editing.value = item;
    draftField.value = item.fieldKey;
    draftValue.value = item.value;
    success.value = '';
    error.value = '';
  }
  function reset() {
    editing.value = undefined;
    draftField.value = 'response.language';
    draftValue.value = 'zh-CN';
  }
  function revoke(itemId: string) {
    revokedIds.add(itemId);
    if (writingItemId === itemId) {
      writeGeneration++;
      writeController?.abort();
      writingItemId = undefined;
      saving.value = false;
    }
    const before = items.value.length;
    items.value = items.value.filter((item) => item.id !== itemId);
    total.value = Math.max(0, total.value - (before - items.value.length));
    if (editing.value?.id === itemId) reset();
    success.value = '';
  }
  function restore(itemId: string) {
    revokedIds.delete(itemId);
  }
  function clearPrivate() {
    generation++;
    controller?.abort();
    writeController?.abort();
    revokedIds.clear();
    items.value = [];
    total.value = 0;
    reset();
    success.value = '';
    loading.value = false;
    saving.value = false;
  }
  watch(draftField, (field) => {
    if (!(fieldValues[field] as readonly string[]).includes(draftValue.value))
      draftValue.value = fieldValues[field][0];
  });
  async function save() {
    const current = generation;
    const currentWrite = ++writeGeneration;
    writeController?.abort();
    writeController = new AbortController();
    writingItemId = editing.value?.id;
    const targetId = writingItemId;
    saving.value = true;
    success.value = '';
    error.value = '';
    const command = {
      fieldKey: draftField.value,
      value: draftValue.value,
      expectedRevision: editing.value?.revision ?? 0,
      idempotencyKey: crypto.randomUUID(),
    };
    try {
      const saved = editing.value
        ? await api.correct(editing.value.id, scope.value, command, writeController.signal)
        : await api.save(scope.value, command, writeController.signal);
      if (current !== generation || currentWrite !== writeGeneration) return;
      if (revokedIds.has(saved.id)) return;
      if (saved.topAgent !== scope.value.topAgent) throw new Error('Scope mismatch');
      const existing = items.value.findIndex((item) => item.id === saved.id);
      if (existing >= 0) items.value[existing] = saved;
      else {
        items.value.unshift(saved);
        total.value++;
      }
      editing.value = saved;
      success.value = '偏好已保存';
    } catch (reason) {
      if (
        current === generation &&
        currentWrite === writeGeneration &&
        (!targetId || !revokedIds.has(targetId))
      ) {
        if (reason instanceof MemoryApiError && [401, 403, 404].includes(reason.status)) {
          clearPrivate();
          authorizationDenied?.();
        }
        error.value = memoryErrorMessage(reason);
      }
    } finally {
      if (current === generation && currentWrite === writeGeneration) {
        saving.value = false;
        writingItemId = undefined;
      }
    }
  }
  watch(
    [() => scope.value.topAgent, () => scope.value.sessionId, () => authority?.()],
    () => {
      revokedIds.clear();
      writeController?.abort();
      writingItemId = undefined;
      items.value = [];
      total.value = 0;
      saving.value = false;
      reset();
      void load();
    },
    { immediate: true, flush: 'sync' },
  );
  onBeforeUnmount(() => {
    generation++;
    controller?.abort();
    writeController?.abort();
  });
  return {
    items,
    total,
    page,
    loading,
    saving,
    draftField,
    draftValue,
    editing,
    error,
    success,
    load,
    edit,
    reset,
    save,
    revoke,
    restore,
    clearPrivate,
  };
}
