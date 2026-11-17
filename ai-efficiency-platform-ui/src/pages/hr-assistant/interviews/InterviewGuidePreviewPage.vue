<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useRoute } from 'vue-router';
import { Alert, Button, Checkbox, Modal, Select } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest, hrWrite } from '../../../entities/hr';
import { guideSchema, exportSchema } from '../../../entities/hr/completion';
import styles from './InterviewGuidePreviewPage.module.css';
const route = useRoute();
const guide = ref<z.infer<typeof guideSchema>>();
const job = ref<z.infer<typeof exportSchema>>();
const format = ref<'PDF' | 'WORD'>('PDF');
const busy = ref(false);
const contactExport = ref(false);
const contactConfirm = ref(false);
const exportPending = ref(false);
let polls = 0;
const error = ref('');
let timer: ReturnType<typeof setTimeout> | undefined;
async function load() {
  const id = route.query.questionSetId;
  if (!id) return;
  busy.value = true;
  error.value = '';
  try {
    guide.value = await hrRequest(
      `/interview-sets/${encodeURIComponent(String(id))}/preview`,
      guideSchema,
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取失败';
  } finally {
    busy.value = false;
  }
}
async function poll() {
  if (!job.value) return;
  try {
    job.value = await hrRequest(`/exports/${job.value.id}`, exportSchema);
    if (!['SUCCEEDED', 'READY', 'FAILED', 'BLOCKED'].includes(job.value.status) && polls++ < 120)
      timer = setTimeout(poll, 2000);
    else exportPending.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : '读取导出失败';
  }
}
async function generate() {
  if (!guide.value || busy.value || exportPending.value) return;
  if (contactExport.value && !contactConfirm.value) {
    contactConfirm.value = true;
    return;
  }
  contactConfirm.value = false;
  polls = 0;
  busy.value = true;
  error.value = '';
  try {
    job.value = await hrWrite('/exports', exportSchema, {
      setId: guide.value.setId,
      setVersion: guide.value.version,
      format: format.value,
      assignmentId: null,
      includeContact: contactExport.value,
    });
    if (!job.value.grantId) {
      exportPending.value = true;
      await poll();
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '导出失败';
  } finally {
    busy.value = false;
  }
}
onMounted(load);
onBeforeUnmount(() => clearTimeout(timer));
</script>
<template>
  <div :class="[styles.page, 'ui-page']">
    <header>
      <h1>面试提纲 · A4预览</h1>
      <p>预览与导出使用同一安全数据，不包含评分、排名、联系方式或原始附件。</p>
    </header>
    <Alert v-if="error" type="error" :message="error" show-icon /><Button v-if="error" @click="load"
      >重试读取</Button
    >
    <p v-if="!route.query.questionSetId">请选择真实题集后预览。</p>
    <template v-if="guide"
      ><div class="export-toolbar">
        <Select
          v-model:value="format"
          :options="[
            { value: 'PDF', label: 'PDF' },
            { value: 'WORD', label: 'Word' },
          ]"
          style="width: 120px"
        /><Checkbox v-model:checked="contactExport">HR联系版（敏感用途单独授权）</Checkbox
        ><Button type="primary" :loading="busy || exportPending" @click="generate">{{
          contactExport ? '申请HR联系版导出' : '生成安全版导出'
        }}</Button
        ><a
          v-if="job?.grantId"
          :href="`/api/hr/downloads/${encodeURIComponent(job.grantId)}`"
          download
          >下载一次性文件</a
        ><span v-if="job">{{ job.status }} {{ job.failureCode ?? '' }}</span>
      </div>
      <article class="a4">
        <h1>{{ guide.positionName }} · 面试提纲</h1>
        <p>题集版本 {{ guide.version }}</p>
        <section v-for="(question, index) in guide.questions" :key="question.id">
          <h2>{{ index + 1 }}. {{ question.title }}（{{ question.minutes }}分钟）</h2>
          <p>{{ question.purpose }}</p>
          <p v-for="point in question.answerPoints" :key="point">{{ point }}</p>
          <p v-for="follow in question.followUps" :key="follow">追问：{{ follow }}</p>
          <p>来源：{{ question.sourceType === 'REQUIREMENT' ? '岗位要求' : '简历待核实' }}</p>
          <div style="height: 70px; border-bottom: 1px solid #ddd">记录：</div>
        </section>
        <section v-for="(section, index) in guide.resumeSections" :key="index">
          <h2>{{ section.kind }}</h2>
          <p style="white-space: pre-wrap">{{ section.text }}</p>
        </section>
        <footer>{{ guide.disclaimer }}</footer>
      </article></template
    ><Modal v-model:open="contactConfirm" title="确认导出HR联系版" @ok="generate"
      ><p>
        联系版与面试官安全版分开，包含敏感联系方式并记录审计。仅在服务端确认权限与身份服务就绪后生成。
      </p></Modal
    >
  </div>
</template>
<style scoped>
.export-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 20px;
  background: #ffffffa8;
  border: 1px solid #dde4f2;
  border-radius: 8px;
  margin-bottom: 20px;
}
.a4 {
  width: min(100%, 794px);
  box-sizing: border-box;
  min-height: 1123px;
  padding: 48px;
  background: white;
  margin: auto;
  box-shadow: 0 2px 12px #22335520;
}
.a4 section {
  break-inside: avoid;
  margin: 25px 0;
}
.a4 h2 {
  font-size: 18px;
}
@media (max-width: 700px) {
  .a4 {
    padding: 20px;
    min-height: 0;
  }
}
@media print {
  .a4 {
    box-shadow: none;
    width: 210mm;
    padding: 15mm;
  }
}
</style>
