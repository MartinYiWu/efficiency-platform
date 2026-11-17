<script setup lang="ts">
import { computed } from 'vue';
import type { parseRetrievalFacts } from '../../entities/ai-center/schemas';
type Facts = NonNullable<ReturnType<typeof parseRetrievalFacts>>;
const props = defineProps<{ facts: Facts }>(),
  pack = computed(() => props.facts.evidence_pack),
  absent = '该版本未记录';
const budgetFields = [
  ['上下文预算', 'context_token_limit'],
  ['实际使用 Token', 'used_tokens'],
  ['预留 Token', 'reserved_tokens'],
  ['固定输入 Token', 'fixed_input_tokens'],
  ['证据 Token', 'evidence_tokens'],
  ['输出预留 Token', 'output_tokens'],
  ['中间输出 Token', 'intermediate_output_tokens'],
  ['安全余量 Token', 'safety_tokens'],
] as const;
</script>
<template>
  <div class="ai-facts">
    <a-card size="small" title="等价分组与未合并原因"
      ><template v-if="facts.equivalence_decisions == null">{{ absent }}</template
      ><template v-else-if="facts.equivalence_decisions.length === 0">无候选对</template>
      <div v-for="(item, index) in facts.equivalence_decisions" v-else :key="index">
        <p>
          {{ item.left.chunk_id }} / {{ item.right.chunk_id }} · 相似度 {{ item.similarity }} ·
          {{ item.reason }}
        </p>
        <p>
          保留父片段：{{ item.retained_parent_id ?? '未合并' }}；合并候选：{{
            item.merged_chunk_ids.join('、') || '无'
          }}
        </p>
        <p v-if="item.result">
          {{ item.result.verdict }}：{{ item.result.left_quote }} /
          {{ item.result.right_quote }}；{{ item.result.differing_conditions.join('；') }}
        </p>
      </div>
      <p>判断错误：{{ facts.equivalence_errors?.join('；') ?? absent }}</p></a-card
    ><a-card size="small" title="版本过滤与相邻组装"
      ><p>旧版过滤计数：{{ facts.version_exclusions?.length ?? absent }}</p>
      <p v-for="(item, index) in facts.version_exclusions" :key="index">
        {{ item.chunk_id }} · {{ item.document_version_id }} · {{ item.index_release_id }} ·
        {{ item.reason }}
      </p>
      <p>最终待装配父片段：{{ facts.final_parent_candidates?.join('、') ?? absent }}</p>
      <p>
        相邻组成员：{{
          facts.evidence_groups?.map((group) => group.parent_ids.join(' → ')).join('；') ?? absent
        }}
      </p>
      <p v-for="(item, index) in facts.grouping_decisions" :key="index">
        {{ item.parent_id }}：{{ item.reason }}
      </p></a-card
    ><a-card size="small" title="冲突配对与准确摘录"
      ><template v-if="facts.conflict_screen == null">{{ absent }}</template
      ><template v-else
        ><p>阻断回答：{{ facts.conflict_screen.blocked ? '是' : '否' }}</p>
        <div v-for="(pair, index) in facts.conflict_screen.pairs" :key="index">
          <p>
            {{ pair.left_parent_id }} / {{ pair.right_parent_id }}：{{ pair.verdict }} ·
            同一范围：{{ pair.same_scope ? '是' : '否' }}
          </p>
          <blockquote>{{ pair.left_quote }}</blockquote>
          <blockquote>{{ pair.right_quote }}</blockquote>
          <p>{{ pair.reason }}</p>
        </div>
        <p>核验错误：{{ facts.conflict_screen.errors.join('；') || '无' }}</p></template
      ></a-card
    ><a-card size="small" title="冻结 EvidencePack、预算与实际模型"
      ><template v-if="!pack">{{ absent }}</template
      ><template v-else
        ><a-descriptions size="small" :column="{ xs: 1, sm: 2, lg: 3 }"
          ><a-descriptions-item label="实际模型">{{
            pack.model_policy.model_name
          }}</a-descriptions-item
          ><a-descriptions-item label="模型策略"
            >{{ pack.model_policy.policy_key }}@{{
              pack.model_policy.semantic_version
            }}</a-descriptions-item
          ><a-descriptions-item label="输入上限">{{
            pack.model_policy.max_input_tokens
          }}</a-descriptions-item
          ><a-descriptions-item v-for="[label, key] in budgetFields" :key="key" :label="label">{{
            pack.budget[key]
          }}</a-descriptions-item></a-descriptions
        >
        <p>阻断原因：{{ pack.block_reasons.join('；') || '无' }}</p>
        <a-card
          v-for="entry in pack.entries"
          :key="entry.parent_id ?? entry.chunk_id"
          size="small"
          :title="entry.document_title"
          ><p>
            {{ entry.citation_type === 'EXTRACTED_SPANS' ? '原文节选' : '完整父原文' }} · 父片段
            {{ entry.parent_id }} · 重排名次 {{ entry.rank ?? absent }}
          </p>
          <p>
            文档/版本/索引：{{ entry.document_id }} / {{ entry.document_version_id }} /
            {{ entry.index_release_id }}
          </p>
          <p>
            命中子片段：{{ entry.hit_chunk_ids.join('、') }} · 原文哈希：{{
              entry.original_parent.content_hash
            }}
          </p>
          <div class="ai-original">{{ entry.content }}</div>
          <p>
            原文偏移 [起,止)：{{
              entry.original_spans
                .map((span) => `[${span.start_offset}, ${span.end_offset}) · ${span.content_hash}`)
                .join('；')
            }}
          </p></a-card
        ><a-table
          size="small"
          :pagination="false"
          :row-key="(item: any, index: number) => item.parent_id + '-' + index"
          :data-source="pack.exclusions"
          :columns="[
            { title: '排除父片段', dataIndex: 'parent_id' },
            { title: '准确排除原因', dataIndex: 'reason' },
          ]"
        />
        <p v-for="(item, index) in pack.extraction_decisions" :key="index">
          节选选择 {{ item.parent_id }}：句段 {{ item.selected_sentence_ids.join('、') }} ·
          {{ item.reason }}
        </p></template
      ></a-card
    >
    <p class="ai-muted">以上均来自当次运行快照；缺失字段不按当前规则重算。</p>
  </div>
</template>
<style scoped>
.ai-facts {
  display: grid;
  gap: 16px;
  min-width: 0;
  overflow-wrap: anywhere;
}
.ai-original {
  margin: 0;
  padding: 14px;
  border: 1px solid var(--v1-border);
  border-radius: var(--v1-radius);
  background: #f8fafc;
  color: var(--v1-text);
  font-family: inherit;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
blockquote {
  border-left: 3px solid var(--v1-border);
  margin: 12px 0;
  padding-left: 12px;
}
</style>
