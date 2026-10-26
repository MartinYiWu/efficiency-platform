import { Button, Descriptions, Drawer, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag, Typography, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import type { AgentRelease, EvaluationCase, EvaluationDatasetDetail, EvaluationRun, RagPolicy } from '../../entities/ai-center/model';
import type { IndexRelease, KnowledgeBase } from '../../entities/knowledge/model';
import { createEvaluationCase, getEvaluationDataset, importEvaluationCases, listAgentReleases, listAgents, listPolicies, startEvaluationRun, updateEvaluationCase } from '../../features/ai-center/api';
import { listIndexReleases, listKnowledgeBases } from '../../features/knowledge/api';
import styles from './AiCenter.module.css';

const lines = (value?: string) => value?.split('\n').map((item) => item.trim()).filter(Boolean) ?? [];
const caseInitial = (item?: EvaluationCase) => item ? {
  ...item, expectedFacts: item.expectedFacts.join('\n'), prohibitedFacts: item.prohibitedFacts.join('\n'),
  expectedDocumentTitles: item.expectedDocumentTitles.join('\n'), expectedDocumentVersionIds: item.expectedDocumentVersionIds.join('\n'), tags: item.tags.join('\n'),
} : { expectedAnswerMode: 'COMPANY_KNOWLEDGE', minCitationCount: 1, enabled: true };

export function RagEvaluationDatasetPage() {
  const { datasetId = '' } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<EvaluationDatasetDetail>();
  const [editing, setEditing] = useState<EvaluationCase | null>();
  const [caseOpen, setCaseOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [agentReleases, setAgentReleases] = useState<AgentRelease[]>([]);
  const [ragPolicies, setRagPolicies] = useState<RagPolicy[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [indexReleasesByBase, setIndexReleasesByBase] = useState<Record<string, IndexRelease[]>>({});
  const [importText, setImportText] = useState('[]');
  const [caseForm] = Form.useForm();
  const [runForm] = Form.useForm();
  const knowledgeBindings = Form.useWatch('knowledgeBindings', runForm) ?? [];
  const load = useCallback(() => getEvaluationDataset(datasetId).then(setDetail).catch((error: Error) => message.error(error.message)), [datasetId]);
  useEffect(() => { void load(); }, [load]);
  const importCount = useMemo(() => { try { const value = JSON.parse(importText); return Array.isArray(value) ? value.length : 0; } catch { return 0; } }, [importText]);
  if (!detail) return <Typography.Text>正在加载评测数据集…</Typography.Text>;

  const saveCase = async () => {
    const value = await caseForm.validateFields();
    const request = { ...value, expectedFacts: lines(value.expectedFacts), prohibitedFacts: lines(value.prohibitedFacts), expectedDocumentTitles: lines(value.expectedDocumentTitles), expectedDocumentVersionIds: lines(value.expectedDocumentVersionIds), tags: lines(value.tags) };
    if (editing) await updateEvaluationCase(datasetId, editing.id, request); else await createEvaluationCase(datasetId, request);
    setCaseOpen(false); setEditing(null); await load(); message.success('用例已保存');
  };
  const prepareRun = async () => {
    try {
      const [agents, releases, bases] = await Promise.all([
        listAgents(), listAgentReleases(detail.dataset.agentKey), listKnowledgeBases('page=1&pageSize=100'),
      ]);
      const agent = agents.find((item) => item.agentKey === detail.dataset.agentKey);
      if (!agent) throw new Error('未找到数据集所属 Agent');
      const policies = await listPolicies(agent.id);
      setAgentReleases(releases.filter((item) => item.releaseStatus === 'ACTIVE'));
      setRagPolicies(policies.ragPolicies.filter((item) => item.status === 'PUBLISHED'));
      setKnowledgeBases(bases.items);
      setIndexReleasesByBase({});
      runForm.setFieldsValue({ knowledgeBindings: [{}] });
      setRunOpen(true);
    } catch (error) { message.error(error instanceof Error ? error.message : '加载评测版本失败'); }
  };

  return <div className={styles.page}>
    <div className={styles.header}><div><Button type="link" onClick={() => navigate('/ai-center/rag-evaluations')}>← 返回数据集</Button><Typography.Title level={2}>{detail.dataset.name}</Typography.Title></div><Space><Button onClick={() => setImportOpen(true)}>批量导入</Button><Button onClick={() => { setEditing(null); caseForm.setFieldsValue(caseInitial()); setCaseOpen(true); }}>新增用例</Button><Button type="primary" onClick={() => void prepareRun()}>发起评测</Button></Space></div>
    <Descriptions bordered size="small" items={[
      { key: 'status', label: '状态', children: <Tag>{detail.dataset.status}</Tag> },
      { key: 'agent', label: 'Agent', children: detail.dataset.agentKey },
      { key: 'count', label: '用例数', children: detail.dataset.caseCount },
      { key: 'description', label: '说明', children: detail.dataset.description ?? '—' },
    ]} />
    <Typography.Title level={4}>评测用例</Typography.Title>
    <Table rowKey="id" dataSource={detail.cases} pagination={{ pageSize: 10 }} columns={[
      { title: '编号', dataIndex: 'caseNo', width: 120 }, { title: '问题', dataIndex: 'question' },
      { title: '预期模式', dataIndex: 'expectedAnswerMode', width: 190 },
      { title: '关键事实', render: (_: unknown, item: EvaluationCase) => item.expectedFacts.length },
      { title: '预期来源', render: (_: unknown, item: EvaluationCase) => item.expectedDocumentTitles.join('、') || '不适用' },
      { title: '状态', render: (_: unknown, item: EvaluationCase) => <Tag color={item.enabled ? 'green' : 'default'}>{item.enabled ? '启用' : '停用'}</Tag> },
      { title: '操作', render: (_: unknown, item: EvaluationCase) => <Button type="link" onClick={() => { setEditing(item); caseForm.setFieldsValue(caseInitial(item)); setCaseOpen(true); }}>编辑</Button> },
    ]} />
    <Typography.Title level={4}>运行记录</Typography.Title>
    <Table rowKey="id" dataSource={detail.runs} pagination={false} columns={[
      { title: '批次', dataIndex: 'id', ellipsis: true }, { title: '状态', dataIndex: 'status', render: (value: string) => <Tag>{value}</Tag> },
      { title: '通过', render: (_: unknown, item: EvaluationRun) => `${item.passedCount}/${item.totalCount}` },
      { title: '创建时间', dataIndex: 'createdAt', render: (value: string) => new Date(value).toLocaleString() },
      { title: '操作', render: (_: unknown, item: EvaluationRun) => <Button type="link" onClick={() => navigate(`/ai-center/rag-evaluations/runs/${item.id}`)}>查看结果</Button> },
    ]} />
    <Drawer width={620} title={editing ? '编辑用例' : '新增用例'} open={caseOpen} onClose={() => setCaseOpen(false)} extra={<Button type="primary" onClick={() => void saveCase()}>保存</Button>}>
      <Form form={caseForm} layout="vertical" initialValues={caseInitial()}>
        <Form.Item name="caseNo" label="稳定编号" rules={[{ required: true }]}><Input disabled={Boolean(editing)} /></Form.Item>
        <Form.Item name="question" label="真实提问" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
        <Form.Item name="expectedAnswerMode" label="预期回答模式" rules={[{ required: true }]}><Select options={['COMPANY_KNOWLEDGE', 'MIXED', 'GENERAL_ADVICE', 'INSUFFICIENT_EVIDENCE'].map((value) => ({ value }))} /></Form.Item>
        <Form.Item name="expectedFacts" label="必须事实（每行一条）"><Input.TextArea rows={4} /></Form.Item>
        <Form.Item name="prohibitedFacts" label="禁止事实（每行一条）"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item name="expectedDocumentTitles" label="预期文档标题（每行一条）"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item name="expectedDocumentVersionIds" label="预期文档版本 ID（每行一条）"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item name="minCitationCount" label="最少引用数"><InputNumber min={0} /></Form.Item>
        <Form.Item name="tags" label="标签（每行一条）"><Input.TextArea rows={2} /></Form.Item>
        <Form.Item name="enabled" label="参与评测" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </Drawer>
    <Modal title="批量导入 JSON 用例" open={importOpen} okText="导入" onCancel={() => setImportOpen(false)} onOk={async () => {
      try { const value = JSON.parse(importText); if (!Array.isArray(value)) throw new Error('必须是 JSON 数组'); const result = await importEvaluationCases(datasetId, value); setImportOpen(false); await load(); message.success(`已新增 ${result.createdCount} 条，更新 ${result.updatedCount} 条`); } catch (error) { message.error(error instanceof Error ? error.message : '导入失败'); }
    }}><Typography.Paragraph>已解析 {importCount} 条</Typography.Paragraph><Input.TextArea rows={14} value={importText} onChange={(event) => setImportText(event.target.value)} /></Modal>
    <Drawer width={520} title="发起真实评测" open={runOpen} onClose={() => setRunOpen(false)} extra={<Button type="primary" onClick={() => runForm.validateFields().then(async (value) => {
      const run = await startEvaluationRun({ datasetId, agentKey: detail.dataset.agentKey, agentVersionId: value.agentVersionId, ragPolicyVersionId: value.ragPolicyVersionId, knowledgeBindings: value.knowledgeBindings });
      setRunOpen(false); navigate(`/ai-center/rag-evaluations/runs/${run.id}`);
    }).catch((error) => { if (error instanceof Error) message.error(error.message); })}>开始</Button>}>
      <Typography.Paragraph type="secondary">批次将冻结以下版本，并在后台按用例串行调用真实 Agent。</Typography.Paragraph>
      <Form form={runForm} layout="vertical">
        <Form.Item name="agentVersionId" label="ACTIVE Agent 版本" rules={[{ required: true }]}><Select options={agentReleases.map((item) => ({ value: item.agentVersionId, label: `${item.agentVersionId.slice(0, 8)} · ${item.environment}` }))} /></Form.Item>
        <Form.Item name="ragPolicyVersionId" label="PUBLISHED RAG 策略" rules={[{ required: true }]}><Select options={ragPolicies.map((item) => ({ value: item.id, label: `${item.policyKey} · ${item.semanticVersion}` }))} /></Form.Item>
        <Form.List name="knowledgeBindings" rules={[{ validator: async (_, value) => { if (!value?.length) throw new Error('至少绑定一个知识库版本'); } }]}>
          {(fields, { add, remove }, { errors }) => <>
            {fields.map((field, index) => {
              const knowledgeBaseId = knowledgeBindings[index]?.knowledgeBaseId as string | undefined;
              const releases = knowledgeBaseId ? (indexReleasesByBase[knowledgeBaseId] ?? []) : [];
              return <div key={field.key} className={styles.filters}>
                <Form.Item {...field} name={[field.name, 'knowledgeBaseId']} label={`知识库 ${index + 1}`} rules={[{ required: true }]} style={{ flex: 1 }}>
                  <Select options={knowledgeBases.map((item) => ({ value: item.id, label: item.name }))} onChange={(id) => {
                    runForm.setFieldValue(['knowledgeBindings', field.name, 'indexReleaseId'], undefined);
                    if (!indexReleasesByBase[id]) void listIndexReleases(id).then((items) => setIndexReleasesByBase((current) => ({ ...current, [id]: items }))).catch((error: Error) => message.error(error.message));
                  }} />
                </Form.Item>
                <Form.Item {...field} name={[field.name, 'indexReleaseId']} label="索引发布版本" rules={[{ required: true }]} style={{ flex: 1 }}>
                  <Select disabled={!knowledgeBaseId} options={releases.filter((item) => item.status === 'PUBLISHED').map((item) => ({ value: item.id, label: `${item.releaseNo} · ${item.status}` }))} />
                </Form.Item>
                {fields.length > 1 && <Button danger onClick={() => remove(field.name)}>移除</Button>}
              </div>;
            })}
            <Button block onClick={() => add({})}>添加知识库版本</Button>
            <Form.ErrorList errors={errors} />
          </>}
        </Form.List>
      </Form>
    </Drawer>
  </div>;
}
