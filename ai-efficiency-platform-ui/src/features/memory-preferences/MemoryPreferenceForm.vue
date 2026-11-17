<script setup lang="ts">
import { computed } from 'vue';
import { fieldValues, fieldLabels, valueLabels, type MemoryField } from '../../entities/memory';
defineProps<{ editing: boolean; saving: boolean; disabled: boolean }>();
const field = defineModel<MemoryField>('field', { required: true });
const value = defineModel<string>('value', { required: true });
defineEmits<{ save: []; cancel: [] }>();
const fields = Object.entries(fieldLabels).map(([value, label]) => ({ value, label }));
const values = computed(() =>
  fieldValues[field.value].map((value) => ({ value, label: valueLabels[value] })),
);
</script>
<template>
  <a-form layout="vertical" :model="{ field, value }" @finish="$emit('save')">
    <a-form-item label="偏好字段" html-for="memory-field"
      ><a-select
        id="memory-field"
        v-model:value="field"
        :options="fields"
        :disabled="editing || saving || disabled"
    /></a-form-item>
    <a-form-item label="偏好值" html-for="memory-value"
      ><a-select
        id="memory-value"
        v-model:value="value"
        :options="values"
        :disabled="saving || disabled"
    /></a-form-item>
    <a-space wrap
      ><a-button type="primary" html-type="submit" :loading="saving" :disabled="disabled">{{
        editing ? '保存更正' : '保存偏好'
      }}</a-button
      ><a-button v-if="editing" :disabled="saving" @click="$emit('cancel')"
        >取消更正</a-button
      ></a-space
    >
  </a-form>
</template>
