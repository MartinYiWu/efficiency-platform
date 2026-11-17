<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue';
import { useRouter } from 'vue-router';
import { Alert, Button, Input, Modal, Pagination, Tag } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../../entities/hr';
import { talentSummarySchema, beijing } from '../../../entities/hr/completion';
import styles from './TalentSearchPage.module.css';
const router = useRouter();
const query = ref('');
const skill = ref('');
const education = ref('');
const minMonths = ref('');
const maxMonths = ref('');
const excludedPosition = ref('');
const dictionaryVersion = ref('');
const page = ref(1);
const total = ref(0);
const items = ref<z.infer<typeof talentSummarySchema>[]>([]);
const busy = ref(false);
const error = ref('');
const semanticOpen = ref(false);
const semanticBusy = ref(false);
const searchId = ref('');
const searchSchema = z.object({
  id: z.string(),
  status: z.string(),
  query: z.string(),
  createdAt: z.string(),
  hits: z.array(
    z.object({
      candidateId: z.string(),
      retrievalRelevance: z.number().min(0).max(1).nullable(),
      matches: z.array(
        z.object({ blockId: z.string(), start: z.number(), end: z.number(), quote: z.string() }),
      ),
      status: z.string(),
      failureCode: z.string().nullable(),
    }),
  ),
});
const semantic = ref<z.infer<typeof searchSchema>>();
let searchTimer: ReturnType<typeof setTimeout> | undefined;
let searchPolls = 0;
async function readSearch() {
  if (!searchId.value) return;
  try {
    semantic.value = await hrRequest(
      `/talent-search-jobs/${encodeURIComponent(searchId.value)}`,
      searchSchema,
    );
    if (['PREFLIGHT', 'RUNNING'].includes(semantic.value.status) && searchPolls++ < 120)
      searchTimer = setTimeout(readSearch, 2000);
    else semanticBusy.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '语义检索读取失败';
    semanticBusy.value = false;
  }
}
async function semanticSearch() {
  if (semanticBusy.value || !query.value.trim() || !items.value.length || items.value.length > 20)
    return;
  semanticBusy.value = true;
  error.value = '';
  try {
    semantic.value = await hrWrite('/talent-search-jobs', searchSchema, {
      query: query.value,
      confirmed: true,
      candidateIds: items.value.map((item) => item.candidateId),
    });
    searchId.value = semantic.value.id;
    semanticOpen.value = false;
    searchPolls = 0;
    await readSearch();
  } catch (e) {
    error.value = e instanceof Error ? e.message : '语义检索未执行';
    semanticBusy.value = false;
  }
}
onBeforeUnmount(() => clearTimeout(searchTimer));

