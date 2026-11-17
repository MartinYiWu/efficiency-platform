<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { message } from 'ant-design-vue';
import type { RunReplay } from '../../entities/ai-center/model';
import { parseRetrievalFacts } from '../../entities/ai-center/schemas';
import { getRunReplay } from '../../features/ai-center/api';
import { aiStatusLabel, answerModeLabel } from '../../features/ai-center/presentation';
import { formatAiDate } from './datePresentation';
import RetrievalEvidence from '../../features/ai-center/RetrievalEvidence.vue';
import AiWorkspaceSection from './AiWorkspaceSection.vue';
import './ai-center.css';
const route = useRoute(),
  router = useRouter(),
  replay = ref<RunReplay>();
watch(
  () => route.params.runId,
  async () => {
    try {
      replay.value = await getRunReplay(String(route.params.runId ?? ''));
    } catch (error) {
      message.error((error as Error).message);
    }
  },
  { immediate: true },
);
const stages = computed(() =>
  [...(replay.value?.stages ?? [])].sort((a, b) => a.sequenceNo - b.sequenceNo),
);
const facts = computed(() =>
  stages.value
    .map((stage) => parseRetrievalFacts(stage.internalPayload))
    .find((item) => item !== null),
);
const columns = [
  { title: '#', dataIndex: 'citationNo' },
  { title: '文档', dataIndex: 'documentTitle' },
  { title: '版本', dataIndex: 'versionNo' },
  { title: '章节', dataIndex: 'sectionPath' },
  { title: '引用原文', dataIndex: 'quotedText' },
  { title: '引用类型', key: 'type' },
  { title: '原文偏移', key: 'spans' },
];
</script>
<template>
  <section v-if="replay" class="ui-page ai-page">
    <header class="ui-header">
      <div>
        <a-button type="link" @click="router.push('/ai-center/runs')">返回运行列表</a-button>
        <h2>Run 回放</h2>
      </div>
    </header>
    <div class="ui-card">
      <a-descriptions :column="{ xs: 1, sm: 2, lg: 4 }"
        ><a-descriptions-item label="Run ID">{{ replay.run.id }}</a-descriptions-item
        ><a-descriptions-item label="状态"
          ><a-tag>{{ aiStatusLabel(replay.run.status) }}</a-tag></a-descriptions-item
        ><a-descriptions-item label="回答模式">{{
          replay.run.answerMode ? answerModeLabel(replay.run.answerMode) : '-'
        }}</a-descriptions-item
        ><a-descriptions-item label="Agent Release">{{
          replay.run.agentReleaseId
        }}</a-descriptions-item></a-descriptions
      ><AiWorkspaceSection title="问题"
        ><div class="ai-pre">{{ replay.question.content }}</div></AiWorkspaceSection
      ><AiWorkspaceSection title="结构化阶段"
        ><a-empty v-if="stages.length === 0" description="该版本未记录公开阶段" /><a-timeline
          ><a-timeline-item
            v-for="stage in stages"
            :key="stage.sequenceNo"
            :color="
              stage.status === 'FAILED' ? 'red' : stage.status === 'SUCCEEDED' ? 'green' : 'blue'
            "
            ><strong>{{ stage.stage }}</strong> <a-tag>{{ aiStatusLabel(stage.status) }}</a-tag>
            <p>{{ stage.publicSummary ?? '该版本未记录' }}</p>
            <span v-if="stage.startedAt" class="ai-muted"
              >{{ formatAiDate(stage.startedAt)
              }}{{ stage.finishedAt ? ` → ${formatAiDate(stage.finishedAt)}` : '' }}</span
            ></a-timeline-item
          ></a-timeline
        ></AiWorkspaceSection
      ><AiWorkspaceSection v-if="replay.answer" title="最终回答"
        ><div class="ai-pre">{{ replay.answer.content }}</div></AiWorkspaceSection
      ><AiWorkspaceSection title="检索证据回放"
        ><RetrievalEvidence v-if="facts" :facts="facts" /><template v-else
          >该版本未记录</template
        ></AiWorkspaceSection
      ><AiWorkspaceSection title="引用闭包"
        ><a-table
          row-key="id"
          :data-source="replay.citations"
          :columns="columns"
          :pagination="{ pageSize: 10, hideOnSinglePage: true }"
          :scroll="{ x: 680 }"
          ><template #bodyCell="{ column, record }"
            ><template v-if="column.key === 'type'">{{
              record.citationType === 'EXTRACTED_SPANS'
                ? '原文节选'
                : record.citationType === 'FULL_PARENT'
                  ? '完整原文'
                  : '该版本未记录'
            }}</template
            ><template v-else-if="column.key === 'spans'">{{
              record.originalSpans
                ?.map((span: any) => `[${span.start_offset}, ${span.end_offset})`)
                .join('；') ?? '该版本未记录'
            }}</template></template
          ></a-table
        ></AiWorkspaceSection
      ><AiWorkspaceSection
        v-if="replay.run.failureMessage"
        :title="replay.run.failureCode ?? '运行失败'"
        >{{ replay.run.failureMessage }}</AiWorkspaceSection
      >
    </div>
  </section>
  <a-empty v-else description="正在加载运行事实" />
</template>
