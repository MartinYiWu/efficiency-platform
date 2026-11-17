<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { UploadFile } from 'ant-design-vue';
import type { KnowledgeDocument } from '../../entities/knowledge/model';
import ProcessingTaskDrawer from '../../features/knowledge/ProcessingTaskDrawer.vue';
import EvidenceModeSelect, {
  type EvidenceMode,
} from '../../features/knowledge/EvidenceModeSelect.vue';
import { documentSourceLabel, knowledgeStatusLabel } from '../../features/knowledge/presentation';
import {
  getDocument,
  getKnowledgeBase,
  publishDocumentVersion,
  uploadDocumentVersion,
} from '../../features/knowledge/api';
import styles from './KnowledgeCenter.module.css';
const route = useRoute();
const router = useRouter();
const documentId = computed(() => String(route.params.documentId ?? ''));
const document = ref<KnowledgeDocument>();
const taskId = ref<string>();
const files = ref<UploadFile[]>([]);
const knowledgeType = ref<string>();
const evidenceMode = ref<EvidenceMode>('FULL_ONLY');
const error = ref('');
const uploading = ref(false);
let sequence = 0;
async function load() {
  const current = ++sequence;
  error.value = '';
  try {
    const next = await getDocument(documentId.value);
    if (current !== sequence) return;
    document.value = next;
    knowledgeType.value = undefined;
    const base = await getKnowledgeBase(next.knowledgeBaseId);
    if (current === sequence) knowledgeType.value = base.knowledgeType;
  } catch (e) {
    if (current === sequence) {
      error.value = e instanceof Error ? e.message : '加载失败';
      message.error(error.value);
    }
  }
}
watch(documentId, load, { immediate: true });
onUnmounted(() => {
  sequence++;
});
async function upload() {
  const file = files.value[0]?.originFileObj;
  if (!(file instanceof File)) {
    message.warning('请选择新版本文件');
    return;
  }
  uploading.value = true;
  try {
    const allowed = ['PRODUCT_DOCUMENTATION', 'TECHNICAL_DOCUMENTATION'].includes(
      knowledgeType.value ?? '',
    );
    await uploadDocumentVersion(
      documentId.value,
      file,
      '后台手工更新版本',
      undefined,
      allowed ? evidenceMode.value : 'FULL_ONLY',
    );
    files.value = [];
    message.success('新版本已提交处理');
    await load();
  } catch (e) {
    message.error(e instanceof Error ? e.message : '上传失败');
  } finally {
    uploading.value = false;
  }
}
async function publish(id: string) {
  try {
    await publishDocumentVersion(id);
    await load();
  } catch (e) {
    message.error(e instanceof Error ? e.message : '发布失败');
  }
}
const tasks = computed(
  () =>
    document.value?.versions.flatMap((version) =>
      version.processingTasks.map((task) => ({ ...task, versionNo: version.versionNo })),
    ) ?? [],
);
const taskColumns = [
  { title: '文档版本', dataIndex: 'versionNo' },
  { title: '阶段', dataIndex: 'stage' },
  { title: '状态', dataIndex: 'status' },
  { title: '进度', dataIndex: 'progressPercent' },
  { title: '操作', key: 'action' },
];
const sourceColumns = [
  { title: '版本', dataIndex: 'versionNo', width: 80 },
  { title: '原文文件标识', dataIndex: 'fileId', ellipsis: true },
  { title: '文件格式', dataIndex: 'contentType', width: 220, ellipsis: true },
  { title: '生效日期', dataIndex: 'effectiveDate', width: 140 },
];
</script>
<template>
  <section :class="[styles.page, 'ui-page']">
    <a-alert v-if="error" type="error" :message="error" show-icon
      ><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert
    >
    <a-empty v-if="!document" description="正在加载文档" />
    <template v-else>
      <header :class="[styles.header, 'ui-header']">
        <div>
          <a-button
            type="link"
            :class="styles.link"
            @click="router.push(`/knowledge-center/knowledge-bases/${document.knowledgeBaseId}`)"
            >返回知识库</a-button
          >
          <h2>{{ document.title }}</h2>
          <p>{{ document.documentCode }}</p>
        </div>
      </header>
      <section :class="styles.section" aria-labelledby="document-information">
        <div :class="styles.sectionHeading"><h3 id="document-information">文档信息</h3></div>
        <a-descriptions :column="{ xs: 1, md: 3 }"
          ><a-descriptions-item label="来源">{{
            documentSourceLabel(document.sourceType)
          }}</a-descriptions-item
          ><a-descriptions-item label="状态"
            ><a-tag>{{ knowledgeStatusLabel(document.status) }}</a-tag></a-descriptions-item
          ><a-descriptions-item label="已发布版本">{{
            document.currentPublishedVersionId ?? '未发布'
          }}</a-descriptions-item></a-descriptions
        >
      </section>
      <div :class="styles.versionUploadBar">
        <div>
          <strong>更新文档版本</strong>
          <p>选择处理方式和文件，提交后在下方查看版本与处理任务。</p>
        </div>
        <EvidenceModeSelect v-model:value="evidenceMode" :knowledge-type="knowledgeType" /><a-space
          wrap
          ><a-upload
            :before-upload="() => false"
            :max-count="1"
            :file-list="files"
            @change="files = $event.fileList"
            ><a-button>选择新版本</a-button></a-upload
          ><a-button type="primary" :loading="uploading" @click="upload"
            >上传版本</a-button
          ></a-space
        >
      </div>
      <section :class="styles.section" aria-labelledby="document-versions">
        <div :class="styles.sectionHeading">
          <h3 id="document-versions">版本记录</h3>
          <span>共 {{ document.versions.length }} 个版本</span>
        </div>
        <a-timeline v-if="document.versions.length"
          ><a-timeline-item
            v-for="version in document.versions"
            :key="version.id"
            :color="
              version.status === 'PUBLISHED'
                ? 'green'
                : version.status === 'FAILED'
                  ? 'red'
                  : 'blue'
            "
            ><div :class="styles.versionItem">
              <a-space wrap
                ><strong>V{{ version.versionNo }}</strong
                ><a-tag>{{ knowledgeStatusLabel(version.status) }}</a-tag
                ><time :datetime="version.createdAt" :title="version.createdAt">{{
                  version.createdAt.replace('T', ' ').slice(0, 16)
                }}</time></a-space
              >
              <p>{{ version.changeSummary ?? '未填写变更说明' }}</p>
              <p>
                冻结证据模式：{{
                  version.evidenceMode === 'EXTRACTIVE_NARRATIVE'
                    ? '允许叙述性原文节选'
                    : '全文优先'
                }}
              </p>
              <a-space wrap
                ><a-button
                  v-for="task in version.processingTasks"
                  :key="task.id"
                  size="small"
                  @click="taskId = task.id"
                  >处理任务 {{ task.progressPercent }}%</a-button
                ><a-button
                  v-if="version.status === 'READY'"
                  size="small"
                  type="primary"
                  @click="publish(version.id)"
                  >发布</a-button
                ></a-space
              >
            </div></a-timeline-item
          ></a-timeline
        ><a-empty v-else description="暂无版本记录" />
      </section>
      <section :class="styles.section" aria-labelledby="document-tasks">
        <div :class="styles.sectionHeading"><h3 id="document-tasks">处理任务</h3></div>
        <a-table
          row-key="id"
          :pagination="false"
          :scroll="{ x: 580 }"
          :data-source="tasks"
          :columns="taskColumns"
          ><template #bodyCell="{ column, record, text }"
            ><template v-if="column.dataIndex === 'versionNo'">V{{ text }}</template
            ><template v-else-if="column.dataIndex === 'status'">{{
              knowledgeStatusLabel(text)
            }}</template
            ><template v-else-if="column.dataIndex === 'progressPercent'">{{ text }}%</template
            ><a-button v-else-if="column.key === 'action'" type="link" @click="taskId = record.id"
              >详情</a-button
            ><template v-else>{{ text }}</template></template
          ></a-table
        >
      </section>
      <section :class="styles.section" aria-labelledby="document-source">
        <div :class="styles.sectionHeading">
          <div>
            <h3 id="document-source">原文与引用信息</h3>
            <p>按版本核对原文文件标识与格式，已发布版本标识见文档信息。</p>
          </div>
        </div>
        <a-table
          row-key="id"
          :data-source="document.versions"
          :pagination="false"
          :scroll="{ x: 660 }"
          :columns="sourceColumns"
          ><template #bodyCell="{ column, text }"
            ><template v-if="column.dataIndex === 'versionNo'">V{{ text }}</template
            ><template v-else-if="column.dataIndex === 'effectiveDate'">{{
              text ?? '未设置'
            }}</template
            ><template v-else>{{ text }}</template></template
          ></a-table
        >
      </section>
      <ProcessingTaskDrawer :open="!!taskId" :task-id="taskId" @close="taskId = undefined" />
    </template>
  </section>
</template>
<style scoped>
h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: var(--v1-text);
  overflow-wrap: anywhere;
}
h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--v1-text);
}
p {
  color: var(--v1-text-muted);
  margin: 8px 0 0;
}
</style>
