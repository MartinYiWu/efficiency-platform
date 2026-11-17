<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  Alert,
  Button,
  Input,
  InputNumber,
  Modal,
  Select,
  Table,
  Tabs,
  TabPane,
  Tag,
} from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite, matchingSchema, type HrMatching } from '../../../entities/hr';
import HrInterviewBatchPanel from '../../../features/hr-interview-batch/HrInterviewBatchPanel.vue';
import styles from './MatchResultsPage.module.css';
const route = useRoute();
const router = useRouter();
const rows = ref<HrMatching[]>([]);
const total = ref(0);
const statisticsSchema = z.object({
  total: z.number(),
  strongRecommend: z.number(),
  recommend: z.number(),
  review: z.number(),
  notRecommend: z.number(),
  filtered: z.number(),
  reviewRequired: z.number(),
});
const statistics = ref<z.infer<typeof statisticsSchema>>();
const statisticsScope = ref('');
const statisticLabels = {
  strongRecommend: '强烈推荐',
  recommend: '推荐面试',
  review: '可考虑面试',
  notRecommend: '暂不推荐',
  filtered: '硬条件过滤',
  reviewRequired: '待核验',
};

const page = ref(1);
const loading = ref(false);
const error = ref('');
const keyword = ref('');
const businessStatus = ref('SCORED');
const positionId = ref(String(route.query.positionId ?? ''));
const configVersionId = ref(String(route.query.configVersionId ?? ''));
watch([positionId, configVersionId], () => {
  statistics.value = undefined;
  statisticsScope.value = '';
});
const candidateId = ref(String(route.query.candidateId ?? ''));
const schema = z.object({
  items: z.array(matchingSchema),
  total: z.number(),
  page: z.number(),
  pageSize: z.number(),
});
const recalcOpen = ref(false);
const recalcBusy = ref(false);
const recalcWeights = ref({ skills: 40, experience: 25, projects: 25, education: 5, bonus: 5 });
const recalcThresholds = ref([80, 65, 50]);
const recalcVersion = ref<number>();
const recalcMode = ref('TEMPORARY');
const previewSchema = z.object({
  inputHash: z.string(),
  modelCalls: z.literal(0),
  items: z.array(
    z.object({
      sourceResultId: z.string(),
      candidateId: z.string(),
      oldScore: z.number().nullable(),
      newScore: z.number().nullable(),
      businessStatus: z.string(),
      band: z.string().nullable(),
      coverage: z.number(),
    }),
  ),
});
const preview = ref<z.infer<typeof previewSchema>>();
watch([recalcWeights, recalcThresholds, recalcMode], () => (preview.value = undefined), {
  deep: true,
});
function recalcBody() {
  const first = rows.value[0]!;
  return {
    positionId: first.positionId,
    sourceConfigVersion: first.configVersion,
    resultIds: rows.value
      .filter((r) => r.positionId === first.positionId && r.configVersion === first.configVersion)
      .map((r) => r.resultId),
    weights: recalcWeights.value,
    thresholds: recalcThresholds.value,
    mode: recalcMode.value,
    expectedVersion: recalcVersion.value,
  };
}
async function previewRecalc() {
  if (recalcBusy.value || !recalcValid.value) return;
  recalcBusy.value = true;
  error.value = '';
  try {
    preview.value = await hrWrite('/recalculations/preview', previewSchema, recalcBody());
  } catch (e) {
    error.value = e instanceof Error ? e.message : '预览失败';
  } finally {
    recalcBusy.value = false;
  }
}

