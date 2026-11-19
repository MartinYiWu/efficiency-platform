<script setup lang="ts">
import { inject, onBeforeUnmount, ref, watch } from 'vue';
import {
  MemoryApiError,
  memoryAccessTokenKey,
  memoryErrorMessage,
  type MemoryScope,
} from '../../entities/memory';
import {
  createMemoryEpisodeApi,
  type EpisodeContent,
  type MemoryEpisode,
  type MemoryPromotion,
  type PromotionInput,
} from '../../entities/memory/episodes';
const props = defineProps<{ scope: MemoryScope; authorizationVersion?: number }>();
const emit = defineEmits<{ denied: [status: number] }>();
const token = inject(memoryAccessTokenKey, () => undefined),
  api = createMemoryEpisodeApi(token);
const open = ref(false),
  busy = ref(false),
  error = ref(''),
  success = ref('');
const items = ref<MemoryEpisode[]>([]),
  promotion = ref<MemoryPromotion>();
const promotions = ref<MemoryPromotion[]>([]);
const sharingEpisode = ref<MemoryEpisode>(),
  sharingScopeId = ref(''),
  deidentified = ref({
    scenario: '',
    preconditions: '',
    actions: '',
    observedResults: '',
    disallowedConditions: '',
  });
const proof = ref({
  suiteId: '',
  suiteVersion: '',
  reportSha256: '',
  totalCases: 1,
  passedCases: 1,
});
const form = ref({
  executionId: '',
  category: 'USER_PREFERENCE' as EpisodeContent['category'],
  scenario: '',
  preconditions: '',
  actions: '',
  observedResults: '',
  denominator: '',
  observedFrom: '',
  observedUntil: '',
  evidenceRefs: '',
  applicableVersion: '',
  disallowedConditions: '',
});
const target = ref<PromotionInput>({
  targetType: 'PROMPT',
  targetDefinitionId: '',
  semanticVersion: '',
  changeSummary: '',
  graphKey: null,
  graphVersion: null,
});
const selected = ref<MemoryEpisode>();
let generation = 0,
  controller: AbortController | undefined;
const lines = (value: string) =>
  value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
