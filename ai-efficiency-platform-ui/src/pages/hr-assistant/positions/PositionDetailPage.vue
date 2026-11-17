<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Alert, Button, Modal, Select, Tag } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../../entities/hr';
import { draftSchema, dimensions } from '../../../features/hr-position-draft/model';
const route = useRoute();
const router = useRouter();
const positionSchema = z.object({
  id: z.string(),
  name: z.string(),
  family: z.string(),
  departmentId: z.string(),
  level: z.string().nullable(),
  code: z.string(),
  status: z.string(),
  configVersion: z.string().nullable(),
  contextVersion: z.string(),
  version: z.number(),
});
const configSchema = z.object({
  id: z.string(),
  positionId: z.string(),
  version: z.string(),
  contextVersion: z.string(),
  snapshot: draftSchema,
  snapshotHash: z.string(),
  publishedBy: z.string(),
  publishedAt: z.string(),
});
const position = ref<z.infer<typeof positionSchema>>();
const config = ref<z.infer<typeof configSchema>>();
const loading = ref(false);
const busy = ref(false);
const error = ref('');
const disableOpen = ref(false);
const versions = ref<z.infer<typeof configSchema>[]>([]);
const compareFrom = ref('');
const compareTo = ref('');
const differences = ref<{ field: string; oldValue: unknown; newValue: unknown }[]>([]);
async function compare() {
  if (!position.value || !compareFrom.value || !compareTo.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const diff = await hrRequest(
      `/positions/${position.value.id}/config-diff?from=${encodeURIComponent(compareFrom.value)}&to=${encodeURIComponent(compareTo.value)}`,
      z.object({
        from: z.string(),
        to: z.string(),
        changes: z.array(
          z.object({ field: z.string(), oldValue: z.unknown(), newValue: z.unknown() }),
        ),
      }),
    );
    differences.value = diff.changes;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '比较失败';
  } finally {
    busy.value = false;
  }
}
function display(value: unknown) {
  return typeof value === 'object' ? JSON.stringify(value) : String(value ?? '未记录');
}

