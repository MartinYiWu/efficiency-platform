<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type {
  IndexRelease,
  KnowledgeBase,
  KnowledgeDirectory,
  KnowledgeDocument,
} from '../../entities/knowledge/model';
import {
  createDirectory,
  getKnowledgeBase,
  listDirectories,
  listDocuments,
  listIndexReleases,
  rollbackIndexRelease,
  updateKnowledgeBase,
} from '../../features/knowledge/api';
import {
  knowledgeStatusLabel,
  knowledgeTypeLabel,
  visibilityScopeLabel,
} from '../../features/knowledge/presentation';
import KnowledgeBatchImportModal from '../../features/knowledge/KnowledgeBatchImportModal.vue';
import KnowledgeUploadDrawer from '../../features/knowledge/KnowledgeUploadDrawer.vue';
import styles from './KnowledgeCenter.module.css';
const route = useRoute();
const router = useRouter();
const baseId = computed(() => String(route.params.baseId ?? ''));
const base = ref<KnowledgeBase>();
const directories = ref<KnowledgeDirectory[]>([]);
const documents = ref<KnowledgeDocument[]>([]);
const releases = ref<IndexRelease[]>([]);
const directoryId = ref<string>();
const page = ref(1);
const total = ref(0);
const uploadOpen = ref(false);
const batchOpen = ref(false);
const batchId = ref<string>();
const activating = ref(false);
const loading = ref(false);
const error = ref('');
const directoryOpen = ref(false);
const directoryName = ref('');
const directorySaving = ref(false);
const isActive = computed(() => base.value?.status === 'ACTIVE');
let sequence = 0;
async function load() {
  const current = ++sequence;
  loading.value = true;
  error.value = '';
  const query = new URLSearchParams({ page: String(page.value), pageSize: '10' });
  if (directoryId.value) query.set('directoryId', directoryId.value);
  try {
    const [nextBase, nextDirectories, nextDocuments, nextReleases] = await Promise.all([
      getKnowledgeBase(baseId.value),
      listDirectories(baseId.value),
      listDocuments(baseId.value, query.toString()),
      listIndexReleases(baseId.value),
    ]);
    if (current !== sequence) return false;
    base.value = nextBase;
    directories.value = nextDirectories;
    documents.value = nextDocuments.items;
    total.value = nextDocuments.total;
    releases.value = nextReleases;
    return true;
  } catch (e) {
    if (current === sequence) {
      error.value = e instanceof Error ? e.message : '加载失败';
      message.error(error.value);
    }
    return false;
  } finally {
    if (current === sequence) loading.value = false;
  }
}
watch([baseId, directoryId, page], load, { immediate: true });
onUnmounted(() => {
  sequence++;
});
async function activate() {
  if (!base.value) return;
  activating.value = true;
  try {
    await updateKnowledgeBase(baseId.value, {
      name: base.value.name,
      description: base.value.description,
      knowledgeType: base.value.knowledgeType,
      status: 'ACTIVE',
    });
    if (await load()) message.success('知识库已启用');
  } catch (e) {
    message.error(e instanceof Error ? e.message : '启用知识库失败');
  } finally {
    activating.value = false;
  }
}
async function addDirectory() {
  if (!directoryName.value.trim()) {
    message.warning('请输入目录名称');
    return;
  }
  directorySaving.value = true;
  try {
    await createDirectory(baseId.value, {
      name: directoryName.value.trim(),
      parentId: directoryId.value ?? null,
      sortNo: directories.value.length + 1,
    });
    message.success('目录已创建');
    directoryOpen.value = false;
    directoryName.value = '';
    await load();
  } catch (e) {
    message.error(e instanceof Error ? e.message : '创建失败');
  } finally {
    directorySaving.value = false;
  }
}
async function rollback(id: string) {
  try {
    await rollbackIndexRelease(id);
    await load();
  } catch (e) {
    message.error(e instanceof Error ? e.message : '回滚失败');
  }
}
function selectDirectory(keys: (string | number)[]) {
  directoryId.value = keys[0]?.toString() || undefined;
  page.value = 1;
}
function closeBatch() {
  batchOpen.value = false;
  batchId.value = undefined;
}
const documentColumns = [
  { title: '名称', dataIndex: 'title', width: 220, ellipsis: true },
  { title: '编码', dataIndex: 'documentCode', width: 160, ellipsis: true },
  { title: '状态', dataIndex: 'status', width: 100 },
  { title: '操作', key: 'action', width: 80 },
];
const releaseColumns = [
  { title: '版本', dataIndex: 'releaseNo', width: 80 },
  { title: '状态', dataIndex: 'status', width: 100 },
  { title: '文档 / 分块', key: 'counts', width: 120 },
  { title: '模型', dataIndex: 'embeddingModel', ellipsis: true },
  { title: '发布时间', dataIndex: 'publishedAt', width: 180 },
  { title: '操作', key: 'action', width: 150 },
];
</script>
<template>
  <section :class="[styles.page, 'ui-page']">
    <a-alert v-if="error" type="error" :message="error" show-icon
      ><template #action><a-button size="small" @click="load">重试</a-button></template></a-alert
    >
    <a-empty v-if="!base" description="正在加载知识库" />
    <template v-else>
      <header :class="[styles.header, 'ui-header']">
        <div>
          <a-button
            type="link"
            :class="styles.link"
            @click="router.push('/knowledge-center/knowledge-bases')"
            >返回知识中心</a-button
          >
          <h2>{{ base.name }}</h2>
          <p>{{ base.description ?? '暂无描述' }}</p>
        </div>
        <a-space wrap
          ><a-button
            v-if="['DRAFT', 'DISABLED'].includes(base.status)"
            :loading="activating"
            @click="activate"
            >启用知识库</a-button
          ><a-button :disabled="!isActive" @click="batchOpen = true">批量导入</a-button
          ><a-button type="primary" :disabled="!isActive" @click="uploadOpen = true"
            >上传文档</a-button
          ></a-space
        >
      </header>
      <a-alert
        v-if="!isActive"
        type="warning"
        show-icon
        message="知识库未启用，请先启用知识库后再上传文档或批量导入。"
      />
      <section :class="styles.section" aria-labelledby="base-information">
        <div :class="styles.sectionHeading">
          <h3 id="base-information">知识库信息</h3>
          <span>{{ base.code }}</span>
        </div>
        <a-descriptions size="small" :column="{ xs: 1, sm: 2, lg: 4 }"
          ><a-descriptions-item label="类型">{{
            knowledgeTypeLabel(base.knowledgeType)
          }}</a-descriptions-item
          ><a-descriptions-item label="范围">{{
            visibilityScopeLabel(base.visibilityScope)
          }}</a-descriptions-item
          ><a-descriptions-item label="状态">{{
            knowledgeStatusLabel(base.status)
          }}</a-descriptions-item
          ><a-descriptions-item label="当前索引版本">{{
            base.currentIndexReleaseId ?? '未发布'
          }}</a-descriptions-item></a-descriptions
        >
      </section>
      <section :class="styles.section" aria-labelledby="base-documents">
        <div :class="styles.sectionHeading">
          <h3 id="base-documents">目录与文档</h3>
          <span>共 {{ total }} 份文档</span>
        </div>
        <div :class="styles.split">
          <aside :class="styles.directory" aria-label="文档目录">
            <div :class="styles.directoryHeading">
              <strong>目录</strong
              ><a-button size="small" @click="directoryOpen = true">新建目录</a-button>
            </div>
            <a-tree
              default-expand-all
              :selected-keys="[directoryId || '']"
              :tree-data="[
                {
                  key: '',
                  title: '全部文档',
                  children: directories.map((item) => ({ key: item.id, title: item.name })),
                },
              ]"
              @select="selectDirectory"
            />
          </aside>
          <div :class="styles.tableRegion">
            <a-table
              row-key="id"
              :data-source="documents"
              :columns="documentColumns"
              :loading="loading"
              :scroll="{ x: 650 }"
              :pagination="{
                current: page,
                pageSize: 10,
                total,
                showSizeChanger: false,
                onChange: (value: number) => (page = value),
              }"
              ><template #emptyText><a-empty description="当前目录暂无文档" /></template
              ><template #bodyCell="{ column, record, text }"
                ><template v-if="column.dataIndex === 'status'">{{
                  knowledgeStatusLabel(text)
                }}</template
                ><a-button
                  v-else-if="column.key === 'action'"
                  type="link"
                  @click="router.push(`/knowledge-center/documents/${record.id}`)"
                  >查看</a-button
                ></template
              ></a-table
            >
          </div>
        </div>
      </section>
      <section :class="styles.section" aria-labelledby="base-releases">
        <div :class="styles.sectionHeading">
          <div>
            <h3 id="base-releases">索引版本</h3>
            <p>查看发布历史与各版本的文档、分块和模型信息。</p>
          </div>
        </div>
        <a-table
          row-key="id"
          :data-source="releases"
          :columns="releaseColumns"
          :scroll="{ x: 750 }"
          :pagination="{ pageSize: 10, hideOnSinglePage: true }"
          ><template #bodyCell="{ column, record, text }"
            ><template v-if="column.dataIndex === 'releaseNo'">R{{ text }}</template
            ><template v-else-if="column.dataIndex === 'status'">{{
              knowledgeStatusLabel(text)
            }}</template
            ><template v-else-if="column.key === 'counts'"
              >{{ record.documentCount }} / {{ record.chunkCount }}</template
            ><template v-else-if="column.dataIndex === 'publishedAt'">{{
              text?.replace('T', ' ').slice(0, 16) ?? '未发布'
            }}</template
            ><template v-else-if="column.key === 'action'"
              ><a-button
                v-if="record.id !== base.currentIndexReleaseId"
                type="link"
                @click="rollback(record.id)"
                >回滚到此版本</a-button
              ><span v-else>当前版本</span></template
            ></template
          ></a-table
        >
      </section>
      <KnowledgeUploadDrawer
        :open="uploadOpen"
        :base-id="baseId"
        :knowledge-type="base.knowledgeType"
        :directories="directories"
        @close="uploadOpen = false"
        @submitted="
          (id) => {
            batchId = id;
            batchOpen = true;
          }
        "
      />
      <KnowledgeBatchImportModal
        v-if="batchOpen"
        :open="true"
        :base-id="baseId"
        :directories="directories"
        :initial-batch-id="batchId"
        @close="closeBatch"
        @changed="load"
      />
      <a-modal
        title="新建目录"
        :open="directoryOpen"
        :confirm-loading="directorySaving"
        @cancel="directoryOpen = false"
        @ok="addDirectory"
        ><a-input
          v-model:value="directoryName"
          aria-label="目录名称"
          placeholder="目录名称"
          @press-enter="addDirectory"
      /></a-modal>
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
