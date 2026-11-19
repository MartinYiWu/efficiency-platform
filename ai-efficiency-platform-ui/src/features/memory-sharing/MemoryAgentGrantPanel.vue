<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue';
import {
  fieldLabels,
  MemoryApiError,
  memoryAccessTokenKey,
  memoryErrorMessage,
  type MemoryPreference,
  type MemoryScope,
} from '../../entities/memory';
import {
  createMemorySharingApi,
  type AgentMemoryGrant,
  type SharingAgent,
} from '../../entities/memory/sharing';
const props = defineProps<{
  scope: MemoryScope;
  items: MemoryPreference[];
  authorizationVersion?: number;
}>();
const emit = defineEmits<{ denied: [status: number] }>();
const token = inject(memoryAccessTokenKey, () => undefined),
  api = createMemorySharingApi(token);
const open = ref(false),
  busy = ref(false),
  error = ref(''),
  success = ref('');
const grants = ref<AgentMemoryGrant[]>([]),
  selected = ref('');
const target = computed<SharingAgent>(() =>
  props.scope.topAgent === 'operations' ? 'customer-service' : 'operations',
);
let generation = 0,
  controller: AbortController | undefined;
function clear() {
  generation++;
  controller?.abort();
  grants.value = [];
  selected.value = '';
  error.value = '';
  success.value = '';
  busy.value = false;
}
function reportFailure(reason: unknown) {
  if (reason instanceof MemoryApiError && [401, 403, 404].includes(reason.status)) {
    clear();
    open.value = false;
    emit('denied', reason.status);
  }
  error.value = memoryErrorMessage(reason);
}
async function load() {
  clear();
  if (!open.value || !token() || props.scope.topAgent === 'hr') return;
  controller = new AbortController();
  const current = generation;
  busy.value = true;
  try {
    const value = await api.grants(props.scope.topAgent, controller.signal);
    if (current === generation) grants.value = value;
  } catch (reason) {
    if (current === generation && !controller.signal.aborted) reportFailure(reason);
  } finally {
    if (current === generation) busy.value = false;
  }
}
async function mutate(grant?: AgentMemoryGrant) {
  if (busy.value) return;
  const item = props.items.find((value) => value.id === selected.value);
  if (!grant && !item) {
    error.value = '请选择已保存的偏好';
    return;
  }
  busy.value = true;
  error.value = '';
  success.value = '';
  const current = generation;
  try {
    const value = grant
      ? await api.withdrawGrant(grant, crypto.randomUUID(), controller?.signal)
      : await api.grant(
          item!,
          target.value,
          new Date(
            Math.min(
              Date.now() + 30 * 86400000,
              item!.expiresAt ? new Date(item!.expiresAt).getTime() : Infinity,
            ),
          ).toISOString(),
          crypto.randomUUID(),
          controller?.signal,
        );
    if (current !== generation) return;
    grants.value = [...grants.value.filter((record) => record.id !== value.id), value];
    success.value =
      grant && value.status === 'REVOKED'
        ? '已撤回目标 Agent 的授权，原私有偏好保留。'
        : !grant && value.status === 'ACTIVE'
          ? '已授权指定偏好；聊天历史和摘要不在共享范围内。'
          : '请重新加载核对当前授权状态。';
    selected.value = '';
  } catch (reason) {
    if (current === generation) reportFailure(reason);
  } finally {
    if (current === generation) busy.value = false;
  }
}
watch(
  () => [props.scope.topAgent, props.scope.sessionId, props.authorizationVersion, token()],
  () => {
    clear();
    if (open.value) void load();
  },
  { flush: 'sync' },
);
watch(open, () => {
  if (open.value) void load();
  else clear();
});
onBeforeUnmount(clear);
</script>
<template>
  <section
    v-if="scope.topAgent !== 'hr'"
    class="ui-card grant-panel"
    aria-label="跨 Agent 偏好授权"
  >
    <button type="button" :aria-expanded="open" @click="open = !open">跨 Agent 偏好授权</button>
    <div v-if="open">
      <p>仅授权回复语言、详细程度和格式。聊天历史、会话摘要及业务材料不会共享。</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-if="success" role="status">{{ success }}</p>
      <form class="grant-form" @submit.prevent="mutate()">
        <label
          >已保存的偏好<select v-model="selected" :disabled="busy">
            <option value="">请选择偏好</option>
            <option v-for="item in items" :key="item.id" :value="item.id">
              {{ fieldLabels[item.fieldKey] }} · 版本 {{ item.revision }}
            </option>
          </select></label
        >
        <p>
          授权给：{{ target === 'operations' ? '内容运营助手' : '智能客服' }}；期限最长 30
          天，且不超过原偏好有效期。
        </p>
        <a-button type="primary" html-type="submit" :disabled="busy || !selected || !token()"
          >确认授权</a-button
        >
      </form>
      <a-button size="small" :disabled="busy" @click="load">刷新授权</a-button>
      <p v-if="!busy && !grants.length">暂无跨 Agent 授权</p>
      <article v-for="grant in grants" :key="grant.id" class="grant-item">
        <strong>{{ fieldLabels[grant.fieldKey] }}</strong
        ><span
          >{{ grant.targetAgent === 'operations' ? '内容运营助手' : '智能客服' }} ·
          {{ grant.status === 'ACTIVE' ? '授权有效' : '已撤回' }}</span
        >
        <span>有效至 {{ new Date(grant.expiresAt).toLocaleString('zh-CN') }}</span>
        <a-button
          v-if="grant.status === 'ACTIVE'"
          danger
          size="small"
          :disabled="busy"
          @click="mutate(grant)"
          >撤回授权</a-button
        >
      </article>
    </div>
  </section>
</template>
<style scoped>
.grant-panel {
  padding: 20px;
  margin-block: 16px;
}
.grant-panel > button {
  border: 0;
  background: none;
  color: var(--ant-color-primary, #6366f1);
  cursor: pointer;
  font: inherit;
}
.grant-form {
  margin-block: 16px;
}
label {
  display: grid;
  gap: 8px;
}
select {
  padding: 8px;
  border: 1px solid var(--ant-color-border, #ddd);
  border-radius: 6px;
  background: var(--ant-color-bg-container, white);
  color: inherit;
}
.grant-item {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  border-top: 1px solid var(--ant-color-border-secondary, #eee);
  padding-block: 14px;
  overflow-wrap: anywhere;
}
button:focus-visible {
  outline: 2px solid var(--ant-color-primary, #6366f1);
  outline-offset: 3px;
}
</style>
