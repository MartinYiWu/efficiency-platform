<script setup lang="ts">
import { ref } from 'vue';
import { message } from 'ant-design-vue';
import type { UploadFile } from 'ant-design-vue';
import type { KnowledgeDirectory } from '../../entities/knowledge/model';
import { uploadDocuments } from './api';
import EvidenceModeSelect, { type EvidenceMode } from './EvidenceModeSelect.vue';
const props = defineProps<{
  open: boolean;
  baseId: string;
  knowledgeType?: string;
  directories: KnowledgeDirectory[];
}>();
const emit = defineEmits<{ close: []; submitted: [batchId: string] }>();
const files = ref<UploadFile[]>([]);
const directoryId = ref<string>();
const evidenceMode = ref<EvidenceMode>('FULL_ONLY');
const submitting = ref(false);
async function submit() {
  const selected = files.value.flatMap((file) =>
    file.originFileObj ? [file.originFileObj as File] : [],
  );
  if (selected.length !== 1) {
    message.warning('请选择 1 个文件');
    return;
  }
  submitting.value = true;
  try {
    const allowed = ['PRODUCT_DOCUMENTATION', 'TECHNICAL_DOCUMENTATION'].includes(
      props.knowledgeType ?? '',
    );
    const batch = await uploadDocuments(
      props.baseId,
      selected,
      directoryId.value,
      allowed ? evidenceMode.value : 'FULL_ONLY',
    );
    message.success('文件已提交处理');
    emit('submitted', batch.id);
    files.value = [];
    emit('close');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '上传失败');
  } finally {
    submitting.value = false;
  }
}
</script>
<template>
  <a-drawer title="上传文档" :open="open" width="min(480px, 100vw)" @close="emit('close')">
    <template #extra
      ><a-button type="primary" :loading="submitting" @click="submit">开始处理</a-button></template
    >
    <a-space direction="vertical" :size="20" style="width: 100%">
      <EvidenceModeSelect v-model:value="evidenceMode" :knowledge-type="knowledgeType" />
      <a-select
        v-model:value="directoryId"
        aria-label="目标目录"
        allow-clear
        placeholder="选择目录（可选）"
        style="width: 100%"
        :options="directories.map((item) => ({ label: item.path, value: item.id }))"
      />
      <a-upload-dragger
        :before-upload="() => false"
        :max-count="1"
        :file-list="files"
        accept=".pdf,.doc,.docx,.txt,.md"
        @change="files = $event.fileList"
      >
        <p>拖拽文件到这里，或点击选择</p>
        <p>支持 PDF、Word、TXT、Markdown</p>
      </a-upload-dragger>
    </a-space>
  </a-drawer>
</template>
