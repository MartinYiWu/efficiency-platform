<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Alert, Button, Input, Modal, Tabs, TabPane, Tag } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../../entities/hr';
import { profileSchema, beijing } from '../../../entities/hr/completion';
import styles from './CandidateProfilePage.module.css';
const route = useRoute();
const router = useRouter();
const profile = ref<z.infer<typeof profileSchema>>();
const busy = ref(false);
const error = ref('');
const contactOpen = ref(false);
const reason = ref('');
const tab = ref('facts');
const mergeOpen = ref(false);
const mergeSources = ref('');
const mergeReason = ref('');
const deleteOpen = ref(false);
const deleteReason = ref('');
const lifecycle = ref('');
const deletionId = ref('');
let deletionTimer: ReturnType<typeof setTimeout> | undefined;
let deletionPolls = 0;
const retentionOpen = ref(false);
const retentionExpiry = ref('');
const retentionBasis = ref('');
const retentionPolicy = ref('');
async function refreshDeletion() {
  if (!deletionId.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const job = await hrRequest(
      `/deletion-jobs/${deletionId.value}`,
      z.object({
        id: z.string(),
        status: z.string(),
        step: z.string(),
        failureCode: z.string().nullable(),
      }),
    );
    lifecycle.value = `清理任务 ${job.status} · ${job.step} · ${job.failureCode ?? ''}`;
    if (
      !['COMPLETED', 'DELETED', 'BLOCKED', 'FAILED'].includes(job.status) &&
      deletionPolls++ < 120
    )
      deletionTimer = setTimeout(refreshDeletion, 3000);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '清理状态读取失败';
  } finally {
    busy.value = false;
  }
}
async function retention() {
  if (
    !profile.value ||
    busy.value ||
    !retentionExpiry.value ||
    !retentionBasis.value.trim() ||
    !retentionPolicy.value.trim()
  )
    return;
  const source = profile.value.sources.find((s) => s.candidateId === profile.value!.candidateId);
  if (!source) return;
  busy.value = true;
  error.value = '';
  try {
    await hrWrite(`/candidates/${profile.value.candidateId}/retention-extensions`, z.null(), {
      expectedVersion: source.candidateVersion,
      expiresAt: new Date(retentionExpiry.value).toISOString(),
      legalBasis: retentionBasis.value,
      policyVersion: retentionPolicy.value,
    });
    retentionOpen.value = false;
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : '延长保留失败';
  } finally {
    busy.value = false;
  }
}

const mergeVersion = ref<number>();
const mergeSchema = z.object({
  id: z.string(),
  primaryCandidateId: z.string(),
  sourceCandidateIds: z.array(z.string()),
  status: z.string(),
  createdAt: z.string(),
  revocableUntil: z.string(),
  version: z.number(),
});
async function merge() {
  if (!profile.value || busy.value || !mergeReason.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    const result = await hrWrite('/candidate-merges', mergeSchema, {
      primaryCandidateId: profile.value.candidateId,
      sourceCandidateIds: mergeSources.value.split(/[\s,，]+/).filter(Boolean),
      reason: mergeReason.value,
    });
    mergeVersion.value = result.version;
    mergeOpen.value = false;
    lifecycle.value = '已合并，来源权限和保留期不会扩大';
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : '合并失败';
  } finally {
    busy.value = false;
  }
}
async function revokeMerge() {
  if (
    !profile.value?.mergeId ||
    mergeVersion.value === undefined ||
    busy.value ||
    !mergeReason.value.trim()
  )
    return;
  busy.value = true;
  error.value = '';
  try {
    await hrWrite(`/candidate-merges/${profile.value.mergeId}/revocations`, mergeSchema, {
      expectedVersion: mergeVersion.value,
      reason: mergeReason.value,
    });
    lifecycle.value = '已撤销合并';
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : '撤销失败';
  } finally {
    busy.value = false;
  }
}
async function deletion() {
  if (!profile.value || busy.value || !deleteReason.value.trim()) return;
  const source = profile.value.sources.find((s) => s.candidateId === profile.value!.candidateId);
  if (!source) {
    error.value = '缺少主档版本，不能提交删除';
    return;
  }
  busy.value = true;
  error.value = '';
  try {
    const job = await hrWrite(
      `/candidates/${profile.value.candidateId}/deletions`,
      z.object({
        id: z.string(),
        candidateId: z.string(),
        status: z.string(),
        step: z.string(),
        attempts: z.number(),
        nextAttemptAt: z.string().nullable(),
        createdAt: z.string(),
        alert: z.boolean(),
        failureCode: z.string().nullable(),
      }),
      { expectedVersion: source.candidateVersion, confirmed: true, reason: deleteReason.value },
    );
    deleteOpen.value = false;
    deletionId.value = job.id;
    lifecycle.value = `清理任务 ${job.status} · ${job.step} · ${job.failureCode ?? ''}（未完成前不显示已删除）`;
    profile.value = undefined;
    deletionPolls = 0;
    deletionTimer = setTimeout(refreshDeletion, 3000);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '删除提交失败';
  } finally {
    busy.value = false;
  }
}

