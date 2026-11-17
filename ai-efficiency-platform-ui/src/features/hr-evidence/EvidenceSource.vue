<script setup lang="ts">
import { ref, nextTick, computed } from 'vue';
import { Button } from 'ant-design-vue';
const props = defineProps<{
  blocks: {
    id: string;
    page: number | null;
    text: string;
    section?: string | null;
    bbox?: [number, number, number, number] | null;
    paragraph?: number | null;
    ocrQuality?: number | null;
  }[];
  pageCount: number;
}>();
const page = ref(1);
const active = ref('');
const open = ref(false);
let trigger: HTMLElement | null = null;
const visible = computed(() =>
  props.blocks.filter((b) => b.page === null || b.page === page.value),
);
async function locate(ids: string[]) {
  const block = props.blocks.find((b) => ids.includes(b.id));
  if (!block) return;
  trigger = document.activeElement as HTMLElement;
  active.value = block.id;
  page.value = block.page ?? 1;
  open.value = window.matchMedia('(max-width: 700px)').matches;
  await nextTick();
  document.getElementById(`evidence-${block.id}`)?.focus();
}
function close() {
  open.value = false;
  trigger?.focus();
}
defineExpose({ locate });
</script>
<template>
  <aside
    class="source"
    :class="{ opened: open }"
    :role="open ? 'dialog' : undefined"
    :aria-modal="open || undefined"
    aria-label="原文证据"
    @keydown.esc="close"
  >
    <div class="toolbar">
      <h2>原文证据</h2>
      <Button v-if="open" @click="close">关闭原文</Button
      ><template v-if="pageCount > 0"
        ><Button :disabled="page <= 1" @click="page--">上一页</Button
        ><span>{{ page }} / {{ pageCount }}</span
        ><Button :disabled="page >= pageCount" @click="page++">下一页</Button></template
      >
    </div>
    <article class="paper">
      <section
        v-for="block in visible"
        :id="`evidence-${block.id}`"
        :key="block.id"
        tabindex="-1"
        :class="{ selected: active === block.id }"
      >
        <h3 v-if="block.section">{{ block.section }}</h3>
        <p>{{ block.text }}</p>
        <small
          >{{ block.page ? `第${block.page}页` : '文本段落' }} · {{ block.id
          }}<span v-if="block.paragraph"> · 段{{ block.paragraph }}</span
          ><span v-if="block.bbox"> · 原件坐标{{ block.bbox.join(', ') }}</span></small
        >
      </section>
      <p v-if="!visible.length">暂无可核验原文。</p>
    </article>
  </aside>
</template>
<style scoped>
.source {
  background: #ffffffa8;
  border: 1px solid #dde4f2;
  border-radius: 8px;
  padding: 12px;
  min-width: 0;
}
.toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar h2 {
  font-size: 17px;
  margin: 0 auto 0 0;
}
.paper {
  background: white;
  padding: 20px;
  max-height: 660px;
  overflow: auto;
}
.paper section {
  padding: 10px;
  margin: 10px 0;
  white-space: pre-wrap;
}
.selected {
  background: #fff4d0;
  outline: 2px solid #ffb94a;
}
small {
  color: #59657b;
}
@media (max-width: 700px) {
  .source {
    display: none;
  }
  .source.opened {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 1100;
    border-radius: 0;
    background: #f5f7fb;
  }
  .paper {
    max-height: calc(100dvh - 100px);
  }
}
</style>
