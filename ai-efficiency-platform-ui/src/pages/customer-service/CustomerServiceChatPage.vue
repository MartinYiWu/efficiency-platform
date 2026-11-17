<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import {
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  HistoryOutlined,
  PlusOutlined,
  ReadOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons-vue';
import type { Citation, Conversation } from '../../entities/customer-service/model';
import CitationDrawer from '../../features/customer-service-chat/CitationDrawer.vue';
import CustomerServiceAnswer from '../../features/customer-service-chat/CustomerServiceAnswer.vue';
import CustomerServiceProgress from '../../features/customer-service-chat/CustomerServiceProgress.vue';
import FeedbackControl from '../../features/customer-service-chat/FeedbackControl.vue';
import { useCustomerServiceChat } from '../../features/customer-service-chat/useCustomerServiceChat';
import styles from './CustomerServiceChatPage.module.css';

const {
  state,
  busy,
  send,
  cancel,
  selectConversation,
  newConversation,
  removeConversation,
  renameConversation,
} = useCustomerServiceChat();
const draft = ref('');
const citation = ref<Citation>();
const historyOpen = ref(false);
const renameTarget = ref<Conversation>();
const renameError = ref<string>();
const renaming = ref(false);
const renameTitle = ref('');
const viewport = ref<HTMLDivElement>();
const following = ref(true);
const readingConversation = ref<string>();
const showLatest = computed(() => readingConversation.value === (state.value.conversationId ?? ''));
function scrollToLatest() {
  following.value = true;
  readingConversation.value = undefined;
  viewport.value?.scrollTo({ top: viewport.value.scrollHeight, behavior: 'auto' });
}
watch(
  () => state.value.conversationId,
  async () => {
    following.value = true;
    await nextTick();
    scrollToLatest();
  },
);
watch(
  () => [state.value.messages, state.value.progressByRun],
  async () => {
    await nextTick();
    if (following.value) scrollToLatest();
  },
);
let observer: ResizeObserver | undefined;
onMounted(() => {
  if (viewport.value) {
    observer = new ResizeObserver(() => {
      if (following.value) scrollToLatest();
    });
    observer.observe(viewport.value);
  }
});
onBeforeUnmount(() => observer?.disconnect());
function onScroll() {
  const element = viewport.value;
  if (!element) return;
  following.value = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
  readingConversation.value = following.value ? undefined : (state.value.conversationId ?? '');
}
function submit() {
  const value = draft.value.trim();
  if (!value || busy.value) return;
  scrollToLatest();
  draft.value = '';
  void send(value);
}
function onEnter(event: KeyboardEvent) {
  if (!event.shiftKey && !event.isComposing) {
    event.preventDefault();
    submit();
  }
}
function openRename(item: Conversation) {
  renameTarget.value = item;
  renameTitle.value = item.title;
  renameError.value = undefined;
}
async function saveRename() {
  if (!renameTitle.value.trim()) {
    renameError.value = '请输入会话名称';
    return;
  }
  if (renameTitle.value.length > 80) {
    renameError.value = '会话名称不能超过80个字符';
    return;
  }
  if (!renameTarget.value || renaming.value) return;
  renaming.value = true;
  renameError.value = undefined;
  try {
    await renameConversation(renameTarget.value.id, renameTitle.value.trim());
    renameTarget.value = undefined;
  } catch (error) {
    renameError.value = error instanceof Error ? error.message : '重命名会话失败';
  } finally {
    renaming.value = false;
  }
}
async function select(id: string) {
  await selectConversation(id);
  historyOpen.value = false;
}
</script>

<template>
  <section :class="styles.page">
    <aside :class="styles.sidebar">
      <div :class="styles.sidebarTitle">智能客服</div>
      <a-button block type="primary" :disabled="busy" @click="newConversation"
        ><template #icon><PlusOutlined /></template>新建对话</a-button
      >
      <div :class="styles.historyTitle">
        历史会话 <span>{{ state.conversations.length }}</span>
      </div>
      <nav :class="styles.historyList" aria-label="历史会话">
        <div
          v-for="item in state.conversations"
          :key="item.id"
          :class="[
            styles.conversationRow,
            item.id === state.conversationId && styles.conversationActive,
          ]"
        >
          <button
            type="button"
            :class="styles.conversation"
            :disabled="busy"
            :title="item.title || '新对话'"
            @click="select(item.id)"
          >
            {{ item.title || '新对话' }}</button
          ><a-button
            type="text"
            size="small"
            :class="styles.renameButton"
            :aria-label="`重命名会话：${item.title || '新对话'}`"
            @click="openRename(item)"
            ><template #icon><EditOutlined /></template></a-button
          ><a-popconfirm
            title="删除这条会话？"
            description="删除后将从历史列表移除。"
            ok-text="删除"
            cancel-text="取消"
            :ok-button-props="{ danger: true }"
            @confirm="removeConversation(item.id)"
            ><a-button
              type="text"
              size="small"
              :class="styles.deleteButton"
              :disabled="busy"
              :aria-label="`删除会话：${item.title || '新对话'}`"
              ><template #icon><DeleteOutlined /></template></a-button
          ></a-popconfirm>
        </div>
      </nav>
    </aside>
    <main :class="styles.chat">
      <header :class="styles.chatHeader">
        <span :class="styles.headerAvatar"><ReadOutlined /></span>
        <div>
          <h1 class="chat-title">AI 智能客服</h1>
          <span class="chat-subtitle">基于公司知识，提供可追溯的回答</span>
          <RouterLink
            style="display: block; font-size: 12px"
            :to="{
              path: '/ai-center/memories',
              query: { topAgent: 'customer-service', sessionId: state.conversationId || undefined },
            }"
            >当前 Agent 私有偏好</RouterLink
          >
        </div>
        <a-button
          :class="styles.mobileHistoryButton"
          aria-label="历史会话"
          @click="historyOpen = true"
          ><template #icon><HistoryOutlined /></template></a-button
        ><a-button
          :class="styles.mobileHistoryButton"
          aria-label="新建对话"
          :disabled="busy"
          @click="newConversation"
          ><template #icon><PlusOutlined /></template
        ></a-button>
      </header>
      <div :class="styles.messageArea">
        <div
          ref="viewport"
          :class="styles.messages"
          role="log"
          aria-label="智能客服对话消息"
          aria-live="polite"
          @scroll="onScroll"
        >
          <div v-if="!state.messages.length" :class="styles.empty">
            <span :class="styles.emptyIcon"><ReadOutlined /></span>
            <h2>有什么可以帮你？</h2>
            <p>你可以询问公司制度、业务流程或常见工作问题</p>
          </div>
          <article
            v-for="item in state.messages"
            :key="item.message.id"
            :class="[styles.row, item.message.role === 'USER' && styles.userRow]"
          >
            <span
              v-if="item.message.role === 'ASSISTANT'"
              :class="styles.assistantAvatar"
              aria-hidden="true"
              ><ReadOutlined
            /></span>
            <div :class="styles.messageContent">
              <div :class="[styles.bubble, item.message.role === 'USER' && styles.userBubble]">
                <template v-if="item.message.role === 'USER'">{{ item.message.content }}</template
                ><template v-else
                  ><CustomerServiceProgress
                    :steps="
                      item.message.runId ? (state.progressByRun[item.message.runId] ?? []) : []
                    "
                    :status="
                      item.message.status === 'COMPLETED' ? 'SUCCEEDED' : item.message.status
                    "
                    :pending="
                      state.status === 'SUBMITTING' &&
                      item.message.id.startsWith('local-assistant-')
                    " /><CustomerServiceAnswer
                    :content="item.message.content"
                    :mode="item.message.answerMode"
                    :citations="item.citations"
                    :streaming="
                      item.message.status === 'STREAMING' &&
                      !!(
                        item.message.runId &&
                        state.progressByRun[item.message.runId]?.some(
                          (step) => step.stage === 'answer',
                        )
                      )
                    "
                    @citation="citation = $event"
                /></template>
              </div>
              <FeedbackControl
                v-if="
                  item.message.role === 'ASSISTANT' &&
                  item.message.status === 'COMPLETED' &&
                  !item.message.id.startsWith('local-')
                "
                :message-id="item.message.id"
              />
            </div>
          </article>
        </div>
        <a-button
          v-if="showLatest"
          :class="styles.latestButton"
          aria-label="回到最新消息"
          @click="scrollToLatest"
          ><template #icon><DownOutlined /></template>回到最新消息</a-button
        >
      </div>
      <div v-if="state.error" :class="styles.error" role="alert">
        {{ state.error }}{{ state.traceId ? ` · Trace ID: ${state.traceId}` : '' }}
      </div>
      <div :class="styles.composer" role="form" aria-label="发送消息">
        <div :class="styles.composerBox">
          <a-textarea
            v-model:value="draft"
            aria-label="输入问题"
            :auto-size="{ minRows: 1, maxRows: 5 }"
            placeholder="输入你的问题…"
            @press-enter="onEnter"
          />
          <div :class="styles.composerActions">
            <span>Enter 发送 · Shift + Enter 换行</span
            ><a-button v-if="busy" danger @click="cancel"
              ><template #icon><StopOutlined /></template>停止</a-button
            ><a-button v-else type="primary" :disabled="!draft.trim()" @click="submit"
              ><template #icon><SendOutlined /></template>发送</a-button
            >
          </div>
        </div>
      </div>
    </main>
    <a-drawer
      title="历史会话"
      role="dialog"
      aria-label="历史会话"
      :aria-modal="historyOpen"
      placement="left"
      :width="300"
      :open="historyOpen"
      @close="historyOpen = false"
      ><div v-if="historyOpen" role="dialog" aria-label="历史会话" aria-modal="true">
        <a-button
          block
          type="primary"
          :disabled="busy"
          @click="
            newConversation();
            historyOpen = false;
          "
          >新建对话</a-button
        >
        <nav :class="styles.mobileHistoryList" aria-label="移动端历史会话">
          <div v-for="item in state.conversations" :key="item.id" :class="styles.conversationRow">
            <button :class="styles.conversation" :disabled="busy" @click="select(item.id)">
              {{ item.title || '新对话' }}</button
            ><a-button
              type="text"
              :aria-label="`重命名会话：${item.title || '新对话'}`"
              @click="openRename(item)"
              ><template #icon><EditOutlined /></template></a-button
            ><a-popconfirm title="删除这条会话？" @confirm="removeConversation(item.id)"
              ><a-button
                type="text"
                danger
                :disabled="busy"
                :aria-label="`删除会话：${item.title || '新对话'}`"
                ><template #icon><DeleteOutlined /></template></a-button
            ></a-popconfirm>
          </div>
        </nav></div
    ></a-drawer>
    <a-modal
      title="重命名会话"
      :open="!!renameTarget"
      ok-text="保存"
      cancel-text="取消"
      :confirm-loading="renaming"
      :cancel-button-props="{ disabled: renaming }"
      :closable="!renaming"
      @ok="saveRename"
      @cancel="!renaming && (renameTarget = undefined)"
      ><a-form layout="vertical"
        ><a-form-item label="会话名称" html-for="conversation-title"
          ><a-input
            id="conversation-title"
            aria-label="会话名称"
            v-model:value="renameTitle"
            :maxlength="80"
            show-count
            :disabled="renaming"
            @press-enter="saveRename"
            @change="renameError = undefined"
        /></a-form-item>
        <div v-if="renameError" :class="styles.renameError" role="alert">
          {{ renameError }}
        </div></a-form
      ></a-modal
    ><CitationDrawer :citation="citation" @close="citation = undefined" />
  </section>
</template>
<style scoped>
.chat-title {
  margin: 0 0 2px;
  font-size: 17px;
}
.chat-subtitle {
  color: var(--text-tertiary);
  font-size: 12px;
}
</style>
