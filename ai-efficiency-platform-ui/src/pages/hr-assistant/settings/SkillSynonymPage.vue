<script setup lang="ts">
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import { Alert, Button, Input, InputNumber, Tabs, TabPane, Tag } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../../entities/hr';
import { dictionarySchema, settingsSchema, entrySchema } from '../../../entities/hr/completion';
import styles from './SkillSynonymPage.module.css';
const uuid = () => crypto.randomUUID();
const tab = ref(useRoute().path.endsWith('/global') ? 'global' : 'dictionary');
const department = ref('');
const dictionary = ref<z.infer<typeof dictionarySchema>>();
const settings = ref<z.infer<typeof settingsSchema>>();
const busy = ref(false);
const error = ref('');
const done = ref('');
const importFile = ref<File>();
const histories = ref<{ version: number; status: string }[]>([]);
const audit = ref<
  {
    id: string;
    action: string;
    kind: string;
    objectId: string;
    actorId: string;
    version: number;
    at: string;
  }[]
>([]);
async function history() {
  if (!department.value.trim() || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    histories.value =
      tab.value === 'dictionary'
        ? await hrRequest(
            `/dictionaries/versions?departmentId=${encodeURIComponent(department.value)}`,
            z.array(dictionarySchema),
          )
        : await hrRequest(
            `/settings/versions?departmentId=${encodeURIComponent(department.value)}`,
            z.array(settingsSchema),
          );
    audit.value = await hrRequest(
      `/configuration-audit?departmentId=${encodeURIComponent(department.value)}`,
      z.array(
        z.object({
          id: z.string(),
          action: z.string(),
          kind: z.string(),
          objectId: z.string(),
          actorId: z.string(),
          version: z.number(),
          at: z.string(),
        }),
      ),
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '历史读取失败';
  } finally {
    busy.value = false;
  }
}

const previewSchema = z.object({
  id: z.string(),
  departmentId: z.string(),
  baseVersion: z.number(),
  entries: z.array(entrySchema),
  conflicts: z.array(z.string()),
  version: z.number(),
});
const preview = ref<z.infer<typeof previewSchema>>();
async function load() {
  if (!department.value.trim() || busy.value) return;
  busy.value = true;
  error.value = '';
  done.value = '';
  try {
    if (tab.value === 'dictionary')
      dictionary.value = await hrRequest(
        `/dictionaries?departmentId=${encodeURIComponent(department.value)}`,
        dictionarySchema,
      );
    else
      settings.value = await hrRequest(
        `/settings?departmentId=${encodeURIComponent(department.value)}`,
        settingsSchema,
      );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    busy.value = false;
  }
}
async function write(publish = false) {
  if (busy.value) return;
  const target = tab.value === 'dictionary' ? dictionary.value : settings.value;
  if (!target) return;
  busy.value = true;
  error.value = '';
  done.value = '';
  const path = tab.value === 'dictionary' ? '/dictionaries' : '/settings';
  try {
    const data = publish
      ? { departmentId: department.value, expectedVersion: target.version }
      : { ...target, expectedVersion: target.version };
    if (tab.value === 'dictionary') {
      dictionary.value = publish
        ? await hrWrite(`${path}/publish`, dictionarySchema, data)
        : await hrRequest(path, dictionarySchema, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
            body: JSON.stringify(data),
          });
    } else {
      settings.value = publish
        ? await hrWrite(`${path}/publish`, settingsSchema, data)
        : await hrRequest(path, settingsSchema, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
            body: JSON.stringify(data),
          });
    }
    done.value = publish ? '已发布新版本，仅影响后续对象。' : '草稿已保存。';
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败';
  } finally {
    busy.value = false;
  }
}
async function preflight() {
  if (!importFile.value || !dictionary.value || busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const body = new FormData();
    body.set('file', importFile.value);
    body.set('departmentId', department.value);
    body.set('expectedVersion', String(dictionary.value.version));
    preview.value = await hrRequest('/dictionaries/import-file', previewSchema, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body,
    });
  } catch (e) {
    error.value = e instanceof Error ? e.message : '预检失败';
  } finally {
    busy.value = false;
  }
}
async function adopt() {
  if (!preview.value || busy.value || preview.value.conflicts.length) return;
  busy.value = true;
  error.value = '';
  try {
    dictionary.value = await hrWrite(
      `/dictionaries/imports/${preview.value.id}/adopt`,
      dictionarySchema,
      { expectedVersion: preview.value.version },
    );
    preview.value = undefined;
    done.value = '已采用导入批次，仍需显式发布。';
  } catch (e) {
    error.value = e instanceof Error ? e.message : '采用失败';
  } finally {
    busy.value = false;
  }
}
const labels: Record<string, string> = {
  retentionMonths: '默认保留月数',
  confirmationWaitDays: '人工确认等待天数',
  maxModelAttempts: '单操作最大尝试',
  failedItemRetentionDays: '失败材料保留天数',
  highThreshold: '强烈推荐阈值',
  middleThreshold: '推荐阈值',
  lowThreshold: '可考虑阈值',
  maxFileBytes: '单文件字节上限',
  maxArchiveBytes: '压缩包字节上限',
  maxBatchItems: '单批份数上限',
};
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header>
      <h1>词典与全局配置</h1>
      <p>修改只影响新对象；历史结果保留冻结版本。禁止属性为只读政策。</p>
    </header>
    <Alert v-if="error" type="error" :message="error" show-icon /><Alert
      v-if="done"
      type="success"
      :message="done"
    /><Tabs v-model:active-key="tab" @change="load"
      ><TabPane key="dictionary" tab="技能同义词库" /><TabPane key="global" tab="全局设置"
    /></Tabs>
    <div style="display: flex; gap: 12px">
      <Input
        v-model:value="department"
        aria-label="配置部门ID"
        placeholder="部门ID"
        style="max-width: 280px"
      /><Button :loading="busy" :disabled="!department.trim()" @click="load">读取配置</Button>
    </div>
    <Button :loading="busy" :disabled="!department.trim()" @click="history">配置历史与审计</Button>
    <p v-for="version in histories" :key="version.version">
      冻结版本 v{{ version.version }} · {{ version.status }}
    </p>
    <p v-for="event in audit" :key="event.id">
      {{ event.at }} · {{ event.actorId }} · {{ event.action }} · {{ event.kind }} /
      {{ event.objectId }} · v{{ event.version }}
    </p>
    <template v-if="tab === 'dictionary' && dictionary"
      ><p>版本 {{ dictionary.version }} · {{ dictionary.status }}</p>
      <div style="overflow: auto">
        <table style="width: 100%; min-width: 700px">
          <thead>
            <tr>
              <th>类别</th>
              <th>标准名</th>
              <th>别名（逗号分隔）</th>
              <th>歧义上下文规则</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(entry, index) in dictionary.entries" :key="entry.id">
              <td>
                <select v-model="entry.category" aria-label="词条类别">
                  <option
                    v-for="category in [
                      'SKILL',
                      'INDUSTRY',
                      'FUNCTION',
                      'DEGREE',
                      'MAJOR',
                      'CERTIFICATE',
                      'LANGUAGE',
                    ]"
                    :key="category"
                  >
                    {{ category }}
                  </option>
                </select>
              </td>
              <td><Input v-model:value="entry.canonical" aria-label="标准名" /></td>
              <td>
                <Input
                  :value="entry.aliases.join(',')"
                  aria-label="技能别名"
                  @update:value="
                    entry.aliases = $event
                      .split(',')
                      .map((v) => v.trim())
                      .filter(Boolean)
                  "
                />
              </td>
              <td><Input v-model:value="entry.contextPattern" aria-label="上下文规则" /></td>
              <td><Button @click="dictionary.entries.splice(index, 1)">移除草稿词条</Button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="!dictionary.entries.length">暂无词条，请添加或导入并预检。</p>
      <Button
        @click="
          dictionary.entries.push({
            id: uuid(),
            category: 'SKILL',
            canonical: '',
            aliases: [],
            contextPattern: '',
          })
        "
        >新增词条</Button
      ><Button :loading="busy" @click="write()">保存草稿</Button
      ><Button type="primary" :loading="busy" @click="write(true)">发布词典</Button>
      <section style="margin-top: 24px">
        <h2>批量导入预检</h2>
        <input
          type="file"
          accept=".csv,.xlsx"
          aria-label="导入词典文件"
          @change="importFile = ($event.target as HTMLInputElement).files?.[0]"
        /><Button :disabled="!importFile" :loading="busy" @click="preflight">预检CSV / XLSX</Button
        ><a :href="`/api/hr/dictionaries/export?departmentId=${encodeURIComponent(department)}`"
          >导出词典CSV</a
        ><template v-if="preview"
          ><p>待采用 {{ preview.entries.length }} 条 · 基础版本 {{ preview.baseVersion }}</p>
          <Alert
            v-for="conflict in preview.conflicts"
            :key="conflict"
            type="warning"
            :message="conflict"
          /><Button :disabled="!!preview.conflicts.length" :loading="busy" @click="adopt"
            >采用预检结果</Button
          ></template
        >
      </section></template
    ><template v-if="tab === 'global' && settings"
      ><p>版本 {{ settings.version }} · {{ settings.status }}</p>
      <section
        style="
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
          gap: 18px;
          margin: 20px 0;
        "
      >
        <label v-for="(label, key) in labels" :key="key"
          >{{ label
          }}<InputNumber
            :value="settings[key as keyof typeof settings] as number"
            :min="0"
            :precision="0"
            style="width: 100%"
            @update:value="(settings as unknown as Record<string, unknown>)[key] = $event" /></label
        ><label
          >候选人授权告知文本<Input.TextArea
            v-model:value="settings.authorizationText"
            :rows="4" /></label
        ><label>授权告知版本<Input v-model:value="settings.noticeVersion" /></label>
      </section>
      <h2>禁止属性（只读）</h2>
      <Tag v-for="attribute in settings.prohibitedAttributes" :key="attribute">{{ attribute }}</Tag>
      <p>文件与尝试上限只能降低。发布前请核对阈值递减和告知版本。</p>
      <Button :loading="busy" @click="write()">保存设置草稿</Button
      ><Button
        type="primary"
        :loading="busy"
        :disabled="!settings.noticeVersion.trim()"
        @click="write(true)"
        >发布全局设置</Button
      ></template
    >
  </div>
