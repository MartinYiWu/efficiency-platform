<script setup lang="ts">
import { CopyOutlined, DownloadOutlined, EyeOutlined } from '@ant-design/icons-vue';
import { message } from 'ant-design-vue';
import { artifactUrl } from '../operation-chat/api';
import type { OperationArtifactSummary } from '../operation-chat/types';
const props = defineProps<{ artifact: OperationArtifactSummary; baseUrl: string }>();
async function copy() {
  try {
    const response = await fetch(artifactUrl(props.baseUrl, props.artifact.artifactId, 'copy'));
    if (!response.ok) throw new Error('copy failed');
    const content = await response.text();
    if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
    await navigator.clipboard.writeText(content);
    message.success('已复制成稿');
  } catch {
    message.error('复制失败，请使用下载功能');
  }
}
function preview() {
  window.open(
    artifactUrl(props.baseUrl, props.artifact.artifactId, 'wechat-html'),
    '_blank',
    'noopener,noreferrer',
  );
}
</script>
<template>
  <a-space
    wrap
    :aria-label="`${artifact.platform === 'wechat_official_account' ? '公众号' : '平台'}文章操作`"
    ><a-button @click="copy"
      ><template #icon><CopyOutlined /></template>复制成稿</a-button
    ><a-button v-if="artifact.platform === 'wechat_official_account'" @click="preview"
      ><template #icon><EyeOutlined /></template>微信预览</a-button
    ><a-button download :href="artifactUrl(baseUrl, artifact.artifactId, 'download')"
      ><template #icon><DownloadOutlined /></template>下载 Markdown</a-button
    ></a-space
  >
</template>
