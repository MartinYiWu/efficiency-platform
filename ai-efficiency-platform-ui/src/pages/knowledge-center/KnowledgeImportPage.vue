<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { KnowledgeBase, KnowledgeDirectory } from '../../entities/knowledge/model';
import { getKnowledgeBase, listDirectories } from '../../features/knowledge/api';
import KnowledgeBatchImportModal from '../../features/knowledge/KnowledgeBatchImportModal.vue';
import styles from './KnowledgeCenter.module.css';
const route = useRoute();
const router = useRouter();
const baseId = computed(() => String(route.params.baseId ?? ''));
const base = ref<KnowledgeBase>();
const directories = ref<KnowledgeDirectory[]>([]);
const open = ref(false);
const error = ref('');
let sequence = 0;
async function load() {
  const current = ++sequence;
  if (!baseId.value) return;
  error.value = '';
  try {
    const [nextBase, nextDirectories] = await Promise.all([
      getKnowledgeBase(baseId.value),
      listDirectories(baseId.value),
    ]);
    if (current === sequence) {
      base.value = nextBase;
      directories.value = nextDirectories;
    }
  } catch (e) {
    if (current === sequence) {
      error.value = e instanceof Error ? e.message : '加载失败';
      message.error(error.value);
    }
  }
}
watch(baseId, load, { immediate: true });
onUnmounted(() => {
  sequence++;
});
function back() {
  void router.push(`/knowledge-center/knowledge-bases/${baseId.value}`);
}
</script>
<template>
  <section :class="[styles.page, 'ui-page']">
    <a-alert v-if="error" type="error" :message="error" show-icon
      ><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert
    >
    <a-empty v-if="!baseId" description="缺少知识库标识" /><a-empty
      v-else-if="!base"
      description="正在加载知识库"
    />
    <template v-else>
      <header :class="[styles.header, 'ui-header']">
        <div>
          <a-button type="link" :class="styles.link" @click="back">返回知识库</a-button>
          <h2>批量导入</h2>
          <p>{{ base.name }}</p>
        </div>
        <a-button type="primary" :disabled="base.status !== 'ACTIVE'" @click="open = true"
          >选择文件并导入</a-button
        >
      </header>
      <a-alert
        v-if="base.status !== 'ACTIVE'"
        type="warning"
        show-icon
        message="知识库未启用，请返回知识库启用后再批量导入。"
        ><template #action><a-button @click="back">返回知识库启用</a-button></template></a-alert
      >
      <section :class="styles.section" aria-labelledby="import-files">
        <div :class="styles.sectionHeading"><h3 id="import-files">目录与文件</h3></div>
        <p>
          选择目标目录并上传至少 2 个文件，支持 PDF、Word、TXT 和
          Markdown。单个文档请在知识库中使用“上传文档”。
        </p>
      </section>
      <section :class="styles.section" aria-labelledby="import-tasks">
        <div :class="styles.sectionHeading"><h3 id="import-tasks">处理任务</h3></div>
        <p>提交后在导入窗口查看本批文件的进度、结果与失败原因，并可重试失败项。</p>
        <a-empty description="选择文件并提交后显示本次导入进度" />
      </section>
      <KnowledgeBatchImportModal
        v-if="open"
        :open="true"
        :base-id="baseId"
        :directories="directories"
        @close="open = false"
      />
    </template>
  </section>
</template>
<style scoped>
h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--v1-text);
}
h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--v1-text);
}
p {
  color: var(--v1-text-muted);
  margin: 0;
}
</style>