const recalcValid = computed(
  () =>
    Object.values(recalcWeights.value).reduce((a, b) => a + b, 0) === 100 &&
    recalcThresholds.value[0]! > recalcThresholds.value[1]! &&
    recalcThresholds.value[1]! > recalcThresholds.value[2]!,
);
async function openRecalc() {
  const first = rows.value[0];
  if (!first) return;
  recalcBusy.value = true;
  error.value = '';
  try {
    if (first.dimensions.length !== 5 || first.thresholds.length !== 3)
      throw new Error('结果缺少完整权重与阈值快照，不能重算');
    recalcWeights.value = {
      skills: first.dimensions[0]!.weight,
      experience: first.dimensions[1]!.weight,
      projects: first.dimensions[2]!.weight,
      education: first.dimensions[3]!.weight,
      bonus: first.dimensions[4]!.weight,
    };
    recalcThresholds.value = [...first.thresholds];
    const position = await hrRequest(
      `/positions/${first.positionId}`,
      z.object({ version: z.number() }),
    );
    recalcVersion.value = position.version;
    recalcOpen.value = true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '配置版本读取失败';
  } finally {
    recalcBusy.value = false;
  }
}
async function recalculate() {
  const first = rows.value[0];
  if (!first || !recalcValid.value || recalcVersion.value === undefined || recalcBusy.value) return;
  recalcBusy.value = true;
  try {
    const run = await hrWrite(
      '/recalculations',
      z.object({ runId: z.string(), status: z.string() }),
      { ...recalcBody(), previewHash: preview.value?.inputHash },
    );
    recalcOpen.value = false;
    await router.replace({
      path: route.path,
      query: { ...route.query, runId: run.runId, candidateId: first.candidateId },
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : '重算失败，历史结果保留';
  } finally {
    recalcBusy.value = false;
  }
}
let controller: AbortController | undefined;
let runController: AbortController | undefined;
let runTimer: ReturnType<typeof setTimeout> | undefined;
const runStatus = ref('');
let runAttempts = 0;
async function readRun() {
  const id = route.query.runId;
  if (!id) return;
  runController = new AbortController();
  try {
    const run = await hrRequest(
      `/matching-runs/${encodeURIComponent(String(id))}`,
      z.object({
        runId: z.string(),
        status: z.string(),
        resultId: z.string().nullable(),
        failureCode: z.string().nullable(),
      }),
      { signal: runController.signal },
    );
    runStatus.value =
      (
        {
          PENDING: '任务等待中',
          RUNNING: '正在分析',
          SUCCEEDED: '分析完成',
          FAILED: '分析失败',
          BLOCKED: '服务阻塞',
          CANCELLED: '已取消',
          TIMED_OUT: '已超时',
        } as Record<string, string>
      )[run.status] ?? '状态待核验';
    if (run.status === 'SUCCEEDED' && run.resultId) {
      await router.replace(
        `/ai-assistants/hr/matching/${route.query.candidateId ?? 'result'}?resultId=${encodeURIComponent(run.resultId)}`,
      );
      return;
    }
    if (['PENDING', 'RUNNING'].includes(run.status) && runAttempts++ < 120)
      runTimer = setTimeout(readRun, Math.min(runAttempts, 5) * 1000);
    if (run.failureCode) error.value = `分析任务未完成：${run.failureCode}`;
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError'))
      error.value = e instanceof Error ? e.message : '任务读取失败';
  }
}
watch(
  () => route.query.runId,
  () => {
    clearTimeout(runTimer);
    runController?.abort();
    runAttempts = 0;
    readRun();
  },
  { immediate: true },
);
const bands: Record<string, string> = {
  STRONGLY_RECOMMENDED: '强烈推荐面试',
  STRONG_RECOMMEND: '强烈推荐面试',
  RECOMMENDED: '推荐面试',
  RECOMMEND: '推荐面试',
  CONSIDER: '可考虑面试',
  REVIEW: '建议复核',
  NOT_RECOMMEND: '暂不推荐',
  NOT_RECOMMENDED: '暂不推荐',
};
const statuses: Record<string, string> = {
  SCORED: '正式评分',
  FILTERED: '被硬条件过滤',
  REVIEW_REQUIRED: '待核验',
  SUPERSEDED: '历史版本',
  STALE: '配置已更新',
};
async function load(next = 1) {
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = '';
  page.value = next;
  const params = new URLSearchParams({
    page: String(next),
    pageSize: '20',
    businessStatus: businessStatus.value,
  });
  if (positionId.value) params.set('positionId', positionId.value);
  if (configVersionId.value) params.set('configVersionId', configVersionId.value);
  if (candidateId.value) params.set('candidateId', candidateId.value);
  if (keyword.value) params.set('keyword', keyword.value);
  try {
    const data = await hrRequest(`/matching-results?${params}`, schema, {
      signal: controller.signal,
    });
    rows.value = data.items;
    total.value = data.total;
    if (positionId.value.trim() && configVersionId.value.trim()) {
      const scope = new URLSearchParams({
        positionId: positionId.value,
        configVersionId: configVersionId.value,
      });
      statistics.value = await hrRequest(
        `/matching-results/statistics?${scope}`,
        statisticsSchema,
        { signal: controller.signal },
      );
      statisticsScope.value = `${positionId.value} · ${configVersionId.value}`;
    } else {
      statistics.value = undefined;
      statisticsScope.value = '';
    }
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError'))
      error.value = e instanceof Error ? e.message : '匹配结果读取失败';
  } finally {
    loading.value = false;
  }
}
watch(
  () => [route.query.positionId, route.query.configVersionId],
  () => {
    positionId.value = String(route.query.positionId ?? '');
    configVersionId.value = String(route.query.configVersionId ?? '');
    load();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  controller?.abort();
  runController?.abort();
  clearTimeout(runTimer);
});
const columns = [
  { title: '候选人', key: 'candidateName', dataIndex: 'candidateName' },
  { title: '目标岗位 / 规则版本', key: 'positionName', dataIndex: 'positionName' },
  { title: '总分', key: 'totalScore', dataIndex: 'totalScore' },
  { title: '分档 / 状态', key: 'band' },
  { title: '五维分数', key: 'dimensions' },
  { title: '证据覆盖率', key: 'evidenceCoverage', dataIndex: 'evidenceCoverage' },
  { title: '操作', key: 'actions' },
];
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header :class="styles.header">
      <div>
        <h1>岗位匹配结果</h1>
        <p>按岗位和配置版本查看真实结果；待核验、硬过滤与历史结果独立展示。</p>
      </div>
      <div>
        <Button
          :disabled="!rows.length || businessStatus !== 'SCORED'"
          :loading="recalcBusy"
          @click="openRecalc"
          >调整权重重算</Button
        ><Button @click="load(page)">刷新快照</Button>
      </div>
    </header>
    <Alert
      v-if="runStatus"
      type="info"
      show-icon
      :message="runStatus"
      description="仅恢复任务读取，不重新提交模型调用。"
    />
    <Alert
      type="info"
      show-icon
      message="AI辅助分析，仅供面试参考；最终判断由招聘人员作出。"
    /><Alert v-if="error" type="error" show-icon :message="error" /><Button
      v-if="error"
      @click="load(page)"
      >重试读取</Button
    >
    <HrInterviewBatchPanel
      :candidate-ids="rows.filter((r) => r.businessStatus === 'SCORED').map((r) => r.candidateId)"
      :position-id="positionId || rows[0]?.positionId"
    />
    <form class="filters" @submit.prevent="load()">
      <Input
        v-model:value="candidateId"
        placeholder="候选人ID（历史范围）"
        aria-label="候选人ID"
      /><Input v-model:value="positionId" placeholder="岗位ID" aria-label="岗位ID" /><Input
        v-model:value="configVersionId"
        placeholder="配置版本ID"
        aria-label="配置版本ID"
      /><Input v-model:value="keyword" placeholder="搜索候选人" /><Button
        html-type="submit"
        type="primary"
        :loading="loading"
        >查询</Button
      ><Select
        v-model:value="businessStatus"
        :options="Object.entries(statuses).map(([value, label]) => ({ value, label }))"
        style="min-width: 150px"
        @change="load()"
      />
    </form>
    <section v-if="statistics" class="matching-statistics">
      <div class="statistics-heading">
        <b>授权范围分母 {{ statistics.total }}</b
        ><span>{{ statisticsScope }} · 全授权当前版本，不随当前分页与候选搜索改变</span>
      </div>
      <div class="statistics-grid">
        <article v-for="(label, key) in statisticLabels" :key="key">
          <span>{{ label }}</span
          ><strong>{{ statistics[key] }}</strong>
        </article>
      </div>
    </section>
    <p v-else class="statistics-empty">请选择岗位与同一规则版本</p>
    <Tabs v-model:active-key="businessStatus" @change="load()"
      ><TabPane key="SCORED" tab="正式评分" /><TabPane key="REVIEW_REQUIRED" tab="待核验" /><TabPane
        key="FILTERED"
        tab="被硬条件过滤" /><TabPane key="SUPERSEDED" tab="历史结果"
    /></Tabs>
    <p v-if="businessStatus === 'REVIEW_REQUIRED'">
      待核验结果不进入正式排名；参考分只用于复核，未知不表示不具备。
    </p>
    <div style="min-width: 0; overflow-x: auto">
      <Table
        :columns="columns"
        :data-source="rows"
        row-key="resultId"
        :loading="loading"
        :scroll="{ x: 1100 }"
        :pagination="{
          current: page,
          pageSize: 20,
          total,
          showTotal: (n: number) => `共 ${n} 条`,
          onChange: (next: number) => load(next),
        }"
        ><template #emptyText
          ><span>{{
            error ? '读取未完成，请重试。' : '暂无匹配结果，请先选择已发布岗位并完成解析。'
          }}</span></template
        ><template #bodyCell="{ column, record }"
          ><template v-if="column.key === 'candidateName'">{{
            record.candidateName ?? '姓名未记录'
          }}</template
          ><template v-else-if="column.key === 'positionName'"
            >{{ record.positionName
            }}<small class="version">规则 {{ record.configVersion }}</small></template
          ><template v-else-if="column.key === 'totalScore'"
            ><strong>{{
              record.businessStatus === 'SCORED' && record.totalScore !== null
                ? record.totalScore.toFixed(1)
                : '—'
            }}</strong
            ><small
              v-if="record.businessStatus === 'REVIEW_REQUIRED' && record.referenceScore !== null"
              class="version"
              >参考 {{ record.referenceScore.toFixed(1) }}</small
            ></template
          ><template v-else-if="column.key === 'band'"
            ><Tag
              :color="
                record.businessStatus === 'REVIEW_REQUIRED'
                  ? 'orange'
                  : record.businessStatus === 'FILTERED'
                    ? 'default'
                    : record.totalScore >= 80
                      ? 'green'
                      : record.totalScore >= 65
                        ? 'blue'
                        : record.totalScore >= 50
                          ? 'orange'
                          : 'default'
              "
              >{{
                record.businessStatus === 'SCORED'
                  ? (bands[record.band] ?? record.band ?? '未记录')
                  : (statuses[record.businessStatus] ?? '未记录')
              }}</Tag
            ></template
          ><template v-else-if="column.key === 'dimensions'"
            ><span v-for="d in record.dimensions" :key="d.id" class="dimension"
              >{{ d.label }} {{ d.score ?? '—' }}</span
            ></template
          ><template v-else-if="column.key === 'evidenceCoverage'"
            >{{ record.evidenceCoverage }}%</template
          ><template v-else-if="column.key === 'actions'"
            ><Button
              type="link"
              @click="
                router.push(
                  `/ai-assistants/hr/matching/${record.candidateId}?resultId=${record.resultId}`,
                )
              "
              >查看分析</Button
            ><Button
              v-if="record.businessStatus === 'SCORED'"
              type="link"
              @click="
                router.push(
                  `/ai-assistants/hr/interviews/generate?candidateId=${record.candidateId}&positionId=${record.positionId}&resultId=${record.resultId}`,
                )
              "
              >生成面试提纲</Button
            ></template
          ></template
        ></Table
      >
    </div>
    <p class="hint">四档仅统计正式评分结果。历史结果保留原事实与配置快照；刷新不会重新调用模型。</p>
    <Modal
      v-model:open="recalcOpen"
      title="调整权重重算（无需模型调用）"
      ok-text="确认仅本次重算"
      :confirm-loading="recalcBusy"
      :ok-button-props="{ disabled: !recalcValid || !preview }"
      @ok="recalculate"
    >
      <p>
        影响当前页同岗位同规则版本的{{
          rows.filter(
            (r) =>
              r.positionId === rows[0]?.positionId && r.configVersion === rows[0]?.configVersion,
          ).length
        }}条结果。历史结果保留，生成新的参考配置结果，不修改岗位默认规则。
      </p>
      <label
        v-for="(label, key) in {
          skills: '技能',
          experience: '经验',
          projects: '项目',
          education: '学历',
          bonus: '加分',
        }"
        :key="key"
        style="display: flex; justify-content: space-between; margin: 12px 0"
        >{{ label }}权重<InputNumber
          v-model:value="recalcWeights[key]"
          :min="0"
          :max="100"
          :precision="0"
        />%</label
      >
      <Select
        v-model:value="recalcMode"
        :options="[
          { value: 'TEMPORARY', label: '仅本次临时重算' },
          { value: 'DEFAULT', label: '设为新默认版本' },
        ]"
        style="width: 220px"
      /><Button :loading="recalcBusy" :disabled="!recalcValid" @click="previewRecalc"
        >预览变化（无需模型调用）</Button
      >
      <section v-if="preview">
        <p>模型调用 {{ preview.modelCalls }} 次</p>
        <p v-for="item in preview.items" :key="item.sourceResultId">
          {{ item.candidateId }}：{{ item.oldScore ?? '—' }} → {{ item.newScore ?? '—' }} ·
          {{ item.businessStatus }}
        </p>
      </section>
      <p>合计 {{ Object.values(recalcWeights).reduce((a, b) => a + b, 0) }}%</p>
      <label
        v-for="(label, index) in ['强烈推荐', '推荐', '建议复核']"
        :key="label"
        style="display: flex; justify-content: space-between; margin: 12px 0"
        >{{ label }}阈值<InputNumber
          v-model:value="recalcThresholds[index]"
          :min="0"
          :max="100"
          :precision="0"
      /></label>
    </Modal>
  </div>
