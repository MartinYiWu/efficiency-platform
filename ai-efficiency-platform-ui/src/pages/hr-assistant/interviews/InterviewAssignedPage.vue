<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { Alert, Button } from 'ant-design-vue';
import { z } from 'zod';
import { hrRequest } from '../../../entities/hr';
import { guideSchema } from '../../../entities/hr/completion';
const route = useRoute();
const guide = ref<z.infer<typeof guideSchema>>();
const error = ref('');
const busy = ref(false);
async function load() {
  guide.value = undefined;
  busy.value = true;
  error.value = '';
  try {
    guide.value = await hrRequest(
      `/interview-assignments/${encodeURIComponent(String(route.params.assignmentId))}/view`,
      guideSchema,
      { cache: 'no-store' },
    );
  } catch (e) {
    error.value = e instanceof Error ? e.message : '指派读取失败';
  } finally {
    busy.value = false;
  }
}
onMounted(load);
</script>
<template>
  <div class="ui-page">
    <h1>面试官提纲</h1>
    <Alert v-if="error" type="error" :message="error" show-icon /><Button
      :loading="busy"
      @click="load"
      >重新验证指派</Button
    ><template v-if="guide"
      ><h2>{{ guide.positionName }}</h2>
      <p>题集版本 {{ guide.version }}</p>
      <article v-for="question in guide.questions" :key="question.id" class="question">
        <h2>{{ question.title }}</h2>
        <p>{{ question.purpose }}</p>
        <p>
          预计 {{ question.minutes }} 分钟 ·
          {{ question.sourceType === 'REQUIREMENT' ? '岗位要求' : '简历待核实' }}
        </p>
        <ul>
          <li v-for="point in question.answerPoints" :key="point">{{ point }}</li>
        </ul>
        <p v-for="follow in question.followUps" :key="follow">追问：{{ follow }}</p>
        <p>充分回答：{{ question.references.excellent }}</p>
        <p>基本回答：{{ question.references.qualified }}</p>
        <p>待核实：{{ question.references.needsVerification }}</p>
      </article>
      <section v-for="(section, index) in guide.resumeSections" :key="index">
        <h2>{{ section.kind }}</h2>
        <p>{{ section.text }}</p>
      </section>
      <p>{{ guide.disclaimer }}</p></template
    >
  </div>
</template>
<style scoped>
.ui-page {
  max-width: 980px;
  margin: auto;
  color: #334155;
}
.ui-page > h1 {
  font-size: 24px;
  margin-bottom: 8px;
}
.ui-page > h2 {
  font-size: 19px;
}
.ui-page > p {
  font-size: 13px;
  color: #64748b;
}
.question h2 {
  font-size: 17px;
  margin: 0 0 10px;
}
.question p,
.question li {
  font-size: 14px;
  line-height: 1.8;
}
.question {
  background: #ffffffa8;
  border: 1px solid #dde4f2;
  border-radius: 8px;
  padding: 20px;
  margin: 16px 0;
}
</style>
