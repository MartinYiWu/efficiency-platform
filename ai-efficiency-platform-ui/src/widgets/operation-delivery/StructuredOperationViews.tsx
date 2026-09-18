import { Tag, Typography } from 'antd';

import type {
  ActionPlanViewModel,
  DiagnosisViewModel,
  RetrospectiveViewModel,
} from '../../entities/operation-deliverable';
import styles from './OperationDelivery.module.css';

interface ActionPlanViewProps {
  deliverable: ActionPlanViewModel;
  onCopyItem?: (copyText: string) => void;
}

interface DiagnosisViewProps {
  deliverable: DiagnosisViewModel;
  onCopyItem?: (copyText: string) => void;
}

interface RetrospectiveViewProps {
  deliverable: RetrospectiveViewModel;
  onCopyItem?: (copyText: string) => void;
}

function TextList({ items }: { items: string[] }) {
  if (items.length === 0) return <Typography.Text type="secondary">未提供</Typography.Text>;
  return (
    <ul>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function DocumentTitle({ id, lead, title }: { id: string; lead: string; title: string }) {
  return (
    <header>
      <Typography.Title id={id} level={2}>
        {title}
      </Typography.Title>
      <Typography.Paragraph className={styles.documentLead}>{lead}</Typography.Paragraph>
    </header>
  );
}

export function ActionPlanView({ deliverable }: ActionPlanViewProps) {
  const titleId = `action-plan-${deliverable.id}`;
  return (
    <article aria-labelledby={titleId} className={styles.deliveryDocument}>
      <DocumentTitle id={titleId} lead={deliverable.lead} title={deliverable.title} />
      <section className={styles.structuredSummary}>
        <div>
          <Typography.Text strong>行动目标</Typography.Text>
          <Typography.Paragraph>{deliverable.content.goal}</Typography.Paragraph>
        </div>
        <div>
          <Typography.Text strong>目标受众</Typography.Text>
          <Typography.Paragraph>{deliverable.content.audience}</Typography.Paragraph>
        </div>
      </section>
      <section aria-labelledby={`${titleId}-phases`} className={styles.structuredSections}>
        <Typography.Title id={`${titleId}-phases`} level={3}>
          执行阶段
        </Typography.Title>
        {deliverable.content.phases.map((phase) => (
          <section
            aria-labelledby={`${titleId}-${phase.phase_id}`}
            className={styles.actionPhase}
            key={phase.phase_id}
          >
            <Typography.Title id={`${titleId}-${phase.phase_id}`} level={3}>
              {phase.title}
            </Typography.Title>
            <div>
              <Typography.Text strong>行动</Typography.Text>
              <TextList items={phase.actions} />
            </div>
            <div>
              <Typography.Text strong>阶段指标</Typography.Text>
              <TextList items={phase.metrics} />
            </div>
          </section>
        ))}
      </section>
      <section aria-label="整体指标" className={styles.structuredSections}>
        <Typography.Title level={3}>整体指标</Typography.Title>
        <TextList items={deliverable.content.metrics} />
      </section>
      <section aria-label="前提假设" className={styles.structuredSections}>
        <Typography.Title level={3}>前提假设</Typography.Title>
        <TextList items={deliverable.content.assumptions} />
      </section>
    </article>
  );
}

const diagnosisPriorityLabel = {
  high: '高优先级',
  medium: '中优先级',
  low: '低优先级',
} as const;

const diagnosisPriorityOrder = { high: 0, medium: 1, low: 2 } as const;

export function DiagnosisView({ deliverable }: DiagnosisViewProps) {
  const titleId = `diagnosis-${deliverable.id}`;
  const findings = [...deliverable.content.findings].sort(
    (left, right) => diagnosisPriorityOrder[left.priority] - diagnosisPriorityOrder[right.priority],
  );

  return (
    <article aria-labelledby={titleId} className={styles.deliveryDocument}>
      <DocumentTitle id={titleId} lead={deliverable.lead} title={deliverable.title} />
      <section aria-label="诊断发现" className={styles.diagnosisFindings}>
        {findings.map((finding) => (
          <section
            aria-labelledby={`${titleId}-${finding.finding_id}`}
            className={styles.diagnosisFinding}
            key={finding.finding_id}
          >
            <Typography.Title id={`${titleId}-${finding.finding_id}`} level={3}>
              {finding.title}
            </Typography.Title>
            <Tag>{diagnosisPriorityLabel[finding.priority]}</Tag>
            <div>
              <Typography.Text strong>证据</Typography.Text>
              <TextList items={finding.evidence} />
            </div>
            <div>
              <Typography.Text strong>判断与建议</Typography.Text>
              <Typography.Paragraph>{finding.recommendation}</Typography.Paragraph>
            </div>
          </section>
        ))}
      </section>
      <section aria-labelledby={`${titleId}-gaps`} className={styles.structuredSections}>
        <Typography.Title id={`${titleId}-gaps`} level={4}>
          数据缺口
        </Typography.Title>
        <TextList items={deliverable.content.data_gaps} />
      </section>
    </article>
  );
}

export function RetrospectiveView({ deliverable }: RetrospectiveViewProps) {
  const titleId = `retrospective-${deliverable.id}`;
  const sections: Array<{ id: string; label: string; values: string[] }> = [
    { id: 'objectives', label: '目标', values: deliverable.content.objectives },
    { id: 'outcomes', label: '结果', values: deliverable.content.outcomes },
    { id: 'gaps', label: '差距', values: deliverable.content.gaps },
    { id: 'causes', label: '原因', values: deliverable.content.causes },
    { id: 'next-steps', label: '下一步', values: deliverable.content.next_steps },
  ];

  return (
    <article aria-labelledby={titleId} className={styles.deliveryDocument}>
      <DocumentTitle id={titleId} lead={deliverable.lead} title={deliverable.title} />
      {sections.map((section) => (
        <section
          aria-labelledby={`${titleId}-${section.id}`}
          className={styles.structuredSections}
          key={section.id}
        >
          <Typography.Title id={`${titleId}-${section.id}`} level={3}>
            {section.label}
          </Typography.Title>
          <TextList items={section.values} />
        </section>
      ))}
    </article>
  );
}
