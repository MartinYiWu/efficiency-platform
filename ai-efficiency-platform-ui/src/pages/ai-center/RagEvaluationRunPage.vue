<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type {
  EvaluationRunDetail,
  EvaluationCaseResult,
  EvaluationRun,
  EvaluationRunComparison,
} from '../../entities/ai-center/model';
import {
  getEvaluationRun,
  listEvaluationRuns,
  compareEvaluationRuns,
} from '../../features/ai-center/api';
import { aiStatusLabel } from '../../features/ai-center/presentation';
import { formatAiDate } from './datePresentation';
import MarkdownContent from '../../shared/ui/MarkdownContent.vue';
import AiWorkspaceSection from './AiWorkspaceSection.vue';
import './ai-center.css';
const route = useRoute(),
  router = useRouter(),
  runId = computed(() => String(route.params.runId ?? '')),
  detail = ref<EvaluationRunDetail>(),
  selected = ref<EvaluationCaseResult>(),
  failure = ref<string>(),
  baselineId = ref<string>(),
  baselineRuns = ref<EvaluationRun[]>([]),
  comparison = ref<EvaluationRunComparison>();
let timer: ReturnType<typeof setTimeout> | undefined,
  generation = 0;
async function load(request: number) {
  try {
    const value = await getEvaluationRun(runId.value);
    if (request !== generation) return;
    detail.value = value;
    if (['PENDING', 'RUNNING'].includes(value.run.status))
      timer = setTimeout(() => load(request), 2000);
  } catch (error) {
    if (request === generation) message.error((error as Error).message);
  }
}
watch(
  runId,
  () => {
    clearTimeout(timer);
    detail.value = undefined;
    selected.value = undefined;
    comparison.value = undefined;
    void load(++generation);
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  generation++;
  clearTimeout(timer);
});
const caseById = computed(() => new Map(detail.value?.cases.map((item) => [item.id, item]) ?? []));
const results = computed(
  () =>
    detail.value?.results.filter(
      (item) =>
        !failure.value ||
        (failure.value === 'EXECUTION_FAILED'
          ? item.executionStatus === 'FAILED'
          : item.metrics?.failures.includes(failure.value)),
    ) ?? [],
);
const percent = (value: number | null | undefined) =>
  value == null ? 'N/A' : `${(value * 100).toFixed(1)}%`;
