<script setup lang="ts">
import { computed } from 'vue';
import type {
  ActionPlanViewModel,
  DiagnosisViewModel,
  RetrospectiveViewModel,
} from '../../entities/operation-deliverable';
import styles from './OperationDelivery.module.css';
const props = defineProps<{
  deliverable: ActionPlanViewModel | DiagnosisViewModel | RetrospectiveViewModel;
}>();
const priority = { high: '高优先级', medium: '中优先级', low: '低优先级' };
const order = { high: 0, medium: 1, low: 2 };
const findings = computed(() =>
  props.deliverable.kind === 'diagnosis'
    ? [...props.deliverable.content.findings].sort((a, b) => order[a.priority] - order[b.priority])
    : [],
);
const retro = computed(() => {
  if (props.deliverable.kind !== 'retrospective') return [];
  const c = props.deliverable.content;
  return [
    { label: '目标', values: c.objectives },
    { label: '结果', values: c.outcomes },
    { label: '差距', values: c.gaps },
    { label: '原因', values: c.causes },
    { label: '下一步', values: c.next_steps },
  ];
});
</script>
<template>
  <article :class="styles.deliveryDocument" :aria-labelledby="`structured-${deliverable.id}`">
    <header>
      <h2 :id="`structured-${deliverable.id}`">{{ deliverable.title }}</h2>
      <p :class="styles.documentLead">{{ deliverable.lead }}</p>
    </header>
    <template v-if="deliverable.kind === 'action_plan'"
      ><section :class="styles.structuredSummary">
        <div>
          <strong>行动目标</strong>
          <p>{{ deliverable.content.goal }}</p>
        </div>
        <div>
          <strong>目标受众</strong>
          <p>{{ deliverable.content.audience }}</p>
        </div>
      </section>
      <section :class="styles.structuredSections" aria-label="执行阶段">
        <h3>执行阶段</h3>
        <section
          v-for="phase in deliverable.content.phases"
          :key="phase.phase_id"
          :class="styles.actionPhase"
        >
          <h3>{{ phase.title }}</h3>
          <div>
            <strong>行动</strong>
            <ul v-if="phase.actions.length">
              <li v-for="item in phase.actions" :key="item">{{ item }}</li>
            </ul>
            <span v-else>未提供</span>
          </div>
          <div>
            <strong>阶段指标</strong>
            <ul v-if="phase.metrics.length">
              <li v-for="item in phase.metrics" :key="item">{{ item }}</li>
            </ul>
            <span v-else>未提供</span>
          </div>
        </section>
      </section>
      <section
        v-for="section in [
          { label: '整体指标', values: deliverable.content.metrics },
          { label: '前提假设', values: deliverable.content.assumptions },
        ]"
        :key="section.label"
        :class="styles.structuredSections"
        :aria-label="section.label"
      >
        <h3>{{ section.label }}</h3>
        <ul v-if="section.values.length">
          <li v-for="item in section.values" :key="item">{{ item }}</li>
        </ul>
        <span v-else>未提供</span>
      </section></template
    >
    <template v-else-if="deliverable.kind === 'diagnosis'"
      ><section aria-label="诊断发现" :class="styles.diagnosisFindings">
        <section
          v-for="finding in findings"
          :key="finding.finding_id"
          :class="styles.diagnosisFinding"
        >
          <h3>{{ finding.title }}</h3>
          <a-tag>{{ priority[finding.priority] }}</a-tag>
          <div>
            <strong>证据</strong>
            <ul v-if="finding.evidence.length">
              <li v-for="item in finding.evidence" :key="item">{{ item }}</li>
            </ul>
            <span v-else>未提供</span>
          </div>
          <div>
            <strong>判断与建议</strong>
            <p>{{ finding.recommendation }}</p>
          </div>
        </section>
      </section>
      <section :class="styles.structuredSections" aria-label="数据缺口">
        <h4>数据缺口</h4>
        <ul v-if="deliverable.content.data_gaps.length">
          <li v-for="item in deliverable.content.data_gaps" :key="item">{{ item }}</li>
        </ul>
        <span v-else>未提供</span>
      </section></template
    >
    <template v-else
      ><section
        v-for="section in retro"
        :key="section.label"
        :class="styles.structuredSections"
        :aria-label="section.label"
      >
        <h3>{{ section.label }}</h3>
        <ul v-if="section.values.length">
          <li v-for="item in section.values" :key="item">{{ item }}</li>
        </ul>
        <span v-else>未提供</span>
      </section></template
    >
  </article>
</template>
