<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, inject } from 'vue';
import { useRoute, useRouter, onBeforeRouteLeave, matchedRouteKey } from 'vue-router';
import { Alert, Button, Checkbox, Input, InputNumber, Modal, Select, Steps } from 'ant-design-vue';
import { z } from 'zod';
import { hrWrite } from '../../../entities/hr';
import { dimensions, useHrPositionDraft } from '../../../features/hr-position-draft/model';
import HrJdDraftPanel from '../../../features/hr-jd/HrJdDraftPanel.vue';
import HrTrialPanel from '../../../features/hr-trials/HrTrialPanel.vue';
import styles from './PositionWizardPage.module.css';
const props = defineProps<{ step: number }>();
const route = useRoute();
const router = useRouter();
const { draft, busy, error, dirty, conflict, load, create, save } = useHrPositionDraft();
const publishOpen = ref(false);
const basic = ref({ name: '', family: 'TECHNOLOGY', departmentId: '', level: '' });
const names = ['基础信息', '硬性条件', '软性要求', '权重与分档', '预演与保存'];
const stage = ['BASIC', 'HARD_CONDITIONS', 'SOFT_REQUIREMENTS', 'WEIGHTS', 'PREVIEW'];
const paths = ['', '/hard-conditions', '/soft-requirements', '/weights', '/preview'];
const families: Record<string, string> = {
  TECHNOLOGY: '技术研发',
  PRODUCT: '产品',
  DESIGN: '设计',
  OPERATIONS: '运营',
  MARKETING: '市场',
  SALES: '销售',
  SUPPORT: '职能支持',
  MANAGEMENT: '管理岗',
  GRADUATE: '应届培养',
};
const dimensionNames: Record<string, string> = {
  SKILL: '技能匹配',
  EXPERIENCE: '经验匹配',
  PROJECT: '项目匹配',
  EDUCATION: '学历匹配',
  BONUS: '加分项',
};
const ruleTypes: Record<string, string> = {
  EDUCATION: '学历',
  WORK_EXPERIENCE: '工作经验',
  REQUIRED_SKILL: '必需技能',
  LOCATION: '工作地域',
  CERTIFICATE: '证书',
  LANGUAGE: '语言',
  PROJECT_SCALE: '项目规模',
  TEAM_SIZE: '团队规模',
};
const weights = ref<Record<string, number>>({
  SKILL: 40,
  EXPERIENCE: 25,
  PROJECT: 25,
  EDUCATION: 5,
  BONUS: 5,
});
const thresholds = ref([80, 65, 50]);
const requirementWeights = ref<Record<string, number>>({});
const currentScoring = computed(() => draft.value?.draftScoring ?? draft.value?.scoring);
const total = computed(() => Object.values(weights.value).reduce((a, b) => a + b, 0));
const weightValid = computed(
  () =>
    total.value === 100 &&
    thresholds.value[0]! <= 100 &&
    thresholds.value[0]! > thresholds.value[1]! &&
    thresholds.value[1]! > thresholds.value[2]! &&
    thresholds.value[2]! >= 0,
);
const basicValid = computed(
  () =>
    !!basic.value.name.trim() && !!basic.value.departmentId.trim() && !!basic.value.level.trim(),
);
let controller: AbortController | undefined;
watch(
  () => route.query.positionId,
  async (id) => {
    controller?.abort();
    controller = new AbortController();
    if (id) {
      await load(String(id), controller.signal);
      if (draft.value) {
        basic.value = {
          name: draft.value.name,
          family: draft.value.family,
          departmentId: draft.value.departmentId,
          level: draft.value.level,
        };
        const savedScoring = draft.value.draftScoring ?? draft.value.scoring;
        if (savedScoring) {
          weights.value = { ...savedScoring.weights };
          requirementWeights.value = Object.fromEntries(
            savedScoring.requirements.map((r) => [r.id, r.weight]),
          );
          thresholds.value = [
            savedScoring.highThreshold,
            savedScoring.middleThreshold,
            savedScoring.lowThreshold,
          ];
        }
      }
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => controller?.abort());
if (inject(matchedRouteKey, undefined))
  onBeforeRouteLeave(
    () => !dirty.value || window.confirm('草稿尚未保存，确认离开并放弃本页修改？'),
  );
function changed() {
  dirty.value = true;
}
function addRule() {
  if (!draft.value) return;
  draft.value.hardConditions.push({
    id: crypto.randomUUID(),
    type: 'WORK_EXPERIENCE',
    label: '',
    expected: '',
    unit: '月',
    threshold: 36,
    tolerance: 0,
    overridable: true,
    values: [],
    matchMode: 'ALL',
  });
  changed();
}
function addCriterion() {
  if (!draft.value) return;
  draft.value.criteria.push({
    id: crypto.randomUUID(),
    label: '',
    dimension: 'SKILL',
    criterion: '',
    strongAnchor: '',
    matchAnchor: '',
    partialAnchor: '',
    notMetAnchor: '',
    critical: false,
  });
  changed();
}
function scoring() {
  if (!draft.value) return;
  draft.value.draftScoring = {
    version: draft.value.scoring?.version ?? 'draft',
    weights: weights.value as Record<(typeof dimensions)[number], number>,
    requirements: draft.value.criteria.map((c) => ({
      id: c.id,
      dimension: c.dimension,
      weight:
        requirementWeights.value[c.id] ??
        currentScoring.value?.requirements.find((r) => r.id === c.id)?.weight ??
        1,
      critical: c.critical,
      applicable: true,
    })),
    highThreshold: thresholds.value[0]!,
    middleThreshold: thresholds.value[1]!,
    lowThreshold: thresholds.value[2]!,
    minimumCoverage: 80,
    strongCoverage: 90,
  };
}
async function persist(next?: number) {
  if (busy.value) return;
  if (!draft.value) {
    if (!basicValid.value) return;
    const id = await create(basic.value);
    if (!id) return;
    await router.replace({ path: route.path, query: { positionId: id } });
  }
  if (!draft.value) return;
  Object.assign(draft.value, { name: basic.value.name, level: basic.value.level });
  scoring();
  if (await save(stage[props.step]!)) {
    if (next !== undefined)
      await router.push(
        `/ai-assistants/hr/positions/new${paths[next]}?positionId=${draft.value.positionId}`,
      );
  }
}
async function publish() {
  if (!draft.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    await hrWrite(
      `/positions/${draft.value.positionId}/config-versions`,
      z.object({ id: z.string(), version: z.string(), snapshotHash: z.string() }),
      { expectedVersion: draft.value.version },
    );
    publishOpen.value = false;
    dirty.value = false;
    await router.push(`/ai-assistants/hr/positions/${draft.value.positionId}`);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '发布失败';
  } finally {
    busy.value = false;
  }
}
const complete = computed(() => {
  const d = draft.value;
  return (
    !!d &&
    !!(d.draftScoring ?? d.scoring) &&
    d.hardConditions.length > 0 &&
    d.criteria.some((c) => c.dimension === 'SKILL') &&
    d.criteria.every(
      (c) =>
        c.label &&
        c.criterion &&
        c.strongAnchor &&
        c.matchAnchor &&
        c.partialAnchor &&
        c.notMetAnchor,
    )
  );
});
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header class="heading">
      <div>
        <h1>{{ step === 0 ? '新建岗位' : names[step] }}</h1>
        <p>逐步保存真实岗位草稿；已发布规则使用不可变快照。</p>
      </div>
      <Button @click="router.push('/ai-assistants/hr/positions')">返回岗位列表</Button>
    </header>
    <Steps :current="step" :items="names.map((title) => ({ title }))" size="small" /><Alert
      v-if="error"
      type="error"
      show-icon
      :message="error"
    /><Alert
      v-if="conflict"
      type="warning"
      message="当前草稿版本发生冲突，请保留本页输入并读取服务端版本比较，不能强制覆盖。"
    /><Button v-if="error && route.query.positionId" @click="load(String(route.query.positionId))"
      >读取服务端草稿</Button
    >
    <p v-if="busy && !draft" role="status">正在读取岗位草稿…</p>
    <p v-if="step > 0 && !draft && !busy">请先创建岗位，或从岗位列表恢复已有草稿。</p>
    <section v-if="step === 0" class="panel">
      <h2>岗位基础信息</h2>
      <div class="formgrid">
        <label
          >岗位名称<Input
            v-model:value="basic.name"
            :maxlength="80"
            placeholder="请输入岗位名称"
            @change="changed" /></label
        ><label
          >岗位族<Select
            v-model:value="basic.family"
            :disabled="!!draft"
            :options="Object.entries(families).map(([value, label]) => ({ value, label }))"
            @change="changed" /></label
        ><label
          >所属部门<Input
            v-model:value="basic.departmentId"
            :disabled="!!draft"
            placeholder="请输入授权部门标识"
            @change="changed" /></label
        ><label
          >岗位职级<Input
            v-model:value="basic.level"
            :maxlength="32"
            placeholder="如 P6"
            @change="changed"
        /></label>
      </div>
      <label v-if="draft" style="margin-top: 18px"
        >岗位JD（仅上下文，不隐式进入评分）<Input.TextArea
          v-model:value="draft.jdText"
          :rows="6"
          :maxlength="20000"
          @change="changed"
      /></label>
    </section>
    <template v-if="draft"
      ><section v-if="step === 1" class="panel">
        <h2>硬性条件</h2>
        <Alert
          type="info"
          message="未提及不等于不满足。必需技能及证书不能人工放行；容差只用于配置允许的类型。"
        />
        <article v-for="(rule, index) in draft.hardConditions" :key="rule.id" class="rule">
          <div class="formgrid">
            <label
              >条件类型<Select
                v-model:value="rule.type"
                :options="Object.entries(ruleTypes).map(([value, label]) => ({ value, label }))"
                @change="changed" /></label
            ><label
              >条件名称<Input
                v-model:value="rule.label"
                placeholder="填写可审核条件名称"
                @change="changed" /></label
            ><label>期望值说明<Input v-model:value="rule.expected" @change="changed" /></label
            ><template
              v-if="['REQUIRED_SKILL', 'CERTIFICATE', 'LOCATION', 'LANGUAGE'].includes(rule.type)"
              ><label
                >标准值<Select v-model:value="rule.values" mode="tags" @change="changed" /></label
              ><label
                >匹配方式<Select
                  v-model:value="rule.matchMode"
                  :options="[
                    { value: 'ALL', label: '全部满足' },
                    { value: 'ANY', label: '任一满足' },
                  ]"
                  @change="changed" /></label></template
            ><template v-else
              ><label
                >阈值<InputNumber
                  :value="rule.threshold ?? undefined"
                  :min="0"
                  @update:value="
                    (value) => (rule.threshold = value === null ? null : Number(value))
                  "
                  @change="changed" /></label
              ><label>单位<Input v-model:value="rule.unit" @change="changed" /></label
              ><label
                >容差<InputNumber
                  :value="rule.tolerance ?? undefined"
                  :min="0"
                  @update:value="
                    (value) => (rule.tolerance = value === null ? null : Number(value))
                  "
                  @change="changed" /></label
            ></template>
          </div>
          <section v-if="rule.type === 'LANGUAGE'">
            <label
              >考试体系（如CEFR / JLPT）<Input v-model:value="rule.unit" @change="changed" /></label
            ><label
              >目标等级序号（按已发布等级体系配置）<InputNumber
                :value="rule.threshold ?? undefined"
                :min="1"
                :precision="0"
                @update:value="
                  rule.threshold = $event == null ? null : Number($event);
                  changed();
                " /></label
            ><label
              >允许容差等级<InputNumber
                :max="Math.floor((rule.threshold ?? 0) * 0.3)"
                :value="rule.tolerance ?? undefined"
                :min="0"
                :precision="0"
                @update:value="
                  rule.tolerance = $event == null ? null : Number($event);
                  changed();
                "
            /></label>
            <p>
              目标序号须按已发布的同考试体系等级顺序显式配置；不得由界面或模型猜测体系换算。容差须为非负整数，最多为目标序号×30%向下取整，小阈值只能为0；仍按冻结四档锚点判断，容差档须在部分满足锚点明确写明，不从B2/N2的数字比较候选等级。
            </p>
            <Button
              v-if="!draft.criteria.some((c) => c.id === rule.id)"
              @click="
                draft.criteria.push({
                  id: rule.id,
                  label: rule.label,
                  dimension: 'SKILL',
                  criterion: rule.expected,
                  strongAnchor: '',
                  matchAnchor: '',
                  partialAnchor: '',
                  notMetAnchor: '',
                  critical: true,
                });
                changed();
              "
              >配置语言四档锚点</Button
            ><template
              v-for="criterion in draft.criteria.filter((c) => c.id === rule.id)"
              :key="criterion.id"
              ><label
                >语言判断标准<Input.TextArea
                  v-model:value="criterion.criterion"
                  @change="changed" /></label
              ><label
                v-for="key in [
                  'strongAnchor',
                  'matchAnchor',
                  'partialAnchor',
                  'notMetAnchor',
                ] as const"
                :key="key"
                >{{
                  {
                    strongAnchor: '显著满足',
                    matchAnchor: '满足',
                    partialAnchor: '部分满足 / 容差档',
                    notMetAnchor: '明确不满足',
                  }[key]
                }}<Input.TextArea v-model:value="criterion[key]" @change="changed" /></label
            ></template>
          </section>
          <Checkbox
            v-model:checked="rule.overridable"
            :disabled="['REQUIRED_SKILL', 'CERTIFICATE'].includes(rule.type)"
            @change="changed"
            >允许授权人员有理由放行</Checkbox
          ><Button
            :aria-label="`删除条件-${index + 1}`"
            @click="
              draft.hardConditions.splice(index, 1);
              changed();
            "
            >删除</Button
          >
        </article>
        <Button @click="addRule">＋ 添加硬性条件</Button>
      </section>
      <section v-if="step === 2" class="panel">
        <h2>软性要求与评分锚点</h2>
        <HrJdDraftPanel
          :position-id="draft.positionId"
          :position-version="draft.version"
          :has-unsaved="dirty"
          @adopted="load(draft.positionId)"
        />
        <p>要求必须绑定维度、可核验材料与完整锚点，不能只按关键词计分。</p>
        <article v-for="(criterion, index) in draft.criteria" :key="criterion.id" class="rule">
          <div class="formgrid">
            <label>要求名称<Input v-model:value="criterion.label" @change="changed" /></label
            ><label
              >所属维度<Select
                v-model:value="criterion.dimension"
                :options="dimensions.map((value) => ({ value, label: dimensionNames[value] }))"
                @change="changed" /></label
            ><label class="wide"
              >业务标准<Input.TextArea
                v-model:value="criterion.criterion"
                :rows="2"
                @change="changed" /></label
            ><label
              >显著满足锚点<Input.TextArea
                v-model:value="criterion.strongAnchor"
                :rows="2"
                @change="changed" /></label
            ><label
              >满足锚点<Input.TextArea
                v-model:value="criterion.matchAnchor"
                :rows="2"
                @change="changed" /></label
            ><label
              >部分满足锚点<Input.TextArea
                v-model:value="criterion.partialAnchor"
                :rows="2"
                @change="changed" /></label
            ><label
              >明确不足锚点<Input.TextArea
                v-model:value="criterion.notMetAnchor"
                :rows="2"
                @change="changed"
            /></label>
          </div>
          <label
            >评分计算规则<Select
              :value="criterion.calculation?.type ?? 'SEMANTIC'"
              :options="[
                { value: 'SEMANTIC', label: '语义锚点' },
                ...Object.entries({
                  EXPERIENCE_MONTHS: '工作月数',
                  EDUCATION_RANK: '学历等级',
                  PROJECT_SCALE: '同一项目规模',
                  PROJECT_ROLE: '同一项目角色',
                  TEAM_SIZE: '同一项目管理人数',
                  BONUS_DECLARATION: '明确加分声明',
                }).map(([value, label]) => ({ value, label })),
              ]"
              @update:value="
                criterion.calculation =
                  $event === 'SEMANTIC'
                    ? null
                    : {
                        type: $event as NonNullable<typeof criterion.calculation>['type'],
                        minimum: null,
                        maximum: null,
                        expected: null,
                        metric: null,
                        unit: null,
                      };
                changed();
              "
          /></label>
          <div v-if="criterion.calculation" class="formgrid">
            <label
              >最低值<InputNumber
                :value="criterion.calculation.minimum ?? undefined"
                :min="0"
                @update:value="
                  criterion.calculation.minimum = $event == null ? null : Number($event)
                "
                @change="changed" /></label
            ><label
              >最高值<InputNumber
                :value="criterion.calculation.maximum ?? undefined"
                :min="0"
                @update:value="
                  criterion.calculation.maximum = $event == null ? null : Number($event)
                "
                @change="changed" /></label
            ><label
              >期望值<InputNumber
                :value="criterion.calculation.expected ?? undefined"
                :min="1"
                @update:value="
                  criterion.calculation.expected = $event == null ? null : Number($event)
                "
                @change="changed" /></label
            ><label
              >指标<Input
                :value="criterion.calculation.metric ?? undefined"
                @update:value="criterion.calculation.metric = $event ?? null"
                @change="changed" /></label
            ><label
              >单位<Input
                :value="criterion.calculation.unit ?? undefined"
                @update:value="criterion.calculation.unit = $event ?? null"
                @change="changed"
            /></label>
            <p>
              学历等级1至5、角色1至3；月数填写整数。项目规模、角色与管理人数只取同一项目明确证据。
            </p>
          </div>
          <label
            >维度内相对权重<InputNumber
              :value="requirementWeights[criterion.id] ?? 1"
              :min="1"
              :precision="0"
              @update:value="
                requirementWeights[criterion.id] = Number($event);
                changed();
              "
          /></label>
          <Checkbox v-model:checked="criterion.critical" @change="changed"
            >关键项（未知时阻断正式评分）</Checkbox
          ><Button
            :aria-label="`删除要求-${index + 1}`"
            @click="
              draft!.criteria.splice(index, 1);
              changed();
            "
            >删除</Button
          >
        </article>
        <Button @click="addCriterion">＋ 添加评分要求</Button>
      </section>
      <section v-if="step === 3" class="panel">
        <h2>五维权重与分档</h2>
        <fieldset class="mark-settings">
          <legend>特殊标记展示</legend>
          <p>仅控制标记是否显示，不改变判断、评分或分档。</p>
          <Checkbox.Group
            v-model:value="draft.visibleMarks"
            :options="[
              { value: 'MANUAL_REVIEW', label: '人工复核：提示需人工核验' },
              { value: 'BORDERLINE', label: '临界：提示接近判断边界' },
              { value: 'QUALITY_WARNING', label: '材料质量：提示证据质量风险' },
              { value: 'DUPLICATE', label: '疑似重复：提示需核查来源' },
              { value: 'SPECIAL_BACKGROUND', label: '特殊背景：提示已记录背景信息' },
            ]"
            @change="changed"
          />
        </fieldset>
        <div v-for="dimension in dimensions" :key="dimension" class="weight">
          <b>{{ dimensionNames[dimension] }}</b
          ><InputNumber
            v-model:value="weights[dimension]"
            :min="0"
            :max="100"
            :precision="0"
            :aria-label="`${dimensionNames[dimension]}权重`"
            @change="changed"
          /><span>%</span>
        </div>
        <p :class="{ invalid: total !== 100 }">合计 {{ total }}%</p>
        <Alert
          v-if="Object.values(weights).some((w) => w > 60)"
          type="warning"
          message="单维权重超过60%，请检查是否过度依赖单一维度。"
        />
        <div class="formgrid">
          <label v-for="(name, index) in ['强烈推荐阈值', '推荐阈值', '建议复核阈值']" :key="name"
            >{{ name
            }}<InputNumber
              v-model:value="thresholds[index]"
              :min="0"
              :max="100"
              :precision="0"
              @change="changed"
          /></label>
        </div>
        <p>最低证据覆盖率80%，强烈推荐90%；关键项未知不可绕过，阈值必须严格递减。</p>
      </section>
      <section v-if="step === 4" class="panel">
        <h2>配置预演与保存</h2>
        <p>{{ draft.name }} · {{ families[draft.family] }} · 草稿版本 {{ draft.version }}</p>
        <p>
          硬性条件 {{ draft.hardConditions.length }} 项，评分要求 {{ draft.criteria.length }} 项。
        </p>
        <p v-if="currentScoring">
          五维权重：{{ dimensions.map((d) => currentScoring!.weights[d]).join(' / ') }}；阈值
          {{ currentScoring.highThreshold }} / {{ currentScoring.middleThreshold }} /
          {{ currentScoring.lowThreshold }}
        </p>
        <HrTrialPanel :position-id="draft.positionId" :position-version="draft.version" />
        <p v-if="!complete">
          配置尚不完整，请补齐硬性条件、核心技能、各维评分标准与完整锚点后保存。
        </p>
        <Button type="primary" :disabled="!complete || dirty || busy" @click="publishOpen = true"
          >发布并启用岗位</Button
        >
      </section></template
    >
    <footer>
      <span v-if="draft"
        >{{ dirty ? '有未保存修改' : '草稿已保存' }} · 版本 {{ draft.version }}</span
      ><span v-else>保存后生成岗位草稿</span>
      <div>
        <Button v-if="step > 0 && draft" :disabled="busy" @click="persist(step - 1)">上一步</Button
        ><Button :loading="busy" :disabled="step === 0 ? !basicValid : !draft" @click="persist()"
          >保存草稿</Button
        ><Button
          v-if="step < 4"
          type="primary"
          :loading="busy"
          :disabled="step === 0 ? !basicValid : !draft || (step === 3 && !weightValid)"
          @click="persist(step + 1)"
          >下一步：{{ names[step + 1] }}</Button
        >
      </div>
    </footer>
    <Modal
      v-model:open="publishOpen"
      title="确认发布岗位规则？"
      ok-text="发布并启用"
      :confirm-loading="busy"
      @ok="publish"
      ><p>
        将保存不可变评分配置并允许新简历按此岗位匹配。服务端会再次校验完整规则与版本，已发布历史不会覆盖。
      </p></Modal
    >
  </div>
