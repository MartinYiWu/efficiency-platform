import { Collapse, Tag, Typography } from 'antd';
import { useState } from 'react';

import type { CitationV2, DeliveryProvenanceViewModel } from '../../entities/operation-deliverable';
import styles from './OperationDelivery.module.css';

interface SourceEvidencePanelProps {
  citations: CitationV2[];
  provenance: DeliveryProvenanceViewModel | null;
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
}

const verificationStatusLabel = {
  verified: '已核验',
  partially_verified: '部分核验',
  unverified: '待核验',
  conflicted: '存在冲突',
} as const;

const rankingBasisLabel = {
  importance: '重要性',
  recency: '新近性',
  heat: '热度',
  mixed: '综合排序',
} as const;

function safeExternalHref(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' &&
      parsed.hostname.length > 0 &&
      parsed.username.length === 0 &&
      parsed.password.length === 0
      ? url
      : null;
  } catch {
    return null;
  }
}

function sourceLabel(citation: CitationV2): string {
  if (citation.title) return citation.title;
  if (citation.source) return citation.source;
  try {
    return new URL(citation.url).hostname;
  } catch {
    return '未命名来源';
  }
}

function formatDateTime(value: string | null): string {
  if (!value) return '时间未提供';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未提供';
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function collectionWindow(provenance: DeliveryProvenanceViewModel | null): string {
  if (!provenance?.collection_window_start && !provenance?.collection_window_end) {
    return '采集时间窗未提供';
  }
  return `${formatDateTime(provenance.collection_window_start)} 至 ${formatDateTime(
    provenance.collection_window_end,
  )}`;
}

function sourceList(citations: CitationV2[]) {
  return (
    <ul className={styles.sourceList}>
      {citations.map((citation) => {
        const href = safeExternalHref(citation.url);
        const label = sourceLabel(citation);
        return (
          <li className={styles.sourceItem} key={citation.citation_id}>
            <div>
              {href ? (
                <a href={href} target="_blank" rel="noopener noreferrer">
                  {label}
                </a>
              ) : (
                <Typography.Text>{label}</Typography.Text>
              )}
              {citation.source && citation.source !== label && (
                <Typography.Text type="secondary"> · {citation.source}</Typography.Text>
              )}
            </div>
            <div className={styles.sourceMeta}>
              <Typography.Text type="secondary">
                发布于 {formatDateTime(citation.published_at)}
              </Typography.Text>
              <Tag>{verificationStatusLabel[citation.verification_status]}</Tag>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function SourceEvidencePanel({
  citations,
  provenance,
  expanded,
  onExpandedChange,
}: SourceEvidencePanelProps) {
  const [internalExpanded, setInternalExpanded] = useState(false);
  const isExpanded = expanded ?? internalExpanded;
  const conflictedCount = citations.filter(
    (citation) => citation.verification_status === 'conflicted',
  ).length;
  const rankingBasis = provenance?.ranking_basis ?? null;

  return (
    <section className={styles.sourcePanel} aria-label="来源与采集依据">
      <Collapse
        activeKey={isExpanded ? ['sources'] : []}
        onChange={(activeKey) => {
          const keys = Array.isArray(activeKey) ? activeKey : [activeKey];
          const nextExpanded = keys.some((key) => String(key) === 'sources');
          if (expanded === undefined) setInternalExpanded(nextExpanded);
          onExpandedChange?.(nextExpanded);
        }}
        items={[
          {
            key: 'sources',
            label: `来源与采集依据（${citations.length} 条）`,
            children: (
              <div className={styles.sourcePanelContent}>
                <dl className={styles.provenanceList}>
                  <div>
                    <dt>采集时间窗</dt>
                    <dd>{collectionWindow(provenance)}</dd>
                  </div>
                  <div>
                    <dt>排序口径</dt>
                    <dd>{rankingBasis ? rankingBasisLabel[rankingBasis] : '未提供'}</dd>
                  </div>
                  {provenance && (
                    <>
                      <div>
                        <dt>候选</dt>
                        <dd>{`候选 ${provenance.candidate_count} 条`}</dd>
                      </div>
                      <div>
                        <dt>合并</dt>
                        <dd>{`合并 ${provenance.merged_event_count} 条`}</dd>
                      </div>
                      <div>
                        <dt>保留</dt>
                        <dd>{`保留 ${provenance.retained_count} 条`}</dd>
                      </div>
                      <div>
                        <dt>淘汰</dt>
                        <dd>{`淘汰 ${provenance.eliminated_count} 条`}</dd>
                      </div>
                    </>
                  )}
                  <div>
                    <dt>核验</dt>
                    <dd>
                      {provenance
                        ? `已核验 ${provenance.verified_source_count} 条，冲突 ${conflictedCount} 条`
                        : '核验统计未提供'}
                    </dd>
                  </div>
                </dl>
                {sourceList(citations)}
              </div>
            ),
          },
        ]}
      />
    </section>
  );
}
