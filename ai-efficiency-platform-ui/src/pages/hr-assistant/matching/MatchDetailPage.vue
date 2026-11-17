<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Alert, Button, Modal, Progress, Tabs, TabPane, Tag } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite, matchingSchema, type HrMatching } from '../../../entities/hr';
import { draftSchema } from '../../../features/hr-position-draft/model';
import EvidenceSource from '../../../features/hr-evidence/EvidenceSource.vue';
const evidenceDrawer = ref<InstanceType<typeof EvidenceSource>>();
const route = useRoute();
const router = useRouter();
const result = ref<HrMatching>();
const loading = ref(false);
const error = ref('');
const tab = ref('requirements');
const page = ref(1);
const active = ref('');
const feedbackOpen = ref(false);
const feedbackBusy = ref(false);
const feedbackRating = ref('ACCURATE');
const feedbackReason = ref('');
const feedbackDone = ref('');
async function submitFeedback() {
  if (!result.value || feedbackBusy.value || !feedbackReason.value.trim()) return;
  feedbackBusy.value = true;
  error.value = '';
  try {
    await hrWrite(
      `/matching-results/${result.value.resultId}/feedback`,
      z.object({
        id: z.string(),
        resultId: z.string(),
        rating: z.string(),
        reason: z.string(),
        actorId: z.string(),
        createdAt: z.string(),
      }),
      {
        expectedSnapshotHash: result.value.snapshotHash,
        rating: feedbackRating.value,
        reason: feedbackReason.value,
      },
    );
    feedbackDone.value = '反馈已保存';
    feedbackOpen.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '反馈失败';
  } finally {
    feedbackBusy.value = false;
  }
}
const revokeId = ref('');
const revokeReason = ref('');
async function revokeOverride() {
  if (!result.value || !revokeId.value || !revokeReason.value.trim() || feedbackBusy.value) return;
  feedbackBusy.value = true;
  error.value = '';
  try {
    const next = await hrWrite(
      `/matching-results/${result.value.resultId}/override-revocations`,
      matchingSchema,
      {
        overrideId: revokeId.value,
        reason: revokeReason.value,
        expectedSnapshotHash: result.value.snapshotHash,
      },
    );
    revokeId.value = '';
    await router.replace({ path: route.path, query: { ...route.query, resultId: next.resultId } });
  } catch (e) {
    error.value = e instanceof Error ? e.message : '撤销失败';
  } finally {
    feedbackBusy.value = false;
  }
}
const snapshot = ref(false);
const snapshotBusy = ref(false);
const snapshotError = ref('');
const frozenSchema = z.object({
  id: z.string(),
  positionId: z.string(),
  version: z.string(),
  contextVersion: z.string(),
  snapshot: draftSchema,
  snapshotHash: z.string(),
  publishedBy: z.string(),
  publishedAt: z.string(),
  context: z
    .object({
      positionId: z.string(),
      name: z.string(),
      departmentId: z.string(),
      level: z.string().nullable(),
      jdText: z.string().nullable(),
      version: z.string(),
    })
    .nullish(),
});
const frozen = ref<z.infer<typeof frozenSchema>>();
async function openSnapshot() {
  if (!result.value || snapshotBusy.value) return;
  snapshot.value = true;
  snapshotBusy.value = true;
  snapshotError.value = '';
  frozen.value = undefined;
  try {
    frozen.value = await hrRequest(
      `/matching-results/${encodeURIComponent(result.value.resultId)}/configuration-snapshot`,
      frozenSchema,
    );
  } catch (e) {
    snapshotError.value = e instanceof Error ? e.message : '结果冻结配置读取失败';
  } finally {
    snapshotBusy.value = false;
  }
}

