<script setup lang="ts">
import { ref } from 'vue';
import { Alert, Button, Checkbox, Input } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../entities/hr';
const props = defineProps<{ positionId: string; positionVersion: number; hasUnsaved: boolean }>();
const emit = defineEmits<{ adopted: [] }>();
const schema = z.object({
  id: z.string(),
  positionId: z.string(),
  departmentId: z.string(),
  sourceText: z.string(),
  truncated: z.boolean(),
  candidates: z.array(
    z.object({
      id: z.string(),
      type: z.string(),
      label: z.string(),
      originalQuote: z.string(),
      start: z.number(),
      end: z.number(),
    }),
  ),
  safetyWarnings: z.array(z.string()),
  version: z.number(),
  adoptedIds: z.array(z.string()),
});
const text = ref('');
const file = ref<File>();
async function generateFile() {
  if (!file.value || busy.value || props.hasUnsaved) return;
  busy.value = true;
  error.value = '';
  try {
    const body = new FormData();
    body.set('file', file.value);
    body.set('expectedPositionVersion', String(props.positionVersion));
    draft.value = await hrRequest(`/positions/${props.positionId}/jd-drafts/file`, schema, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body,
    });
    selected.value = [];
    draftId.value = draft.value.id;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '文件草案失败';
  } finally {
    busy.value = false;
  }
}
const draft = ref<z.infer<typeof schema>>();
const selected = ref<string[]>([]);
const busy = ref(false);
const error = ref('');
const draftId = ref('');
async function generate() {
  if (busy.value || !text.value.trim() || props.hasUnsaved) return;
  busy.value = true;
  error.value = '';
  try {
    draft.value = await hrWrite(`/positions/${props.positionId}/jd-drafts`, schema, {
      text: text.value,
      expectedPositionVersion: props.positionVersion,
    });
    selected.value = [];
    draftId.value = draft.value.id;
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'JD草案生成失败';
  } finally {
    busy.value = false;
  }
}
async function read() {
  if (!draftId.value.trim() || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    draft.value = await hrRequest(
      `/positions/${props.positionId}/jd-drafts/${encodeURIComponent(draftId.value)}`,
      schema,
    );
    selected.value = [];
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    busy.value = false;
  }
}
async function adopt() {
  if (!draft.value || !selected.value.length || busy.value || props.hasUnsaved) return;
  busy.value = true;
  error.value = '';
  try {
    draft.value = await hrWrite(
      `/positions/${props.positionId}/jd-drafts/${draft.value.id}/adopt`,
      schema,
      {
        expectedVersion: draft.value.version,
        expectedPositionVersion: props.positionVersion,
        candidateIds: selected.value,
      },
    );
    selected.value = [];
    emit('adopted');
  } catch (e) {
    error.value = e instanceof Error ? e.message : '采用失败';
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <details>
    <summary>JD辅助草案（默认不采用）</summary>
    <Alert v-if="error" type="error" :message="error" show-icon />
    <p>
      生成需要已绑定技能与有效预算；敏感字段不进入评分。请先保存当前修改，候选要求须人工选择并补齐评分锚点。
    </p>
    <input
      type="file"
      accept=".doc,.docx,.pdf,.txt"
      aria-label="JD文件"
      @change="file = ($event.target as HTMLInputElement).files?.[0]"
    /><Button :loading="busy" :disabled="!file || hasUnsaved" @click="generateFile"
      >从文件生成草案（需要预算）</Button
    >
    <Input.TextArea v-model:value="text" :rows="4" aria-label="JD原文" /><Button
      :loading="busy"
      :disabled="!text.trim() || hasUnsaved"
      @click="generate"
      >确认生成JD草案</Button
    ><Input v-model:value="draftId" placeholder="已有草案ID" /><Button
      :loading="busy"
      :disabled="!draftId.trim()"
      @click="read"
      >读取已有草案</Button
    ><template v-if="draft"
      ><Alert
        v-for="warning in draft.safetyWarnings"
        :key="warning"
        type="warning"
        :message="warning"
      /><Checkbox.Group v-model:value="selected"
        ><article v-for="candidate in draft.candidates" :key="candidate.id">
          <Checkbox :value="candidate.id">{{ candidate.label }} · {{ candidate.type }}</Checkbox>
          <blockquote>{{ candidate.originalQuote }}</blockquote>
          <small>原文偏移 {{ candidate.start }}–{{ candidate.end }}</small>
        </article></Checkbox.Group
      ><Button :loading="busy" :disabled="!selected.length || hasUnsaved" @click="adopt"
        >仅采用勾选项到岗位草稿</Button
      ></template
    >
  </details>
</template>