const contactView = ref<{ phone: string | null; email: string | null }>();
let contactTimer: ReturnType<typeof setTimeout> | undefined;
onBeforeUnmount(() => {
  clearTimeout(contactTimer);
  clearTimeout(deletionTimer);
});
async function load() {
  if (!route.params.candidateId) return;
  busy.value = true;
  error.value = '';
  try {
    profile.value = await hrRequest(
      `/candidates/${encodeURIComponent(String(route.params.candidateId))}`,
      profileSchema,
    );
    mergeVersion.value = profile.value.mergeVersion ?? undefined;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    busy.value = false;
  }
}
async function contact() {
  if (!profile.value || busy.value || !reason.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    const grant = await hrWrite(
      `/candidates/${profile.value.candidateId}/contact-grants`,
      z.object({ id: z.string(), expiresAt: z.string() }),
      { reason: reason.value },
    );
    contactView.value = await hrRequest(
      `/contact-grants/${grant.id}`,
      z.object({ phone: z.string().nullable(), email: z.string().nullable() }),
      { cache: 'no-store' },
    );
    clearTimeout(contactTimer);
    contactTimer = setTimeout(() => (contactView.value = undefined), 30000);
    contactOpen.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '查看失败';
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <Button @click="router.push('/ai-assistants/hr/talent')">返回人才库</Button>
    <header>
      <h1>候选人档案</h1>
      <p>按可见来源展示事实和版本，不扩大合并前的授权范围。</p>
    </header>
    <Alert v-if="error" type="error" :message="error" show-icon /><Button v-if="error" @click="load"
      >重试读取</Button
    >
    <p v-if="lifecycle" role="status">{{ lifecycle }}</p>
    <Button v-if="deletionId" :loading="busy" @click="refreshDeletion">读取清理进度</Button>
    <p v-if="busy" role="status">正在读取档案…</p>
    <p v-if="!route.params.candidateId">请从人才库选择真实候选人。</p>
    <p v-if="contactView" role="status">
      电话 {{ contactView.phone ?? '未记录' }} · 邮箱
      {{ contactView.email ?? '未记录' }}（30秒后隐藏）
    </p>
    <template v-if="profile"
      ><Button
        @click="
          mergeOpen = true;
          mergeReason = '';
        "
        >合并授权来源</Button
      ><Button @click="retentionOpen = true">申请延长保留期</Button
      ><Button danger @click="deleteOpen = true">申请删除与清理</Button
      ><Button @click="contactOpen = true">查看联系方式（需授权）</Button
      ><Tabs v-model:active-key="tab"
        ><TabPane key="facts" tab="事实与来源" /><TabPane key="interviews" tab="题集历史" /></Tabs
      ><template v-if="tab === 'facts'"
        ><section
          v-for="source in profile.sources"
          :key="source.candidateId"
          style="
            background: #ffffffa8;
            border: 1px solid #dde4f2;
            padding: 20px;
            margin: 12px 0;
            border-radius: 8px;
          "
        >
          <h2>{{ source.facts.profile.name ?? '姓名未记录' }}</h2>
          <p>
            部门 {{ source.departmentId }} · 事实 v{{ source.facts.version }} · 保留至
            {{ beijing(source.expiresAt) }}（北京时间）
          </p>
          <p>授权政策 {{ source.consentPolicyId }} · {{ source.facts.filename }}</p>
          <Tag>{{ source.facts.status }}</Tag>
          <p>
            {{ source.facts.profile.education ?? '学历未记录' }} ·
            {{
              source.facts.profile.experienceMonths === null
                ? '经验未记录'
                : `${source.facts.profile.experienceMonths}个月`
            }}
          </p>
          <article v-for="field in source.facts.fields" :key="field.id">
            <b>{{ field.label }}</b>
            <p>{{ field.value || '未提及' }}</p>
            <Tag>{{ field.status }}</Tag>
          </article>
          <Button
            @click="
              router.push(`/ai-assistants/hr/resumes/candidates/${source.candidateId}/confirm`)
            "
            >核对事实与修正历史</Button
          ><Button
            @click="router.push(`/ai-assistants/hr/matching?candidateId=${source.candidateId}`)"
            >查看匹配历史</Button
          >
        </section>
        <p v-if="!profile.sources.length">没有当前授权可见的来源。</p></template
      ><template v-else
        ><article v-for="set in profile.interviewSets" :key="set.id">
          <p>{{ beijing(set.createdAt) }} · v{{ set.version }} · {{ set.status }}</p>
          <Button
            @click="router.push(`/ai-assistants/hr/interviews/questions?questionSetId=${set.id}`)"
            >查看题集快照</Button
          >
        </article>
        <p v-if="!profile.interviewSets.length">尚无面试题集。</p></template
      ></template
    ><Modal
      v-model:open="retentionOpen"
      title="确认延长保留期"
      :confirm-loading="busy"
      :ok-button-props="{
        disabled: !retentionExpiry || !retentionBasis.trim() || !retentionPolicy.trim(),
      }"
      @ok="retention"
      ><p>仅在新合法依据与授权政策支持时延长，不自动扩大用途或权限。</p>
      <label>新到期时间<input v-model="retentionExpiry" type="datetime-local" /></label
      ><label>合法依据<Input v-model:value="retentionBasis" /></label
      ><label>政策版本<Input v-model:value="retentionPolicy" /></label></Modal
    ><Modal
      v-model:open="mergeOpen"
      title="确认合并来源"
      :confirm-loading="busy"
      :ok-button-props="{ disabled: !mergeSources.trim() || !mergeReason.trim() }"
      @ok="merge"
      ><p>主档不会扩大来源权限、用途或保留期。混合产物会过期；7天内可按来源撤销。</p>
      <label>来源候选人ID<Input v-model:value="mergeSources" /></label
      ><label>合并原因<Input v-model:value="mergeReason" /></label></Modal
    ><Modal
      v-model:open="deleteOpen"
      title="确认申请删除"
      :confirm-loading="busy"
      :ok-button-props="{ disabled: !deleteReason.trim() }"
      @ok="deletion"
      ><p>
        立即撤销普通可见性，并异步清理业务、索引、文件与缓存；依赖失败会显示阻塞，不冒充已删除。
      </p>
      <Input v-model:value="deleteReason" aria-label="删除原因"
    /></Modal>
    <section v-if="profile?.mergeId">
      <p>
        合并 {{ profile.mergeId }} · 可撤销至
        {{ profile.revocableUntil ? beijing(profile.revocableUntil) : '未记录' }}
      </p>
      <Input v-model:value="mergeReason" placeholder="撤销合并原因" /><Button
        :disabled="mergeVersion === undefined || !mergeReason.trim()"
        @click="revokeMerge"
        >撤销本次合并</Button
      >
    </section>
    <Modal
      v-model:open="contactOpen"
      title="确认查看联系方式"
      :confirm-loading="busy"
      :ok-button-props="{ disabled: !reason.trim() }"
      @ok="contact"
      ><p>仅在合法招聘用途下查看，操作会记录审计。</p>
      <Input v-model:value="reason" aria-label="查看原因" placeholder="填写查看原因"
    /></Modal>
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