const key = () => crypto.randomUUID();
function clear() {
  generation++;
  controller?.abort();
  items.value = [];
  selected.value = undefined;
  promotion.value = undefined;
  target.value = {
    targetType: 'PROMPT',
    targetDefinitionId: '',
    semanticVersion: '',
    changeSummary: '',
    graphKey: null,
    graphVersion: null,
  };
  proof.value = { suiteId: '', suiteVersion: '', reportSha256: '', totalCases: 1, passedCases: 1 };
  promotions.value = [];
  sharingEpisode.value = undefined;
  sharingScopeId.value = '';
  deidentified.value = {
    scenario: '',
    preconditions: '',
    actions: '',
    observedResults: '',
    disallowedConditions: '',
  };
  error.value = '';
  success.value = '';
  busy.value = false;
  for (const name of Object.keys(form.value)) {
    if (name !== 'category') (form.value as unknown as Record<string, string>)[name] = '';
  }
}
function reportFailure(reason: unknown) {
  if (reason instanceof MemoryApiError && [401, 403, 404].includes(reason.status)) {
    clear();
    open.value = false;
    emit('denied', reason.status);
  }
  error.value = memoryErrorMessage(reason);
}
async function load() {
  clear();
  if (!open.value || !token() || (props.scope.topAgent !== 'hr' && !props.scope.sessionId)) return;
  controller = new AbortController();
  const current = generation;
  busy.value = true;
  try {
    const result = await api.list(props.scope, controller.signal);
    if (current === generation) items.value = result;
  } catch (reason) {
    if (current === generation && !controller.signal.aborted) reportFailure(reason);
  } finally {
    if (current === generation) busy.value = false;
  }
}
async function mutate(work: () => Promise<MemoryEpisode | MemoryPromotion>) {
  if (busy.value) return;
  const current = generation;
  busy.value = true;
  error.value = '';
  success.value = '';
  try {
    const result = await work();
    if (current !== generation) return;
    if ('episodeId' in result) {
      promotion.value = result;
      promotions.value = [...promotions.value.filter((item) => item.id !== result.id), result];
      success.value =
        result.status === 'PUBLISHED'
          ? '正式资产版本已批准发布，部署状态请在原发布管理中核对。'
          : result.status === 'REGRESSION_PASSED'
            ? '固定回归证明已登记，仍需另一位有权人员批准发布。'
            : '已创建正式资产候选，仍需固定回归与人工发布批准。';
    } else {
      items.value = [...items.value.filter((item) => item.id !== result.id), result];
      success.value = '案例状态已更新，请核对确认与共享状态。';
    }
  } catch (reason) {
    if (current === generation) reportFailure(reason);
  } finally {
    if (current === generation) busy.value = false;
  }
}
async function loadPromotions() {
  if (busy.value) return;
  const current = generation;
  busy.value = true;
  error.value = '';
  try {
    const result = await api.promotions(controller?.signal);
    if (current === generation) promotions.value = result;
  } catch (reason) {
    if (current === generation) reportFailure(reason);
  } finally {
    if (current === generation) busy.value = false;
  }
}
async function loadShared() {
  if (busy.value || !sharingScopeId.value.trim()) return;
  const current = generation;
  busy.value = true;
  error.value = '';
  items.value = [];
  try {
    const result = await api.shared(sharingScopeId.value.trim(), controller?.signal);
    if (current === generation) items.value = result;
  } catch (reason) {
    if (current === generation) reportFailure(reason);
  } finally {
    if (current === generation) busy.value = false;
  }
}
function shareEpisode() {
  const episode = sharingEpisode.value;
  if (!episode || !sharingScopeId.value.trim()) {
    error.value = '请填写已批准的记忆范围编号';
    return;
  }
  if (!episode.content) return;
  const draft = deidentified.value;
  const content: EpisodeContent = {
    ...episode.content,
    scenario: draft.scenario,
    preconditions: lines(draft.preconditions),
    actions: lines(draft.actions),
    observedResults: draft.observedResults,
    disallowedConditions: lines(draft.disallowedConditions),
  };
  void mutate(() =>
    api.sharing(
      episode,
      props.scope,
      sharingScopeId.value.trim(),
      content,
      key(),
      controller?.signal,
    ),
  );
}
function beginSharing(episode: MemoryEpisode) {
  if (!episode.content) return;
  sharingEpisode.value = episode;
  deidentified.value = {
    scenario: episode.content.scenario,
    preconditions: episode.content.preconditions.join('\n'),
    actions: episode.content.actions.join('\n'),
    observedResults: episode.content.observedResults,
    disallowedConditions: episode.content.disallowedConditions.join('\n'),
  };
}
function create() {
  const draft = form.value;
  if (!draft.executionId.trim()) {
    error.value = '请提供当前有权任务的执行编号';
    return;
  }
  const content: EpisodeContent = {
    category: props.scope.topAgent === 'hr' ? 'TECHNICAL_EXPERIENCE' : draft.category,
    scenario: draft.scenario,
    preconditions: lines(draft.preconditions),
    actions: lines(draft.actions),
    observedResults: draft.observedResults,
    denominator: draft.denominator ? Number(draft.denominator) : null,
    observedFrom: draft.observedFrom ? new Date(draft.observedFrom).toISOString() : null,
    observedUntil: draft.observedUntil ? new Date(draft.observedUntil).toISOString() : null,
    evidenceRefs: lines(draft.evidenceRefs),
    applicableVersion: draft.applicableVersion,
    disallowedConditions: lines(draft.disallowedConditions),
  };
  if (
    content.category === 'MEASURED_RESULT' &&
    (!content.denominator || !content.observedFrom || !content.observedUntil)
  ) {
    error.value = '效果经验必须填写真实测量分母与观察时间';
    return;
  }
  void mutate(() =>
    api.create(props.scope, draft.executionId.trim(), content, key(), controller?.signal),
  );
}
watch(
  () => [props.scope.topAgent, props.scope.sessionId, props.authorizationVersion, token()],
  () => {
    clear();
    if (open.value) void load();
  },
  { flush: 'sync' },
);
watch(open, () => {
  if (open.value) void load();
  else clear();
});
onBeforeUnmount(clear);
const labels: Record<string, string> = {
  CANDIDATE: '待确认案例',
  CONFIRMED: '已确认',
  REJECTED: '已拒绝',
  SHARE_PENDING: '脱敏共享待审批',
  SHARED: '已批准共享',
  REVOKED: '来源失效',
  DRAFT: '正式资产草稿',
  REGRESSION_PASSED: '固定回归已通过',
  PUBLISHED: '已发布',
};
</script>
<template>
  <section class="ui-card promotion-panel" aria-label="经验案例与资产晋升">
    <button type="button" :aria-expanded="open" @click="open = !open">经验案例与资产晋升</button>
    <div v-if="open">
      <p>点赞只表示偏好。效果经验需真实测量；共享、回归和发布各需独立批准，不自动修改线上规则。</p>
      <p v-if="scope.topAgent === 'hr'">仅记录去身份的技术处理经验，不保存候选人长期印象。</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <p v-if="success" role="status">{{ success }}</p>
      <details>
        <summary>记录案例候选</summary>
        <form class="episode-form" @submit.prevent="create">
          <label
            >当前执行编号<input
              v-model="form.executionId"
              required
              maxlength="128"
              :disabled="busy"
          /></label>
          <label v-if="scope.topAgent !== 'hr'"
            >案例类型<select v-model="form.category" :disabled="busy">
              <option value="USER_PREFERENCE">用户偏好</option>
              <option value="MEASURED_RESULT">真实测量结果</option>
              <option value="TECHNICAL_EXPERIENCE">技术经验</option>
            </select></label
          >
          <label
            >适用场景<textarea
              v-model="form.scenario"
              required
              maxlength="2048"
              :disabled="busy"
            /></label
          ><label
            >前置条件（每行一项）<textarea v-model="form.preconditions" :disabled="busy" /></label
          ><label
            >采取措施（每行一项）<textarea
              v-model="form.actions"
              required
              :disabled="busy"
            /></label
          ><label
            >真实观察结果<textarea
              v-model="form.observedResults"
              required
              maxlength="4096"
              :disabled="busy"
            />
          </label>
          <template v-if="form.category === 'MEASURED_RESULT'"
            ><label
              >测量分母<input
                v-model="form.denominator"
                type="number"
                min="1"
                step="1"
                required
                :disabled="busy" /></label
            ><label
              >观察开始时间<input
                v-model="form.observedFrom"
                type="datetime-local"
                required
                :disabled="busy" /></label
            ><label
              >观察结束时间<input
                v-model="form.observedUntil"
                type="datetime-local"
                required
                :disabled="busy" /></label
          ></template>
          <label
            >有权证据引用（每行一项）<textarea
              v-model="form.evidenceRefs"
              required
              :disabled="busy"
            /></label
          ><label
            >适用版本<input
              v-model="form.applicableVersion"
              required
              maxlength="128"
              :disabled="busy" /></label
          ><label
            >禁用条件（每行一项）<textarea
              v-model="form.disallowedConditions"
              :disabled="busy"
            /></label
          ><a-button html-type="submit" type="primary" :disabled="busy">保存案例候选</a-button>
        </form>
      </details>
      <a-button size="small" :disabled="busy" @click="load">刷新案例</a-button>
      <form class="episode-form" @submit.prevent="loadShared">
        <label
          >读取已获授权范围的脱敏案例<input
            v-model="sharingScopeId"
            maxlength="128"
            required
            :disabled="busy"
            placeholder="记忆范围编号" /></label
        ><a-button html-type="submit" size="small" :disabled="busy">查看范围案例与待审批</a-button>
      </form>
      <p v-if="!busy && !items.length">当前范围暂无案例</p>
      <article v-for="item in items" :key="item.id" class="episode-item">
        <a-tag>{{ labels[item.status] }}</a-tag
        ><template v-if="item.content"
          ><strong>{{ item.content.scenario }}</strong>
          <p>{{ item.content.observedResults }}</p>
          <p>
            适用版本 {{ item.content.applicableVersion }} ·
            {{ item.content.evidenceRefs.length }} 条证据
          </p>
          <p v-if="item.content.denominator">
            真实测量分母 {{ item.content.denominator }}
          </p></template
        >
        <p>有效至 {{ new Date(item.expiresAt).toLocaleString('zh-CN') }}</p>
        <a-space wrap
          ><a-button
            v-if="item.status === 'CANDIDATE'"
            size="small"
            :disabled="busy"
            @click="mutate(() => api.decide(item, scope, 'CONFIRM', key(), controller?.signal))"
            >确认案例</a-button
          ><a-button
            v-if="item.status === 'CANDIDATE'"
            size="small"
            :disabled="busy"
            @click="mutate(() => api.decide(item, scope, 'REJECT', key(), controller?.signal))"
            >拒绝案例</a-button
          ><a-button
            v-if="item.status === 'CONFIRMED' && item.content"
            size="small"
            :disabled="busy"
            @click="beginSharing(item)"
            >申请脱敏共享</a-button
          ><a-button
            v-if="item.status === 'SHARE_PENDING'"
            size="small"
            :disabled="busy"
            @click="mutate(() => api.approveSharing(item, key(), controller?.signal))"
            >审批脱敏共享</a-button
          ><a-button
            v-if="item.status !== 'REVOKED' && item.status !== 'REJECTED'"
            size="small"
            :disabled="busy"
            @click="mutate(() => api.like(item, scope, controller?.signal))"
            >偏好反馈（{{ item.feedbackLikes }}）</a-button
          ><a-popconfirm
            v-if="item.status !== 'REVOKED'"
            title="撤回后该案例将停止共享和后续晋升。正式资产请同时在原发布管理中核对。"
            @confirm="mutate(() => api.withdraw(item, scope, key(), controller?.signal))"
            ><a-button size="small" danger :disabled="busy">撤回案例</a-button></a-popconfirm
          ><a-button
            v-if="item.status === 'SHARED'"
            size="small"
            :disabled="busy"
            @click="selected = item"
            >申请正式资产候选</a-button
          ></a-space
        >
      </article>
      <form v-if="sharingEpisode" class="episode-form" @submit.prevent="shareEpisode">
        <h4>提交人工脱敏案例</h4>
        <p>请逐项删除身份及敏感细节，保留证据、适用条件和禁用条件；提交后需独立审批人核验。</p>
        <label
          >已批准的记忆范围编号<input
            v-model="sharingScopeId"
            required
            maxlength="128"
            :disabled="busy"
        /></label>
        <label
          >脱敏后的适用场景<textarea
            v-model="deidentified.scenario"
            required
            maxlength="2048"
            :disabled="busy"
          />
        </label>
        <label
          >前置条件（每行一项）<textarea v-model="deidentified.preconditions" :disabled="busy" />
        </label>
        <label
          >采取措施（每行一项）<textarea v-model="deidentified.actions" required :disabled="busy" />
        </label>
        <label
          >可观察结果<textarea
            v-model="deidentified.observedResults"
            required
            maxlength="4096"
            :disabled="busy"
          />
        </label>
        <label
          >禁用条件（每行一项）<textarea
            v-model="deidentified.disallowedConditions"
            :disabled="busy"
          />
        </label>
        <p>证据、测量记录和适用版本沿用原案例，来源权限会在审批时重新核验。</p>
        <a-button type="primary" html-type="submit" :disabled="busy">确认申请脱敏共享</a-button>
      </form>
      <form
        v-if="selected"
        class="episode-form"
        @submit.prevent="
          mutate(() => api.proposePromotion(selected!, scope, target, key(), controller?.signal))
        "
      >
        <h4>创建正式资产草稿</h4>
        <label
          >资产类型<select v-model="target.targetType">
            <option value="PROMPT">Prompt</option>
            <option value="WORKFLOW">Workflow</option>
            <option value="SKILL">Skill</option>
          </select></label
        ><label
          >现有资产定义编号<input
            v-model="target.targetDefinitionId"
            required
            maxlength="128" /></label
        ><label>语义版本<input v-model="target.semanticVersion" required maxlength="128" /></label
        ><label>变更说明<textarea v-model="target.changeSummary" required /></label
        ><template v-if="target.targetType !== 'PROMPT'"
          ><label>已发布图标识<input v-model="target.graphKey" required /></label
          ><label>已发布图版本<input v-model="target.graphVersion" required /></label></template
        ><a-button html-type="submit" type="primary" :disabled="busy">创建候选草稿</a-button>
      </form>
      <p v-if="promotion" role="status">
        {{ labels[promotion.status] }} · 目标版本 {{ promotion.targetVersionId }}
      </p>
      <details>
        <summary>正式资产候选审核</summary>
        <p>
          回归证明需由独立审核人员提交，套件与通过门槛以发布策略为准。批准发布不会自动部署到外部服务。
        </p>
        <a-button size="small" :disabled="busy" @click="loadPromotions">读取候选审核列表</a-button>
        <article v-for="candidate in promotions" :key="candidate.id" class="episode-item">
          <strong>{{ candidate.targetType }} · {{ candidate.targetVersionId }}</strong>
          <p>{{ labels[candidate.status] }}</p>
          <p>候选摘要 {{ candidate.candidateDigest }}</p>
          <form
            v-if="candidate.status === 'DRAFT'"
            class="episode-form"
            @submit.prevent="
              mutate(() => api.regression(candidate, proof, key(), controller?.signal))
            "
          >
            <label>固定套件编号<input v-model="proof.suiteId" required /></label
            ><label>套件版本<input v-model="proof.suiteVersion" required /></label
            ><label
              >真实回归报告 SHA-256<input
                v-model="proof.reportSha256"
                required
                pattern="[0-9a-f]{64}"
                maxlength="64" /></label
            ><label
              >实际用例总数<input
                v-model.number="proof.totalCases"
                type="number"
                min="1"
                step="1"
                required /></label
            ><label
              >通过数<input
                v-model.number="proof.passedCases"
                type="number"
                min="0"
                step="1"
                required /></label
            ><a-button html-type="submit" :disabled="busy">登记固定回归证明</a-button>
          </form>
          <a-popconfirm
            v-if="candidate.status === 'REGRESSION_PASSED'"
            title="确认以当前候选与回归证明批准正式资产版本发布？"
            @confirm="mutate(() => api.publish(candidate, key(), controller?.signal))"
            ><a-button type="primary" :disabled="busy">批准版本发布</a-button></a-popconfirm
          >
        </article>
      </details>
    </div>
  </section>
</template>
<style scoped>
.promotion-panel {
  padding: 20px;
  margin-block: 16px;
}
.promotion-panel > button {
  border: 0;
  background: none;
  color: var(--ant-color-primary, #6366f1);
  cursor: pointer;
  font: inherit;
}
.episode-form {
  display: grid;
  gap: 12px;
  margin-block: 16px;
}
label {
  display: grid;
  gap: 6px;
}
input,
select,
textarea {
  padding: 8px;
  border: 1px solid var(--ant-color-border, #ddd);
  border-radius: 6px;
  background: var(--ant-color-bg-container, white);
  color: inherit;
}
textarea {
  min-height: 64px;
  resize: vertical;
}
.episode-item {
  border-top: 1px solid var(--ant-color-border-secondary, #eee);
  padding-block: 16px;
  overflow-wrap: anywhere;
}
button:focus-visible {
  outline: 2px solid var(--ant-color-primary, #6366f1);
  outline-offset: 3px;
}
</style>
