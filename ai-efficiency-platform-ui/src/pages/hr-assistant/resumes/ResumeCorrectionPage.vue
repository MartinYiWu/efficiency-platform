<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  Button,
  Checkbox,
  Alert,
  Input,
  InputNumber,
  Modal,
  Tag,
  Tabs,
  TabPane,
  message,
} from 'ant-design-vue';
import { z } from 'zod';
import {
  factsSchema,
  structuredFactSchema,
  hrRequest,
  hrWrite,
  type HrFacts,
} from '../../../entities/hr';
import EvidenceSource from '../../../features/hr-evidence/EvidenceSource.vue';
const evidenceDrawer = ref<InstanceType<typeof EvidenceSource>>();
const route = useRoute();
const router = useRouter();
const facts = ref<HrFacts>();
const loading = ref(false);
const busy = ref(false);
const error = ref('');
const page = ref(1);
const zoom = ref(100);
const activeBlock = ref('');
const tab = ref('facts');
const editing = ref('');
const value = ref('');
const reason = ref('');
const structuredEdit = ref<z.infer<typeof structuredFactSchema>>();
const structuredReason = ref('');
const humanSource = ref('');
const history = ref<HrFacts[]>([]);
const skipOpen = ref(false);
const skipReason = ref('');
const original = ref('');
const notApplicable = ref<string[]>([]);
async function confirmNotApplicable() {
  if (!facts.value || busy.value || !notApplicable.value.length) return;
  busy.value = true;
  error.value = '';
  try {
    facts.value = await hrWrite(
      `/candidates/${facts.value.candidateId}/confirmations`,
      factsSchema,
      {
        expectedVersion: facts.value.version,
        fieldIds: [],
        notApplicableGroups: notApplicable.value,
      },
    );
    notApplicable.value = [];
  } catch (e) {
    error.value = e instanceof Error ? e.message : '不适用确认失败';
  } finally {
    busy.value = false;
  }
}

