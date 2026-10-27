import { Alert, Button, Tag } from 'antd';
import ReactMarkdown from 'react-markdown';

import type { AnswerMode, Citation } from '../../entities/customer-service/model';
import styles from '../../pages/customer-service/CustomerServiceChatPage.module.css';

const labels: Record<AnswerMode, { title: string; color: string }> = {
  COMPANY_KNOWLEDGE: { title: '依据公司知识', color: 'blue' },
  MIXED: { title: '公司知识 + 通用建议', color: 'purple' },
  GENERAL_ADVICE: { title: '通用建议（非公司制度）', color: 'orange' },
  CLARIFY: { title: '需要补充信息', color: 'gold' },
  INSUFFICIENT_EVIDENCE: { title: '现有资料不足', color: 'default' },
};
export function CustomerServiceAnswer({
  content,
  mode,
  citations,
  streaming,
  onCitation,
}: {
  content: string;
  mode: AnswerMode | null;
  citations: Citation[];
  streaming: boolean;
  onCitation(citation: Citation): void;
}) {
  const meta = mode ? labels[mode] : null;
  return (
    <div className={styles.answer}>
      {meta && <Tag color={meta.color} className={styles.answerMode}>{meta.title}</Tag>}
      {mode === 'GENERAL_ADVICE' && (
        <Alert type="warning" showIcon message="以下为通用建议，不代表公司制度或正式流程。" />
      )}
      <div className={styles.answerBody}>
        <ReactMarkdown>{content || (streaming ? '正在生成回答…' : '')}</ReactMarkdown>
      </div>
      {citations.length > 0 && (
        <div className={styles.sources}>
          <div className={styles.sourcesLabel}>参考来源 · {citations.length}</div>
          <div className={styles.sourceItems}>
            {citations.map((citation) => (
              <Button key={citation.id} size="small" className={styles.sourceButton}
                onClick={() => onCitation(citation)}>
                [{citation.citationNo}] {citation.documentTitle}
                {citation.citationType === 'EXTRACTED_SPANS' ? ' · 原文节选' : ''}
              </Button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
