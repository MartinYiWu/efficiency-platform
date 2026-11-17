<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  agentOptions,
  createMemoryApi,
  fieldLabels,
  memoryAccessTokenKey,
  topAgentSchema,
  valueLabels,
  type MemoryScope,
  type TopAgent,
  type MemoryPreference,
} from '../../entities/memory';
import { useMemoryPreferences } from '../../features/memory-preferences/useMemoryPreferences';
import MemoryPreferenceForm from '../../features/memory-preferences/MemoryPreferenceForm.vue';
import MemoryDeletionPanel from '../../features/memory-preferences/MemoryDeletionPanel.vue';
import styles from './MemoryCenterPage.module.css';
const route = useRoute(),
  router = useRouter();
const token = inject(memoryAccessTokenKey, () => undefined);
const validAgent = computed(() => topAgentSchema.safeParse(route.query.topAgent ?? 'operations'));
const scope = computed<MemoryScope>(() => ({
  topAgent: validAgent.value.success ? validAgent.value.data : 'operations',
  ...(typeof route.query.sessionId === 'string' &&
  route.query.sessionId &&
  route.query.topAgent !== 'hr'
    ? { sessionId: route.query.sessionId }
    : {}),
}));
const authenticated = computed(() => validAgent.value.success && Boolean(token()));
const api = createMemoryApi(() => (authenticated.value ? token() : undefined));
const forgetTarget = ref<MemoryPreference>();
const authorizationVersion = ref(0);
function authorizationDenied() {
  forgetTarget.value = undefined;
  authorizationVersion.value++;
}
const {
  items,
  total,
  page,
  loading,
  saving,
  draftField,
  draftValue,
  editing,
  error,
  success,
  load,
  edit,
  reset,
  save,
  revoke,
  restore,
  clearPrivate,
} = useMemoryPreferences(
  scope,
  api,
  () => (authenticated.value ? token() : undefined),
  authorizationDenied,
);
function invalidateAuthorization() {
  clearPrivate();
  authorizationDenied();
}
const jobId = computed(() =>
  typeof route.query.jobId === 'string' ? route.query.jobId : undefined,
);
function revoked(itemId: string, acceptedJobId: string) {
  revoke(itemId);
  forgetTarget.value = undefined;
  if (route.query.jobId !== acceptedJobId)
    void router.replace({ query: { ...route.query, jobId: acceptedJobId } });
}
function restored(item: MemoryPreference) {
  restore(item.id);
  forgetTarget.value = undefined;
  void router.replace({ query: { ...route.query, jobId: undefined } });
  void load();
}
watch(
  [() => scope.value.topAgent, () => scope.value.sessionId, token],
  () => {
    forgetTarget.value = undefined;
  },
  { flush: 'sync' },
);
function switchAgent(topAgent: TopAgent) {
  void router.replace({ query: { topAgent } });
}
</script>
<template>
  <section class="ui-page" :class="styles.page">
    <header class="ui-header">
      <div>
        <h2>记忆中心</h2>
        <p>管理你明确设置的回复偏好，让协作更合心意。</p>
      </div>
      <a-tag color="blue">当前 Agent 私有</a-tag>
    </header>
    <div class="ui-card" :class="styles.scopeCard">
      <div :class="styles.toolbar">
        <div :class="styles.agentPicker">
          <label for="memory-agent">当前 Agent</label
          ><a-select
            id="memory-agent"
            :value="scope.topAgent"
            :options="agentOptions"
            @change="switchAgent"
          />
        </div>
        <a-button disabled title="跨 Agent 共享尚未开放">跨 Agent 共享</a-button>
      </div>
      <div :class="styles.boundaries">
        <span>同 Agent 跨会话可用</span><span>会话内容仅用于本次会话</span>
      </div>
      <p>
        只有已保存的偏好可在当前 Agent 的其他会话使用；当前聊天内容不会自动保存为偏好。跨 Agent
        共享尚未开放。
      </p>
      <p v-if="scope.topAgent === 'hr'">
        人事助手采用 TASK_ONLY：仅处理当前任务，不提供跨任务聊天历史。
      </p>
    </div>
    <a-alert
      v-if="!validAgent.success"
      type="error"
      message="不支持的 Agent，请重新选择"
      show-icon
    />
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <a-alert v-if="success" type="success" :message="success" show-icon />
    <MemoryDeletionPanel
      :scope="scope"
      :target="forgetTarget"
      :job-id="jobId"
      :authorization-version="authorizationVersion"
      @revoked="revoked"
      @restored="restored"
      @cleared="forgetTarget = undefined"
      @denied="invalidateAuthorization"
    />
    <div :class="styles.workspace">
      <div class="ui-card" :class="styles.listPanel">
        <div :class="styles.toolbar">
          <h3>
            已保存的偏好 <small>{{ total }}</small>
          </h3>
          <a-button :loading="loading" :disabled="saving || !authenticated" @click="load(page)"
            >重新加载</a-button
          >
        </div>
        <p v-if="loading" role="status">正在读取当前 Agent 的偏好…</p>
        <a-empty v-else-if="!items.length" description="当前没有可用偏好" />
        <div v-else :class="styles.tableScroll">
          <table :class="styles.table">
            <thead>
              <tr>
                <th>偏好</th>
                <th>来源与版本</th>
                <th>有效期</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.id">
                <td data-label="偏好">
                  <strong>{{ fieldLabels[item.fieldKey] }}</strong>
                  <div>{{ valueLabels[item.value] }}</div>
                </td>
                <td data-label="来源与版本">
                  用户明确设置
                  <div :class="styles.secondary">版本 {{ item.revision }}</div>
                </td>
                <td data-label="有效期">
                  {{
                    item.expiresAt
                      ? new Date(item.expiresAt).toLocaleString('zh-CN')
                      : '未设置截止时间'
                  }}
                </td>
                <td data-label="操作">
                  <a-space wrap
                    ><RouterLink
                      :to="{
                        path: `/ai-center/memories/${encodeURIComponent(item.id)}`,
                        query: { topAgent: scope.topAgent, sessionId: scope.sessionId },
                      }"
                      >详情与来源</RouterLink
                    ><a-button size="small" :disabled="saving" @click="edit(item)">更正</a-button
                    ><a-button size="small" disabled title="功能暂未开放">暂停</a-button
                    ><a-button
                      size="small"
                      danger
                      :disabled="saving || !authenticated"
                      @click="forgetTarget = item"
                      >忘记</a-button
                    ></a-space
                  >
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <a-pagination
          v-if="total > 20"
          :current="page"
          :total="total"
          :page-size="20"
          :show-size-changer="false"
          :disabled="loading || saving"
          @change="load"
        />
        <p :class="styles.secondary">
          暂停功能暂未开放。忘记后将停止自动记住，清理状态以任务结果为准。
        </p>
      </div>
      <aside class="ui-card" :class="styles.formPanel">
        <h3>{{ editing ? '更正偏好' : '设置私有偏好' }}</h3>
        <p v-if="editing">基于版本 {{ editing.revision }} 更正；冲突时保留当前值和草稿。</p>
        <p v-else>主动选择并保存，即表示你确认此项偏好。</p>
        <MemoryPreferenceForm
          v-model:field="draftField"
          v-model:value="draftValue"
          :editing="Boolean(editing)"
          :saving="saving"
          :disabled="!authenticated || loading"
          @save="save"
          @cancel="reset"
        />
      </aside>
    </div>
  </section>
</template>
