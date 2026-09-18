import { CopyOutlined } from '@ant-design/icons';
import { Button, Tag, Typography } from 'antd';

import type {
  DeliveryProvenanceViewModel,
  RankedDigestViewModel,
} from '../../entities/operation-deliverable';
import { SourceEvidencePanel } from './SourceEvidencePanel';
import styles from './OperationDelivery.module.css';

interface RankedDigestViewProps {
  deliverable: RankedDigestViewModel;
  provenance: DeliveryProvenanceViewModel | null;
  onCopyItem?: (copyText: string) => void;
  sourcesExpanded?: boolean;
  onSourcesExpandedChange?: (expanded: boolean) => void;
}

const confidenceLabel = {
  high: '高可信度',
  medium: '中可信度',
  low: '低可信度',
} as const;

const verificationStatusLabel: Record<
  RankedDigestViewModel['content']['items'][number]['verification_status'],
  string
> = {
  verified: '已核验',
  partially_verified: '部分核验',
  unverified: '待核验',
  conflicted: '存在冲突',
};

function formatOccurredAt(value: string | null): string {
  if (!value) return '时间未提供';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未提供';
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(date);
}

export function RankedDigestView({
  deliverable,
  provenance,
  onCopyItem,
  sourcesExpanded,
  onSourcesExpandedChange,
}: RankedDigestViewProps) {
  return (
    <article
      className={styles.deliveryDocument}
      aria-labelledby={`ranked-digest-${deliverable.id}`}
    >
      <header className={styles.documentHeader}>
        <div>
          <Typography.Title id={`ranked-digest-${deliverable.id}`} level={2}>
            {deliverable.title}
          </Typography.Title>
          <Typography.Paragraph className={styles.documentLead}>
            {deliverable.lead}
          </Typography.Paragraph>
          <Typography.Text type="secondary">
            {deliverable.content.selection_summary}
          </Typography.Text>
        </div>
        {onCopyItem && (
          <Button
            icon={
              <span aria-hidden="true">
                <CopyOutlined />
              </span>
            }
            onClick={() => onCopyItem(deliverable.copyText)}
            type="default"
          >
            复制热点榜
          </Button>
        )}
      </header>

      <ol aria-label="热点榜" className={styles.rankedList}>
        {deliverable.content.items.map((item, index) => {
          const displayRank = index + 1;
          return (
            <li className={styles.rankedItem} key={item.item_id}>
              <div className={styles.itemHeader}>
                <Typography.Title level={3}>{`${displayRank}. ${item.title}`}</Typography.Title>
                <div className={styles.itemMeta}>
                  <Typography.Text type="secondary">
                    {formatOccurredAt(item.occurred_at)}
                  </Typography.Text>
                  <Typography.Text type="secondary">{`关联来源 ${item.source_refs.length} 条`}</Typography.Text>
                  <Tag>{confidenceLabel[item.confidence]}</Tag>
                  <Tag>{verificationStatusLabel[item.verification_status]}</Tag>
                </div>
              </div>
              <Typography.Paragraph className={styles.itemSummary}>
                {item.summary}
              </Typography.Paragraph>
              <section className={styles.itemRationale} aria-label={`${item.title}的运营价值`}>
                <Typography.Text strong>为什么值得关注</Typography.Text>
                <Typography.Paragraph>{item.why_it_matters}</Typography.Paragraph>
              </section>
              {item.content_angles.length > 0 && (
                <section className={styles.itemAngles} aria-label={`${item.title}的内容角度`}>
                  <Typography.Text strong>内容角度</Typography.Text>
                  <ul>
                    {item.content_angles.map((angle) => (
                      <li key={angle}>{angle}</li>
                    ))}
                  </ul>
                </section>
              )}
              {item.metrics.length > 0 && (
                <div className={styles.itemMetrics} aria-label={`${item.title}的关键指标`}>
                  {item.metrics.map((metric) => (
                    <Tag key={metric}>{metric}</Tag>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      <SourceEvidencePanel
        citations={deliverable.citations}
        expanded={sourcesExpanded}
        onExpandedChange={onSourcesExpandedChange}
        provenance={provenance}
      />
    </article>
  );
}
