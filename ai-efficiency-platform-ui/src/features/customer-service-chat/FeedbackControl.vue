<script setup lang="ts">
import { ref } from 'vue';
import { message } from 'ant-design-vue';
import { LikeOutlined, DislikeOutlined } from '@ant-design/icons-vue';
import { submitFeedback } from './api';
const props = defineProps<{ messageId: string }>();
const open = ref(false);
const reasonCode = ref<string>();
const comment = ref('');
const options = [
  { value: 'INCORRECT', label: '内容错误' },
  { value: 'OUTDATED', label: '内容过期' },
  { value: 'MISSING_CITATION', label: '缺少依据' },
  { value: 'IRRELEVANT', label: '答非所问' },
  { value: 'UNCLEAR', label: '表达不清楚' },
  { value: 'OTHER', label: '其他' },
];
async function up() {
  try {
    await submitFeedback(props.messageId, { rating: 'UP', reasonCode: null, comment: null });
    message.success('感谢反馈');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '提交失败');
  }
}
async function down() {
  if (!reasonCode.value || (reasonCode.value === 'OTHER' && !comment.value.trim())) {
    message.warning(reasonCode.value === 'OTHER' ? '请填写具体问题' : '请选择原因');
    return;
  }
  try {
    await submitFeedback(props.messageId, {
      rating: 'DOWN',
      reasonCode: reasonCode.value,
      comment: comment.value.trim() || null,
    });
    message.success('反馈已提交');
    open.value = false;
  } catch (error) {
    message.error(error instanceof Error ? error.message : '提交失败');
  }
}
</script>
<template>
  <a-space
    ><a-button type="text" aria-label="回答有帮助" @click="up"
      ><template #icon><LikeOutlined /></template></a-button
    ><a-button type="text" aria-label="回答无帮助" @click="open = true"
      ><template #icon><DislikeOutlined /></template></a-button></a-space
  ><a-modal v-model:open="open" title="这个回答有什么问题？" @ok="down"
    ><a-space direction="vertical" class="feedback-form"
      ><a-select
        v-model:value="reasonCode"
        placeholder="选择原因"
        :options="options"
        class="reason" /><a-textarea
        v-if="reasonCode === 'OTHER'"
        v-model:value="comment"
        :rows="4"
        placeholder="请说明具体问题" /></a-space
  ></a-modal>
</template>
<style scoped>
.feedback-form,
.reason {
  width: 100%;
}
</style>
