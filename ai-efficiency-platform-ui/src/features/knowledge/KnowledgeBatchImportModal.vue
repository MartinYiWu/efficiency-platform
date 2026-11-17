<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue';
import { message } from 'ant-design-vue';
import type { UploadFile } from 'ant-design-vue';
import type { IngestBatch, KnowledgeDirectory } from '../../entities/knowledge/model';
import { getImportBatch, retryImportItem, uploadDocuments } from './api';
const props = defineProps<{
  open: boolean;
  baseId: string;
  directories: KnowledgeDirectory[];
  initialBatchId?: string;
}>();
const emit = defineEmits<{ close: []; changed: [] }>();
const terminal = new Set(['SUCCEEDED', 'PARTIAL_FAILED', 'FAILED']);
const files = ref<UploadFile[]>([]);
const directoryId = ref<string>();
const batch = ref<IngestBatch>();
const loading = ref(false);
let timer: ReturnType<typeof setInterval> | undefined;
let sequence = 0;
const percent = computed(() =>
  batch.value
    ? Math.round(
        ((batch.value.succeededCount + batch.value.failedCount) /
          Math.max(batch.value.totalCount, 1)) *
          100,
      )
    : 0,
);
async function refresh(id: string) {
  const current = sequence;
  try {
    const next = await getImportBatch(id);
    if (current !== sequence) return;
    batch.value = next;
    if (terminal.has(next.status)) emit('changed');
  } catch (error) {
    if (current === sequence) message.error(error instanceof Error ? error.message : '加载失败');
  }
}
watch(
  () => [props.open, props.initialBatchId] as const,
  ([open, id]) => {
    sequence++;
    if (open && id) void refresh(id);
  },
  { immediate: true },
);
watch(
  () => [props.open, batch.value?.id, batch.value?.status] as const,
  ([open, id, status]) => {
    if (timer) clearInterval(timer);
    if (open && id && status && !terminal.has(status))
      timer = setInterval(() => void refresh(id), 3000);
  },
  { immediate: true },
);
onUnmounted(() => {
  sequence++;
  if (timer) clearInterval(timer);
});
async function submit() {
  const selected = files.value.flatMap((file) =>
    file.originFileObj ? [file.originFileObj as File] : [],
  );
  if (selected.length < 2) {
    message.warning('批量导入至少选择 2 个文件');
    return;
  }
  loading.value = true;
  try {
    batch.value = await uploadDocuments(props.baseId, selected, directoryId.value);
    emit('changed');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '导入失败');
  } finally {
    loading.value = false;
  }
}
async function retry(id: string) {
  try {
    await retryImportItem(id);
    if (batch.value) await refresh(batch.value.id);
  } catch (error) {
    message.error(error instanceof Error ? error.message : '重试失败');
  }
}
const columns = [
  { title: '文件', dataIndex: 'fileId' },
  { title: '状态', dataIndex: 'status' },
  { title: '错误', dataIndex: 'errorMessage' },
  { title: '操作', key: 'action' },
];
</script>
<template>
  <a-modal title="批量导入" :open="open" :width="760" @cancel="emit('close')">
    <template #footer
      ><a-button v-if="batch" @click="emit('close')">关闭</a-button
      ><a-button v-else type="primary" :loading="loading" @click="submit"
        >开始导入</a-button
      ></template
    >
    <a-space v-if="!batch" direction="vertical" :size="16" style="width: 100%">
      <a-select
        v-model:value="directoryId"
        aria-label="目标目录"
        allow-clear
        placeholder="选择目录（可选）"
        style="width: 100%"
        :options="directories.map((item) => ({ label: item.path, value: item.id }))"
      />
      <a-upload-dragger
        multiple
        :before-upload="() => false"
        :file-list="files"
        accept=".pdf,.doc,.docx,.txt,.md"
        @change="files = $event.fileList"
        ><p>选择多个文件批量导入</p></a-upload-dragger
      >
    </a-space>
    <a-space v-else direction="vertical" :size="16" style="width: 100%">
      <a-progress
        :percent="percent"
        :status="batch.status === 'FAILED' ? 'exception' : undefined"
      />
      <div>
        成功 {{ batch.succeededCount }}，失败 {{ batch.failedCount }}，共 {{ batch.totalCount }}
      </div>
      <a-table
        row-key="id"
        :pagination="false"
        :data-source="batch.items"
        :columns="columns"
        :scroll="{ x: 580 }"
      >
        <template #bodyCell="{ column, record, text }"
          ><a-button
            v-if="column.key === 'action' && record.status === 'FAILED'"
            size="small"
            @click="retry(record.id)"
            >重试</a-button
          ><template v-else-if="column.key !== 'action'">{{ text ?? '-' }}</template></template
        >
      </a-table>
    </a-space>
  </a-modal>
</template>
