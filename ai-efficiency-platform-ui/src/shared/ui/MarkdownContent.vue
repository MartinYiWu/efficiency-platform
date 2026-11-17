<script setup lang="ts">
import { computed } from 'vue';
import MarkdownIt from 'markdown-it';

const props = defineProps<{ content: string }>();
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true });
const defaultLink = markdown.renderer.rules.link_open;
markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  const token = tokens[index];
  const href = token.attrGet('href');
  let safe = false;
  try {
    const url = new URL(href ?? '');
    safe = url.protocol === 'https:' && !!url.hostname && !url.username && !url.password;
  } catch {
    /* 非公开 HTTPS 地址只展示文字。 */
  }
  if (!safe) token.attrSet('href', '');
  token.attrSet('target', '_blank');
  token.attrSet('rel', 'noopener noreferrer');
  return defaultLink
    ? defaultLink(tokens, index, options, env, self)
    : self.renderToken(tokens, index, options);
};
markdown.renderer.rules.image = (tokens, index) => markdown.utils.escapeHtml(tokens[index].content);
const html = computed(() =>
  markdown
    .render(props.content)
    .replace(/<a\b[^>]*href=""[^>]*>([\s\S]*?)<\/a>/g, '<span>$1</span>'),
);
</script>

<template><div class="markdown-content" v-html="html" /></template>

<style scoped>
.markdown-content {
  color: #111827;
  font-size: 14px;
  line-height: 1.78;
  white-space: normal;
  word-break: break-word;
}

.markdown-content :deep(p) {
  margin: 0 0 12px;
}

.markdown-content :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-content :deep(strong) {
  color: #0f172a;
  font-weight: 700;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4) {
  margin: 16px 0 8px;
  color: #0f172a;
  font-weight: 700;
  line-height: 1.35;
}

.markdown-content :deep(h1) {
  font-size: 18px;
}

.markdown-content :deep(h2) {
  font-size: 17px;
}

.markdown-content :deep(h3),
.markdown-content :deep(h4) {
  font-size: 15px;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  margin: 8px 0 12px;
  padding-left: 22px;
}

.markdown-content :deep(li) {
  margin: 4px 0;
  padding-left: 2px;
}

.markdown-content :deep(blockquote) {
  margin: 12px 0;
  padding: 8px 12px;
  color: #475569;
  background: #f8fafc;
  border-left: 3px solid #93c5fd;
  border-radius: 6px;
}

.markdown-content :deep(code) {
  padding: 2px 5px;
  color: #1d4ed8;
  background: #eff6ff;
  border-radius: 4px;
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
}

.markdown-content :deep(pre) {
  margin: 12px 0;
  padding: 12px;
  overflow: auto;
  color: #e5e7eb;
  background: #111827;
  border-radius: 8px;
}

.markdown-content :deep(pre code) {
  padding: 0;
  color: inherit;
  background: transparent;
}

.markdown-content :deep(a) {
  color: #1677ff;
  text-decoration: none;
}

.markdown-content :deep(a:hover) {
  text-decoration: underline;
}

.markdown-content :deep(table) {
  width: 100%;
  margin: 12px 0;
  border-collapse: collapse;
  font-size: 13px;
}

.markdown-content :deep(th),
.markdown-content :deep(td) {
  padding: 8px 10px;
  border: 1px solid #e5e7eb;
}

.markdown-content :deep(th) {
  color: #334155;
  background: #f8fafc;
  font-weight: 700;
}

.markdown-content.failed {
  color: #7f1d1d;
}

.markdown-content {
  min-width: 0;
  overflow-wrap: anywhere;
}
.markdown-content :deep(pre),
.markdown-content :deep(table) {
  max-width: 100%;
  overflow-x: auto;
}
</style>