async function load() {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  try {
    const params = new URLSearchParams({
      page: String(page.value),
      pageSize: '20',
      query: query.value,
    });
    for (const [key, value] of Object.entries({
      skill: skill.value,
      education: education.value,
      minimumExperienceMonths: minMonths.value,
      maximumExperienceMonths: maxMonths.value,
      excludeMatchedPositionId: excludedPosition.value,
      dictionaryVersion: dictionaryVersion.value,
    }))
      if (value) params.set(key, value);
    const data = await hrRequest(
      `/candidates?${params}`,
      z.object({
        items: z.array(talentSummarySchema),
        total: z.number(),
        page: z.number(),
        pageSize: z.number(),
      }),
    );
    items.value = data.items;
    total.value = data.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header :class="styles.header">
      <div>
        <h1>人才库</h1>
        <p>可访问且授权有效的候选人档案</p>
      </div>
      <Button type="primary" @click="router.push('/ai-assistants/hr/resumes/upload')"
        >导入简历</Button
      >
    </header>
    <Alert v-if="error" type="error" :message="error" show-icon />
    <section class="talent-toolbar">
      <div class="talent-search">
        <Input
          v-model:value="query"
          aria-label="人才检索"
          placeholder="搜索姓名、标准技能或经历"
          @press-enter="
            page = 1;
            load();
          "
        /><Button
          type="primary"
          :loading="busy"
          @click="
            page = 1;
            load();
          "
          >搜索人才</Button
        >
      </div>
      <details>
        <summary>结构化筛选</summary>
        <label>标准技能<Input v-model:value="skill" /></label
        ><label>学历<Input v-model:value="education" /></label
        ><label>最低经验月数<input v-model="minMonths" type="number" min="0" /></label
        ><label>最高经验月数<input v-model="maxMonths" type="number" min="0" /></label
        ><label>排除已匹配岗位ID<Input v-model:value="excludedPosition" /></label
        ><label>词典版本<Input v-model:value="dictionaryVersion" /></label>
      </details>
    </section>
    <Button
      :disabled="!query.trim() || !items.length || items.length > 20 || semanticBusy"
      :loading="semanticBusy"
      @click="semanticOpen = true"
      >语义检索（需模型预算）</Button
    >
    <details>
      <summary>恢复已有语义检索</summary>
      <Input v-model:value="searchId" placeholder="检索任务ID" /><Button
        :disabled="!searchId"
        @click="readSearch"
        >只读恢复检索</Button
      >
    </details>
    <section v-if="semantic" class="talent-results">
      <div class="results-heading">
        <h2>语义检索相关度</h2>
        <span>{{ semantic.status }} · 非能力评分</span>
      </div>
      <article
        v-for="hit in semantic.hits"
        :key="hit.candidateId"
        style="padding: 16px 20px; border-bottom: 1px solid #edf0f5"
      >
        <b>{{ hit.candidateId }}</b>
        <p>
          {{ hit.status }} · 检索相关度 {{ hit.retrievalRelevance ?? '未生成' }} ·
          {{ hit.failureCode ?? '' }}
        </p>
        <blockquote v-for="match in hit.matches" :key="`${match.blockId}:${match.start}`">
          {{ match.quote
          }}<small> · {{ match.blockId }}（{{ match.start }}–{{ match.end }}）</small>
        </blockquote>
      </article>
    </section>
    <Modal
      v-model:open="semanticOpen"
      title="确认有费用语义检索"
      :confirm-loading="semanticBusy"
      @ok="semanticSearch"
      ><p>
        范围为当前有权可见的{{
          items.length
        }}位候选人，最多20位。使用有效模型预算；不输入身份或禁止属性。查询是招聘材料相关性，不生成候选人能力分。
      </p></Modal
    >
    <p class="scope-note">仅检索当前权限与保留期内的材料；检索命中不代表能力评分。</p>
    <p v-if="busy" role="status">正在检索授权人才…</p>
    <p v-else-if="!items.length && !error">暂无符合条件的授权人才。</p>
    <section class="talent-results">
      <div class="results-heading">
        <h2>授权人才档案</h2>
        <span>共 {{ total }} 位 · 按当前权限筛选</span>
      </div>
      <div style="overflow: auto">
        <table v-if="items.length" style="width: 100%; min-width: 650px">
          <thead>
            <tr>
              <th>候选人</th>
              <th>教育 / 经历</th>
              <th>标准技能</th>
              <th>保留期 / 更新</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.candidateId">
              <td>
                {{ item.name ?? '姓名未记录' }}
                <p>{{ item.snippet ?? '' }}</p>
                <small
                  v-if="item.retrievalRelevance !== null && item.retrievalRelevance !== undefined"
                  >检索相关度 {{ item.retrievalRelevance }}（非能力评分）</small
                >
              </td>
              <td>
                {{ item.education ?? '学历未记录' }} ·
                {{ item.experienceMonths === null ? '经验未记录' : `${item.experienceMonths}个月` }}
              </td>
              <td>
                <Tag v-for="skillName in item.skills" :key="skillName">{{ skillName }}</Tag
                ><span v-if="!item.skills.length">未归一</span>
              </td>
              <td>
                <span class="expiry">保留至 {{ beijing(item.expiresAt) }}</span
                ><Tag v-if="item.expiringWithin30Days" color="orange">即将到期</Tag
                ><Tag v-if="item.olderThan30Days">档案较旧</Tag
                ><small>{{ beijing(item.updatedAt) }} 更新（北京时间）</small>
              </td>
              <td>
                <Button @click="router.push(`/ai-assistants/hr/talent/${item.candidateId}`)"
                  >查看档案</Button
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pagination
        v-if="total"
        v-model:current="page"
        :total="total"
        :page-size="20"
        @change="load"
      />
    </section>
    <Button v-if="error" @click="load">重试读取</Button>
  </div>
</template>

<style scoped>
.talent-toolbar,
.talent-results {
  background: #fff;
  border: 1px solid var(--v1-border);
  border-radius: var(--v1-radius);
}
.talent-toolbar {
  padding: 18px 20px;
}
.talent-search {
  display: flex;
  gap: 10px;
  max-width: 760px;
}
.talent-search :deep(.ant-input) {
  flex: 1;
  min-width: 0;
}
.talent-search :deep(.ant-btn) {
  flex: none;
}
.talent-toolbar details {
  margin-top: 14px;
  color: var(--text-secondary);
}
.talent-toolbar details[open] {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.talent-toolbar summary {
  grid-column: 1/-1;
  cursor: pointer;
  font-size: 13px;
}
.talent-toolbar label {
  display: grid;
  gap: 5px;
  font-size: 12px;
}
.scope-note {
  color: var(--text-secondary);
  font-size: 12px;
  margin: 12px 2px;
}
.results-heading {
  padding: 17px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--v1-border);
}
.results-heading h2 {
  font-size: 16px;
  margin: 0;
}
.results-heading span {
  font-size: 12px;
  color: var(--text-secondary);
}
table {
  border-collapse: collapse;
  text-align: left;
}
th {
  background: #f6f8fc;
  color: #64748b;
  font-size: 12px;
  font-weight: 500;
  padding: 13px 20px;
}
td {
  padding: 20px;
  border-bottom: 1px solid #edf0f5;
  font-size: 13px;
  vertical-align: middle;
}
td:first-child {
  font-size: 15px;
  font-weight: 600;
}
td p,
td small {
  font-size: 12px;
  font-weight: 400;
  color: #64748b;
  margin: 6px 0;
  max-width: 240px;
}
td small,
.expiry {
  display: block;
  white-space: nowrap;
}
.expiry {
  margin-bottom: 6px;
}
td :deep(.ant-tag) {
  margin-top: 4px;
}
.talent-results :deep(.ant-pagination) {
  padding: 16px 20px;
  text-align: right;
}
@media (max-width: 700px) {
  .talent-toolbar {
    padding: 14px;
  }
  .talent-toolbar details[open] {
    grid-template-columns: 1fr;
  }
  .results-heading {
    padding: 14px;
    gap: 10px;
  }
  .results-heading span {
    max-width: 150px;
  }
  th,
  td {
    padding: 14px;
  }
  .talent-search {
    align-items: center;
  }
}
</style>