</template>
<style scoped>
.filters {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.filters .ant-input {
  max-width: 230px;
}
.version {
  display: block;
  color: #647087;
  margin-top: 5px;
}
.dimension {
  display: inline-block;
  margin: 2px 8px 2px 0;
  font-size: 12px;
}
.hint {
  font-size: 13px;
  color: #5e6a82;
}
@media (max-width: 700px) {
  .filters .ant-input {
    max-width: none;
  }
}
</style>

<style scoped>
.matching-statistics {
  background: #fff;
  border: 1px solid #dde4f2;
  border-radius: 8px;
  margin: 16px 0;
}
.statistics-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid #edf0f5;
}
.statistics-heading span {
  font-size: 12px;
  color: #64748b;
}
.statistics-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
}
.statistics-grid article {
  padding: 18px 20px;
  border-right: 1px solid #edf0f5;
}
.statistics-grid article:last-child {
  border: 0;
}
.statistics-grid span {
  color: #64748b;
  font-size: 12px;
}
.statistics-grid strong {
  display: block;
  font-size: 26px;
  margin-top: 7px;
  color: #334155;
}
.statistics-grid article:first-child strong {
  color: #16a34a;
}
.statistics-grid article:nth-child(2) strong {
  color: #2563eb;
}
.statistics-grid article:nth-child(3) strong {
  color: #d97706;
}
.statistics-empty {
  padding: 14px 18px;
  border: 1px dashed #cbd5e1;
  color: #64748b;
  border-radius: 6px;
}
@media (max-width: 700px) {
  .statistics-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .statistics-heading {
    display: block;
  }
  .statistics-heading span {
    display: block;
    margin-top: 5px;
  }
  .statistics-grid article {
    padding: 12px;
  }
}
</style>
