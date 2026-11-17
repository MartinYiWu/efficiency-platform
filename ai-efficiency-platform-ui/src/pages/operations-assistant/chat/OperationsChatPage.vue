<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import {
  ArrowLeftOutlined,
  EditOutlined,
  SendOutlined,
  StopOutlined,
  UserOutlined,
} from '@ant-design/icons-vue';
import OperationProgress from '../../../features/operation-chat/OperationProgress.vue';
import StreamingAssistantContent from '../../../features/operation-chat/StreamingAssistantContent.vue';
import { useOperationChat } from '../../../features/operation-chat/useOperationChat';
import OperationDelivery from '../../../widgets/operation-delivery/OperationDelivery.vue';
import styles from './OperationsChatPage.module.css';
const router = useRouter();
const draft = ref('');
const viewport = ref<HTMLDivElement>();
const composer = ref<HTMLElement>();
const followUpFocus = ref<'awaiting-control' | 'stop-focused' | null>(null);
const { state, sendMessage, cancel, isBusy, artifacts, artifactError, baseUrl, isRestoring } =
  useOperationChat();
const currentAssistant = computed(() =>
  state.value.messages.at(-1)?.role === 'assistant' ? state.value.messages.at(-1) : null,
);
const activelyStreaming = computed(() => ['submitting', 'streaming'].includes(state.value.status));
const showThinking = computed(
  () => activelyStreaming.value && !currentAssistant.value?.content.trim(),
);
function displayMode(id: string): 'typing' | 'complete' | 'frozen' {
  const item = state.value.messages.find((item) => item.id === id);
  if (item?.frozen) return 'frozen';
  if (currentAssistant.value?.id !== id) return 'complete';
  return activelyStreaming.value
    ? 'typing'
    : ['succeeded', 'degraded_succeeded'].includes(state.value.status)
      ? 'complete'
      : 'frozen';
}
function submit() {
  const value = draft.value.trim();
  if (!value || isBusy.value) return;
  draft.value = '';
  void sendMessage(value);
}
function openMemoryPreferences() {
  const sessionId = new URLSearchParams(window.location.search).get('conversationId') || undefined;
  void router.push({ path: '/ai-center/memories', query: { topAgent: 'operations', sessionId } });
}
function onEnter(event: KeyboardEvent) {
  if (!event.shiftKey && !event.isComposing) {
    event.preventDefault();
    submit();
  }
}
function followUp(value: string) {
  followUpFocus.value = 'awaiting-control';
  void sendMessage(value);
}
watch(
  [
    isBusy,
    () => state.value.deliverableSets.length,
    () => state.value.error,
    () => state.value.status,
  ],
  async () => {
    if (!followUpFocus.value) return;
    await nextTick();
    if (isBusy.value) {
      if (followUpFocus.value === 'stop-focused') return;
      const stop = composer.value?.querySelector<HTMLButtonElement>(
        'button[aria-label="停止生成"]',
      );
      if (stop) {
        stop.focus();
        followUpFocus.value = 'stop-focused';
      }
      return;
    }
    if (followUpFocus.value === 'stop-focused' && document.activeElement !== document.body) {
      followUpFocus.value = null;
      return;
    }
    const deliveries = viewport.value?.querySelectorAll<HTMLElement>(
      'section[aria-label="运营交付"]',
    );
    const latest = deliveries?.item((deliveries?.length ?? 0) - 1);
    const target =
      latest?.querySelector<HTMLElement>('button:not(:disabled)') ??
      composer.value?.querySelector<HTMLTextAreaElement>('textarea');
    target?.focus();
    followUpFocus.value = null;
  },
);
</script>

