<script setup lang="ts">
import { inject, onBeforeUnmount, ref, watch } from 'vue';
import {
  fieldLabels,
  memoryAccessTokenKey,
  MemoryApiError,
  memoryErrorMessage,
  valueLabels,
  type MemoryScope,
} from '../../entities/memory';
import {
  createMemoryProposalApi,
  type MemoryProposal,
  type ProposalDecision,
} from '../../entities/memory/proposals';

const props = defineProps<{ scope: MemoryScope; authorizationVersion?: number }>();
const emit = defineEmits<{ saved: []; denied: [] }>();
const token = inject(memoryAccessTokenKey, () => undefined);
const api = createMemoryProposalApi(token);
const open = ref(false),
  loading = ref(false),
  saving = ref(false);
const items = ref<MemoryProposal[]>([]),
  selected = ref<MemoryProposal>();
const error = ref(''),
  success = ref('');
const keys = new Map<string, string>();
let generation = 0,
  controller: AbortController | undefined;

function clear() {
  generation++;
  controller?.abort();
  items.value = [];
  selected.value = undefined;
  error.value = '';
  success.value = '';
  loading.value = false;
  saving.value = false;
  keys.clear();
}
function failure(reason: unknown) {
  if (reason instanceof MemoryApiError && [401, 403, 404].includes(reason.status)) {
    clear();
    open.value = false;
    emit('denied');
  }
  error.value = memoryErrorMessage(reason);
}
async function load() {
  controller?.abort();
  controller = new AbortController();
  const current = ++generation;
  items.value = [];
  selected.value = undefined;
  error.value = '';
  success.value = '';
  if (!open.value || !token() || props.scope.topAgent === 'hr' || !props.scope.sessionId) return;
  loading.value = true;
  try {
    const value = await api.list(props.scope, controller.signal);
    if (current === generation) items.value = value;
  } catch (reason) {
    if (current === generation && !controller.signal.aborted) failure(reason);
  } finally {
    if (current === generation) loading.value = false;
  }
}
async function decide(item: MemoryProposal, action: ProposalDecision) {
  if (saving.value || item.status !== 'PENDING' || item.value === null) return;
  const current = generation;
  const key = `${item.id}:${item.revision}:${action}`;
  if (!keys.has(key)) keys.set(key, crypto.randomUUID());
  saving.value = true;
  error.value = '';
  success.value = '';
  try {
    const result = await api.decide(item, props.scope, action, keys.get(key)!, controller?.signal);
    if (current !== generation) return;
    items.value = items.value.map((record) => (record.id === result.id ? result : record));
    selected.value = undefined;
    if (action === 'CONFIRM' && result.status === 'ACCEPTED') {
      success.value = '已保存，可按字段使用；尚未建立语义索引。';
      emit('saved');
    } else if (action === 'REJECT' && result.status === 'REJECTED') {
      success.value = '已拒绝此候选。';
    } else {
      error.value = '候选状态已经变化，请重新加载后核对。';
    }
  } catch (reason) {
    if (current === generation) failure(reason);
  } finally {
    if (current === generation) saving.value = false;
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
const labels: Record<string, string> = {
  PENDING: '待确认',
  ACCEPTED: '已保存',
  REJECTED: '已拒绝',
  STALE: '来源已变化',
  SUPPRESSED: '已停止学习',
  EXPIRED: '已过期',
};
</script>
<template>
  <section
    v-if="scope.topAgent !== 'hr' && scope.sessionId"
    class="ui-card proposal-panel"
    aria-label="待确认的记忆候选"
  >
    <div class="proposal-toolbar">
      <button type="button" :aria-expanded="open" @click="open = !open">
        {{ open ? '收起候选记忆' : '查看候选记忆' }}
      </button>
      <a-button v-if="open" size="small" :disabled="saving || loading || !token()" @click="load"
        >重新加载</a-button
      >
    </div>
    <div v-if="open">
      <p>
        候选尚未成为记忆。只有你确认后才在当前 Agent 中生效；确认不调用大模型，也不建立语义索引。
      </p>
      <p v-if="loading" role="status">正在读取当前会话的候选…</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-if="success" role="status">{{ success }}</p>
      <a-empty v-if="!loading && !error && !items.length" description="暂无候选记忆" />
      <article v-for="item in items" :key="item.id" class="proposal-item">
        <div class="proposal-toolbar">
          <strong>{{ fieldLabels[item.fieldKey] }}</strong
          ><a-tag>{{ labels[item.status] }}</a-tag>
        </div>
        <p v-if="item.value !== null">{{ valueLabels[item.value] ?? item.value }}</p>
        <p v-if="item.action === 'CONFLICT_CANDIDATE'" class="proposal-note">
          与已保存的值存在冲突；确认将更正当前偏好。
        </p>
        <p v-if="item.status === 'ACCEPTED'" class="proposal-note">
          已保存，可按字段使用；尚未建立语义索引。
        </p>
        <p class="proposal-note">
          版本 {{ item.revision }} · 有效至 {{ new Date(item.expiresAt).toLocaleString('zh-CN') }}
        </p>
        <a-space v-if="item.status === 'PENDING' && item.value !== null" wrap>
          <a-button
            type="primary"
            size="small"
            :disabled="saving || !token()"
            @click="selected = item"
            >确认保存</a-button
          >
          <a-button size="small" :disabled="saving || !token()" @click="decide(item, 'REJECT')"
            >拒绝候选</a-button
          >
        </a-space>
      </article>
      <div v-if="selected" class="proposal-confirm" role="group" aria-label="确认保存候选">
        <strong>确认长期保存{{ fieldLabels[selected.fieldKey] }}？</strong>
        <p>
          {{ selected.value === null ? '' : (valueLabels[selected.value] ?? selected.value) }} ·
          仅当前 Agent 可用
        </p>
        <p>此操作会保存或更正偏好，不产生模型费用；语义索引尚未请求。</p>
        <a-space wrap
          ><a-button type="primary" :loading="saving" @click="decide(selected, 'CONFIRM')"
            >确认保存</a-button
          ><a-button :disabled="saving" @click="selected = undefined">返回核对</a-button></a-space
        >
      </div>
    </div>
  </section>
</template>
<style scoped>
.proposal-panel {
  padding: 20px;
  margin-block: 16px;
}
.proposal-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.proposal-toolbar > button {
  border: 0;
  padding: 4px 0;
  color: var(--ant-color-primary, #6366f1);
  background: transparent;
  cursor: pointer;
  font: inherit;
}
.proposal-item {
  border-top: 1px solid var(--ant-color-border-secondary, #eee);
  padding-block: 16px;
  overflow-wrap: anywhere;
}
.proposal-note {
  color: var(--ant-color-text-secondary, #737373);
  font-size: 13px;
}
.proposal-confirm {
  padding: 16px;
  background: var(--ant-color-primary-bg, #f0f5ff);
  border-radius: 8px;
}
button:focus-visible {
  outline: 2px solid var(--ant-color-primary, #6366f1);
  outline-offset: 3px;
}
@media (max-width: 640px) {
  .proposal-panel {
    padding: 14px;
  }
}
</style>
