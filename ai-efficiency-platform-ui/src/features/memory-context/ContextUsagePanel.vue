<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue';
import { memoryAccessTokenKey, memoryErrorMessage } from '../../entities/memory';
import {
  createContextUsageApi,
  type ContextUsage,
  type SummaryDetail,
} from '../../entities/memory/context';
import SummarySegmentView from './SummarySegmentView.vue';
const props = defineProps<{
  topAgent: 'operations' | 'customer-service';
  sessionId?: string | null;
  runId?: string | null;
  refreshKey?: string;
}>();
const token = inject(memoryAccessTokenKey, () => undefined);
const api = createContextUsageApi(token);
const open = ref(false),
  loading = ref(false),
  error = ref('');
const usage = ref<ContextUsage>();
const summary = ref<SummaryDetail>();
const selectedId = ref<string>();
const scope = computed(() =>
  props.sessionId
    ? {
        topAgent: props.topAgent,
        sessionId: props.sessionId,
        ...(props.runId ? { runId: props.runId } : {}),
      }
    : undefined,
);
let revision = 0,
  controller: AbortController | undefined;
function clear() {
  revision++;
  controller?.abort();
  usage.value = undefined;
  summary.value = undefined;
  selectedId.value = undefined;
  error.value = '';
  loading.value = false;
}
async function load() {
  clear();
  if (!scope.value || !open.value) return;
  const current = revision;
  controller = new AbortController();
  loading.value = true;
  try {
    const value = await api.read(scope.value, controller.signal);
    if (current === revision) usage.value = value;
  } catch (reason) {
    if (current === revision && !controller.signal.aborted)
      error.value = memoryErrorMessage(reason);
  } finally {
    if (current === revision) loading.value = false;
  }
}
async function details(id: string) {
  if (!scope.value || !usage.value?.summaries.some((item) => item.segmentId === id)) return;
  const current = revision;
  summary.value = undefined;
  selectedId.value = id;
  error.value = '';
  try {
    const value = await api.summary(id, scope.value, controller?.signal);
    if (current === revision && selectedId.value === id && value.segmentId === id)
      summary.value = value;
  } catch (reason) {
    if (current === revision) {
      summary.value = undefined;
      error.value = memoryErrorMessage(reason);
    }
  }
}
watch(
  () => [props.topAgent, props.sessionId, props.runId, props.refreshKey, token()],
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
  ALLOW: '窗口充足',
  TRIM: '已省略部分历史',
  REJECT: '输入超过上限',
  HISTORY_LIMIT: '历史条数上限',
  TOKEN_LIMIT: '窗口预算上限',
  SUMMARY_SLOT_LIMIT: '摘要空间上限',
  SOURCE_REVOKED: '来源已失效',
  NOT_BENEFICIAL: '压缩未降低输入',
  STALE: '来源版本已变化',
};
function number(value: number | null) {
  return value === null ? '未报告' : value.toLocaleString('zh-CN');
}
</script>
<template>
  <section v-if="sessionId" class="context-usage" aria-label="本次上下文使用">
    <div class="context-toolbar">
      <button type="button" :aria-expanded="open" @click="open = !open">
        {{ open ? '收起上下文使用' : '查看上下文与摘要' }}
      </button>
      <button v-if="open" type="button" :disabled="loading" @click="load">刷新记录</button>
    </div>
    <div v-if="open" class="context-content">
      <p v-if="loading" role="status">正在读取已保存记录…</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <template v-if="usage">
        <p v-if="!usage.operations.length && !usage.summaries.length" class="context-muted">
          当前会话暂无已保存的上下文使用记录。
        </p>
        <article
          v-for="(operation, index) in usage.operations"
          :key="`${operation.nodeId}-${index}`"
          class="context-node"
        >
          <strong>{{ operation.nodeId }}</strong
          ><span>{{ labels[operation.windowStatus] ?? '窗口状态未报告' }}</span>
          <dl>
            <dt>输入上界</dt>
            <dd>{{ number(operation.inputTokens) }} tokens</dd>
            <dt>输入上限</dt>
            <dd>{{ number(operation.inputLimit) }} tokens</dd>
            <dt>输出预留</dt>
            <dd>{{ number(operation.outputReserveTokens) }} tokens</dd>
            <dt>历史选择前 / 后</dt>
            <dd>
              {{ number(operation.cpuBeforeTokens) }} / {{ number(operation.cpuAfterTokens) }}
            </dd>
            <dt>摘要采用</dt>
            <dd>
              {{
                operation.summaryAdoptionStatus === 'not-applied'
                  ? '未采用摘要'
                  : operation.summaryAdoptionStatus
              }}
            </dd>
            <dt>费用</dt>
            <dd>
              {{
                operation.costMicrounits === null
                  ? '尚未同步实际费用'
                  : `¥${(operation.costMicrounits / 1000000).toFixed(6)}`
              }}
            </dd>
          </dl>
          <ul v-if="operation.omissions.length">
            <li v-for="omission in operation.omissions" :key="omission.reason">
              {{ labels[omission.reason] ?? '其他历史省略' }}：{{ omission.count }} 项
            </li>
          </ul>
        </article>
        <section v-if="usage.summaries.length" aria-label="已保存摘要">
          <h4>已保存摘要</h4>
          <p class="context-muted">仅当前用户、当前 Agent 与会话可用；刷新不会生成新摘要。</p>
          <article v-for="item in usage.summaries" :key="item.segmentId" class="context-node">
            <span
              >覆盖第 {{ item.firstSequence }}—{{ item.lastSequence }} 条 ·
              {{ item.sourceCount }} 个来源</span
            >
            <span>有效至 {{ new Date(item.expiresAt * 1000).toLocaleString('zh-CN') }}</span>
            <button type="button" @click="details(item.segmentId)">查看摘要内容</button>
            <SummarySegmentView
              v-if="summary && selectedId === item.segmentId"
              :summary="summary"
            />
          </article>
        </section>
      </template>
    </div>
  </section>
</template>
<style scoped>
.context-usage {
  padding: 8px 20px;
  font-size: 13px;
}
.context-toolbar {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
button {
  background: none;
  color: var(--ant-color-primary, #6366f1);
  border: 0;
  cursor: pointer;
  padding: 4px 0;
  font: inherit;
  text-align: left;
}
button:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 3px;
}
button:disabled {
  opacity: 0.5;
  cursor: wait;
}
.context-content {
  padding-top: 8px;
  max-height: 420px;
  overflow: auto;
}
.context-node {
  border-top: 1px solid var(--ant-color-border-secondary, #e5e7eb);
  padding: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow-wrap: anywhere;
}
.context-muted {
  color: var(--ant-color-text-secondary, #6b7280);
}
dl {
  display: grid;
  grid-template-columns: minmax(90px, 1fr) minmax(100px, 2fr);
  gap: 4px 12px;
  margin: 4px 0;
}
dd {
  margin: 0;
}
ul {
  margin: 0;
  padding-left: 20px;
}
@media (max-width: 480px) {
  .context-usage {
    padding: 8px 12px;
  }
  dl {
    grid-template-columns: 100px minmax(0, 1fr);
  }
}
</style>
