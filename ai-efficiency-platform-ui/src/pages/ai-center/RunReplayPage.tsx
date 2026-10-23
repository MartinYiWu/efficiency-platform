import {
  Button,
  Card,
  Descriptions,
  Empty,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import type { RunReplay } from '../../entities/ai-center/model';
import { parseRetrievalFacts } from '../../entities/ai-center/schemas';
import { getRunReplay } from '../../features/ai-center/api';
import styles from './AiCenter.module.css';
import { EvidenceFactsPanel } from '../../features/ai-center/EvidenceFactsPanel';

export function RunReplayPage() {
  const { runId = '' } = useParams();
  const navigate = useNavigate();
  const [replay, setReplay] = useState<RunReplay>();
  useEffect(() => {
    void getRunReplay(runId)
      .then(setReplay)
      .catch((error: Error) => message.error(error.message));
  }, [runId]);
  if (!replay) return <Empty description="正在加载运行事实" />;
  const retrievalFacts = replay.stages
    .map((stage) => parseRetrievalFacts(stage.internalPayload))
    .find((item) => item !== null);
  return (
    <section className={styles.page}>
      <header>
        <Button type="link" onClick={() => navigate('/ai-center/runs')}>
          返回运行列表
        </Button>
        <Typography.Title level={2}>Run 回放</Typography.Title>
      </header>
      <Descriptions
        bordered
        items={[
          { key: 'id', label: 'Run ID', children: replay.run.id },
          { key: 'status', label: '状态', children: <Tag>{replay.run.status}</Tag> },
          { key: 'mode', label: '回答模式', children: replay.run.answerMode ?? '-' },
          { key: 'release', label: 'Agent Release', children: replay.run.agentReleaseId },
        ]}
      />
      <Card title="问题">
        <div className={styles.pre}>{replay.question.content}</div>
      </Card>
      <Card title="结构化阶段">
        <Timeline
          items={replay.stages.map((stage) => ({
            color: stage.status === 'FAILED' ? 'red' : 'green',
            children: (
              <>
                <strong>{stage.stage}</strong>
                <p>{stage.publicSummary}</p>
              </>
            ),
          }))}
        />
      </Card>
      {!retrievalFacts && <Card title="检索证据回放">该版本未记录</Card>}
      {retrievalFacts && (
        <Card title="检索证据回放">
          <EvidenceFactsPanel facts={retrievalFacts} />
          {retrievalFacts.budget_usage && (
            <Descriptions
              size="small"
              items={[
                {
                  key: 'used',
                  label: '已使用 Token',
                  children: retrievalFacts.budget_usage.used_tokens,
                },
                {
                  key: 'limit',
                  label: '上下文上限',
                  children: retrievalFacts.budget_usage.context_token_limit,
                },
              ]}
            />
          )}
          <Tabs
            items={(
              [
                ['向量原始分数', retrievalFacts.vector_candidates],
                ['全文原始分数', retrievalFacts.fts_candidates],
                ['RRF 分数', retrievalFacts.fused_candidates],
                ['Rerank 分数', retrievalFacts.child_hits],
              ] as const
            ).map(([label, candidates]) => ({
              key: label,
              label: `${label} (${candidates.length})`,
              children: (
                <Table
                  size="small"
                  rowKey={(item, index) => `${item.chunk_id}-${index}`}
                  pagination={false}
                  dataSource={candidates}
                  columns={[
                    { title: '子片段', dataIndex: 'chunk_id' },
                    {
                      title: '阶段名次',
                      dataIndex: 'rank',
                      render: (value: number | null | undefined) => value ?? '该版本未记录',
                    },
                    {
                      title: '分数',
                      dataIndex: 'score',
                      render: (value: number) => value.toFixed(3),
                    },
                    { title: '命中原文', dataIndex: 'excerpt' },
                  ]}
                />
              ),
            }))}
          />
          <Table
            rowKey="chunk_id"
            pagination={false}
            dataSource={retrievalFacts.child_hits}
            columns={[
              { title: '子片段', dataIndex: 'chunk_id' },
              { title: '父片段', dataIndex: 'parent_id' },
              {
                title: '重排分数',
                dataIndex: 'score',
                render: (value: number) => value.toFixed(3),
              },
              { title: '命中原文', dataIndex: 'excerpt' },
            ]}
          />
          {retrievalFacts.assembly_decisions.map((decision) => (
            <p key={decision.parent_id}>
              {decision.parent_id}：{decision.selected ? '已入选' : decision.reason}
            </p>
          ))}
          {retrievalFacts.parent_evidence.map((item) => (
            <Card
              key={item.parent_id}
              size="small"
              title={`${item.document_title} · v${item.version_no} · ${item.section_path ?? '正文'}${item.page_start ? ` · 第 ${item.page_start}${item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ''} 页` : ''}`}
            >
              <div className={styles.pre}>{item.content}</div>
            </Card>
          ))}
        </Card>
      )}
      {replay.answer && (
        <Card title="最终回答">
          <div className={styles.pre}>{replay.answer.content}</div>
        </Card>
      )}
      <Card title="引用闭包">
        <Table
          rowKey="id"
          pagination={false}
          dataSource={replay.citations}
          columns={[
            { title: '#', dataIndex: 'citationNo' },
            { title: '文档', dataIndex: 'documentTitle' },
            { title: '版本', dataIndex: 'versionNo' },
            { title: '章节', dataIndex: 'sectionPath' },
            { title: '引用原文', dataIndex: 'quotedText' },
            {
              title: '引用类型',
              dataIndex: 'citationType',
              render: (value: string | null) =>
                value === 'EXTRACTED_SPANS'
                  ? '原文节选'
                  : value === 'FULL_PARENT'
                    ? '完整原文'
                    : '该版本未记录',
            },
            {
              title: '原文偏移',
              render: (_, item) =>
                item.originalSpans
                  ?.map((span) => `[${span.start_offset}, ${span.end_offset})`)
                  .join('；') ?? '该版本未记录',
            },
          ]}
        />
      </Card>
      {replay.run.failureMessage && (
        <Card title={replay.run.failureCode ?? '运行失败'}>{replay.run.failureMessage}</Card>
      )}
    </section>
  );
}
