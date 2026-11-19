<script setup lang="ts">
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import MemoryDeletionPanel from '../../features/memory-preferences/MemoryDeletionPanel.vue';
import ContextUsagePanel from '../../features/memory-context/ContextUsagePanel.vue';
import {
  createMemoryApi,
  fieldLabels,
  memoryAccessTokenKey,
  memoryErrorMessage,
  MemoryApiError,
  topAgentSchema,
  valueLabels,
  type MemoryDetail,
  type MemoryScope,
  type MemoryPreference,
} from '../../entities/memory';
import styles from './MemoryCenterPage.module.css';
const route = useRoute(),
  router = useRouter(),
  token = inject(memoryAccessTokenKey, () => undefined),
  api = createMemoryApi(token);
const detail = ref<MemoryDetail>(),
  error = ref(''),
  loading = ref(false);
const forgetTarget = ref<MemoryPreference>();
const authorizationVersion = ref(0);
const jobId = computed(() =>
  typeof route.query.jobId === 'string' ? route.query.jobId : undefined,
);
const scope = computed<MemoryScope | undefined>(() => {
  const agent = topAgentSchema.safeParse(route.query.topAgent);
  return agent.success
    ? {
        topAgent: agent.data,
        ...(agent.data !== 'hr' &&
        typeof route.query.sessionId === 'string' &&
        route.query.sessionId
          ? { sessionId: route.query.sessionId }
          : {}),
      }
    : undefined;
});
let generation = 0,
  controller: AbortController | undefined;
async function load() {
  controller?.abort();
  controller = new AbortController();
  const current = ++generation;
  detail.value = undefined;
  error.value = '';
  loading.value = true;
  if (!scope.value || typeof route.params.id !== 'string') {
    error.value = '记忆地址不完整或 Agent 不受支持';
    loading.value = false;
    return;
  }
  try {
    const result = await api.detail(route.params.id, scope.value, controller.signal);
    if (current === generation) {
      if (result.preference.topAgent !== scope.value.topAgent) throw new Error('Scope mismatch');
      detail.value = result;
    }
  } catch (reason) {
    if (current === generation) {
      if (reason instanceof MemoryApiError && [401, 403, 404].includes(reason.status))
        invalidateAuthorization();
      error.value = memoryErrorMessage(reason);
    }
  } finally {
    if (current === generation) loading.value = false;
  }
}
function clearPrivate() {
  generation++;
  controller?.abort();
  detail.value = undefined;
  forgetTarget.value = undefined;
  loading.value = false;
}
function invalidateAuthorization() {
  clearPrivate();
  authorizationVersion.value++;
}
function revoked(_itemId: string, acceptedJobId: string) {
  clearPrivate();
  if (route.query.jobId !== acceptedJobId)
    void router.replace({ query: { ...route.query, jobId: acceptedJobId } });
}
function restored() {
  void router.replace({ query: { ...route.query, jobId: undefined } });
  void load();
}
watch(
  () => [route.params.id, scope.value?.topAgent, scope.value?.sessionId, token()],
  () => {
    forgetTarget.value = undefined;
    if (!jobId.value) void load();
    else clearPrivate();
  },
  { immediate: true, flush: 'sync' },
);
onBeforeUnmount(() => {
  generation++;
  controller?.abort();
});
</script>
<template>
  <section class="ui-page" :class="styles.page">
    <header class="ui-header">
      <div>
        <RouterLink
          :to="{
            path: '/ai-center/memories',
            query: { topAgent: scope?.topAgent, sessionId: scope?.sessionId },
          }"
          >返回记忆中心</RouterLink
        >
        <h2>偏好详情</h2>
        <p>当前 Agent 私有 · 同 Agent 跨会话可用</p>
      </div>
    </header>
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <ContextUsagePanel
      v-if="scope && scope.topAgent !== 'hr'"
      :top-agent="scope.topAgent"
      :session-id="scope.sessionId"
    />
    <p v-if="loading" role="status">正在读取偏好详情…</p>
    <MemoryDeletionPanel
      v-if="scope"
      :scope="scope"
      :target="forgetTarget"
      :job-id="jobId"
      :authorization-version="authorizationVersion"
      @revoked="revoked"
      @restored="restored"
      @cleared="forgetTarget = undefined"
      @denied="invalidateAuthorization"
    />
    <div v-if="detail" class="ui-card" :class="styles.detailPanel">
      <h3>{{ fieldLabels[detail.preference.fieldKey] }}</h3>
      <p :class="styles.value">{{ valueLabels[detail.preference.value] }}</p>
      <dl :class="styles.facts">
        <dt>当前版本</dt>
        <dd>{{ detail.preference.revision }}</dd>
        <dt>来源</dt>
        <dd>用户明确设置</dd>
        <dt>来源记录</dt>
        <dd>{{ detail.preference.sourceRef }}</dd>
        <dt>有效期</dt>
        <dd>
          {{
            detail.preference.expiresAt
              ? new Date(detail.preference.expiresAt).toLocaleString('zh-CN')
              : '未设置截止时间'
          }}
        </dd>
      </dl>
      <a-space wrap
        ><RouterLink
          :to="{
            path: '/ai-center/memories',
            query: { topAgent: scope?.topAgent, sessionId: scope?.sessionId },
          }"
          >返回列表更正</RouterLink
        ><a-button disabled title="功能暂未开放">暂停</a-button
        ><a-button danger :disabled="!token()" @click="forgetTarget = detail.preference"
          >忘记</a-button
        ></a-space
      >
      <p :class="styles.secondary">
        来源仅显示你的安全决策记录，不读取其他会话原文。暂停功能暂未开放。
      </p>
      <h3>版本记录</h3>
      <a-empty v-if="!detail.history.length" description="暂无可显示的版本记录" />
      <ol v-else :class="styles.history">
        <li v-for="version in detail.history" :key="version.versionId">
          <strong>{{ valueLabels[version.value] }}</strong
          ><a-tag>{{ version.status === 'ACTIVE' ? '当前生效' : '已替代' }}</a-tag>
          <p>用户明确设置 · 来源记录 {{ version.sourceRef }}</p>
          <p>
            有效期：{{
              version.expiresAt
                ? new Date(version.expiresAt).toLocaleString('zh-CN')
                : '未设置截止时间'
            }}
          </p>
        </li>
      </ol>
    </div>
    <a-button v-if="error && token()" @click="load">重试</a-button>
  </section>
</template>
