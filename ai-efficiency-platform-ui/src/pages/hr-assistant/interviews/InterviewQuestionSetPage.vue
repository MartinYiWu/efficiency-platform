<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Alert, Button, Input, InputNumber, Modal, Tag } from 'ant-design-vue';
import { hrRequest, hrWrite } from '../../../entities/hr';
import { interviewSchema } from '../../../entities/hr/completion';
import { z } from 'zod';
import styles from './InterviewQuestionSetPage.module.css';
const route = useRoute();
const router = useRouter();
const set = ref<z.infer<typeof interviewSchema>>();
const busy = ref(false);
const error = ref('');
const editing = ref(false);
const dirty = ref(false);
const assignmentOpen = ref(false);
const interviewer = ref('');
const assignmentExpiry = ref('');
const assignment = ref<{
  id: string;
  setId: string;
  setVersion: number;
  interviewerId: string;
  expiresAt: string;
  status: string;
}>();
const assignmentReason = ref('');
async function assign() {
  if (!set.value || busy.value || !interviewer.value.trim() || !assignmentExpiry.value) return;
  busy.value = true;
  error.value = '';
  try {
    assignment.value = await hrWrite(
      '/interview-assignments',
      z.object({
        id: z.string(),
        setId: z.string(),
        setVersion: z.number(),
        interviewerId: z.string(),
        expiresAt: z.string(),
        status: z.string(),
      }),
      {
        setId: set.value.id,
        setVersion: set.value.version,
        interviewerId: interviewer.value,
        expiresAt: new Date(assignmentExpiry.value).toISOString(),
      },
    );
    assignmentOpen.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '指派失败';
  } finally {
    busy.value = false;
  }
}
async function revokeAssignment() {
  if (!assignment.value || busy.value || !assignmentReason.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    await hrWrite(`/interview-assignments/${assignment.value.id}/revocations`, z.unknown(), {
      reason: assignmentReason.value,
    });
    assignment.value = undefined;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '撤销失败';
  } finally {
    busy.value = false;
  }
}
function addQuestion() {
  if (!set.value) return;
  set.value.questions.push({
    id: crypto.randomUUID(),
    layer: 0,
    title: '',
    purpose: '',
    answerPoints: [],
    followUps: [],
    references: { excellent: '', qualified: '', needsVerification: '' },
    sourceType: 'REQUIREMENT',
    sourceIds: [],
    minutes: 5,
    dimension: null,
  });
  dirty.value = true;
  editing.value = true;
}