const metrics = computed(() => {
  const value = detail.value?.run.metrics;
  return [
    ['用例通过率', percent(value?.casePassRate)],
    ['执行成功率', percent(value?.executionSuccessRate)],
    ['来源召回', percent(value?.sourceRecallAtK)],
    ['引用合规率', percent(value?.citationComplianceRate)],
    ['模式准确率', percent(value?.answerModeAccuracy)],
    ['P50 / P95', value ? `${value.latencyP50Ms} / ${value.latencyP95Ms} ms` : '运行中'],
  ];
});
async function loadBaselines(open: boolean) {
  if (open && detail.value)
    try {
      baselineRuns.value = await listEvaluationRuns(detail.value.run.datasetId);
    } catch (error) {
      message.error((error as Error).message);
    }
}
async function compare() {
  if (baselineId.value)
    try {
      comparison.value = await compareEvaluationRuns(baselineId.value, runId.value);
    } catch (error) {
      message.error((error as Error).message);
    }
}
const columns = [
  { title: '编号', key: 'no' },
  { title: '问题', key: 'question' },
  { title: '结果', key: 'passed' },
  { title: '回答模式', dataIndex: 'answerMode' },
  { title: '来源', key: 'sources' },
  { title: '耗时', key: 'latency' },
  { title: '错误', dataIndex: 'errorCode' },
  { title: '操作', key: 'action' },
];
</script>
<template>
  <section v-if="detail" class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <a-button
          type="link"
          @click="router.push(`/ai-center/rag-evaluations/${detail.run.datasetId}`)"
          >← 返回数据集</a-button
        >
        <h2>评测运行详情</h2>
      </div>
      <a-tag>{{ aiStatusLabel(detail.run.status) }}</a-tag>
    </header>
    <div class="ui-card">
      <dl class="ai-metrics">
        <div v-for="[title, value] in metrics" :key="title">
          <dt>{{ title }}</dt>
          <dd>{{ value }}</dd>
        </div>
      </dl>
      <AiWorkspaceSection title="批次冻结信息"
        ><a-descriptions size="small" :column="{ xs: 1, sm: 2 }"
          ><a-descriptions-item label="Agent 版本">{{
            detail.run.agentVersionId
          }}</a-descriptions-item
          ><a-descriptions-item label="RAG 策略">{{
            detail.run.ragPolicyVersionId
          }}</a-descriptions-item
          ><a-descriptions-item label="知识绑定">{{
            detail.run.knowledgeBindings
              .map((item) => `${item.knowledgeBaseId} / ${item.indexReleaseId}`)
              .join('；')
          }}</a-descriptions-item
          ><a-descriptions-item label="完成时间">{{
            detail.run.finishedAt ? formatAiDate(detail.run.finishedAt) : '尚未完成'
          }}</a-descriptions-item></a-descriptions
        ></AiWorkspaceSection
      ><AiWorkspaceSection title="用例执行与证据结果"
        ><div class="ui-filters">
          <a-select
            v-model:value="failure"
            allow-clear
            placeholder="失败类型"
            :options="
              [
                'EXECUTION_FAILED',
                'ANSWER_MODE_MISMATCH',
                'EXPECTED_FACT_MISSING',
                'PROHIBITED_FACT_MATCHED',
                'EXPECTED_SOURCE_MISSING',
                'CITATION_COUNT_INSUFFICIENT',
                'VERSION_MISMATCH',
              ].map((value) => ({ value }))
            "
          /><a-select
            v-model:value="baselineId"
            allow-clear
            placeholder="选择基线批次"
            :options="
              baselineRuns
                .filter((item) => item.id !== runId)
                .map((item) => ({
                  value: item.id,
                  label: `${item.id.slice(0, 8)} · ${aiStatusLabel(item.status)} · ${formatAiDate(item.createdAt)}`,
                }))
            "
            @dropdown-visible-change="loadBaselines"
          /><a-button :disabled="!baselineId" @click="compare">比较</a-button>
        </div>
        <AiWorkspaceSection v-if="comparison" title="与基线比较"
          ><a-space wrap
            ><a-tag
              v-for="(value, key) in comparison.metricDeltas"
              :key="key"
              :color="value >= 0 ? 'green' : 'red'"
              >{{ key }}: {{ value.toFixed(3) }}</a-tag
            ></a-space
          ></AiWorkspaceSection
        ><a-table
          row-key="id"
          :data-source="results"
          :columns="columns"
          :scroll="{ x: 1050 }"
          :pagination="{ pageSize: 10 }"
          ><template #emptyText
            ><a-empty
              :description="
                detail.run.status === 'RUNNING' ? '正在生成真实结果' : '暂无结果'
              " /></template
          ><template #bodyCell="{ column, record }"
            ><template v-if="column.key === 'no'">{{
              caseById.get(record.caseId)?.caseNo ?? record.caseId
            }}</template
            ><template v-else-if="column.key === 'question'">{{
              caseById.get(record.caseId)?.question ?? '—'
            }}</template
            ><a-tag v-else-if="column.key === 'passed'" :color="record.passed ? 'green' : 'red'">{{
              record.passed ? '通过' : '未通过'
            }}</a-tag
            ><template v-else-if="column.key === 'sources'">{{
              [...new Set(record.citations.map((item: any) => item.document_title))].join('、') ||
              '—'
            }}</template
            ><template v-else-if="column.key === 'latency'">{{ record.latencyMs }} ms</template
            ><a-button v-else-if="column.key === 'action'" type="link" @click="selected = record"
              >查看事实</a-button
            ></template
          ></a-table
        ></AiWorkspaceSection
      >
    </div>
    <a-drawer
      :open="!!selected"
      width="min(720px, 100vw)"
      title="用例真实结果"
      @close="selected = undefined"
      ><template v-if="selected"
        ><a-descriptions bordered size="small" :column="1"
          ><a-descriptions-item label="问题">{{
            caseById.get(selected.caseId)?.question ?? '—'
          }}</a-descriptions-item
          ><a-descriptions-item label="调试 Run ID">{{
            selected.debugRunId ?? '—'
          }}</a-descriptions-item
          ><a-descriptions-item label="判定失败项">{{
            selected.metrics?.failures.join('、') || selected.errorCode || '无'
          }}</a-descriptions-item></a-descriptions
        ><AiWorkspaceSection title="真实回答"
          ><MarkdownContent
            v-if="selected.answerMarkdown"
            :content="selected.answerMarkdown" /><a-empty
            v-else
            description="调用未返回回答" /></AiWorkspaceSection
        ><AiWorkspaceSection title="冻结引用"
          ><template v-if="selected.citations.length"
            ><AiWorkspaceSection
              v-for="citation in selected.citations"
              :key="citation.citation_no"
              compact
              :title="`[${citation.citation_no}] ${citation.document_title} · v${citation.version_no}`"
              ><p>{{ citation.quoted_text }}</p>
              <span class="ai-muted"
                >文档版本 {{ citation.document_version_id }} / 索引
                {{ citation.index_release_id }}</span
              ></AiWorkspaceSection
            ></template
          ><a-empty v-else description="无引用" /></AiWorkspaceSection></template
    ></a-drawer>
  </section>
  <span v-else>正在加载评测结果…</span>
</template>