async function loadHistory() {
  if (!facts.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    history.value = await hrRequest(
      `/candidates/${facts.value.candidateId}/fact-history`,
      z.array(factsSchema),
      { cache: 'no-store' },
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '历史读取失败';
  } finally {
    busy.value = false;
  }
}
async function skip() {
  if (!facts.value || busy.value || !skipReason.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    facts.value = await hrWrite(`/candidates/${facts.value.candidateId}/skips`, factsSchema, {
      expectedVersion: facts.value.version,
      confirmed: true,
      reason: skipReason.value,
    });
    skipOpen.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '跳过失败';
  } finally {
    busy.value = false;
  }
}
async function originalGrant() {
  if (!facts.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const grant = await hrWrite(
      `/candidates/${facts.value.candidateId}/original-grants`,
      z.object({ id: z.string(), expiresAt: z.string() }),
      {},
    );
    original.value = `/api/hr/original-grants/${encodeURIComponent(grant.id)}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '原件授权失败';
  } finally {
    busy.value = false;
  }
}

function startStructured(fact: z.infer<typeof structuredFactSchema>) {
  structuredEdit.value = structuredClone(fact);
  structuredReason.value = '';
  humanSource.value = '';
}
async function saveStructured() {
  if (
    !facts.value ||
    !structuredEdit.value ||
    busy.value ||
    !structuredReason.value.trim() ||
    !humanSource.value.trim()
  )
    return;
  busy.value = true;
  error.value = '';
  try {
    facts.value = await hrWrite(
      `/candidates/${facts.value.candidateId}/structured-corrections`,
      factsSchema,
      {
        expectedVersion: facts.value.version,
        changes: [
          {
            fieldId: structuredEdit.value.fact_id,
            fact: structuredEdit.value,
            reason: structuredReason.value,
            humanSource: humanSource.value,
          },
        ],
      },
    );
    structuredEdit.value = undefined;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '结构化修正失败';
  } finally {
    busy.value = false;
  }
}

let controller: AbortController | undefined;
const pending = computed(() => facts.value?.fields.filter((f) => f.status !== 'CONFIRMED') ?? []);
const blocks = computed(
  () => facts.value?.blocks.filter((b) => b.page === page.value || b.page === null) ?? [],
);
async function load() {
  controller?.abort();
  const id = route.params.candidateId;
  if (!id) return;
  controller = new AbortController();
  loading.value = true;
  error.value = '';
  try {
    facts.value = await hrRequest(
      `/candidates/${encodeURIComponent(String(id))}/facts`,
      factsSchema,
      { signal: controller.signal },
    );
    page.value = facts.value.blocks[0]?.page ?? 1;
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError'))
      error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    loading.value = false;
  }
}
watch(() => route.params.candidateId, load, { immediate: true });
onBeforeUnmount(() => controller?.abort());
function locate(ids: string[]) {
  if (window.matchMedia('(max-width: 700px)').matches) {
    evidenceDrawer.value?.locate(ids);
    return;
  }
  const block = facts.value?.blocks.find((b) => ids.includes(b.id));
  if (!block) return;
  activeBlock.value = block.id;
  page.value = block.page ?? 1;
  requestAnimationFrame(() =>
    document
      .getElementById(`source-${block.id}`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }),
  );
}
async function confirm(fieldId: string) {
  if (!facts.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    facts.value = await hrWrite(
      `/candidates/${facts.value.candidateId}/confirmations`,
      factsSchema,
      { expectedVersion: facts.value.version, fieldIds: [fieldId] },
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '确认失败';
  } finally {
    busy.value = false;
  }
}
async function saveCorrection() {
  if (!facts.value || busy.value || !reason.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    facts.value = await hrWrite(`/candidates/${facts.value.candidateId}/corrections`, factsSchema, {
      expectedVersion: facts.value.version,
      changes: [{ fieldId: editing.value, value: value.value, reason: reason.value.trim() }],
    });
    editing.value = '';
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败';
  } finally {
    busy.value = false;
  }
}
async function proceed() {
  if (!facts.value || busy.value || pending.value.length) return;
  busy.value = true;
  error.value = '';
  try {
    const result = await hrWrite(
      `/candidates/${facts.value.candidateId}/continue`,
      z.object({ runId: z.string(), status: z.string() }),
      { expectedVersion: facts.value.version },
    );
    message.success('已提交匹配任务');
    await router.push(
      `/ai-assistants/hr/matching?runId=${encodeURIComponent(result.runId)}&candidateId=${encodeURIComponent(facts.value.candidateId)}`,
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '提交失败';
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="hr-review ui-page">
    <header>
      <div>
        <Button @click="router.push('/ai-assistants/hr/resumes/upload')">← 返回简历中心</Button>
        <h1>核对解析结果</h1>
        <p>
          {{
            facts
              ? `${facts.filename} · ${facts.pageCount}页 · 已完成结构化解析`
              : '请选择简历中心的候选人，读取真实解析事实后进行核对。'
          }}
        </p>
      </div>
      <div class="actions">
        <Button @click="router.push('/ai-assistants/hr/resumes/upload')">保存并稍后处理</Button
        ><Button
          type="primary"
          :loading="busy"
          :disabled="!facts || pending.length > 0 || loading"
          @click="proceed"
          >确认并继续匹配</Button
        >
      </div>
    </header>
    <Alert v-if="error" type="error" show-icon :message="error" /><Button v-if="error" @click="load"
      >重试读取</Button
    >
    <p v-if="loading" role="status">正在读取解析事实…</p>
    <template v-if="facts && !loading">
      <section class="status">
        <b class="green">● 解析完成</b><span>{{ facts.totalCount }}项事实</span
        ><b class="orange">{{ pending.length }}项需确认</b><span>尚未进行岗位分析</span>
      </section>
      <Alert
        v-if="pending.length"
        type="warning"
        show-icon
        :message="`${pending.length}项信息需要确认：${pending.map((f) => f.label).join('、')}。未提及不等于不具备。`"
      />
      <div class="workspace">
        <section class="card source">
          <div class="toolbar">
            <h2>原简历预览</h2>
            <Button :loading="busy" @click="originalGrant">申请原件下载</Button
            ><a v-if="original" :href="original" download>下载一次性原件</a>
            <Button :disabled="page <= 1" @click="page--">‹</Button
            ><b>{{ page }} / {{ facts.pageCount }}</b
            ><Button :disabled="page >= facts.pageCount" @click="page++">›</Button
            ><Button aria-label="缩小" @click="zoom = Math.max(80, zoom - 10)">−</Button
            ><span>{{ zoom }}%</span
            ><Button aria-label="放大" @click="zoom = Math.min(140, zoom + 10)">＋</Button>
          </div>
          <div class="paper-area">
            <article class="paper" :style="{ fontSize: `${zoom}%` }">
              <h2>{{ facts.profile.name ?? '姓名待确认' }}</h2>
              <p>{{ facts.profile.targetPosition ?? '目标岗位未记录' }}</p>
              <section
                v-for="block in blocks"
                :id="`source-${block.id}`"
                :key="block.id"
                class="source-block"
                :class="{ selected: activeBlock === block.id }"
              >
                <h3 v-if="block.section">{{ block.section }}</h3>
                <p>{{ block.text }}</p>
                <small
                  >{{ block.page ? `第${block.page}页` : `文本段落${block.paragraph ?? ''}` }} ·
                  {{ block.id
                  }}<span v-if="block.bbox"> · 原件坐标 {{ block.bbox.join(', ') }}</span
                  ><span v-if="block.ocrQuality !== null && block.ocrQuality !== undefined">
                    · OCR质量 {{ block.ocrQuality }}</span
                  ></small
                >
              </section>
              <p v-if="!blocks.length">本页暂无可核对文本块。</p>
            </article>
          </div>
          <small>证据基于原文块定位，不推测未记录的原件坐标。</small>
        </section>
        <section class="card facts">
          <Tabs v-model:active-key="tab"
            ><TabPane key="facts" tab="解析事实" /><TabPane key="skills" tab="技能证据" /><TabPane
              key="quality"
              tab="质量检查" /></Tabs
          ><span class="count">已核对 {{ facts.confirmedCount }} / {{ facts.totalCount }}</span>
          <section class="group">
            <h2>⌄ 基本信息</h2>
            <div class="basic">
              <label>姓名<Input :value="facts.profile.name ?? '未记录'" readonly /></label
              ><label
                >目标岗位<Input :value="facts.profile.targetPosition ?? '未记录'" readonly /></label
              ><label>最高学历<Input :value="facts.profile.education ?? '未记录'" readonly /></label
              ><label
                >工作经验<Input
                  :value="
                    facts.profile.experienceMonths === null
                      ? '未记录'
                      : `${facts.profile.experienceMonths}个月（按自然月去重）`
                  "
                  readonly /></label
              ><label
                >资料状态<Tag :color="pending.length ? 'orange' : 'green'">{{
                  pending.length ? '待人工确认' : '已核对'
                }}</Tag></label
              >
            </div>
          </section>
          <section v-if="tab === 'facts' && facts.structuredFacts.length" class="group">
            <h2>结构化事实与日期精度</h2>
            <article v-for="fact in facts.structuredFacts" :key="fact.fact_id" class="field">
              <b>{{ fact.kind }} · {{ fact.value }}</b>
              <p>{{ fact.organization ?? '机构未记录' }} · {{ fact.title ?? '职务未记录' }}</p>
              <p>
                开始 {{ fact.start_date?.source_text ?? '未记录' }}（{{
                  fact.start_date?.precision ?? '未知精度'
                }}） / 结束 {{ fact.end_date?.source_text ?? '未记录' }}（{{
                  fact.end_date?.precision ?? '未知精度'
                }}）
              </p>
              <Button @click="locate(fact.evidence.map((e) => e.block_id))">定位结构化证据</Button
              ><Button @click="startStructured(fact)">修正结构化事实</Button>
              <div v-if="structuredEdit?.fact_id === fact.fact_id" class="editor">
                <label>事实内容<Input v-model:value="structuredEdit.value" /></label
                ><label
                  >机构<Input
                    :value="structuredEdit.organization ?? undefined"
                    @update:value="structuredEdit.organization = $event" /></label
                ><label
                  >职务<Input
                    :value="structuredEdit.title ?? undefined"
                    @update:value="structuredEdit.title = $event" /></label
                ><label
                  >学历<Input
                    :value="structuredEdit.degree ?? undefined"
                    @update:value="structuredEdit.degree = $event" /></label
                ><template v-for="key in ['start_date', 'end_date'] as const" :key="key"
                  ><template v-if="structuredEdit[key]"
                    ><label
                      >{{ key === 'start_date' ? '开始日期' : '结束日期'
                      }}<Input v-model:value="structuredEdit[key]!.value" /></label
                    ><label
                      >精度<select v-model="structuredEdit[key]!.precision">
                        <option>DAY</option>
                        <option>MONTH</option>
                        <option>YEAR</option>
                        <option>UNKNOWN</option>
                      </select></label
                    ></template
                  ></template
                ><label
                  >专业<Input
                    :value="structuredEdit.major ?? undefined"
                    @update:value="structuredEdit.major = $event" /></label
                ><label
                  >是否至今<select
                    :value="
                      structuredEdit.ongoing === null ? 'UNKNOWN' : String(structuredEdit.ongoing)
                    "
                    @change="
                      structuredEdit.ongoing =
                        ($event.target as HTMLSelectElement).value === 'UNKNOWN'
                          ? null
                          : ($event.target as HTMLSelectElement).value === 'true'
                    "
                  >
                    <option value="UNKNOWN">未记录</option>
                    <option value="true">至今</option>
                    <option value="false">已结束</option>
                  </select></label
                ><label
                  >是否实习<select
                    :value="
                      structuredEdit.is_internship === null
                        ? 'UNKNOWN'
                        : String(structuredEdit.is_internship)
                    "
                    @change="
                      structuredEdit.is_internship =
                        ($event.target as HTMLSelectElement).value === 'UNKNOWN'
                          ? null
                          : ($event.target as HTMLSelectElement).value === 'true'
                    "
                  >
                    <option value="UNKNOWN">未记录</option>
                    <option value="true">实习</option>
                    <option value="false">正式工作</option>
                  </select></label
                ><Button
                  v-if="!structuredEdit.measurement"
                  @click="
                    structuredEdit.measurement = {
                      metric: null,
                      unit: null,
                      value: null,
                      project_id: null,
                      role_level: null,
                      managed_team_size: null,
                    }
                  "
                  >补充同一项目明确测量</Button
                ><template v-if="structuredEdit.measurement"
                  ><label
                    >项目标识<Input
                      :value="structuredEdit.measurement.project_id ?? undefined"
                      @update:value="structuredEdit.measurement.project_id = $event" /></label
                  ><label
                    >规模指标<Input
                      :value="structuredEdit.measurement.metric ?? undefined"
                      @update:value="structuredEdit.measurement.metric = $event" /></label
                  ><label
                    >单位<Input
                      :value="structuredEdit.measurement.unit ?? undefined"
                      @update:value="structuredEdit.measurement.unit = $event" /></label
                  ><label
                    >明确规模数值<InputNumber
                      :value="structuredEdit.measurement.value ?? undefined"
                      :min="0"
                      @update:value="
                        structuredEdit.measurement.value = $event == null ? null : Number($event)
                      " /></label
                  ><label
                    >角色等级（1参与 / 2负责 / 3主导）<InputNumber
                      :value="structuredEdit.measurement.role_level ?? undefined"
                      :min="1"
                      :max="3"
                      :precision="0"
                      @update:value="
                        structuredEdit.measurement.role_level =
                          $event == null ? null : Number($event)
                      " /></label
                  ><label
                    >明确管理人数<InputNumber
                      :value="structuredEdit.measurement.managed_team_size ?? undefined"
                      :min="0"
                      :precision="0"
                      @update:value="
                        structuredEdit.measurement.managed_team_size =
                          $event == null ? null : Number($event)
                      " /></label
                ></template>
                <p>派生工作月数按服务端自然月并集计算，不直接编辑。</p>
                <label>修正原因<Input v-model:value="structuredReason" /></label
                ><label>人工来源（如候选人补充说明）<Input v-model:value="humanSource" /></label
                ><Button
                  type="primary"
                  :disabled="!structuredReason.trim() || !humanSource.trim()"
                  :loading="busy"
                  @click="saveStructured"
                  >保存结构化新事实版本</Button
                ><Button @click="structuredEdit = undefined">取消</Button>
              </div>
            </article>
          </section>
          <section v-if="tab === 'facts'" class="group">
            <h2>⌄ 工作与项目</h2>
            <article
              v-for="field in facts.fields"
              :key="field.id"
              class="field"
              :class="{ review: field.status !== 'CONFIRMED' }"
            >
              <div class="field-head">
                <b>{{ field.label }}</b
                ><Tag :color="field.status === 'CONFIRMED' ? 'green' : 'orange'">{{
                  field.status === 'CONFIRMED' ? '已确认' : '需确认'
                }}</Tag>
              </div>
              <p>{{ field.value || '未提及' }}</p>
              <p v-if="field.reason" class="muted">{{ field.reason }}</p>
              <Button
                type="link"
                :disabled="!field.evidenceIds.length"
                @click="locate(field.evidenceIds)"
                >在原文中定位 ↗</Button
              ><template v-if="field.status !== 'CONFIRMED'"
                ><Button :loading="busy" @click="confirm(field.id)">✓ 确认无误</Button
                ><Button
                  @click="
                    editing = field.id;
                    value = field.value;
                    reason = '';
                  "
                  >修改</Button
                ></template
              >
              <div v-if="editing === field.id" class="editor">
                <Input v-model:value="value" aria-label="修正内容" /><Input
                  v-model:value="reason"
                  aria-label="修正原因"
                  placeholder="请填写修正原因"
                /><Button
                  type="primary"
                  :disabled="!reason.trim()"
                  :loading="busy"
                  @click="saveCorrection"
                  >保存新事实版本</Button
                ><Button @click="editing = ''">取消</Button>
              </div>
            </article>
          </section>
          <section v-if="tab !== 'quality'" class="group">
            <h2>⌄ 技能与证据</h2>
            <p v-if="facts.dictionaryVersion !== null && facts.dictionaryVersion !== undefined">
              冻结词典 v{{ facts.dictionaryVersion }}
            </p>
            <p v-for="normalization in facts.normalizations" :key="normalization.factId">
              原句「{{ normalization.original }}」 → {{ normalization.canonical ?? '未归一' }} ·
              {{ normalization.status }} · 归一质量 {{ normalization.quality }}
            </p>
            <table>
              <thead>
                <tr>
                  <th>技能</th>
                  <th>证据强度</th>
                  <th>证据数量</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="skill in facts.skills" :key="skill.name">
                  <td>{{ skill.name }}</td>
                  <td>
                    <Tag :color="skill.strength === 'STRONG' ? 'green' : 'blue'">{{
                      { STRONG: '强', MEDIUM: '中', WEAK: '弱', UNKNOWN: '待核验' }[skill.strength]
                    }}</Tag>
                  </td>
                  <td>
                    <Button
                      type="link"
                      :disabled="!skill.evidenceIds.length"
                      @click="locate(skill.evidenceIds)"
                      >{{ skill.evidenceCount }}处</Button
                    >
                  </td>
                </tr>
              </tbody>
            </table>
            <small>ⓘ 证据强度表示材料支撑，不等于能力评级。</small>
          </section>
          <fieldset>
            <legend>明确不适用组（仅在材料与人工核实支持时确认）</legend>
            <Checkbox.Group
              v-model:value="notApplicable"
              :options="[
                { value: 'employment', label: '工作经历不适用' },
                { value: 'project', label: '项目经历不适用' },
                { value: 'skill', label: '技能组不适用' },
                { value: 'education', label: '教育组不适用' },
                { value: 'other', label: '其他组不适用' },
              ]"
            /><Button
              :disabled="!notApplicable.length"
              :loading="busy"
              @click="confirmNotApplicable"
              >明确确认所选组不适用</Button
            >
            <p>已确认：{{ facts.notApplicableGroups.join('、') || '无' }}</p>
          </fieldset>
          <Button :loading="busy" @click="loadHistory">读取修正历史</Button
          ><Button :disabled="!pending.length" @click="skipOpen = true">跳过待确认事实</Button>
          <details v-if="history.length">
            <summary>历史事实快照</summary>
            <article v-for="item in history" :key="item.version">
              <p>
                版本 {{ item.version }} · {{ item.status }} · 已确认 {{ item.confirmedCount }} /
                {{ item.totalCount }}
              </p>
              <p v-for="field in item.fields" :key="field.id">
                {{ field.label }}：{{ field.value || '未提及' }} · {{ field.status }}
              </p>
            </article>
          </details>
          <section v-if="tab === 'quality'" class="group">
            <h2>质量检查</h2>
            <p>解析质量：{{ facts.qualityScore === null ? '未记录' : `${facts.qualityScore}%` }}</p>
            <p>未确认事实 {{ pending.length }} 项；确认只改变事实状态，不直接生成候选人评分。</p>
          </section>
        </section>
      </div>
      <footer>
        ⓘ 本页仅确认简历事实，不生成评分。人工修正会保存新版本并保留记录。<Button
          type="primary"
          :disabled="pending.length > 0"
          :loading="busy"
          @click="proceed"
          >确认并继续匹配</Button
        >
      </footer>
      <Modal
        v-model:open="skipOpen"
        title="确认跳过待确认事实"
        :confirm-loading="busy"
        :ok-button-props="{ disabled: !skipReason.trim() }"
        @ok="skip"
        ><p>跳过不会把未知改成已具备，后续评分仍受证据覆盖与关键项门禁限制。</p>
        <Input v-model:value="skipReason" aria-label="跳过原因"
      /></Modal>
      <div class="mobile-evidence">
        <EvidenceSource ref="evidenceDrawer" :blocks="facts.blocks" :page-count="facts.pageCount" />
      </div>
    </template>
  </div>
</template>
<style scoped>
.mobile-evidence {
  display: none;
}
@media (max-width: 700px) {
  .mobile-evidence {
    display: block;
  }
  .source,
  .evidence {
    display: none;
  }
}
.hr-review {
  color: #10172b;
  padding: 0;
  font-size: 14px;
  display: grid;
  gap: 12px;
}
header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}
h1 {
  font-size: 26px;
  font-weight: 700;
  margin: 9px 0 3px;
}
h2 {
  font-size: 17px;
  font-weight: 700;
  margin: 0 0 9px;
}
h3 {
  font-size: 18px;
  margin: 0 0 8px;
}
p {
  margin: 5px 0 9px;
}
.actions,
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}
.status {
  display: flex;
  gap: 25px;
  border: 1px solid #e0e6f3;
  background: #ffffffa8;
  padding: 14px 22px;
  border-radius: 6px;
}
.status > * + * {
  border-left: 1px solid #dce3f0;
  padding-left: 25px;
}
.green {
  color: #0a9e3c;
}
.orange {
  color: #e7680b;
}
.workspace {
  display: grid;
  grid-template-columns: minmax(300px, 41%) minmax(0, 1fr);
  gap: 14px;
}
.card {
  border: 1px solid #dde4f2;
  border-radius: 8px;
  background: #ffffffa8;
  padding: 12px;
  min-width: 0;
}
.toolbar h2 {
  margin: 0 auto 0 0;
  white-space: nowrap;
}
.toolbar {
  flex-wrap: wrap;
}
.paper-area {
  background: #eaf0f6;
  padding: 16px;
  margin: 12px -6px 9px;
  max-height: 680px;
  overflow: auto;
}
.paper {
  background: white;
  padding: 25px;
  box-shadow: 0 1px 7px #23385c28;
  min-height: 590px;
  line-height: 1.7;
}
.paper > h2 {
  font-size: 28px;
}
.source-block {
  border: 1px solid #a6d7bb;
  border-radius: 4px;
  background: #f7fcf8;
  padding: 12px;
  margin: 18px 0;
  white-space: pre-wrap;
}
.source-block.selected {
  background: #fff4d0;
  border-color: #ffb94a;
  box-shadow: 0 0 0 2px #ffbf4733;
}
.source-block small,
.muted {
  color: #59657b;
}
.facts {
  position: relative;
}
.count {
  position: absolute;
  right: 16px;
  top: 29px;
  font-size: 12px;
}
.group {
  border: 1px solid #e0e6ef;
  border-radius: 5px;
  padding: 10px 14px;
  margin: 7px 0;
}
.basic {
  display: grid;
  grid-template-columns: 1fr 1.2fr 1fr;
  gap: 9px 20px;
}
.basic label {
  font-size: 12px;
  display: grid;
  gap: 3px;
}
.field {
  border: 1px solid #a4dac0;
  padding: 9px;
  border-radius: 4px;
  margin: 8px 0;
}
.field.review {
  border-color: #ffcf9d;
  background: #fff9f3;
}
.field-head {
  display: flex;
  justify-content: space-between;
}
.field .ant-btn {
  margin-right: 7px;
}
.editor {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th,
td {
  border-bottom: 1px solid #e0e6ef;
  padding: 4px 10px;
  text-align: left;
}
th {
  background: #eef2fa;
}
footer {
  border: 1px solid #dde4f2;
  background: #f4f6ff;
  padding: 10px 16px;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
}
small {
  font-size: 12px;
}
@media (min-width: 1101px) {
  header > div:first-child {
    display: grid;
    grid-template-columns: auto 1fr;
    column-gap: 16px;
    align-items: center;
  }
  header > div:first-child > .ant-btn {
    grid-row: 1 / 3;
  }
  header h1 {
    margin: 0;
  }
  header p {
    margin: 3px 0 0;
  }
  .workspace {
    max-height: 690px;
  }
  .paper-area {
    height: 580px;
    max-height: 580px;
  }
  .facts {
    overflow: auto;
  }
  .facts :deep(.ant-tabs-nav) {
    margin-bottom: 4px;
  }
  .group {
    padding: 5px 10px;
    margin: 4px 0;
  }
  .group h2 {
    margin-bottom: 3px;
    font-size: 16px;
  }
  .basic {
    gap: 3px 14px;
  }
  .basic label {
    gap: 1px;
  }
  .basic :deep(.ant-input) {
    height: 26px;
    padding: 2px 8px;
  }
  .field {
    padding: 4px 8px;
    margin: 4px 0;
    font-size: 13px;
  }
  .field-head {
    float: left;
    gap: 8px;
    margin-right: 10px;
  }
  .field > p {
    margin: 1px 0;
    line-height: 1.4;
  }
  .field > p.muted {
    clear: both;
  }
  .field > .ant-btn {
    height: 23px;
    padding: 0 8px;
    margin-top: 2px;
    font-size: 12px;
  }
  .field :deep(.ant-tag) {
    line-height: 18px;
  }
  td {
    padding: 0 8px;
  }
  td :deep(.ant-btn) {
    height: 26px;
  }
}
@media (max-width: 1100px) {
  .workspace {
    grid-template-columns: minmax(270px, 43%) minmax(0, 1fr);
  }
  .basic {
    grid-template-columns: 1fr 1fr;
  }
  .count {
    position: static;
    display: block;
    text-align: right;
  }
  header {
    align-items: flex-start;
  }
  .actions {
    flex-wrap: wrap;
  }
  .toolbar {
    gap: 5px;
  }
}
@media (max-width: 700px) {
  .hr-review {
    padding: 14px 10px;
  }
  header {
    display: block;
  }
  .actions {
    margin-top: 12px;
  }
  .workspace {
    grid-template-columns: 1fr;
  }
  .paper-area {
    max-height: 360px;
  }
  .status {
    flex-wrap: wrap;
    gap: 10px;
    padding: 12px;
  }
  .status > * + * {
    border: 0;
    padding: 0;
  }
  .basic {
    grid-template-columns: 1fr;
  }
  footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .paper {
    padding: 18px;
    min-height: 300px;
  }
}
</style>
