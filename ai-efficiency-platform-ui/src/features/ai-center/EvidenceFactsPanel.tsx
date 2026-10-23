import { Card, Descriptions, Table, Typography } from 'antd';
import type { parseRetrievalFacts } from '../../entities/ai-center/schemas';
import styles from './EvidenceFactsPanel.module.css';

type Facts = NonNullable<ReturnType<typeof parseRetrievalFacts>>;
const absent = '该版本未记录';

/** 调试与回放共享冻结事实；不调用当前策略或重新计算名次、偏移、预算。 */
export function EvidenceFactsPanel({ facts }: { facts: Facts }) {
  const pack = facts.evidence_pack;
  return (
    <div className={styles.facts}>
      <Card size="small" title="等价分组与未合并原因">
        {facts.equivalence_decisions == null
          ? absent
          : facts.equivalence_decisions.length === 0
            ? '无候选对'
            : facts.equivalence_decisions.map((item, index) => (
                <div key={index}>
                  <p>
                    {item.left.chunk_id} / {item.right.chunk_id} · 相似度 {item.similarity} ·{' '}
                    {item.reason}
                  </p>
                  <p>
                    保留父片段：{item.retained_parent_id ?? '未合并'}；合并候选：
                    {item.merged_chunk_ids.join('、') || '无'}
                  </p>
                  {item.result && (
                    <p>
                      {item.result.verdict}：{item.result.left_quote} / {item.result.right_quote}；
                      {item.result.differing_conditions.join('；')}
                    </p>
                  )}
                </div>
              ))}
        <p>判断错误：{facts.equivalence_errors?.join('；') ?? absent}</p>
      </Card>
      <Card size="small" title="版本过滤与相邻组装">
        <p>旧版过滤计数：{facts.version_exclusions?.length ?? absent}</p>
        {facts.version_exclusions?.map((item, index) => (
          <p key={index}>
            {item.chunk_id} · {item.document_version_id} · {item.index_release_id} · {item.reason}
          </p>
        ))}
        <p>最终待装配父片段：{facts.final_parent_candidates?.join('、') ?? absent}</p>
        <p>
          相邻组成员：
          {facts.evidence_groups?.map((group) => group.parent_ids.join(' → ')).join('；') ?? absent}
        </p>
        {facts.grouping_decisions?.map((item, index) => (
          <p key={index}>
            {item.parent_id}：{item.reason}
          </p>
        ))}
      </Card>
      <Card size="small" title="冲突配对与准确摘录">
        {facts.conflict_screen == null ? (
          absent
        ) : (
          <>
            <p>阻断回答：{facts.conflict_screen.blocked ? '是' : '否'}</p>
            {facts.conflict_screen.pairs.map((pair, index) => (
              <div key={index}>
                <p>
                  {pair.left_parent_id} / {pair.right_parent_id}：{pair.verdict} · 同一范围：
                  {pair.same_scope ? '是' : '否'}
                </p>
                <blockquote>{pair.left_quote}</blockquote>
                <blockquote>{pair.right_quote}</blockquote>
                <p>{pair.reason}</p>
              </div>
            ))}
            <p>核验错误：{facts.conflict_screen.errors.join('；') || '无'}</p>
          </>
        )}
      </Card>
      <Card size="small" title="冻结 EvidencePack、预算与实际模型">
        {!pack ? (
          absent
        ) : (
          <>
            <Descriptions
              size="small"
              column={{ xs: 1, sm: 2, lg: 3 }}
              items={[
                { key: 'model', label: '实际模型', children: pack.model_policy.model_name },
                {
                  key: 'policy',
                  label: '模型策略',
                  children: pack.model_policy.policy_key + '@' + pack.model_policy.semantic_version,
                },
                { key: 'input', label: '输入上限', children: pack.model_policy.max_input_tokens },
                { key: 'context', label: '上下文预算', children: pack.budget.context_token_limit },
                { key: 'used', label: '实际使用 Token', children: pack.budget.used_tokens },
                { key: 'reserve', label: '预留 Token', children: pack.budget.reserved_tokens },
                { key: 'fixed', label: '固定输入 Token', children: pack.budget.fixed_input_tokens },
                { key: 'evidence', label: '证据 Token', children: pack.budget.evidence_tokens },
                { key: 'output', label: '输出预留 Token', children: pack.budget.output_tokens },
                {
                  key: 'intermediate',
                  label: '中间输出 Token',
                  children: pack.budget.intermediate_output_tokens,
                },
                { key: 'safety', label: '安全余量 Token', children: pack.budget.safety_tokens },
              ]}
            />
            <p>阻断原因：{pack.block_reasons.join('；') || '无'}</p>
            {pack.entries.map((entry) => (
              <Card
                size="small"
                key={entry.parent_id ?? entry.chunk_id}
                title={entry.document_title}
              >
                <p>
                  {entry.citation_type === 'EXTRACTED_SPANS' ? '原文节选' : '完整父原文'} · 父片段{' '}
                  {entry.parent_id} · 重排名次 {entry.rank ?? absent}
                </p>
                <p>
                  文档/版本/索引：{entry.document_id} / {entry.document_version_id} /{' '}
                  {entry.index_release_id}
                </p>
                <p>
                  命中子片段：{entry.hit_chunk_ids.join('、')} · 原文哈希：
                  {entry.original_parent.content_hash}
                </p>
                <div className={styles.original}>{entry.content}</div>
                <p>
                  原文偏移 [起,止)：
                  {entry.original_spans
                    .map(
                      (span) => `[${span.start_offset}, ${span.end_offset}) · ${span.content_hash}`,
                    )
                    .join('；')}
                </p>
              </Card>
            ))}
            <Table
              size="small"
              pagination={false}
              rowKey={(item, index) => item.parent_id + '-' + index}
              dataSource={pack.exclusions}
              columns={[
                { title: '排除父片段', dataIndex: 'parent_id' },
                { title: '准确排除原因', dataIndex: 'reason' },
              ]}
            />
            {pack.extraction_decisions.map((item, index) => (
              <p key={index}>
                节选选择 {item.parent_id}：句段 {item.selected_sentence_ids.join('、')} ·{' '}
                {item.reason}
              </p>
            ))}
          </>
        )}
      </Card>
      <Typography.Text type="secondary">
        以上均来自当次运行快照；缺失字段不按当前规则重算。
      </Typography.Text>
    </div>
  );
}
