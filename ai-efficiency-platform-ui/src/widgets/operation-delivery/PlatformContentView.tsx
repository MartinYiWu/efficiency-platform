import { CopyOutlined } from '@ant-design/icons';
import { Button, Tag, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';

import type {
  DeliveryProvenanceViewModel,
  PlatformContentViewModel,
} from '../../entities/operation-deliverable';
import { SourceEvidencePanel } from './SourceEvidencePanel';
import styles from './OperationDelivery.module.css';

interface PlatformContentViewProps {
  deliverable: PlatformContentViewModel;
  provenance: DeliveryProvenanceViewModel | null;
  onCopyItem?: (copyText: string) => void;
  sourcesExpanded?: boolean;
  onSourcesExpandedChange?: (expanded: boolean) => void;
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

export function PlatformContentView({
  deliverable,
  provenance,
  onCopyItem,
  sourcesExpanded,
  onSourcesExpandedChange,
}: PlatformContentViewProps) {
  return (
    <article
      aria-labelledby={`platform-content-${deliverable.id}`}
      className={styles.deliveryDocument}
    >
      <header className={styles.documentHeader}>
        <div>
          <Typography.Title id={`platform-content-${deliverable.id}`} level={2}>
            {deliverable.title}
          </Typography.Title>
          <Typography.Paragraph className={styles.documentLead}>
            {deliverable.lead}
          </Typography.Paragraph>
        </div>
        {onCopyItem && (
          <Button
            icon={
              <span aria-hidden="true">
                <CopyOutlined />
              </span>
            }
            onClick={() => onCopyItem(deliverable.copyText)}
          >
            复制全文
          </Button>
        )}
      </header>

      <section aria-label="正文" className={styles.platformBody}>
        <ReactMarkdown
          skipHtml
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
        >
          {deliverable.content.body_markdown}
        </ReactMarkdown>
      </section>

      {deliverable.content.hashtags.length > 0 && (
        <section aria-label="标签" className={styles.platformTags}>
          <Typography.Text strong>标签</Typography.Text>
          <div>
            {deliverable.content.hashtags.map((hashtag) => (
              <Tag key={hashtag}>{hashtag}</Tag>
            ))}
          </div>
        </section>
      )}

      {deliverable.content.format_notes.length > 0 && (
        <section aria-labelledby={`format-notes-${deliverable.id}`} className={styles.formatNotes}>
          <Typography.Title id={`format-notes-${deliverable.id}`} level={3}>
            格式说明
          </Typography.Title>
          <ul>
            {deliverable.content.format_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </section>
      )}

      <SourceEvidencePanel
        citations={deliverable.citations}
        expanded={sourcesExpanded}
        onExpandedChange={onSourcesExpandedChange}
        provenance={provenance}
      />
    </article>
  );
}