const conditions = ref(false);
let controller: AbortController | undefined;
const visibleBlocks = computed(
  () => result.value?.blocks.filter((b) => b.page === page.value || b.page === null) ?? [],
);
const passed = computed(
  () =>
    result.value?.hardConditions.filter((c) => ['PASS', 'OVERRIDDEN'].includes(c.status)).length ??
    0,
);
const requirements = computed(() => result.value?.dimensions.flatMap((d) => d.requirements) ?? []);
const filtered = computed(() => result.value?.businessStatus === 'FILTERED');
const review = computed(() => result.value?.businessStatus === 'REVIEW_REQUIRED');
const markLabels: Record<string, string> = {
  MANUAL_REVIEW: '人工复核',
  BORDERLINE: '临界',
  QUALITY_WARNING: '材料质量',
  DUPLICATE: '疑似重复',
  SPECIAL_BACKGROUND: '特殊背景',
};
const labels: Record<string, string> = {
  STRONG_MATCH: '显著满足',
  MATCH: '满足',
  PARTIAL_MATCH: '部分满足',
  EXPLICIT_NOT_MET: '明确不满足',
  UNKNOWN: '未提及',
  NEEDS_REVIEW: '待核验',
  'N/A': '不适用',
  NOT_APPLICABLE: '不适用',
};
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
async function load() {
  controller?.abort();
  if (!route.params.candidateId && !route.query.resultId) return;
  controller = new AbortController();
  loading.value = true;
  error.value = '';
  try {
    let id = route.query.resultId;
    if (!id) {
      const list = await hrRequest(
        `/matching-results?candidateId=${encodeURIComponent(String(route.params.candidateId))}&page=1&pageSize=1`,
        z.object({
          items: z.array(matchingSchema),
          total: z.number(),
          page: z.number(),
          pageSize: z.number(),
        }),
        { signal: controller.signal },
      );
      id = list.items[0]?.resultId;
      if (!id) {
        result.value = undefined;
        return;
      }
    }
    result.value = await hrRequest(
      `/matching-results/${encodeURIComponent(String(id))}`,
      matchingSchema,
      { signal: controller.signal },
    );
    page.value = result.value.blocks[0]?.page ?? 1;
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError'))
      error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    loading.value = false;
  }
}
watch(() => [route.params.candidateId, route.query.resultId], load, { immediate: true });
onBeforeUnmount(() => controller?.abort());
function locate(ids: string[]) {
  if (window.matchMedia('(max-width: 700px)').matches) {
    evidenceDrawer.value?.locate(ids);
    return;
  }
  const b = result.value?.blocks.find((b) => ids.includes(b.id));
  if (!b) return;
  active.value = b.id;
  page.value = b.page ?? 1;
  requestAnimationFrame(() =>
    document
      .getElementById(`match-source-${b.id}`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }),
  );
}
function time(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}
</script>
<template>
  <div class="hr-analysis ui-page">
    <Button class="back" type="link" @click="router.push('/ai-assistants/hr/matching')"
      >← 返回匹配结果</Button
    >
    <header>
      <div>
        <h1>
          {{ result ? `${result.candidateName ?? '姓名未记录'} · 岗位匹配分析` : '岗位匹配分析' }}
        </h1>
        <p v-if="result" class="target">目标岗位：{{ result.positionName }}</p>
        <p v-if="result" class="muted">
          岗位规则 {{ result.configVersion }} · 简历事实 {{ result.factSnapshotId }} · 分析于
          {{ time(result.createdAt) }}（北京时间）
        </p>
      </div>
      <div v-if="result" class="actions">
        <Button @click="feedbackOpen = true">反馈匹配结果</Button
        ><Button @click="openSnapshot">▤ 查看配置快照</Button
        ><Button
          type="primary"
          :disabled="filtered || review"
          @click="
            router.push(
              `/ai-assistants/hr/interviews/generate?candidateId=${result.candidateId}&positionId=${result.positionId}&resultId=${result.resultId}`,
            )
          "
          >✦ 生成面试提纲</Button
        >
      </div>
    </header>
    <Alert v-if="error" type="error" show-icon :message="error" /><Button v-if="error" @click="load"
      >重试读取</Button
    >
    <p v-if="loading" role="status">正在读取已保存的匹配快照…</p>
    <p v-if="!loading && !result && !error">
      请选择匹配列表中的候选人与结果版本，当前没有可展示的真实分析快照。
    </p>
    <template v-if="result && !loading">
      <p v-if="result.configVersion.startsWith('adhoc-')" role="note">临时权重方案，不修改默认</p>
      <Alert type="info" show-icon message="AI辅助分析，仅供面试参考；最终判断由招聘人员作出。" />
      <Alert
        v-if="result.supersededBy"
        type="warning"
        show-icon
        message="此结果为历史快照，配置或事实已更新；页面不会自动重新分析。"
      />
      <Alert
        v-if="filtered || review"
        :type="filtered ? 'info' : 'warning'"
        show-icon
        :message="filtered ? '被硬条件过滤 · 不生成总分或参考分' : '待核验 · 参考分不进入正式排名'"
        :description="result.reasonCodes.join('、')"
      />
      <section v-if="result.specialMarks.some((mark) => mark.active && mark.visible)" class="card">
        <h2>特殊标记</h2>
        <Tag
          v-for="mark in result.specialMarks.filter((mark) => mark.active && mark.visible)"
          :key="mark.key"
          color="orange"
          >{{ markLabels[mark.key] ?? mark.key
          }}<span v-if="mark.reason"> · {{ mark.reason }}</span></Tag
        >
      </section>
      <section class="summary">
        <div>
          <div class="score">
            <strong>{{ filtered || review ? '—' : (result.totalScore?.toFixed(1) ?? '—') }}</strong
            ><b>分</b
            ><Tag v-if="result.band && !filtered && !review" color="green">{{
              bands[result.band] ?? result.band
            }}</Tag>
          </div>
          <p>
            {{
              review && result.referenceScore !== null
                ? `参考分 ${result.referenceScore.toFixed(1)}（待核验）`
                : filtered
                  ? '请查看明确失败的硬性条件'
                  : '已达到当前岗位规则的对应分档'
            }}
          </p>
        </div>
        <div>
          <h2>
            证据覆盖率 <strong class="green">{{ result.evidenceCoverage }}%</strong>
          </h2>
          <Progress :percent="result.evidenceCoverage" :show-info="false" stroke-color="#0aa133" />
          <p>计分证据以服务端核验快照为准</p>
        </div>
        <div>
          <h2>
            硬性条件
            <strong class="green">{{ passed }} / {{ result.hardConditions.length }}</strong> 通过
          </h2>
          <div class="chips">
            <Tag
              v-for="condition in result.hardConditions"
              :key="condition.id"
              :color="['PASS', 'OVERRIDDEN'].includes(condition.status) ? 'green' : 'orange'"
              >{{ ['PASS', 'OVERRIDDEN'].includes(condition.status) ? '✓' : '○' }}
              {{ condition.label }}</Tag
            >
          </div>
          <Button type="link" @click="conditions = true">查看实际值与期望值 ›</Button>
        </div>
      </section>
      <div class="note">
        ⓘ 未提及内容不会直接判定为不具备。下方“面试重点核实”是补充面试内容，不构成负面评价。
      </div>
      <div class="analysis-grid">
        <section class="card dimensions">
          <h2>五维评分 <small>证据覆盖率</small></h2>
          <article v-for="dimension in result.dimensions" :key="dimension.id" class="dimension">
            <b>{{ dimension.label }}</b
            ><strong class="green"
              >{{ dimension.score === null ? '—' : dimension.score.toFixed(1)
              }}<small> 分</small></strong
            >
            <div class="weight">
              权重 {{ dimension.weight }}%<Progress
                :percent="dimension.score ?? 0"
                :show-info="false"
                :stroke-color="['BONUS', 'bonus'].includes(dimension.id) ? '#ff8215' : '#1262ff'"
              />
            </div>
            <span>{{ dimension.evidenceCoverage }}%</span>
          </article>
          <div class="formula">
            ▣ 总分 =
            {{ result.dimensions.map((d) => `${d.score ?? '—'} × ${d.weight}%`).join(' + ')
            }}<strong> = {{ result.totalScore ?? '—' }}</strong>
          </div>
          <p class="threshold">
            阈值：{{ result.thresholds.join(' / ')
            }}<Button
              type="link"
              @click="
                router.push(
                  `/ai-assistants/hr/matching?positionId=${result.positionId}&configVersionId=${result.configVersion}&recalculate=1`,
                )
              "
              >调整权重重算（无需重新解析） ›</Button
            >
          </p>
        </section>
        <section class="card breakdown">
          <Tabs v-model:active-key="tab"
            ><TabPane key="requirements" tab="达标分析" /><TabPane
              key="highlights"
              tab="匹配亮点" /><TabPane key="review" :tab="`核实点 ${result.reviewPoints.length}`"
          /></Tabs>
          <div v-if="tab === 'requirements'" class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>岗位要求</th>
                  <th>判断</th>
                  <th>证据</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in requirements" :key="item.id">
                  <td>{{ item.label }}</td>
                  <td>
                    <Tag
                      :color="
                        item.judgment === 'STRONG_MATCH'
                          ? 'green'
                          : ['UNKNOWN', 'NEEDS_REVIEW', 'PARTIAL_MATCH'].includes(item.judgment)
                            ? 'orange'
                            : 'blue'
                      "
                      >{{ labels[item.judgment] ?? item.judgment }}</Tag
                    >
                  </td>
                  <td>
                    {{ item.quote ?? '未记录可引用原文'
                    }}<Button
                      type="link"
                      :disabled="!item.evidenceIds.length"
                      @click="locate(item.evidenceIds)"
                      >{{ item.evidenceIds.join('、') || '无可定位证据' }} ↗</Button
                    >
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="!requirements.length">暂无原子要求记录。</p>
          </div>
          <ul v-if="tab === 'highlights'">
            <li v-for="item in result.highlights" :key="item">{{ item }}</li>
            <li v-if="!result.highlights.length">暂无已记录的匹配亮点。</li>
          </ul>
          <section v-if="tab !== 'highlights'" class="review-points">
            <h2>面试重点核实</h2>
            <p v-for="(item, index) in result.reviewPoints" :key="item">
              <b>{{ index + 1 }}</b
              >{{ item }}
            </p>
            <p v-if="!result.reviewPoints.length">暂无补充核实事项。</p>
            <small>ⓘ 根据已确认事实生成，不构成负面评价。</small>
          </section>
        </section>
        <aside class="card evidence">
          <div class="toolbar">
            <h2>原文证据</h2>
            <Button :disabled="page <= 1" @click="page--">‹</Button
            ><span>第{{ page }}页 / 共{{ result.pageCount }}页</span
            ><Button :disabled="page >= result.pageCount" @click="page++">›</Button>
          </div>
          <article class="paper">
            <h2>{{ result.candidateName ?? '姓名未记录' }}</h2>
            <section
              v-for="block in visibleBlocks"
              :id="`match-source-${block.id}`"
              :key="block.id"
              :class="{ selected: active === block.id }"
            >
              <h3 v-if="block.section">{{ block.section }}</h3>
              <p>{{ block.text }}</p>
              <small>{{ block.id }}</small>
            </section>
            <p v-if="!visibleBlocks.length">此页暂无可核验的原文块。</p>
          </article>
          <small>点击左侧证据可定位对应原文块。</small>
        </aside>
      </div>
      <section v-if="result.overrides.length" class="card">
        <h2>人工放行记录</h2>
        <article v-for="override in result.overrides" :key="override.id">
          <p>
            {{ override.conditionId }} · {{ override.action }} · {{ override.reason }} ·
            {{ time(override.createdAt) }}
          </p>
          <Button
            v-if="override.action === 'GRANTED' || override.action === 'OVERRIDE'"
            @click="
              revokeId = override.id;
              revokeReason = '';
            "
            >撤销此放行</Button
          >
        </article>
      </section>
      <Modal
        :open="!!revokeId"
        title="撤销人工放行"
        :confirm-loading="feedbackBusy"
        :ok-button-props="{ disabled: !revokeReason.trim() }"
        @cancel="revokeId = ''"
        @ok="revokeOverride"
        ><p>撤销后生成新结果，原历史保留；未放行条件重新适用。</p>
        <textarea v-model="revokeReason" maxlength="500" aria-label="撤销理由" />
      </Modal>
      <footer>● 分析已完成 · 结果与配置快照已保存 · 刷新不会重新分析</footer>
      <p v-if="feedbackDone" role="status">{{ feedbackDone }}</p>
      <Modal
        v-model:open="feedbackOpen"
        title="反馈匹配结果"
        :confirm-loading="feedbackBusy"
        :ok-button-props="{ disabled: !feedbackReason.trim() }"
        @ok="submitFeedback"
        ><label
          >判断<select v-model="feedbackRating">
            <option value="ACCURATE">基本准确</option>
            <option value="HIGH">评分偏高</option>
            <option value="LOW">评分偏低</option>
          </select></label
        ><label
          >原因<textarea v-model="feedbackReason" maxlength="500" aria-label="反馈原因" />
        </label>
        <p>反馈不覆盖原始结果。</p></Modal
      >
      <Modal v-model:open="snapshot" title="结果配置快照" :footer="null" :width="760"
        ><p v-if="snapshotBusy" role="status">正在读取此结果的冻结配置…</p>
        <Alert v-if="snapshotError" type="error" :message="snapshotError" /><Button
          v-if="snapshotError"
          @click="openSnapshot"
          >重试读取冻结快照</Button
        ><template v-if="frozen"
          ><p>配置版本 {{ frozen.version }} · 上下文版本 {{ frozen.contextVersion }}</p>
          <p v-if="frozen.version.startsWith('adhoc-')">临时权重方案，不修改默认</p>
          <h3>冻结硬条件</h3>
          <article v-for="rule in frozen.snapshot.hardConditions" :key="rule.id">
            <b>{{ rule.label }}</b>
            <p>
              类型 {{ rule.type }} · 期望 {{ rule.expected || '未记录' }} · 阈值
              {{ rule.threshold ?? '未记录' }} · 单位 {{ rule.unit || '未记录' }} · 容差
              {{ rule.tolerance ?? '未记录' }}
            </p>
            <p>
              值 {{ rule.values.join('、') || '未记录' }} · 匹配方式
              {{ rule.matchMode || '未记录' }} ·
              {{ rule.overridable ? '允许人工放行' : '不可人工放行' }}
            </p>
          </article>
          <p v-if="!frozen.snapshot.hardConditions.length">未提供硬条件记录。</p>
          <h3>冻结软要求与全部锚点</h3>
          <article v-for="criterion in frozen.snapshot.criteria" :key="criterion.id">
            <b>{{ criterion.label }} · {{ criterion.dimension }}</b>
            <p>{{ criterion.criterion }}</p>
            <p>显著满足：{{ criterion.strongAnchor || '未提供' }}</p>
            <p>满足：{{ criterion.matchAnchor || '未提供' }}</p>
            <p>部分满足：{{ criterion.partialAnchor || '未提供' }}</p>
            <p>明确不足：{{ criterion.notMetAnchor || '未提供' }}</p>
            <p>{{ criterion.critical ? '关键项' : '非关键项' }}</p>
            <p v-if="criterion.calculation">
              计算 {{ criterion.calculation.type }} · 最低
              {{ criterion.calculation.minimum ?? '未记录' }} · 最高
              {{ criterion.calculation.maximum ?? '未记录' }} · 期望
              {{ criterion.calculation.expected ?? '未记录' }} ·
              {{ criterion.calculation.metric ?? '' }} {{ criterion.calculation.unit ?? '' }}
            </p>
          </article>
          <p v-if="!frozen.snapshot.criteria.length">未提供软要求记录。</p>
          <template v-if="frozen.snapshot.draftScoring ?? frozen.snapshot.scoring"
            ><h3>权重、子项与覆盖门槛</h3>
            <template
              v-for="scoring in [frozen.snapshot.draftScoring ?? frozen.snapshot.scoring!]"
              :key="scoring.version"
              ><p v-for="(weight, key) in scoring.weights" :key="key">
                {{ key }} 权重 {{ weight }}%
              </p>
              <p v-for="requirement in scoring.requirements" :key="requirement.id">
                {{ requirement.id }} · {{ requirement.dimension }} · 相对权重
                {{ requirement.weight }} · {{ requirement.critical ? '关键项' : '非关键项' }} ·
                {{ requirement.applicable ? '适用' : '不适用' }}
              </p>
              <p>
                分档阈值 {{ scoring.highThreshold }} / {{ scoring.middleThreshold }} /
                {{ scoring.lowThreshold }}
              </p>
              <p>
                最低覆盖 {{ scoring.minimumCoverage }}% · 强烈推荐覆盖 {{ scoring.strongCoverage }}%
              </p></template
            ></template
          >
          <h3>可见标记</h3>
          <p>
            {{
              frozen.snapshot.visibleMarks.map((key) => markLabels[key] ?? key).join('、') ||
              '全部关闭'
            }}
          </p>
          <details>
            <summary>冻结岗位上下文与JD（只读）</summary>
            <template v-if="frozen.context"
              ><p>
                {{ frozen.context.name }} · {{ frozen.context.level ?? '职级未记录' }} ·
                {{ frozen.context.version }}
              </p>
              <p style="white-space: pre-wrap">
                {{ frozen.context.jdText ?? 'JD未记录' }}
              </p></template
            >
            <p v-else>旧快照未记录独立上下文，不使用当前岗位值补齐。</p>
          </details></template
        ></Modal
      >
      <Modal v-model:open="conditions" title="硬性条件：实际值与期望值" :footer="null"
        ><section v-for="c in result.hardConditions" :key="c.id" class="hard-condition">
          <h3>
            {{ c.label }} <Tag>{{ c.status }}</Tag>
          </h3>
          <p>期望：{{ c.expected ?? '未记录' }}</p>
          <p>实际：{{ c.actual ?? '未提及，待核验' }}</p>
        </section></Modal
      >
      <div class="mobile-evidence">
        <EvidenceSource
          ref="evidenceDrawer"
          :blocks="result.blocks"
          :page-count="result.pageCount"
        />
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
.hr-analysis {
  padding: 0;
  font-size: 14px;
  display: grid;
  gap: 12px;
  color: #10172b;
}
.back {
  padding: 0;
  justify-self: start;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
h1 {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 4px;
}
h2 {
  font-size: 17px;
  font-weight: 700;
  margin: 0 0 10px;
}
h3 {
  font-size: 18px;
}
p {
  margin: 6px 0;
}
.target {
  font-size: 18px;
}
.muted,
small {
  color: #536078;
  font-size: 12px;
}
.actions {
  display: flex;
  gap: 12px;
}
.summary {
  display: grid;
  grid-template-columns: 1fr 1fr 1.5fr;
  gap: 28px;
  border: 1px solid #dce3f2;
  border-radius: 8px;
  background: #ffffffb0;
  padding: 18px 22px;
}
.summary > div + div {
  border-left: 1px solid #dce3ef;
  padding-left: 28px;
}
.score {
  display: flex;
  gap: 10px;
  align-items: baseline;
}
.score > strong {
  font-size: 48px;
  color: #0a9e28;
  line-height: 1.2;
}
.score .ant-tag {
  margin-left: 12px;
  font-weight: 700;
}
.green {
  color: #069329;
}
.summary h2 strong {
  font-size: 26px;
  margin-left: 6px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.summary .ant-btn {
  padding-left: 0;
}
.note {
  background: #eff1f8;
  padding: 9px 15px;
  border-radius: 6px;
  font-size: 13px;
}
.analysis-grid {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(320px, 1.16fr) minmax(270px, 1fr);
  gap: 12px;
  align-items: stretch;
}
.card {
  border: 1px solid #dce3f2;
  border-radius: 8px;
  background: #ffffffb8;
  padding: 14px;
  min-width: 0;
}
.dimensions > h2 {
  padding-bottom: 14px;
  border-bottom: 1px solid #edf0f6;
  display: flex;
  justify-content: space-between;
}
.dimension {
  display: grid;
  grid-template-columns: 1.15fr 0.8fr 1fr 0.5fr;
  gap: 8px;
  align-items: center;
  padding: 17px 0;
  border-bottom: 1px solid #e9edf5;
  font-size: 13px;
}
.dimension > strong {
  font-size: 20px;
}
.dimension small {
  font-size: 11px;
  color: #172338;
  font-weight: 400;
}
.weight {
  font-size: 12px;
}
.weight .ant-progress {
  display: block;
  margin: 0;
}
.formula {
  background: #f0ecff;
  padding: 14px 12px;
  border-radius: 7px;
  line-height: 1.9;
  margin-top: 16px;
  font-size: 14px;
}
.formula strong {
  font-size: 21px;
  color: #792bfc;
}
.threshold {
  font-size: 12px;
  margin-top: 16px;
}
.threshold .ant-btn {
  font-size: 12px;
  padding: 0;
}
.table-wrap {
  overflow: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th {
  background: #edf0f8;
  text-align: left;
}
th,
td {
  padding: 9px;
  border-bottom: 1px solid #e1e7f0;
}
td .ant-btn {
  padding: 0;
  height: auto;
  font-size: 12px;
  display: block;
}
.review-points {
  border: 1px solid #e0e6f1;
  border-radius: 6px;
  padding: 12px;
  margin-top: 12px;
}
.review-points p {
  display: flex;
  gap: 10px;
  font-size: 13px;
  margin: 12px 0;
}
.review-points p b {
  background: #0660ff;
  color: white;
  border-radius: 50%;
  width: 21px;
  min-width: 21px;
  height: 21px;
  text-align: center;
}
.review-points small {
  background: #f3f5fa;
  display: block;
  padding: 8px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.toolbar h2 {
  margin: 0 auto 0 0;
  white-space: nowrap;
}
.toolbar .ant-btn {
  padding: 0 8px;
  height: 28px;
}
.paper {
  border: 1px solid #dce3f0;
  border-radius: 8px;
  padding: 20px;
  margin: 17px -3px 10px;
  min-height: 420px;
  max-height: 580px;
  overflow: auto;
  line-height: 1.7;
}
.paper > h2 {
  font-size: 24px;
  border-bottom: 1px solid #dce2ed;
  padding-bottom: 16px;
}
.paper section {
  padding: 8px 4px;
  border-radius: 4px;
  white-space: pre-wrap;
}
.paper .selected {
  background: #fff1c7;
  box-shadow: inset 3px 0 #ffbf33;
}
.paper small {
  font-size: 11px;
}
footer {
  display: flex;
  justify-content: space-between;
  background: #ecf0f8;
  border-radius: 7px;
  padding: 12px 16px;
  font-size: 13px;
  color: #4b5874;
}
.hard-condition {
  border-bottom: 1px solid #e4e8f0;
  padding-bottom: 10px;
}
@media (min-width: 1201px) {
  .hr-analysis {
    gap: 9px;
  }
  .back {
    height: 22px;
  }
  header p {
    margin: 3px 0;
  }
  .summary {
    padding: 12px 20px;
    gap: 20px;
  }
  .summary > div + div {
    padding-left: 20px;
  }
  .summary h2 {
    margin-bottom: 6px;
  }
  .summary p {
    font-size: 13px;
    margin: 3px 0;
  }
  .summary .ant-btn {
    height: 25px;
  }
  .summary :deep(.ant-progress) {
    margin: 3px 0;
    line-height: 1;
  }
  .summary :deep(.ant-tag) {
    font-size: 11px;
    line-height: 18px;
  }
  .chips {
    gap: 3px;
  }
  .score > strong {
    font-size: 46px;
  }
  .dimension {
    padding: 8px 0;
    min-height: 53px;
  }
  .dimensions > h2 {
    padding-bottom: 9px;
    margin-bottom: 4px;
  }
  .formula {
    margin-top: 10px;
    padding: 8px 10px;
    line-height: 1.7;
  }
  .threshold {
    margin-top: 8px;
  }
  .breakdown :deep(.ant-tabs-nav) {
    margin-bottom: 8px;
  }
  th,
  td {
    padding: 6px 8px;
  }
  .review-points {
    margin-top: 9px;
    padding: 9px 12px;
  }
  .review-points p {
    margin: 7px 0;
  }
  .paper {
    margin-top: 10px;
    max-height: 410px;
    min-height: 410px;
    padding: 16px;
  }
  .paper h3 {
    margin: 5px 0;
  }
  .paper section {
    padding: 5px 4px;
  }
}
@media (max-width: 1200px) {
  .analysis-grid {
    grid-template-columns: 1fr 1.2fr;
  }
  .evidence {
    grid-column: 1/-1;
  }
  .paper {
    min-height: 200px;
    max-height: 350px;
  }
  .summary {
    gap: 15px;
    padding: 15px;
  }
  .summary > div + div {
    padding-left: 15px;
  }
  .score {
    flex-wrap: wrap;
  }
  .score .ant-tag {
    margin-left: 0;
  }
}
@media (max-width: 700px) {
  .hr-analysis {
    padding: 14px 10px;
  }
  header {
    display: block;
  }
  h1 {
    font-size: 23px;
  }
  .actions {
    margin-top: 13px;
    flex-wrap: wrap;
  }
  .summary,
  .analysis-grid {
    grid-template-columns: 1fr;
  }
  .summary > div + div {
    border-left: 0;
    padding-left: 0;
    border-top: 1px solid #e0e6f0;
    padding-top: 14px;
  }
  .evidence {
    grid-column: auto;
  }
  .dimension {
    grid-template-columns: 1.1fr 0.8fr 1fr 0.5fr;
  }
  .toolbar {
    flex-wrap: wrap;
  }
  footer {
    flex-direction: column;
    gap: 8px;
  }
}
</style>