let controller: AbortController | undefined;
const families: Record<string, string> = {
  TECHNOLOGY: '技术研发',
  PRODUCT: '产品',
  DESIGN: '设计',
  OPERATIONS: '运营',
  MARKETING: '市场',
  SALES: '销售',
  SUPPORT: '职能支持',
  MANAGEMENT: '管理岗',
  GRADUATE: '应届培养',
};
const labels: Record<string, string> = {
  SKILL: '技能匹配',
  EXPERIENCE: '经验匹配',
  PROJECT: '项目匹配',
  EDUCATION: '学历匹配',
  BONUS: '加分项',
};
async function load() {
  if (!route.params.positionId) return;
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = '';
  config.value = undefined;
  try {
    position.value = await hrRequest(`/positions/${route.params.positionId}`, positionSchema, {
      signal: controller.signal,
    });
    versions.value = await hrRequest(
      `/positions/${route.params.positionId}/config-versions`,
      z.array(configSchema),
      { signal: controller.signal },
    );
    const version = route.query.configVersion ?? position.value.configVersion;
    if (version)
      config.value = await hrRequest(
        `/positions/${route.params.positionId}/config-versions/${encodeURIComponent(String(version))}`,
        configSchema,
        { signal: controller.signal },
      );
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError'))
      error.value = e instanceof Error ? e.message : '岗位读取失败';
  } finally {
    loading.value = false;
  }
}
watch(() => [route.params.positionId, route.query.configVersion], load, { immediate: true });
onBeforeUnmount(() => controller?.abort());
async function disable() {
  if (!position.value || busy.value) return;
  busy.value = true;
  try {
    position.value = await hrWrite(`/positions/${position.value.id}/disable`, positionSchema, {
      expectedVersion: position.value.version,
    });
    disableOpen.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '停用失败';
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="hr-position-detail ui-page">
    <header>
      <div>
        <h1>{{ position?.name ?? '岗位详情' }}</h1>
        <p v-if="position">
          {{ families[position.family] ?? '未记录' }} · {{ position.level ?? '职级未记录' }} ·
          {{ position.code }}
        </p>
      </div>
      <div class="actions">
        <Button @click="router.push('/ai-assistants/hr/positions')">返回列表</Button
        ><Button
          v-if="position"
          @click="router.push(`/ai-assistants/hr/positions/new?positionId=${position.id}`)"
          >编辑岗位草稿</Button
        ><Button v-if="position?.status === 'ACTIVE'" @click="disableOpen = true">停用岗位</Button>
      </div>
    </header>
    <p v-if="!route.params.positionId">请从岗位列表选择真实岗位。</p>
    <Alert v-if="error" type="error" show-icon :message="error" /><Button v-if="error" @click="load"
      >重试读取</Button
    >
    <p v-if="loading" role="status">正在读取岗位配置快照…</p>
    <section v-if="position && versions.length" class="panel">
      <h2>冻结版本与差异</h2>
      <Select
        :value="String(route.query.configVersion ?? position.configVersion ?? '')"
        :options="
          versions.map((v) => ({ value: v.version, label: `${v.version} · ${v.publishedAt}` }))
        "
        style="width: 100%"
        @update:value="
          router.replace({ path: route.path, query: { configVersion: String($event) } })
        "
      /><Select
        v-model:value="compareFrom"
        :options="versions.map((v) => ({ value: v.version, label: v.version }))"
        placeholder="原版本"
        style="width: 160px"
      /><Select
        v-model:value="compareTo"
        :options="versions.map((v) => ({ value: v.version, label: v.version }))"
        placeholder="目标版本"
        style="width: 160px"
      /><Button :loading="busy" :disabled="!compareFrom || !compareTo" @click="compare"
        >比较冻结版本</Button
      >
      <dl v-for="diff in differences" :key="diff.field">
        <dt>{{ diff.field }}</dt>
        <dd>{{ display(diff.oldValue) }} → {{ display(diff.newValue) }}</dd>
      </dl>
    </section>
    <template v-if="position && !loading"
      ><section class="panel">
        <h2>
          岗位状态
          <Tag :color="position.status === 'ACTIVE' ? 'green' : 'default'">{{
            { ACTIVE: '启用中', DRAFT: '配置待完善', DISABLED: '已停用' }[position.status] ??
            '未记录'
          }}</Tag>
        </h2>
        <p>
          当前配置 {{ position.configVersion ?? '尚未发布' }} · 上下文 {{ position.contextVersion }}
        </p>
        <p v-if="!config">暂无已发布配置，请继续填写草稿。</p>
        <p v-if="config">正在查看结果配置版本 {{ config.version }}，不会以当前草稿冒充历史快照。</p>
      </section>
      <template v-if="config"
        ><section class="panel">
          <h2>五维权重与分档</h2>
          <p v-for="dimension in dimensions" :key="dimension">
            {{ labels[dimension] }}：{{ config.snapshot.scoring?.weights[dimension] ?? '未记录' }}%
          </p>
          <p>
            阈值 {{ config.snapshot.scoring?.highThreshold }} /
            {{ config.snapshot.scoring?.middleThreshold }} /
            {{ config.snapshot.scoring?.lowThreshold }}
          </p>
          <small>配置哈希 {{ config.snapshotHash }}</small>
        </section>
        <section class="panel">
          <h2>硬性条件</h2>
          <article v-for="rule in config.snapshot.hardConditions" :key="rule.id">
            <h3>{{ rule.label }}</h3>
            <p>期望 {{ rule.expected ?? rule.threshold ?? '未记录' }} {{ rule.unit ?? '' }}</p>
            <p>{{ rule.overridable ? '允许授权人员有理由放行' : '不可人工放行' }}</p>
          </article>
        </section>
        <section class="panel">
          <h2>评分要求与锚点</h2>
          <article v-for="criterion in config.snapshot.criteria" :key="criterion.id">
            <h3>{{ criterion.label }} · {{ labels[criterion.dimension] }}</h3>
            <p>{{ criterion.criterion }}</p>
            <p>显著满足：{{ criterion.strongAnchor }}</p>
            <p>满足：{{ criterion.matchAnchor }}</p>
            <p>部分满足：{{ criterion.partialAnchor }}</p>
            <p>明确不足：{{ criterion.notMetAnchor }}</p>
          </article>
        </section></template
      ></template
    ><Modal
      v-model:open="disableOpen"
      title="确认停用岗位？"
      ok-text="确认停用"
      :confirm-loading="busy"
      @ok="disable"
      ><p>停用后不再接受新自动匹配，已冻结任务和历史结果仍保留。</p></Modal
    >
  </div>
</template>
<style scoped>
.hr-position-detail {
  display: grid;
  gap: 16px;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
}
h1 {
  font-size: 26px;
  margin: 0;
}
h2 {
  font-size: 19px;
}
h3 {
  font-size: 16px;
}
.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.panel {
  background: white;
  border: 1px solid #dce3ef;
  border-radius: 8px;
  padding: 18px;
}
article {
  border-top: 1px solid #e4e9f2;
  padding: 10px 0;
}
p {
  line-height: 1.7;
}
small {
  overflow-wrap: anywhere;
  color: #6b778b;
}
@media (max-width: 700px) {
  header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
