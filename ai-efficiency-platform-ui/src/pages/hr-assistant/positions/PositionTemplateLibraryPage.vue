<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { Alert, Button, Input, InputNumber, Modal, Select, Tag } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../../entities/hr';
import { templateSchema } from '../../../entities/hr/completion';
import { draftSchema } from '../../../features/hr-position-draft/model';
import styles from './PositionTemplateLibraryPage.module.css';
const router = useRouter();
const newId = () => crypto.randomUUID();
const items = ref<z.infer<typeof templateSchema>[]>([]);
const department = ref('');
const family = ref('');
const name = ref('');
const level = ref('');
const selected = ref<z.infer<typeof templateSchema>>();
const action = ref<'copy' | 'position' | 'edit'>('copy');
const versions = ref<z.infer<typeof templateSchema>[]>([]);
const sourcePosition = ref('');
const validationTrial = ref('');
async function validateTemplate() {
  if (!editTemplate.value || busy.value || !validationTrial.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    editTemplate.value = await hrWrite(
      `/templates/${editTemplate.value.id}/validate`,
      templateSchema,
      { expectedVersion: editTemplate.value.version, trialId: validationTrial.value },
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '验证失败';
  } finally {
    busy.value = false;
  }
}

const editTemplate = ref<z.infer<typeof templateSchema>>();
async function inspect(item: z.infer<typeof templateSchema>) {
  selected.value = item;
  action.value = 'edit';
  editTemplate.value = structuredClone(item);
  busy.value = true;
  error.value = '';
  try {
    versions.value = await hrRequest(`/templates/${item.id}/versions`, z.array(templateSchema));
  } catch (e) {
    error.value = e instanceof Error ? e.message : '历史读取失败';
  } finally {
    busy.value = false;
  }
}
async function saveTemplate(publish = false) {
  if (!editTemplate.value || busy.value || editTemplate.value.system) return;
  busy.value = true;
  error.value = '';
  try {
    const item = editTemplate.value;
    editTemplate.value = publish
      ? await hrWrite(`/templates/${item.id}/publish`, templateSchema, {
          expectedVersion: item.version,
        })
      : await hrRequest(`/templates/${item.id}`, templateSchema, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
          body: JSON.stringify({ ...item, expectedVersion: item.version }),
        });
    done.value = publish ? '组织模板已发布新版本' : '组织模板草稿已保存';
  } catch (e) {
    error.value = e instanceof Error ? e.message : '模板保存失败';
  } finally {
    busy.value = false;
  }
}
async function fromPosition() {
  if (busy.value || !sourcePosition.value.trim() || !department.value.trim() || !name.value.trim())
    return;
  busy.value = true;
  error.value = '';
  try {
    const draft = await hrRequest(
      `/positions/${encodeURIComponent(sourcePosition.value)}/draft`,
      draftSchema,
    );
    const scoring = draft.draftScoring ?? draft.scoring;
    if (!scoring) throw new Error('岗位尚无权重配置');
    await hrWrite('/templates/from-position', templateSchema, {
      positionId: draft.positionId,
      departmentId: department.value,
      name: name.value,
      expectedVersion: draft.version,
    });
    done.value = '已从岗位另存独立模板';
  } catch (e) {
    error.value = e instanceof Error ? e.message : '另存失败';
  } finally {
    busy.value = false;
  }
  await load();
}