<template>
  <section :class="styles.page" aria-labelledby="operations-chat-title">
    <header :class="styles.header">
      <a-button
        type="text"
        :class="styles.backButton"
        aria-label="返回上一页"
        @click="router.back()"
        ><template #icon><ArrowLeftOutlined /></template></a-button
      ><a-avatar :class="styles.assistantAvatar" :size="44"
        ><template #icon><EditOutlined /></template
      ></a-avatar>
      <div>
        <h1 id="operations-chat-title" :class="styles.title">AI 内容运营助手</h1>
        <span :class="styles.subtitle">协助处理选题、内容创作、活动策划和复盘</span>
        <a-button
          type="link"
          style="display: block; height: auto; padding: 0; font-size: 12px"
          @click="openMemoryPreferences"
          >当前 Agent 私有偏好</a-button
        >
      </div>
    </header>
    <div
      ref="viewport"
      :class="styles.messageViewport"
      role="log"
      aria-label="运营助手对话消息"
      aria-live="polite"
    >
      <div :class="styles.messageList">
        <div :class="styles.messageGroup">
          <time>现在</time>
          <div :class="styles.assistantMessageRow">
            <a-avatar :class="styles.messageAvatar" :size="32"
              ><template #icon><EditOutlined /></template
            ></a-avatar>
            <div :class="styles.assistantBubble">
              你好，我是 AI
              内容运营助手。请告诉我目标、渠道和受众，我会协助梳理可直接使用的运营内容。
            </div>
          </div>
        </div>
        <div v-for="item in state.messages" :key="item.id" :class="styles.messageGroup">
          <time>{{
            new Intl.DateTimeFormat('zh-CN', {
              hour: '2-digit',
              minute: '2-digit',
              hour12: false,
            }).format(item.createdAt)
          }}</time>
          <div :class="item.role === 'user' ? styles.userMessageRow : styles.assistantMessageRow">
            <a-avatar v-if="item.role === 'assistant'" :class="styles.messageAvatar" :size="32"
              ><template #icon><EditOutlined /></template
            ></a-avatar>
            <div :class="item.role === 'user' ? styles.userBubble : styles.assistantBubble">
              <StreamingAssistantContent
                v-if="item.role === 'assistant'"
                :content="item.content"
                :mode="displayMode(item.id)"
              /><template v-else>{{ item.content }}</template>
            </div>
            <a-avatar v-if="item.role === 'user'" :class="styles.userAvatar" :size="34"
              ><template #icon><UserOutlined /></template
            ></a-avatar>
          </div>
        </div>
        <div v-if="showThinking" :class="styles.messageGroup" aria-label="助手正在思考">
          <div :class="styles.assistantMessageRow">
            <a-avatar :class="styles.messageAvatar" :size="32"
              ><template #icon><EditOutlined /></template
            ></a-avatar>
            <div :class="[styles.assistantBubble, styles.thinkingIndicator]">
              <span :class="styles.thinkingDot" /><span :class="styles.thinkingDot" /><span
                :class="styles.thinkingDot"
              />
            </div>
          </div>
        </div>
        <a-card v-if="state.clarification" size="small" title="需要补充信息" aria-label="澄清问题"
          ><p>{{ state.clarification.question }}</p>
          <span v-if="state.clarification.fields.length"
            >请补充：{{ state.clarification.fields.join('、') }}</span
          ></a-card
        >
        <div v-if="state.visiblePhase && isBusy" :class="styles.deliveryProgress">
          <OperationProgress :value="state.visiblePhase" />
        </div>
        <OperationDelivery
          v-for="(set, index) in state.deliverableSets"
          :key="`${set.contract_version}-${index}`"
          :value="set"
          :artifacts="artifacts"
          :base-url="baseUrl"
          @submit-next-action="followUp"
        /><a-typography-text v-if="state.error" type="danger" role="alert">{{
          state.error
        }}</a-typography-text
        ><a-typography-text v-if="artifactError" type="danger" role="alert">{{
          artifactError
        }}</a-typography-text
        ><span v-if="state.status === 'cancelling'">正在停止当前任务…</span
        ><span v-if="isRestoring">正在恢复会话…</span>
      </div>
    </div>
    <footer ref="composer" :class="styles.composer" aria-label="消息输入">
      <a-textarea
        v-model:value="draft"
        aria-label="输入消息"
        :auto-size="{ minRows: 1, maxRows: 4 }"
        placeholder="输入你想咨询的内容运营问题…"
        @press-enter="onEnter"
      /><a-button v-if="isBusy" danger aria-label="停止生成" @click="cancel"
        ><template #icon><StopOutlined /></template>停止</a-button
      ><a-button
        v-else
        type="primary"
        aria-label="发送消息"
        :disabled="!draft.trim()"
        @click="submit"
        ><template #icon><SendOutlined /></template>发送</a-button
      >
    </footer>
  </section>
</template>