</template>
<style scoped>
.heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
h1 {
  font-size: 25px;
  margin: 0 0 6px;
}
h2 {
  font-size: 19px;
}
.panel {
  border: 1px solid #dde3ef;
  background: white;
  border-radius: 8px;
  padding: 20px;
}
.formgrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px 24px;
}
.formgrid label {
  display: grid;
  gap: 6px;
}
.wide {
  grid-column: 1/-1;
}
.rule {
  border: 1px solid #dde4ef;
  background: #fbfcff;
  border-radius: 6px;
  padding: 16px;
  margin: 14px 0;
}
.rule > .ant-btn {
  margin-left: 20px;
}
.weight {
  display: flex;
  gap: 15px;
  align-items: center;
  margin: 16px 0;
}
.weight b {
  width: 100px;
}
.invalid {
  color: #c92c37;
}
footer {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
  padding: 14px;
  background: #f4f6ff;
  border: 1px solid #dce3ef;
  border-radius: 6px;
}
footer > div {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
p {
  line-height: 1.8;
}
@media (max-width: 700px) {
  .formgrid {
    grid-template-columns: 1fr;
  }
  .wide {
    grid-column: auto;
  }
  .heading,
  footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .panel {
    padding: 14px;
  }
  .rule {
    padding: 12px;
  }
}
</style>
