import { Select, Typography } from 'antd';

export type EvidenceMode = 'FULL_ONLY' | 'EXTRACTIVE_NARRATIVE';
export function EvidenceModeSelect({
  knowledgeType,
  value,
  onChange,
}: {
  knowledgeType?: string;
  value: EvidenceMode;
  onChange(value: EvidenceMode): void;
}) {
  const allowed =
    knowledgeType === 'PRODUCT_DOCUMENTATION' || knowledgeType === 'TECHNICAL_DOCUMENTATION';
  return (
    <div>
      <Typography.Paragraph>证据处理</Typography.Paragraph>
      <Select
        aria-label="证据处理"
        disabled={!allowed}
        value={allowed ? value : 'FULL_ONLY'}
        onChange={onChange}
        options={[
          { label: '全文优先', value: 'FULL_ONLY' },
          ...(allowed ? [{ label: '允许叙述性原文节选', value: 'EXTRACTIVE_NARRATIVE' }] : []),
        ]}
      />
      <Typography.Paragraph type="secondary">
        仅选择原文句段，不生成替代公司事实的摘要；制度、流程及受保护条款始终保留全文。模式随新版本冻结。
      </Typography.Paragraph>
    </div>
  );
}
