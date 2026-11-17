<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue';
import { Alert, Button, Checkbox, Input, InputNumber, Select } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../entities/hr';
const props = defineProps<{ candidateIds?: string[]; positionId?: string }>();
const selected = ref<string[]>([]);
const version = ref(1);
const templateId = ref('');
const templateVersion = ref('');
const exportIds = ref('');
const format = ref('PDF');
const confirmed = ref(false);
const busy = ref(false);
const error = ref('');
const id = ref('');
const kind = ref<'interview' | 'export'>('interview');
const batchSchema = z.object({
  id: z.string(),
  status: z.string(),
  items: z.array(
    z.object({
      candidateId: z.string().optional(),
      setId: z.string().nullable().optional(),
      status: z.string(),
      errorCode: z.string().nullable().optional(),
      exportId: z.string().nullable().optional(),
      grantId: z.string().nullable().optional(),
    }),
  ),
});
const batch = ref<z.infer<typeof batchSchema>>();
let timer: ReturnType<typeof setTimeout> | undefined;
let polls = 0;
async function read() {
  if (!id.value) return;
  error.value = '';
  try {
    batch.value = await hrRequest(
      `/${kind.value}-batches/${encodeURIComponent(id.value)}`,
      batchSchema,
    );
    if (
      !['SUCCEEDED', 'COMPLETED', 'FAILED', 'CANCELLED', 'PARTIAL_FAILED'].includes(
        batch.value.status,
      ) &&
      polls++ < 120
    )
      timer = setTimeout(read, 3000);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '批次读取失败';
  }
}
async function submit() {
  if (busy.value || !confirmed.value) return;
  busy.value = true;
  error.value = '';
  try {
    const items =
      kind.value === 'interview'
        ? selected.value.map((candidateId) => ({
            candidateId,
            positionId: props.positionId,
            targetMinutes: 45,
            counts: null,
            durations: null,
            templateId: templateId.value,
            templateVersion: templateVersion.value,
            round: '初试',
            language: '中文',
            expectedCandidateVersion: version.value,
          }))
        : exportIds.value
            .split(/[\s,，]+/)
            .filter(Boolean)
            .map((setId) => ({
              setId,
              setVersion: version.value,
              format: format.value,
              assignmentId: null,
              includeContact: false,
            }));
    batch.value = await hrWrite(`/${kind.value}-batches`, batchSchema, { items, confirmed: true });
    id.value = batch.value.id;
    confirmed.value = false;
    polls = 0;
    await read();
  } catch (e) {
    error.value = e instanceof Error ? e.message : '批次提交失败，不自动重发';
  } finally {
    busy.value = false;
  }
}
onBeforeUnmount(() => clearTimeout(timer));
</script>
<template>
  <details>
    <summary>勾选批量面试 / 安全导出</summary>
    <Alert v-if="error" type="error" :message="error" show-icon /><Select
      v-model:value="kind"
      :options="[
        { value: 'interview', label: '批量面试生成' },
        { value: 'export', label: '批量安全导出' },
      ]"
      style="width: 200px"
    /><template v-if="kind === 'interview'"
      ><Checkbox.Group
        v-model:value="selected"
        :options="(candidateIds ?? []).map((value) => ({ value, label: value }))" />
      <p>
        仅勾选已授权对象，{{
          selected.length
        }}份；每份45分钟，使用所选已发布模板。服务端逐对象核对费用与预算，无法获得预算不得发送。
      </p>
      <label>模板ID<Input v-model:value="templateId" /></label
      ><label>模板版本<Input v-model:value="templateVersion" /></label></template
    ><template v-else
      ><label>明确选择题集ID（逗号分隔）<Input.TextArea v-model:value="exportIds" /></label
      ><Select
        v-model:value="format"
        :options="[
          { value: 'PDF', label: 'PDF' },
          { value: 'WORD', label: 'Word' },
        ]"
        style="width: 120px" /></template
    ><label>所选对象冻结版本<InputNumber v-model:value="version" :min="1" :precision="0" /></label
    ><Checkbox v-model:checked="confirmed">确认所选范围及逐对象预算检查；失败不自动重发</Checkbox
    ><Button
      type="primary"
      :loading="busy"
      :disabled="
        !confirmed ||
        (kind === 'interview'
          ? !selected.length || !templateId || !templateVersion || !positionId
          : !exportIds.trim())
      "
      @click="submit"
      >一次提交所选批次</Button
    ><Input v-model:value="id" placeholder="已有批次ID（刷新恢复）" /><Button
      :disabled="!id"
      @click="read"
      >只读恢复批次</Button
    ><template v-if="batch"
      ><p>{{ batch.status }}</p>
      <p v-for="(item, index) in batch.items" :key="index">
        {{ item.candidateId ?? item.setId }} · {{ item.status }} · {{ item.errorCode ?? ''
        }}<a v-if="item.grantId" :href="`/api/hr/downloads/${item.grantId}`" download
          >下载一次文件</a
        ><a
          v-if="item.setId && kind === 'interview'"
          :href="`/ai-assistants/hr/interviews/questions?questionSetId=${item.setId}`"
          >查看题集</a
        >
      </p></template
    >
  </details>
</template>