</template>

<style scoped>
header {
  margin-bottom: 20px;
}
header h1 {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 6px;
  color: #10172b;
}
header p {
  color: #64748b;
  font-size: 13px;
  margin: 0;
  line-height: 1.6;
}
label {
  line-height: 1.6;
}
label:has(> .ant-input),
label:has(> .ant-input-number) {
  display: grid;
  gap: 5px;
  font-size: 13px;
  color: #475569;
}
details {
  background: #ffffffa8;
  border: 1px solid #dde4f2;
  border-radius: 8px;
  padding: 15px 18px;
  margin: 14px 0;
}
summary {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  cursor: pointer;
}
details[open] > summary {
  margin-bottom: 14px;
}
table {
  background: #fff;
  border-collapse: collapse;
  border: 1px solid #dde4f2;
}
th {
  padding: 12px 18px;
  background: #f6f8fc;
  font-weight: 500;
  color: #64748b;
  font-size: 12px;
  text-align: left;
}
td {
  padding: 15px 18px;
  border-bottom: 1px solid #edf0f5;
  vertical-align: middle;
  font-size: 13px;
}
article h2 {
  font-size: 18px;
  margin: 12px 0;
}
article p {
  line-height: 1.7;
  color: #475569;
}
.ant-btn + .ant-btn {
  margin-left: 8px;
}
@media (max-width: 700px) {
  header {
    margin-bottom: 16px;
  }
  header h1 {
    font-size: 22px;
  }
  details {
    padding: 12px;
  }
  th,
  td {
    padding: 12px;
  }
  .ant-btn + .ant-btn {
    margin-left: 4px;
  }
}
</style>
