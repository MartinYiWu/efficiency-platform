<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  Alert,
  Button,
  Checkbox,
  Input,
  Modal,
  Pagination,
  Tabs,
  TabPane,
  Tag,
} from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite, matchingSchema, type HrMatching } from '../../../entities/hr';
import styles from './FilteredResumesPage.module.css';
const route = useRoute();
const router = useRouter();
const rows = ref<HrMatching[]>([]);
const page = ref(1);
const total = ref(0);
const status = ref('FILTERED');
const loading = ref(false);
const busy = ref(false);
const error = ref('');
const selected = ref<HrMatching>();
const conditionIds = ref<string[]>([]);
const reason = ref('');
let controller: AbortController | undefined;
const schema = z.object({
  items: z.array(matchingSchema),
  page: z.number(),
  pageSize: z.number(),
  total: z.number(),
});
async function load(next = 1) {
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = '';
  page.value = next;
  const params = new URLSearchParams({
    businessStatus: status.value,
    page: String(next),
    pageSize: '20',
  });
  if (route.query.positionId) params.set('positionId', String(route.query.positionId));
  if (route.query.configVersionId)
    params.set('configVersionId', String(route.query.configVersionId));
  try {
    const data = await hrRequest(`/matching-results?${params}`, schema, {
      signal: controller.signal,
    });
    rows.value = data.items;
    total.value = data.total;
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError'))
      error.value = e instanceof Error ? e.message : '过滤结果读取失败';
  } finally {
    loading.value = false;
  }
}
watch(
  () => [route.query.positionId, route.query.configVersionId],
  () => load(),
  { immediate: true },
);
onBeforeUnmount(() => controller?.abort());
function open(result: HrMatching) {
  selected.value = result;
  conditionIds.value = [];
  reason.value = '';
}
async function override() {
  if (!selected.value || busy.value || !reason.value.trim() || !conditionIds.value.length) return;
  busy.value = true;
  try {
    const result = await hrWrite(
      `/matching-results/${selected.value.resultId}/overrides`,
      matchingSchema,
      {
        conditionIds: conditionIds.value,
        reason: reason.value.trim(),
        expectedSnapshotHash: selected.value.snapshotHash,
      },
    );
    selected.value = undefined;
    await router.push(
      `/ai-assistants/hr/matching/${result.candidateId}?resultId=${result.resultId}`,
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '放行失败，未生成新评分';
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header class="heading">
      <div>
        <h1>被硬性条件过滤的简历</h1>
        <p>明确失败与待核验独立展示，所有被过滤简历仍可查看和复核。</p>
      </div>
      <Button @click="router.push('/ai-assistants/hr/matching')">返回匹配结果</Button>
    </header>
    <Alert
      type="info"
      show-icon
      message="未提及不等于不具备。过滤结果不生成总分，不将技术失败视为候选人不达标。"
    /><Alert v-if="error" type="error" show-icon :message="error" /><Button
      v-if="error"
      @click="load(page)"
      >重试读取</Button
    ><Tabs v-model:active-key="status" @change="load()"
      ><TabPane key="FILTERED" tab="被硬条件过滤" /><TabPane key="REVIEW_REQUIRED" tab="待核验"
    /></Tabs>
    <p v-if="loading" role="status">正在读取真实过滤快照…</p>
    <p v-if="!loading && !rows.length && !error">
      {{
        status === 'FILTERED' ? '当前范围没有被硬条件过滤的简历。' : '当前范围没有待核验的简历。'
      }}
    </p>
    <article v-for="result in rows" :key="result.resultId" class="candidate">
      <header>
        <h2>{{ result.candidateName ?? '姓名未记录' }}</h2>
        <Tag :color="result.businessStatus === 'FILTERED' ? 'default' : 'orange'">{{
          result.businessStatus === 'FILTERED' ? '被硬条件过滤 · 总分 —' : '待核验 · 不进入正式排名'
        }}</Tag>
      </header>
      <p>{{ result.positionName }} · 规则 {{ result.configVersion }}</p>
      <section
        v-for="condition in result.hardConditions.filter(
          (c) => !['PASS', 'OVERRIDDEN'].includes(c.status),
        )"
        :key="condition.id"
        class="condition"
      >
        <b>{{ condition.label }}</b
        ><Tag :color="condition.status === 'FAIL' ? 'default' : 'orange'">{{
          {
            PASS: '通过',
            OVERRIDDEN: '已人工放行',
            FAIL: '明确不满足',
            UNKNOWN: '未提及',
            NEEDS_REVIEW: '待核验',
            BORDERLINE: '临界',
          }[condition.status] ?? '待核验'
        }}</Tag>
        <p>
          期望：{{ condition.expected ?? '未记录' }} · 实际：{{
            condition.actual ?? '未提及，不能直接判定不具备'
          }}
        </p>
        <small>{{
          condition.overridable ? '可由授权人员填写理由后申请放行' : '该条件不允许人工放行'
        }}</small>
      </section>
      <div class="actions">
        <Button
          @click="
            router.push(
              `/ai-assistants/hr/matching/${result.candidateId}?resultId=${result.resultId}`,
            )
          "
          >查看原文与分析</Button
        ><Button
          v-if="result.businessStatus === 'FILTERED'"
          type="primary"
          :disabled="
            !result.hardConditions.some(
              (c) => c.overridable && ['FAIL', 'BORDERLINE'].includes(c.status),
            )
          "
          @click="open(result)"
          >人工放行条件</Button
        ><Button
          v-if="result.businessStatus === 'REVIEW_REQUIRED'"
          @click="router.push(`/ai-assistants/hr/resumes/candidates/${result.candidateId}/confirm`)"
          >补充核对事实</Button
        >
      </div>
    </article>
    <Pagination
      v-if="total > 20"
      :current="page"
      :page-size="20"
      :total="total"
      @change="load"
    /><Modal
      :open="!!selected"
      title="人工放行硬性条件"
      ok-text="确认放行并生成新结果"
      cancel-text="取消"
      :confirm-loading="busy"
      :ok-button-props="{ disabled: !reason.trim() || !conditionIds.length }"
      @cancel="selected = undefined"
      @ok="override"
      ><Alert
        type="warning"
        message="原始事实与旧结果保持不变；人工放行是程序性例外，不自动授予推荐高档。"
      /><Checkbox.Group v-model:value="conditionIds" class="conditions"
        ><label
          v-for="condition in selected?.hardConditions.filter((c) => c.status !== 'PASS')"
          :key="condition.id"
          ><Checkbox
            :aria-label="condition.label"
            :value="condition.id"
            :disabled="!condition.overridable || !['FAIL', 'BORDERLINE'].includes(condition.status)"
            >{{ condition.label }}</Checkbox
          ><small>{{ condition.overridable ? '仅放行已明确判断的条件' : '不可放行' }}</small></label
        ></Checkbox.Group
      ><Input.TextArea
        v-model:value="reason"
        :maxlength="500"
        :rows="4"
        placeholder="请说明放行理由（1至500字）"
        aria-label="放行理由"
      />
      <p>未形成判断的条件只显示需评估，不填估算分。</p></Modal
    >
  </div>
</template>
<style scoped>
.heading,
.candidate > header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
}
h1 {
  font-size: 25px;
  margin: 0;
}
h2 {
  font-size: 20px;
  margin: 0;
}
.candidate {
  padding: 20px;
  background: white;
  border: 1px solid #dce3ef;
  border-radius: 8px;
}
.condition {
  background: #f7f9fc;
  border: 1px solid #e0e6ef;
  border-radius: 5px;
  padding: 12px;
  margin: 10px 0;
}
.condition > .ant-tag {
  margin-left: 12px;
}
.actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  flex-wrap: wrap;
}
.conditions {
  display: grid;
  gap: 15px;
  margin: 18px 0;
}
.conditions label {
  display: grid;
  gap: 4px;
}
small {
  font-size: 12px;
  color: #657188;
}
@media (max-width: 700px) {
  .heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .candidate {
    padding: 13px;
  }
}
</style>
