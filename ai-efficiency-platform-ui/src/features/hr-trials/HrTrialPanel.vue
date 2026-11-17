<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Alert, Button, Input, InputNumber, Select } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../entities/hr';
import { trialSchema } from '../../entities/hr/completion';
const props = defineProps<{ positionId: string; positionVersion: number }>();
const trials = ref<z.infer<typeof trialSchema>[]>([]);
const active = ref<z.infer<typeof trialSchema>>();
const size = ref(10);
const seed = ref(1);
const candidates = ref('');
const busy = ref(false);
const error = ref('');
const planSchema = z.object({
  trialId: z.string(),
  departmentId: z.string(),
  trialVersion: z.number(),
  version: z.number(),
  operations: z.array(
    z.object({
      candidateId: z.string(),
      factSnapshotId: z.string(),
      runRef: z.string(),
      semanticBatches: z.number(),
    }),
  ),
  maximumNewHttpAttempts: z.number(),
  maximumCostMicrounits: z.number(),
  status: z.string(),
  errorCode: z.string().nullable(),
  deadline: z.string().nullable(),
});
const plan = ref<z.infer<typeof planSchema>>();
async function executionPlan() {
  if (!active.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    plan.value = await hrWrite(`/trials/${active.value.id}/execution-plan`, planSchema, {
      expectedVersion: active.value.version,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : '预检失败';
  } finally {
    busy.value = false;
  }
}
async function execute() {
  if (!active.value || !plan.value || plan.value.status !== 'READY' || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    select(
      await hrWrite(`/trials/${active.value.id}/execute`, trialSchema, {
        expectedVersion: active.value.version,
        expectedPlanVersion: plan.value.version,
      }),
    );
    plan.value = undefined;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '执行失败，请核查已提交任务，不自动重发';
  } finally {
    busy.value = false;
  }
}

const labels = ref<Record<string, { label: string; reason: string; note: string }>>({});
const options = [
  'STRONGLY_RECOMMENDED',
  'RECOMMENDED',
  'CONSIDER',
  'NOT_RECOMMENDED',
  'FILTERED',
  'REVIEW_REQUIRED',
].map((value) => ({ value, label: value }));
async function load() {
  busy.value = true;
  error.value = '';
  try {
    trials.value = await hrRequest(
      `/trials?positionId=${encodeURIComponent(props.positionId)}`,
      z.array(trialSchema),
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    busy.value = false;
  }
}
function select(trial: z.infer<typeof trialSchema>) {
  active.value = trial;
  plan.value = undefined;
  labels.value = Object.fromEntries(
    trial.results.map((r) => [r.candidateId, { label: '', reason: '', note: '' }]),
  );
}
async function create() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    select(
      await hrWrite('/trials', trialSchema, {
        positionId: props.positionId,
        sampleSize: size.value,
        candidateIds: candidates.value.split(/[\s,，]+/).filter(Boolean),
        seed: seed.value,
        expectedPositionVersion: props.positionVersion,
      }),
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '预演失败';
  } finally {
    busy.value = false;
  }
}
async function save() {
  if (!active.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    select(
      await hrWrite(`/trials/${active.value.id}/labels`, trialSchema, {
        expectedVersion: active.value.version,
        labels: Object.entries(labels.value).map(([candidateId, label]) => ({
          candidateId,
          ...label,
        })),
      }),
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '盲标保存失败';
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <section>
    <h2>独立配置预演</h2>
    <Alert v-if="error" type="error" :message="error" show-icon />
    <p>
      只写预演空间，不进入正式结果。请先独立盲标；未标注不展示系统分档或准确率。最多按样本数核算调用，缺预算将阻断。
    </p>
    <label
      >样本数<Select
        v-model:value="size"
        :options="[10, 20, 50].map((value) => ({ value, label: String(value) }))"
        style="width: 100px" /></label
    ><label>随机种子<InputNumber v-model:value="seed" :precision="0" /></label
    ><Input.TextArea
      v-model:value="candidates"
      aria-label="预演候选人ID"
      placeholder="输入已授权候选人ID，以逗号或换行分隔"
    /><Button type="primary" :loading="busy" :disabled="!candidates.trim()" @click="create"
      >创建独立预演范围</Button
    ><Button :loading="busy" @click="load">读取已有预演</Button
    ><Button v-for="trial in trials" :key="trial.id" @click="select(trial)"
      >{{ trial.id }} · {{ trial.status }}</Button
    ><template v-if="active"
      ><Button :loading="busy" @click="executionPlan">预检整批调用与费用上界</Button>
      <section v-if="plan">
        <p>{{ plan.status }} · {{ plan.errorCode ?? '' }}</p>
        <p>
          最多新增HTTP {{ plan.maximumNewHttpAttempts }} 次 · 费用上界
          {{ plan.maximumCostMicrounits }} 微元 · 截止 {{ plan.deadline ?? '未授权' }}
        </p>
        <Button type="primary" :loading="busy" :disabled="plan.status !== 'READY'" @click="execute"
          >确认费用上界并执行独立预演</Button
        >
      </section>
      <p>实际样本 {{ active.actualSize }} / {{ active.sampleSize }} · {{ active.status }}</p>
      <article v-for="result in active.results" :key="result.candidateId">
        <b>{{ result.candidateId }}</b
        ><template v-if="result.label === null"
          ><Select
            v-model:value="labels[result.candidateId]!.label"
            :options="options"
            placeholder="先独立标注"
            style="width: 240px" /><Input
            v-model:value="labels[result.candidateId]!.reason"
            placeholder="标注理由"
        /></template>
        <p v-else>
          系统分档 {{ result.label }} · {{ result.score === null ? '无分数' : result.score }} · 覆盖
          {{ result.coverage ?? '未记录' }}
        </p>
      </article>
      <Button
        :loading="busy"
        :disabled="
          !Object.values(labels).length ||
          Object.values(labels).some((v) => !v.label || !v.reason.trim())
        "
        @click="save"
        >提交独立标注</Button
      >
      <p v-for="(rate, id) in active.hardConditionFailureRates" :key="id">
        硬条件 {{ id }} 失败率 {{ rate }}%
        <span v-if="rate > 40">（超过40%，优先检查条件设置）</span>
      </p>
      <p v-if="active.diagnosis">{{ active.diagnosis }}</p>
      <p>
        一致率：{{
          active.agreement === null ? '有效双标样本不足，不计算' : `${active.agreement}%`
        }}
      </p>
      <p>{{ active.verified ? '达到当前预演验证门槛' : '尚未达到验证门槛' }}</p></template
    >
  </section>
</template>
