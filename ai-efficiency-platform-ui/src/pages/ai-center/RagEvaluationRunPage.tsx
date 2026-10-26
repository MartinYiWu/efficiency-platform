import { Button, Card, Descriptions, Drawer, Empty, Select, Space, Statistic, Table, Tag, Typography, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { useNavigate, useParams } from 'react-router';

import type { EvaluationCaseResult, EvaluationRun, EvaluationRunComparison, EvaluationRunDetail } from '../../entities/ai-center/model';
import { compareEvaluationRuns, getEvaluationRun, listEvaluationRuns } from '../../features/ai-center/api';
import styles from './AiCenter.module.css';

const percent = (value: number | null | undefined) => value == null ? 'N/A' : `${(value * 100).toFixed(1)}%`;

export function RagEvaluationRunPage() {
  const { runId = '' } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<EvaluationRunDetail>();
  const [selected, setSelected] = useState<EvaluationCaseResult>();
  const [failure, setFailure] = useState<string>();
  const [baselineId, setBaselineId] = useState<string>();
  const [baselineRuns, setBaselineRuns] = useState<EvaluationRun[]>([]);
  const [comparison, setComparison] = useState<EvaluationRunComparison>();
  useEffect(() => { let timer: number | undefined; const load = async () => { try { const value = await getEvaluationRun(runId); setDetail(value); if (['PENDING', 'RUNNING'].includes(value.run.status)) timer = window.setTimeout(load, 2000); } catch (error) { message.error((error as Error).message); } }; void load(); return () => window.clearTimeout(timer); }, [runId]);
  const caseById = useMemo(() => new Map(detail?.cases.map((item) => [item.id, item]) ?? []), [detail]);
  const results = useMemo(() => detail?.results.filter((item) => !failure || (failure === 'EXECUTION_FAILED' ? item.executionStatus === 'FAILED' : item.metrics?.failures.includes(failure))) ?? [], [detail, failure]);
  if (!detail) return <Typography.Text>正在加载评测结果…</Typography.Text>;
  const metrics = detail.run.metrics;

  return <div className={styles.page}>
    <div className={styles.header}><div><Button type="link" onClick={() => navigate(`/ai-center/rag-evaluations/${detail.run.datasetId}`)}>← 返回数据集</Button><Typography.Title level={2}>评测运行详情</Typography.Title></div><Tag>{detail.run.status}</Tag></div>
    <div className={styles.grid}>{[
      ['用例通过率', percent(metrics?.casePassRate)], ['执行成功率', percent(metrics?.executionSuccessRate)],
      ['来源召回', percent(metrics?.sourceRecallAtK)], ['引用合规率', percent(metrics?.citationComplianceRate)],
      ['模式准确率', percent(metrics?.answerModeAccuracy)], ['P50 / P95', metrics ? `${metrics.latencyP50Ms} / ${metrics.latencyP95Ms} ms` : '运行中'],
    ].map(([title, value]) => <Card key={title}><Statistic title={title} value={value} /></Card>)}</div>
    <Card title="批次冻结信息"><Descriptions size="small" column={2} items={[
      { key: 'agent', label: 'Agent 版本', children: detail.run.agentVersionId }, { key: 'rag', label: 'RAG 策略', children: detail.run.ragPolicyVersionId },
      { key: 'knowledge', label: '知识绑定', children: detail.run.knowledgeBindings.map((item) => `${item.knowledgeBaseId} / ${item.indexReleaseId}`).join('；') },
      { key: 'time', label: '完成时间', children: detail.run.finishedAt ? new Date(detail.run.finishedAt).toLocaleString() : '运行中' },
    ]} /></Card>
    <div className={styles.filters}><Select allowClear placeholder="失败类型" style={{ width: 220 }} value={failure} onChange={setFailure} options={[
      'EXECUTION_FAILED', 'ANSWER_MODE_MISMATCH', 'EXPECTED_FACT_MISSING', 'PROHIBITED_FACT_MATCHED', 'EXPECTED_SOURCE_MISSING', 'CITATION_COUNT_INSUFFICIENT', 'VERSION_MISMATCH',
    ].map((value) => ({ value }))} /><Select allowClear placeholder="选择基线批次" style={{ width: 320 }} value={baselineId} onDropdownVisibleChange={(open) => { if (open) void listEvaluationRuns(detail.run.datasetId).then(setBaselineRuns).catch(() => undefined); }} onChange={setBaselineId} options={baselineRuns.filter((item) => item.id !== runId).map((item) => ({ value: item.id, label: `${item.id.slice(0, 8)} · ${item.status} · ${new Date(item.createdAt).toLocaleString()}` }))} /><Button disabled={!baselineId} onClick={() => baselineId && compareEvaluationRuns(baselineId, runId).then(setComparison).catch((error: Error) => message.error(error.message))}>比较</Button></div>
    {comparison && <Card title="与基线比较"><Space wrap>{Object.entries(comparison.metricDeltas).map(([key, value]) => <Tag color={value >= 0 ? 'green' : 'red'} key={key}>{key}: {value.toFixed(3)}</Tag>)}</Space></Card>}
    <Table rowKey="id" dataSource={results} pagination={{ pageSize: 10 }} locale={{ emptyText: <Empty description={detail.run.status === 'RUNNING' ? '正在生成真实结果' : '暂无结果'} /> }} columns={[
      { title: '编号', render: (_: unknown, item: EvaluationCaseResult) => caseById.get(item.caseId)?.caseNo ?? item.caseId },
      { title: '问题', render: (_: unknown, item: EvaluationCaseResult) => caseById.get(item.caseId)?.question ?? '—' },
      { title: '结果', render: (_: unknown, item: EvaluationCaseResult) => <Tag color={item.passed ? 'green' : 'red'}>{item.passed ? '通过' : '未通过'}</Tag> },
      { title: '回答模式', dataIndex: 'answerMode', render: (value: string | null) => value ?? '—' },
      { title: '来源', render: (_: unknown, item: EvaluationCaseResult) => [...new Set(item.citations.map((citation) => citation.document_title))].join('、') || '—' },
      { title: '耗时', dataIndex: 'latencyMs', render: (value: number) => `${value} ms` },
      { title: '错误', dataIndex: 'errorCode', render: (value: string | null) => value ?? '—' },
      { title: '操作', render: (_: unknown, item: EvaluationCaseResult) => <Button type="link" onClick={() => setSelected(item)}>查看事实</Button> },
    ]} />
    <Drawer width={720} title="用例真实结果" open={Boolean(selected)} onClose={() => setSelected(undefined)}>
      {selected && <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Descriptions bordered size="small" column={1} items={[
          { key: 'question', label: '问题', children: caseById.get(selected.caseId)?.question ?? '—' },
          { key: 'debug', label: '调试 Run ID', children: selected.debugRunId ?? '—' },
          { key: 'failures', label: '判定失败项', children: selected.metrics?.failures.join('、') || selected.errorCode || '无' },
        ]} />
        <Card title="真实回答">{selected.answerMarkdown ? <ReactMarkdown>{selected.answerMarkdown}</ReactMarkdown> : <Empty description="调用未返回回答" />}</Card>
        <Card title="冻结引用">{selected.citations.length ? selected.citations.map((citation) => <Card size="small" key={citation.citation_no} title={`[${citation.citation_no}] ${citation.document_title} · v${citation.version_no}`}><Typography.Paragraph>{citation.quoted_text}</Typography.Paragraph><Typography.Text type="secondary">文档版本 {citation.document_version_id} / 索引 {citation.index_release_id}</Typography.Text></Card>) : <Empty description="无引用" />}</Card>
      </Space>}
    </Drawer>
  </div>;
}
