import { Alert, Collapse, Typography } from 'antd';
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';

import {
  mapDeliverableSet,
  type DeliveryProvenanceViewModel,
  type DeliverableSetDto,
  type LegacyDeliverableViewModel,
  type OperationDeliverableViewModel,
} from '../../entities/operation-deliverable';
import { OperationNextActions } from '../../features/operation-next-action';
import { PlatformContentView } from './PlatformContentView';
import { RankedDigestView } from './RankedDigestView';
import { ActionPlanView, DiagnosisView, RetrospectiveView } from './StructuredOperationViews';
import styles from './OperationDelivery.module.css';

interface OperationDeliveryProps {
  value: DeliverableSetDto;
  onSubmitNextAction: (message: string) => void;
}

function safeMarkdownHref(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'https:' &&
      parsed.hostname.length > 0 &&
      parsed.username.length === 0 &&
      parsed.password.length === 0
      ? value
      : null;
  } catch {
    return null;
  }
}

function LegacySources({ deliverable }: { deliverable: LegacyDeliverableViewModel }) {
  if (deliverable.citations.length === 0) return null;

  return (
    <Collapse
      className={styles.legacySources}
      items={[
        {
          key: 'sources',
          label: `来源（${deliverable.citations.length} 条）`,
          children: (
            <ul className={styles.sourceList}>
              {deliverable.citations.map((citation) => {
                const label = citation.title ?? citation.source ?? citation.url;
                return (
                  <li className={styles.sourceItem} key={citation.url}>
                    {citation.href ? (
                      <a href={citation.href} rel="noopener noreferrer" target="_blank">
                        来源：{label}
                      </a>
                    ) : (
                      <Typography.Text>来源：{label}</Typography.Text>
                    )}
                  </li>
                );
              })}
            </ul>
          ),
        },
      ]}
    />
  );
}

function LegacyDeliveryView({ deliverable }: { deliverable: LegacyDeliverableViewModel }) {
  const titleId = `legacy-delivery-${deliverable.platform}-${deliverable.title}`;
  return (
    <article aria-labelledby={titleId} className={styles.legacyDelivery}>
      <Typography.Title id={titleId} level={2}>
        {deliverable.title}
      </Typography.Title>
      <Typography.Text type="secondary">平台：{deliverable.platform}</Typography.Text>
      <section aria-label="正文" className={styles.legacyBody}>
        <ReactMarkdown
          components={{
            a: ({ children, href }) => {
              const safeHref = safeMarkdownHref(href);
              return safeHref ? (
                <a href={safeHref} rel="noopener noreferrer" target="_blank">
                  {children}
                </a>
              ) : (
                <span>{children}</span>
              );
            },
          }}
          skipHtml
        >
          {deliverable.body}
        </ReactMarkdown>
      </section>
      {deliverable.hashtags.length > 0 && (
        <Typography.Paragraph type="secondary">
          标签：{deliverable.hashtags.join(' ')}
        </Typography.Paragraph>
      )}
      {deliverable.format_notes.map((note) => (
        <Typography.Paragraph key={note} type="secondary">
          格式说明：{note}
        </Typography.Paragraph>
      ))}
      <LegacySources deliverable={deliverable} />
      {deliverable.warnings.map((warning) => (
        <Alert key={warning} message={warning} showIcon type="warning" />
      ))}
    </article>
  );
}

function OperationDeliveryView({
  deliverable,
  provenance,
  onCopyItem,
  sourcesExpanded,
  onSourcesExpandedChange,
}: {
  deliverable: OperationDeliverableViewModel;
  provenance: DeliveryProvenanceViewModel | null;
  onCopyItem: (copyText: string) => void;
  sourcesExpanded: boolean;
  onSourcesExpandedChange: (expanded: boolean) => void;
}) {
  switch (deliverable.kind) {
    case 'ranked_digest':
      return (
        <RankedDigestView
          deliverable={deliverable}
          onCopyItem={onCopyItem}
          onSourcesExpandedChange={onSourcesExpandedChange}
          provenance={provenance}
          sourcesExpanded={sourcesExpanded}
        />
      );
    case 'platform_content':
      return (
        <PlatformContentView
          deliverable={deliverable}
          onCopyItem={onCopyItem}
          onSourcesExpandedChange={onSourcesExpandedChange}
          provenance={provenance}
          sourcesExpanded={sourcesExpanded}
        />
      );
    case 'action_plan':
      return <ActionPlanView deliverable={deliverable} />;
    case 'diagnosis':
      return <DiagnosisView deliverable={deliverable} />;
    case 'retrospective':
      return <RetrospectiveView deliverable={deliverable} />;
  }
}

export function OperationDelivery({ value, onSubmitNextAction }: OperationDeliveryProps) {
  const delivery = mapDeliverableSet(value);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState<'success' | 'error' | null>(null);

  const copyItem = async (copyText: string) => {
    setCopyFeedback(null);
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard API unavailable');
      await navigator.clipboard.writeText(copyText);
      setCopyFeedback('success');
    } catch {
      setCopyFeedback('error');
    }
  };

  if (delivery.kind === 'legacy') {
    return (
      <section aria-label="运营交付" className={styles.deliverySet}>
        <Typography.Paragraph className={styles.deliverySummary}>
          {delivery.summary}
        </Typography.Paragraph>
        {delivery.degraded && (
          <Alert message="部分内容已降级，请确认后使用。" showIcon type="warning" />
        )}
        {delivery.deliverables.map((deliverable) => (
          <LegacyDeliveryView
            deliverable={deliverable}
            key={`${deliverable.platform}-${deliverable.title}`}
          />
        ))}
      </section>
    );
  }

  return (
    <section aria-label="运营交付" className={styles.deliverySet}>
      <Typography.Paragraph className={styles.deliverySummary}>
        {delivery.summary.message}
      </Typography.Paragraph>
      {delivery.degraded && (
        <Alert message="部分内容已降级，请确认后使用。" showIcon type="warning" />
      )}
      {delivery.warnings.map((warning) => (
        <Alert key={warning.code} message={warning.message} showIcon type="warning" />
      ))}
      {delivery.deliverables.map((deliverable) => (
        <section className={styles.deliveryItem} key={deliverable.id}>
          <OperationDeliveryView
            deliverable={deliverable}
            onCopyItem={(copyText) => void copyItem(copyText)}
            onSourcesExpandedChange={setSourcesExpanded}
            provenance={delivery.provenance}
            sourcesExpanded={sourcesExpanded}
          />
          {deliverable.warnings.map((warning) => (
            <Alert key={warning.code} message={warning.message} showIcon type="warning" />
          ))}
        </section>
      ))}
      {copyFeedback === 'success' && <Typography.Text role="status">已复制</Typography.Text>}
      {copyFeedback === 'error' && (
        <Alert message="复制失败，请手动复制" role="alert" showIcon type="error" />
      )}
      <OperationNextActions
        actions={delivery.nextActions}
        onShowSources={() => setSourcesExpanded(true)}
        onSubmit={onSubmitNextAction}
      />
    </section>
  );
}
