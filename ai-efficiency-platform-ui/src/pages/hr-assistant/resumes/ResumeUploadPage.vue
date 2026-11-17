<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { Alert, Button, Checkbox, Input, Modal, Select, Tabs, TabPane, Tag } from 'ant-design-vue';
import { z } from 'zod';
import {
  batchSchema,
  batchItemSchema,
  hrRequest,
  hrWrite,
  uploadPolicySchema,
} from '../../../entities/hr';
import styles from './ResumeUploadPage.module.css';
const router = useRouter();
const policy = ref<z.infer<typeof uploadPolicySchema>>();
const positions = ref<{ id: string; name: string }[]>([]);
const mode = ref('MATCH');
const positionId = ref<string>();
const departmentId = ref('');
const maximumItems = ref(100);
const authorized = ref(false);
watch(mode, () => (authorized.value = false));
const files = ref<File[]>([]);
const text = ref('');
const tab = ref('files');
const busy = ref(false);
const loading = ref(false);
const error = ref('');
const uploadIndex = ref(0);
const batchId = ref<string>();
const budgetOpen = ref(false);
const prepared = ref<z.infer<typeof batchSchema>>();
const budgetPlan = ref<{
  maxCalls: number;
  maxCost: number;
  deadline: string | null;
  planRef?: string;
}>();
async function preflight() {
  if (!prepared.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    budgetPlan.value = await hrWrite(
      `/resume-batches/${prepared.value.id}/execution-plan`,
      z.object({
        maxCalls: z.number(),
        maxCost: z.number(),
        deadline: z.string().nullable(),
        planRef: z.string().optional(),
      }),
      {},
    );
    budgetOpen.value = true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '预算预检拒绝，未开始执行';
  } finally {
    busy.value = false;
  }
}
async function confirmStart() {
  if (!prepared.value || !budgetPlan.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    await hrWrite(`/resume-batches/${prepared.value.id}/start`, batchSchema, {
      expectedVersion: prepared.value.version,
      planRef: budgetPlan.value.planRef,
    });
    budgetOpen.value = false;
    authorized.value = false;
    await router.push(`/ai-assistants/hr/resumes/batches/${prepared.value.id}`);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '开始失败，未重新授权预算';
  } finally {
    busy.value = false;
  }
}

