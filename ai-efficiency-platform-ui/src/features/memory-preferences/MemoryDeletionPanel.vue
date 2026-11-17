<script setup lang="ts">
import { computed, inject, toRef, watch } from 'vue';
import {
  createMemoryApi,
  fieldLabels,
  fieldValues,
  memoryAccessTokenKey,
  valueLabels,
  type MemoryPreference,
  type MemoryScope,
} from '../../entities/memory';
import { useMemoryDeletion } from './useMemoryDeletion';
const props = defineProps<{
  scope: MemoryScope;
  target?: MemoryPreference;
  jobId?: string;
  authorizationVersion?: number;
}>();
const emit = defineEmits<{
  revoked: [itemId: string, jobId: string];
  restored: [item: MemoryPreference];
  cleared: [];
  denied: [];
}>();
const token = inject(memoryAccessTokenKey, () => undefined);
const {
  task,
  target,
  busy,
  error,
  success,
  complete,
  relearnField,
  relearnValue,
  choose,
  cancel,
  forget,
  refresh,
  reauthorize,
  reset,
} = useMemoryDeletion(
  toRef(props, 'scope'),
  createMemoryApi(token),
  token,
  (id, job) => emit('revoked', id, job),
  (item) => emit('restored', item),
  () => emit('denied'),
);
const fields = Object.entries(fieldLabels).map(([value, label]) => ({ value, label }));
const reconfigured = computed(
  () =>
    task.value?.status === 'LIVE' &&
    task.value.jobStatus === 'SUCCEEDED' &&
    task.value.completedTargets === task.value.requiredTargets,
);
const values = computed(() =>
  relearnField.value
    ? fieldValues[relearnField.value].map((value) => ({ value, label: valueLabels[value] }))
    : [],
);
watch(
  () => props.target,
  (item) => {
    if (item) choose(item);
  },
  { immediate: true, flush: 'sync' },
);
watch(
  () => props.jobId,
  (jobId) => {
    if (jobId && jobId !== task.value?.jobId) void refresh(jobId);
  },
  { immediate: true },
);
watch(() => props.authorizationVersion, reset, { flush: 'sync' });
function cancelForget() {
  cancel();
  emit('cleared');
}
</script>
<template>
  <section
    v-if="target || task || error || success"
    class="ui-card deletion-panel"
    aria-label="偏好遗忘任务"
  >
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <a-alert v-if="success" type="success" :message="success" show-icon />
    <template v-if="target"
      ><h3>忘记并停止自动记住此偏好</h3>
      <p>
        确认后，此偏好将立即停止使用，并开始清理相关记录。之后只有你明确选择“重新允许记住”才能再次启用。
      </p>
      <a-space wrap
        ><a-button danger type="primary" :loading="busy" @click="forget">确认忘记</a-button
        ><a-button :disabled="busy" @click="cancelForget">取消</a-button></a-space
      ></template
    >
    <template v-if="task">
      <h3>
        {{
          reconfigured
            ? '该次清理已完成，偏好已重新设置'
            : complete
              ? '已清理'
              : ['DELETE_PENDING', 'DELETED'].includes(task.status)
                ? '清理中，尚未全部确认'
                : '状态暂无法确认'
        }}
      </h3>
      <p v-if="reconfigured">
        这项偏好已有新的设置，此前清理任务不会恢复旧版本。请返回记忆中心查看当前偏好。
      </p>
      <p v-else-if="complete">必要清理步骤均已确认。自动记住仍处于关闭状态。</p>
      <p v-else-if="['DELETE_PENDING', 'DELETED'].includes(task.status)">
        相关偏好已停止使用。仍有外部清理步骤未确认，暂不能认定已彻底删除。
      </p>
      <p v-if="task.jobStatus === 'BLOCKED'">清理暂时受阻，请稍后刷新状态。</p>
      <p
        v-else-if="
          !['SUCCEEDED', 'PENDING', 'RUNNING'].includes(task.jobStatus) ||
          (!reconfigured && !['DELETE_PENDING', 'DELETED'].includes(task.status))
        "
      >
        当前状态暂无法确认，请刷新或联系管理员。
      </p>
      <p>已确认 {{ task.completedTargets }} / {{ task.requiredTargets }} 项清理步骤</p>
      <a-button :loading="busy" @click="refresh()">刷新清理状态</a-button>
      <a-form
        v-if="complete"
        layout="vertical"
        :model="{ relearnField, relearnValue }"
        class="relearn-form"
        @finish="reauthorize"
      >
        <h3>重新允许记住</h3>
        <p>请选择要重新授权的原偏好字段和值。这会新建偏好，已清理的旧版本不会恢复。</p>
        <a-form-item label="重新授权的字段" html-for="relearn-field"
          ><a-select
            id="relearn-field"
            v-model:value="relearnField"
            :options="fields"
            placeholder="请选择原偏好字段"
            :disabled="busy"
        /></a-form-item>
        <a-form-item label="新的偏好值" html-for="relearn-value"
          ><a-select
            id="relearn-value"
            v-model:value="relearnValue"
            :options="values"
            :disabled="busy || !relearnField"
            placeholder="请选择偏好值"
        /></a-form-item>
        <a-button
          type="primary"
          html-type="submit"
          :loading="busy"
          :disabled="!relearnField || !relearnValue"
          >重新允许记住</a-button
        >
      </a-form>
    </template>
  </section>
</template>
<style scoped>
.deletion-panel {
  padding: 24px;
  min-width: 0;
}
.deletion-panel :deep(.ant-alert) {
  margin-bottom: 16px;
}
.relearn-form {
  margin-top: 24px;
  max-width: 420px;
}
.relearn-form :deep(.ant-select) {
  width: 100%;
}
@media (max-width: 600px) {
  .deletion-panel {
    padding: 16px;
  }
}
</style>
