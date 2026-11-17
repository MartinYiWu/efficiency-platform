<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Alert, Button, Input, InputNumber, Select } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../../entities/hr';
import { interviewSchema } from '../../../entities/hr/completion';
import styles from './InterviewGeneratePage.module.css';
const route = useRoute();
const router = useRouter();
const candidateId = ref(String(route.query.candidateId ?? ''));
const positionId = ref(String(route.query.positionId ?? ''));
const version = ref<number>();
const minutes = ref(45);
const templateId = ref('');
const templateVersion = ref('');
const templateSchema = z.object({
  id: z.string(),
  departmentId: z.string(),
  name: z.string(),
  status: z.string(),
  version: z.number(),
  layerInstructions: z.array(z.string()),
  counts: z.array(z.number()),
  durations: z.array(z.number()),
  round: z.string(),
  language: z.string(),
});
const templates = ref<z.infer<typeof templateSchema>[]>([]);
const templateName = ref('');
const templateDepartment = ref('');
const templateInstructions = ref(['', '', '', '', '', '']);
const savedTemplate = ref<z.infer<typeof templateSchema>>();
const templateHistory = ref<z.infer<typeof templateSchema>[]>([]);
async function loadTemplates() {
  busy.value = true;
  error.value = '';
  try {
    templates.value = await hrRequest('/interview-templates', z.array(templateSchema));
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取模板失败';
  } finally {
    busy.value = false;
  }
}
function selectTemplate(id: string) {
  const template = templates.value.find((t) => t.id === id);
  if (!template) return;
  templateId.value = template.id;
  templateVersion.value = String(template.version);
  counts.value = [...template.counts];
  durations.value = [...template.durations];
  round.value = template.round;
  language.value = template.language;
  minutes.value = template.durations.reduce(
    (sum, duration, index) => sum + duration * (template.counts[index] ?? 0),
    0,
  );
  savedTemplate.value = structuredClone(template);
  templateName.value = template.name;
  templateDepartment.value = template.departmentId;
  templateInstructions.value = [...template.layerInstructions];
}
async function saveTemplate(publish = false) {
  if (busy.value || !templateName.value.trim() || !templateDepartment.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    const body = {
      departmentId: templateDepartment.value,
      name: templateName.value,
      expectedVersion: savedTemplate.value?.version ?? 0,
      layerInstructions: templateInstructions.value,
      counts: counts.value,
      durations: durations.value,
      round: round.value,
      language: language.value,
    };
    savedTemplate.value =
      publish && savedTemplate.value
        ? await hrWrite(`/interview-templates/${savedTemplate.value.id}/versions`, templateSchema, {
            expectedVersion: savedTemplate.value.version,
          })
        : savedTemplate.value
          ? await hrRequest(`/interview-templates/${savedTemplate.value.id}`, templateSchema, {
              method: 'PUT',
              headers: {
                'Content-Type': 'application/json',
                'Idempotency-Key': crypto.randomUUID(),
              },
              body: JSON.stringify(body),
            })
          : await hrWrite('/interview-templates', templateSchema, body);
    templateHistory.value = await hrRequest(
      `/interview-templates/${savedTemplate.value.id}/versions`,
      z.array(templateSchema),
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '模板保存失败';
  } finally {
    busy.value = false;
  }
}

const round = ref('初试');
const language = ref('中文');
const counts = ref([2, 2, 2, 2, 1, 1]);
const durations = ref([3, 4, 5, 5, 4, 3]);
function preset() {
  const byMinutes: Record<number, number[]> = {
    30: [1, 1, 2, 1, 1, 1],
    45: [2, 2, 2, 2, 1, 1],
    60: [2, 3, 3, 3, 1, 1],
    90: [3, 4, 5, 4, 2, 2],
  };
  counts.value = byMinutes[minutes.value] ?? [2, 2, 2, 2, 1, 1];
  durations.value = [3, 4, 5, 5, 4, 3];
}
const layers = ['开场与基础', '专业知识', '项目深挖', '场景应用', '协作与沟通', '反向提问'];
const error = ref('');
const busy = ref(false);
async function generate() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const set = await hrWrite('/interview-sets', interviewSchema, {
      candidateId: candidateId.value,
      positionId: positionId.value,
      targetMinutes: minutes.value,
      counts: counts.value,
      durations: durations.value,
      templateId: templateId.value,
      templateVersion: templateVersion.value,
      round: round.value,
      language: language.value,
      expectedCandidateVersion: version.value,
    });
    await router.push(`/ai-assistants/hr/interviews/questions?questionSetId=${set.id}`);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '生成失败';
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header>
      <h1>生成面试提纲</h1>
      <p>基于真实事实与岗位要求生成；未具备预算、绑定或素材时明确阻断。</p>
    </header>
    <Alert v-if="error" type="error" :message="error" show-icon /><Alert
      type="info"
      message="生成属于有费用操作，必须已有有效预算。刷新不会自动重发。"
      show-icon
    />
    <section
      style="
        display: grid;
        gap: 14px;
        max-width: 800px;
        background: #ffffffa8;
        padding: 24px;
        border: 1px solid #dde4f2;
        border-radius: 8px;
      "
    >
      <details>
        <summary>面试模板管理与版本</summary>
        <Button :loading="busy" @click="loadTemplates">读取可用模板</Button
        ><Select
          :value="templateId"
          :options="
            templates.map((t) => ({
              value: t.id,
              label: `${t.name} · v${t.version} · ${t.status}`,
            }))
          "
          style="width: 100%"
          @update:value="selectTemplate(String($event))"
        /><label>模板部门ID<Input v-model:value="templateDepartment" /></label
        ><label>模板名称<Input v-model:value="templateName" /></label
        ><label v-for="(layer, index) in layers" :key="layer"
          >{{ layer }}层指令<Input.TextArea v-model:value="templateInstructions[index]" /></label
        ><Button
          :loading="busy"
          :disabled="!templateName.trim() || !templateDepartment.trim()"
          @click="saveTemplate()"
          >保存面试模板草稿</Button
        ><Button :loading="busy" :disabled="!savedTemplate" @click="saveTemplate(true)"
          >发布模板版本</Button
        >
        <p v-for="item in templateHistory" :key="item.version">
          v{{ item.version }} · {{ item.status }}
        </p>
      </details>
      <label>候选人ID<Input v-model:value="candidateId" /></label
      ><label>岗位ID<Input v-model:value="positionId" /></label
      ><label>候选人事实版本<InputNumber v-model:value="version" :min="1" :precision="0" /></label
      ><label>已发布模板ID<Input v-model:value="templateId" /></label
      ><label>模板版本<Input v-model:value="templateVersion" /></label
      ><label>轮次<Input v-model:value="round" /></label
      ><label>语言<Input v-model:value="language" /></label
      ><label
        >面试总时长<Select
          v-model:value="minutes"
          :options="[30, 45, 60, 90].map((value) => ({ value, label: `${value}分钟` }))"
          style="width: 160px"
          @change="preset"
      /></label>
      <div v-for="(layer, index) in layers" :key="layer">
        <b>{{ layer }}</b
        ><label
          >题量<InputNumber
            v-model:value="counts[index]"
            :min="0"
            :max="10"
            :precision="0" /></label
        ><label
          >每题分钟<InputNumber v-model:value="durations[index]" :min="0" :max="90" :precision="0"
        /></label>
      </div>
      <p>
        合计 {{ counts.reduce((a, b) => a + b, 0) }} 题，{{
          durations.reduce((sum, duration, index) => sum + duration * (counts[index] ?? 0), 0)
        }}
        分钟。
      </p>
      <Button
        type="primary"
        :loading="busy"
        :disabled="
          !templateId.trim() ||
          !templateVersion.trim() ||
          !candidateId.trim() ||
          !positionId.trim() ||
          !version ||
          durations.reduce((sum, duration, index) => sum + duration * (counts[index] ?? 0), 0) >
            minutes ||
          counts.reduce((a, b) => a + b, 0) === 0
        "
        @click="generate"
        >确认参数并生成</Button
      >
    </section>
  </div>
</template>

<style scoped>
header {
  margin-bottom: 20px;
}
header h1 {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 6px;
  color: #10172b;
}
header p {
  color: #64748b;
  font-size: 13px;
  margin: 0;
  line-height: 1.6;
}
label {
  line-height: 1.6;
}
label:has(> .ant-input),
label:has(> .ant-input-number) {
  display: grid;
  gap: 5px;
  font-size: 13px;
  color: #475569;
}
details {
  background: #ffffffa8;
  border: 1px solid #dde4f2;
  border-radius: 8px;
  padding: 15px 18px;
  margin: 14px 0;
}
summary {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  cursor: pointer;
}
details[open] > summary {
  margin-bottom: 14px;
}
table {
  background: #fff;
  border-collapse: collapse;
  border: 1px solid #dde4f2;
}
th {
  padding: 12px 18px;
  background: #f6f8fc;
  font-weight: 500;
  color: #64748b;
  font-size: 12px;
  text-align: left;
}
td {
  padding: 15px 18px;
  border-bottom: 1px solid #edf0f5;
  vertical-align: middle;
  font-size: 13px;
}
article h2 {
  font-size: 18px;
  margin: 12px 0;
}
article p {
  line-height: 1.7;
  color: #475569;
}
.ant-btn + .ant-btn {
  margin-left: 8px;
}
@media (max-width: 700px) {
  header {
    margin-bottom: 16px;
  }
  header h1 {
    font-size: 22px;
  }
  details {
    padding: 12px;
  }
  th,
  td {
    padding: 12px;
  }
  .ant-btn + .ant-btn {
    margin-left: 4px;
  }
}
</style>