let controller: AbortController | undefined;
const accept = computed(
  () =>
    policy.value?.formats
      .filter((f) => f.available)
      .map((f) => `.${f.extension}`)
      .join(',') ?? '',
);
const valid = computed(
  () =>
    !!policy.value &&
    authorized.value &&
    !busy.value &&
    (mode.value === 'STORE_ONLY' ? !!departmentId.value.trim() : !!positionId.value) &&
    (tab.value === 'files' ? files.value.length > 0 : !!text.value.trim()) &&
    Array.from(text.value).length <= 50000,
);
async function load() {
  controller?.abort();
  controller = new AbortController();
  loading.value = true;
  error.value = '';
  try {
    const [p, list] = await Promise.all([
      hrRequest('/settings/upload-policy', uploadPolicySchema, { signal: controller.signal }),
      hrRequest(
        '/positions?status=ACTIVE&page=1&pageSize=100',
        z.object({
          items: z.array(z.object({ id: z.string(), name: z.string(), status: z.string() })),
          total: z.number(),
          page: z.number(),
          pageSize: z.number(),
        }),
        { signal: controller.signal },
      ),
    ]);
    policy.value = p;
    positions.value = list.items.filter((p) => p.status === 'ACTIVE');
  } catch (e) {
    if (!(e instanceof DOMException && e.name === 'AbortError'))
      error.value = e instanceof Error ? e.message : '上传配置读取失败';
  } finally {
    loading.value = false;
  }
}
onMounted(load);
onBeforeUnmount(() => controller?.abort());
function choose(event: Event) {
  const selected = Array.from((event.target as HTMLInputElement).files ?? []);
  error.value = '';
  if (files.value.length + selected.length > 100) {
    error.value = '每批最多100个文档条目，请减少文件。';
    return;
  }
  for (const file of selected) {
    const ext = file.name.split('.').pop()?.toLowerCase();
    const format = policy.value?.formats.find((f) => f.extension === ext);
    if (!format?.available) {
      error.value = `${file.name}：当前格式服务不可用`;
      return;
    }
    const archive = ['zip', 'rar', '7z'].includes(ext ?? '');
    if (file.size > (archive ? 100 : 20) * 1024 * 1024) {
      error.value = `${file.name}：超过${archive ? 100 : 20}MiB上限`;
      return;
    }
  }
  files.value = [...files.value, ...selected];
  (event.target as HTMLInputElement).value = '';
}
async function start() {
  if (!valid.value || !policy.value) return;
  busy.value = true;
  error.value = '';
  try {
    let batch = await hrWrite('/resume-batches', batchSchema, {
      positionId: mode.value === 'MATCH' ? positionId.value : null,
      mode: mode.value,
      policyVersionId: policy.value.policyVersionId,
      authorizationConfirmed: true,
      maximumItems: tab.value === 'files' ? maximumItems.value : 1,
      departmentId: mode.value === 'STORE_ONLY' ? departmentId.value : null,
    });
    batchId.value = batch.id;
    if (tab.value === 'files') {
      for (let i = 0; i < files.value.length; i++) {
        uploadIndex.value = i + 1;
        const form = new FormData();
        form.append('file', files.value[i]);
        await hrRequest(`/resume-batches/${batch.id}/uploads`, batchItemSchema, {
          method: 'POST',
          headers: { 'Idempotency-Key': crypto.randomUUID() },
          body: form,
        });
      }
    } else {
      await hrWrite(`/resume-batches/${batch.id}/uploads`, batchItemSchema, {
        text: text.value,
        filename: '粘贴简历.txt',
      });
    }
    batch = await hrRequest(`/resume-batches/${batch.id}`, batchSchema);
    prepared.value = batch;
    busy.value = false;
    await preflight();
  } catch (e) {
    error.value = e instanceof Error ? e.message : '上传失败，批次未自动重发';
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header :class="styles.heading">
      <div>
        <h1>上传简历</h1>
        <p>上传前确认采集授权与目标岗位，解析结果需根据质量规则人工核对。</p>
      </div>
    </header>
    <Alert v-if="error" type="error" show-icon :message="error" /><Button
      v-if="error && !batchId"
      @click="load"
      >重新读取配置</Button
    ><Alert
      v-if="batchId && error"
      type="warning"
      message="已有上传批次，未自动重试或重新申请额度。请查看批次状态后处理。"
    /><Button
      v-if="batchId && error"
      @click="router.push(`/ai-assistants/hr/resumes/batches/${batchId}`)"
      >查看已有批次</Button
    >
    <p v-if="loading" role="status">正在读取格式服务与授权政策…</p>
    <div :class="styles.contentGrid">
      <section :class="styles.settingsPanel" role="complementary" aria-label="上传配置">
        <h2>匹配设置</h2>
        <label
          >处理方式<Select
            v-model:value="mode"
            :disabled="busy"
            :options="[
              { value: 'MATCH', label: '解析并匹配岗位' },
              { value: 'STORE_ONLY', label: '仅入库，不匹配' },
            ]"
            style="width: 100%" /></label
        ><label v-if="mode === 'MATCH'"
          >目标岗位<Select
            v-model:value="positionId"
            :disabled="busy || loading"
            placeholder="请选择已发布的启用岗位"
            :options="positions.map((p) => ({ value: p.id, label: p.name }))"
            style="width: 100%"
        /></label>
        <label v-if="mode === 'STORE_ONLY'"
          >入库授权部门ID<Input v-model:value="departmentId" :disabled="busy" /></label
        ><label
          >批次展开文档上限<select v-model.number="maximumItems" :disabled="busy">
            <option v-for="n in [10, 20, 50, 100]" :key="n" :value="n">{{ n }}份</option>
          </select></label
        >
        <p v-if="mode === 'MATCH' && !positions.length && !loading">
          暂无可用岗位，请先配置并发布岗位。
        </p>
        <Alert
          type="info"
          show-icon
          message="上传不自动授权预算；没有有效预算或服务未就绪时，后端会明确阻止付费调用。"
        />
        <section v-if="policy">
          <h3>本批采集授权</h3>
          <p>{{ policy.authorizationText }}</p>
          <p>
            {{
              mode === 'MATCH'
                ? '本批用途：仅本次招聘与面试，不自动授权人才库跨岗位复用。'
                : '本批用途：人才库保留与跨岗位招聘复用；请核实已取得此范围授权。'
            }}
          </p>
          <Checkbox v-model:checked="authorized" :disabled="busy"
            >我确认本批资料已取得合法授权，并同意按上述政策处理</Checkbox
          ><small>政策版本 {{ policy.policyVersionId }} · 每批必须重新确认</small>
        </section>
        <p v-else>政策未就绪，不能创建解析批次。</p>
      </section>
      <section :class="styles.uploadPanel" class="upload-body" role="region" aria-label="上传方式">
        <Tabs v-model:active-key="tab"
          ><TabPane key="files" tab="文件与压缩包" /><TabPane key="text" tab="粘贴文本" /></Tabs
        ><template v-if="tab === 'files'"
          ><label class="dropzone"
            ><b>＋ 选择简历文件或压缩包</b><span>单文件≤20MiB · 单压缩包≤100MiB · 每批≤100份</span
            ><input
              type="file"
              multiple
              :accept="accept"
              :disabled="busy || !policy"
              aria-label="选择简历文件"
              @change="choose"
          /></label>
          <p>已选择 {{ files.length }} 个文件</p>
          <article v-for="(file, index) in files" :key="`${index}-${file.name}`" class="file">
            <div>
              <b>{{ file.name }}</b
              ><small>{{ (file.size / 1024 / 1024).toFixed(2) }}MiB · 等待服务端格式预检</small>
            </div>
            <Button
              :disabled="busy"
              :aria-label="`移除 ${file.name}`"
              @click="files.splice(index, 1)"
              >移除</Button
            >
          </article>
          <p v-if="!files.length">尚未选择文件，不会自动排入示例简历。</p></template
        ><template v-else
          ><Input.TextArea
            v-model:value="text"
            :disabled="busy"
            :rows="15"
            placeholder="粘贴已获得授权的简历文本"
            aria-label="简历文本" />
          <p>{{ Array.from(text).length }} / 50000 字</p>
          <Alert
            v-if="Array.from(text).length < 200 && text"
            type="warning"
            message="文本不足200字，可能缺少有效事实；仍可提交核验。"
        /></template>
        <div v-if="policy" class="formats">
          <Tag
            v-for="format in policy.formats"
            :key="format.extension"
            :color="format.available ? 'blue' : 'default'"
            >{{ format.extension }}
            {{ format.available ? '可用' : (format.reason ?? '当前不可用') }}</Tag
          >
        </div>
      </section>
    </div>
    <footer :class="styles.footerBar" aria-label="上传操作">
      <span>{{
        busy
          ? `正在上传 ${uploadIndex} / ${files.length}，请勿重复提交`
          : '格式、压缩包与文档条目以服务端预检为准，不会静默截断。'
      }}</span
      ><Button type="primary" :loading="busy" :disabled="!valid || !!batchId" @click="start"
        >开始解析</Button
      >
    </footer>
    <Button v-if="prepared && !budgetOpen" :loading="busy" @click="preflight"
      >预检本批最大调用与费用</Button
    ><Modal
      v-model:open="budgetOpen"
      title="确认本批预算上界"
      :confirm-loading="busy"
      ok-text="确认上界并开始"
      @ok="confirmStart"
      ><template v-if="budgetPlan"
        ><p>最多新增调用 {{ budgetPlan.maxCalls }} 次</p>
        <p>费用上界 ¥{{ (budgetPlan.maxCost / 1000000).toFixed(6) }}</p>
        <p>截止 {{ budgetPlan.deadline ?? '未授权' }}；不会续额或重置已发生消费。</p></template
      ></Modal
    >
  </div>
</template>
<style scoped>
.upload-body {
  padding: 18px;
}
.dropzone {
  border: 1px dashed #8aa8ec;
  background: #f6f9ff;
  display: grid;
  place-items: center;
  gap: 14px;
  padding: 35px 16px;
  border-radius: 8px;
  text-align: center;
}
.dropzone b {
  font-size: 18px;
  color: #185aff;
}
.dropzone input {
  max-width: 100%;
}
.dropzone span,
small {
  font-size: 12px;
  color: #65718a;
}
.file {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
  border: 1px solid #e1e6ef;
  padding: 12px;
  margin: 8px 0;
  border-radius: 5px;
}
.file small,
small {
  display: block;
  margin-top: 6px;
}
.formats {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 16px;
}
h2 {
  font-size: 18px;
}
h3 {
  font-size: 16px;
}
label {
  display: grid;
  gap: 8px;
}
section p {
  line-height: 1.7;
}
</style>