const busy = ref(false);
const error = ref('');
const done = ref('');
async function load() {
  busy.value = true;
  error.value = '';
  try {
    const params = new URLSearchParams();
    if (department.value.trim()) params.set('departmentId', department.value.trim());
    if (family.value.trim()) params.set('family', family.value.trim());
    items.value = await hrRequest(
      `/templates${params.size ? `?${params}` : ''}`,
      z.array(templateSchema),
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    busy.value = false;
  }
}
async function submit() {
  if (!selected.value || busy.value || !department.value.trim() || !name.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    if (action.value === 'copy') {
      await hrWrite(`/templates/${selected.value.id}/copy`, templateSchema, {
        departmentId: department.value,
        name: name.value,
      });
      done.value = '已复制为独立组织模板草稿';
      selected.value = undefined;
    } else {
      const result = await hrWrite(
        `/templates/${selected.value.id}/positions`,
        z.object({ id: z.string() }),
        { departmentId: department.value, name: name.value, level: level.value, code: '' },
      );
      await router.push(`/ai-assistants/hr/positions/new?positionId=${result.id}`);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '提交失败';
  } finally {
    busy.value = false;
  }
  if (!selected.value) await load();
}
onMounted(load);
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header>
      <h1>岗位模板库</h1>
      <p>平台模板仅可复制。组织模板与岗位独立保存，复制技能默认不采用。</p>
    </header>
    <Alert v-if="error" type="error" :message="error" show-icon /><Alert
      v-if="done"
      type="success"
      :message="done"
    />
    <div style="display: flex; gap: 12px; flex-wrap: wrap">
      <Input
        v-model:value="department"
        aria-label="部门ID"
        placeholder="部门ID"
        style="width: 220px"
      /><Select
        v-model:value="family"
        aria-label="岗位族"
        style="width: 180px"
        :options="[
          { value: '', label: '全部岗位族' },
          ...[
            'TECHNOLOGY',
            'PRODUCT',
            'DESIGN',
            'OPERATIONS',
            'MARKETING',
            'SALES',
            'SUPPORT',
            'MANAGEMENT',
            'GRADUATE',
          ].map((value) => ({ value, label: value })),
        ]"
      /><Button :loading="busy" @click="load">查询模板</Button>
    </div>
    <details>
      <summary>从已有岗位另存组织模板</summary>
      <label>岗位ID<Input v-model:value="sourcePosition" /></label
      ><label>模板名<Input v-model:value="name" /></label
      ><Button
        :loading="busy"
        :disabled="!sourcePosition.trim() || !department.trim() || !name.trim()"
        @click="fromPosition"
        >另存组织模板</Button
      >
    </details>
    <p v-if="busy" role="status">正在读取模板…</p>
    <p v-else-if="!items.length && !error">暂无可访问模板。</p>
    <section
      style="
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 16px;
        margin-top: 20px;
      "
    >
      <article
        v-for="item in items"
        :key="item.id"
        style="background: #ffffffa8; border: 1px solid #dde4f2; border-radius: 8px; padding: 20px"
      >
        <Tag :color="item.system ? 'blue' : 'purple'">{{
          item.system ? '平台模板' : '组织模板'
        }}</Tag
        ><Tag>{{ item.status }} · v{{ item.version }}</Tag>
        <h2>{{ item.name }}</h2>
        <Tag v-if="item.verification" color="green"
          >已验证 {{ item.verification.sampleSize }}样本 · {{ item.verification.agreement }}% ·
          {{ item.verification.verifiedAt }}</Tag
        >
        <Button @click="inspect(item)">查看 / 编辑 / 历史</Button>
        <p>{{ item.family }}</p>
        <p v-for="(weight, key) in item.weights" :key="key">{{ key }} {{ weight }}%</p>
        <p>硬条件 {{ item.hardConditions.length }} 项 · 软要求 {{ item.criteria.length }} 项</p>
        <Button
          @click="
            selected = item;
            action = 'copy';
            name = `${item.name} 副本`;
          "
          >复制模板</Button
        ><Button
          type="primary"
          @click="
            selected = item;
            action = 'position';
            name = '';
          "
          >以此新建岗位</Button
        >
      </article>
    </section>
    <Modal
      :open="!!selected"
      :title="
        action === 'edit'
          ? '模板配置与历史'
          : action === 'copy'
            ? '复制为组织模板'
            : '从模板新建岗位'
      "
      :confirm-loading="busy"
      :ok-button-props="{
        disabled: !department.trim() || !name.trim() || (action === 'position' && !level.trim()),
      }"
      @ok="action === 'edit' ? saveTemplate() : submit()"
      @cancel="selected = undefined"
      ><template v-if="action === 'edit' && editTemplate"
        ><p>
          {{ editTemplate.system ? '平台模板只读，仅可复制' : '组织模板' }} · v{{
            editTemplate.version
          }}
        </p>
        <label
          >名称<Input v-model:value="editTemplate.name" :disabled="editTemplate.system" /></label
        ><label v-for="(_weight, key) in editTemplate.weights" :key="key"
          >{{ key
          }}<InputNumber
            v-model:value="editTemplate.weights[key]"
            :disabled="editTemplate.system"
            :min="0"
            :max="100"
        /></label>
        <h3>硬条件</h3>
        <article v-for="(rule, index) in editTemplate.hardConditions" :key="rule.id">
          <Button v-if="!editTemplate.system" @click="editTemplate.hardConditions.splice(index, 1)"
            >删除此硬条件</Button
          ><label
            >条件名称<Input v-model:value="rule.label" :disabled="editTemplate.system" /></label
          ><label
            >类型<Select
              v-model:value="rule.type"
              :disabled="editTemplate.system"
              :options="
                [
                  'EDUCATION',
                  'WORK_EXPERIENCE',
                  'REQUIRED_SKILL',
                  'LOCATION',
                  'CERTIFICATE',
                  'LANGUAGE',
                  'PROJECT_SCALE',
                  'TEAM_SIZE',
                ].map((value) => ({ value, label: value }))
              "
              style="width: 100%" /></label
          ><label>期望<Input v-model:value="rule.expected" :disabled="editTemplate.system" /></label
          ><label
            >阈值<InputNumber
              :value="rule.threshold ?? undefined"
              :disabled="editTemplate.system"
              @update:value="rule.threshold = $event == null ? null : Number($event)" /></label
          ><label
            >容差<InputNumber
              :value="rule.tolerance ?? undefined"
              :disabled="editTemplate.system"
              @update:value="rule.tolerance = $event == null ? null : Number($event)" /></label
          ><label>单位<Input v-model:value="rule.unit" :disabled="editTemplate.system" /></label
          ><label
            >允许人工放行<input
              v-model="rule.overridable"
              :disabled="editTemplate.system"
              type="checkbox"
          /></label>
        </article>
        <Button
          v-if="!editTemplate.system"
          @click="
            editTemplate.hardConditions.push({
              id: newId(),
              type: 'REQUIRED_SKILL',
              label: '',
              expected: '',
              unit: '',
              threshold: null,
              tolerance: null,
              overridable: false,
              values: [],
              matchMode: '',
            })
          "
          >新增模板硬条件</Button
        >
        <h3>软要求与锚点</h3>
        <article v-for="(criterion, index) in editTemplate.criteria" :key="criterion.id">
          <Button v-if="!editTemplate.system" @click="editTemplate.criteria.splice(index, 1)"
            >删除此软要求</Button
          >
          <label
            >名称<Input v-model:value="criterion.label" :disabled="editTemplate.system" /></label
          ><label
            >维度<Select
              v-model:value="criterion.dimension"
              :disabled="editTemplate.system"
              :options="
                ['SKILL', 'EXPERIENCE', 'PROJECT', 'EDUCATION', 'BONUS'].map((value) => ({
                  value,
                  label: value,
                }))
              "
              style="width: 100%" /></label
          ><label
            >业务要求<Input.TextArea
              v-model:value="criterion.criterion"
              :disabled="editTemplate.system" /></label
          ><label
            v-for="key in ['strongAnchor', 'matchAnchor', 'partialAnchor', 'notMetAnchor'] as const"
            :key="key"
            >{{ key
            }}<Input.TextArea
              v-model:value="criterion[key]"
              :disabled="editTemplate.system" /></label
          ><label
            >关键项<input
              v-model="criterion.critical"
              :disabled="editTemplate.system"
              type="checkbox"
          /></label>
        </article>
        <Button
          v-if="!editTemplate.system"
          @click="
            editTemplate.criteria.push({
              id: newId(),
              label: '',
              dimension: 'SKILL',
              criterion: '',
              strongAnchor: '',
              matchAnchor: '',
              partialAnchor: '',
              notMetAnchor: '',
              critical: false,
            })
          "
          >新增模板软要求</Button
        ><label v-for="requirement in editTemplate.requirements" :key="requirement.id"
          >{{ requirement.id }} 相对权重<InputNumber
            v-model:value="requirement.weight"
            :disabled="editTemplate.system"
            :min="1"
        /></label>
        <Button v-if="!editTemplate.system" :loading="busy" @click="saveTemplate()"
          >保存模板草稿</Button
        ><Button
          v-if="!editTemplate.system"
          type="primary"
          :loading="busy"
          @click="saveTemplate(true)"
          >发布模板版本</Button
        >
        <label v-if="!editTemplate.system"
          >独立盲标预演ID<Input v-model:value="validationTrial" /></label
        ><Button
          v-if="!editTemplate.system"
          :disabled="!validationTrial.trim()"
          :loading="busy"
          @click="validateTemplate"
          >核验模板样本门槛</Button
        >
        <h3>历史冻结版本</h3>
        <p v-for="version in versions" :key="version.version">
          v{{ version.version }} · {{ version.name }} · {{ version.status }}
        </p></template
      ><template v-else
        ><label>部门ID<Input v-model:value="department" /></label
        ><label>名称<Input v-model:value="name" /></label
        ><label v-if="action === 'position'">岗位级别<Input v-model:value="level" /></label>
        <p>只复制配置；不复制候选人、JD或匹配结果。</p></template
      ></Modal
    >
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