async function load() {
  if (!route.query.questionSetId) return;
  if (dirty.value && !window.confirm('题集修改尚未保存，确认重新读取并放弃修改？')) return;
  busy.value = true;
  error.value = '';
  try {
    set.value = await hrRequest(
      `/interview-sets/${encodeURIComponent(String(route.query.questionSetId))}`,
      interviewSchema,
    );
    dirty.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    busy.value = false;
  }
}
async function save() {
  if (!set.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    set.value = await hrRequest(`/interview-sets/${set.value.id}`, interviewSchema, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ expectedVersion: set.value.version, questions: set.value.questions }),
    });
    dirty.value = false;
    editing.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败';
  } finally {
    busy.value = false;
  }
}
async function regenerate(id: string) {
  if (!set.value || busy.value || dirty.value) return;
  busy.value = true;
  error.value = '';
  try {
    set.value = await hrWrite(
      `/interview-sets/${set.value.id}/questions/${id}/regenerations`,
      interviewSchema,
      { expectedVersion: set.value.version },
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '重生失败';
  } finally {
    busy.value = false;
  }
}
function move(index: number, delta: number) {
  if (!set.value) return;
  const q = set.value.questions;
  [q[index], q[index + delta]] = [q[index + delta]!, q[index]!];
  dirty.value = true;
}
onMounted(load);
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header>
      <h1>面试题集</h1>
      <p v-if="set">v{{ set.version }} · {{ set.status }} · 预计{{ set.estimatedMinutes }}分钟</p>
      <p v-else>请选择已保存题集，不会自动生成。</p>
    </header>
    <Alert v-if="error" type="error" :message="error" show-icon /><Button
      :loading="busy"
      @click="load"
      >刷新快照</Button
    ><template v-if="set"
      ><Button @click="editing = !editing">{{ editing ? '结束编辑' : '编辑题集' }}</Button>
      <Button @click="addQuestion">新增人工题目</Button
      ><Button :disabled="dirty" @click="assignmentOpen = true">指派面试官</Button
      ><Button type="primary" :loading="busy" :disabled="!dirty" @click="save">保存新版本</Button
      ><Button
        :disabled="dirty"
        @click="router.push(`/ai-assistants/hr/interviews/guide?questionSetId=${set.id}`)"
        >A4预览与导出</Button
      ><Alert
        v-if="set.insufficientLayers.length"
        type="warning"
        :message="`素材不足层级：${set.insufficientLayers.join('、')}；不以虚构个性化题补足。`" />
      <section
        v-for="(question, index) in set.questions"
        :key="question.id"
        style="
          background: #ffffffa8;
          border: 1px solid #dde4f2;
          padding: 20px;
          border-radius: 8px;
          margin: 14px 0;
        "
      >
        <Tag>第{{ question.layer + 1 }}层</Tag><Tag>{{ question.minutes }}分钟</Tag
        ><template v-if="editing"
          ><Input
            v-model:value="question.title"
            aria-label="题目内容"
            @change="dirty = true"
          /><label
            >题目层级<select v-model.number="question.layer" @change="dirty = true">
              <option v-for="layer in [0, 1, 2, 3, 4, 5]" :key="layer" :value="layer">
                第{{ layer + 1 }}层
              </option>
            </select></label
          ><label
            >来源类型<select v-model="question.sourceType" @change="dirty = true">
              <option value="REQUIREMENT">岗位要求</option>
              <option value="RESUME_VERIFY">简历待核实</option>
            </select></label
          ><label
            >来源ID（逗号分隔）<Input
              :value="question.sourceIds.join(',')"
              @update:value="
                question.sourceIds = $event
                  .split(',')
                  .map((v) => v.trim())
                  .filter(Boolean);
                dirty = true;
              " /></label
          ><label
            >回答要点（每行一项）<Input.TextArea
              :value="question.answerPoints.join('\n')"
              @update:value="
                question.answerPoints = $event.split('\n').filter(Boolean);
                dirty = true;
              " /></label
          ><label
            >追问（每行一项）<Input.TextArea
              :value="question.followUps.join('\n')"
              @update:value="
                question.followUps = $event.split('\n').filter(Boolean);
                dirty = true;
              " /></label
          ><label
            >充分回答参考<Input
              v-model:value="question.references.excellent"
              @change="dirty = true" /></label
          ><label
            >基本回答参考<Input
              v-model:value="question.references.qualified"
              @change="dirty = true" /></label
          ><label
            >待核实参考<Input
              v-model:value="question.references.needsVerification"
              @change="dirty = true" /></label
          ><label>目的<Input v-model:value="question.purpose" @change="dirty = true" /></label
          ><label
            >分钟<InputNumber
              v-model:value="question.minutes"
              :min="1"
              @change="dirty = true" /></label
          ><Button :disabled="index === 0" @click="move(index, -1)">上移</Button
          ><Button :disabled="index === set.questions.length - 1" @click="move(index, 1)"
            >下移</Button
          ><Button
            danger
            @click="
              set.questions.splice(index, 1);
              dirty = true;
            "
            >删除本题</Button
          ></template
        >
        <h2 v-else>{{ index + 1 }}. {{ question.title }}</h2>
        <p>{{ question.purpose }}</p>
        <details>
          <summary>回答要点与追问</summary>
          <ul>
            <li v-for="point in question.answerPoints" :key="point">{{ point }}</li>
          </ul>
          <p v-for="follow in question.followUps" :key="follow">追问：{{ follow }}</p>
          <p>充分：{{ question.references.excellent }}</p>
          <p>基本：{{ question.references.qualified }}</p>
          <p>待核实：{{ question.references.needsVerification }}</p>
        </details>
        <p>
          来源：{{ question.sourceType === 'REQUIREMENT' ? '岗位要求' : '简历待核实' }} ·
          {{ question.sourceIds.join('、') }}
        </p>
        <Button :loading="busy" :disabled="dirty" @click="regenerate(question.id)"
          >仅重新生成本题（需要预算）</Button
        >
      </section>
      <p v-if="!set.questions.length">题集暂无问题。</p>
      <section v-if="assignment">
        <p>指派 {{ assignment.status }} · 到期 {{ assignment.expiresAt }}</p>
        <a :href="`/ai-assistants/hr/interviews/assigned/${assignment.id}`">面试官专用链接</a
        ><Input v-model:value="assignmentReason" placeholder="撤销指派原因" /><Button
          :disabled="!assignmentReason.trim()"
          :loading="busy"
          @click="revokeAssignment"
          >撤销指派</Button
        >
      </section>
      <Modal
        v-model:open="assignmentOpen"
        title="指派面试官"
        :confirm-loading="busy"
        :ok-button-props="{ disabled: !interviewer.trim() || !assignmentExpiry }"
        @ok="assign"
        ><p>仅授权安全题集视图，不包含候选人评分、联系方式和原始附件。</p>
        <label>面试官用户ID<Input v-model:value="interviewer" /></label
        ><label
          >到期时间（本地时区）<input
            v-model="assignmentExpiry"
            type="datetime-local" /></label></Modal
    ></template>
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
