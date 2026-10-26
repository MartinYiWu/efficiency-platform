import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';

import type { AgentDefinition, RagPolicy } from '../../entities/ai-center/model';
import { listAgents, listPolicies, saveRagPolicy } from '../../features/ai-center/api';
import { aiStatusLabel } from '../../features/ai-center/presentation';
import styles from './AiCenter.module.css';

const numberFields = [
  'rewriteQueryLimit',
  'vectorTopK',
  'ftsTopK',
  'fusionTopK',
  'rerankTopK',
  'contextTokenLimit',
  'citationLimit',
];
const evidenceFields = [
  {
    name: 'finalEvidenceTopK',
    label: '最终父证据 TopK',
    min: 1,
    max: 20,
    step: 1,
    help: '冲突核验与预算组装的独立父证据数量，相邻成员分别计数。',
  },
  {
    name: 'similarityCandidateThreshold',
    label: '相似候选阈值',
    min: 0.85,
    max: 1,
    step: 0.01,
    help: '仅筛选送入等价判断的候选，不直接决定合并。',
  },
  {
    name: 'similarityPairLimit',
    label: '相似候选对上限',
    min: 1,
    max: 50,
    step: 1,
    help: '每次运行最多核验的相似候选对数。',
  },
  {
    name: 'adjacentGroupMaxParents',
    label: '相邻组父片段上限',
    min: 1,
    max: 5,
    step: 1,
    help: '同版同路径且连续命中的父片段组大小。',
  },
];
export function RagPolicyPage() {
  const [params] = useSearchParams();
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [agentId, setAgentId] = useState(params.get('agentId') ?? '');
  const [items, setItems] = useState<RagPolicy[]>([]);
  const [form] = Form.useForm();
  useEffect(() => {
    void listAgents().then(setAgents);
  }, []);
  useEffect(() => {
    if (!agentId) return;
    void listPolicies(agentId)
      .then((value) => setItems(value.ragPolicies))
      .catch((error: Error) => message.error(error.message));
  }, [agentId]);
  const save = async () => {
    const value = await form.validateFields();
    try {
      await saveRagPolicy({ id: null, ownerAgentId: agentId, ...value, checksum: null });
      message.success('RAG 策略草稿已创建');
      form.resetFields();
      setItems((await listPolicies(agentId)).ragPolicies);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    }
  };
  return (
    <section className={styles.page}>
      <header>
        <Typography.Title level={2}>RAG 策略</Typography.Title>
        <Typography.Text type="secondary">
          配置查询改写、混合召回、重排、上下文与引用上限。
        </Typography.Text>
      </header>
      <Select
        placeholder="先选择所属 Agent"
        value={agentId || undefined}
        onChange={setAgentId}
        style={{ width: 320 }}
        options={agents.map((item) => ({
          label: `${item.name} (${item.agentKey})`,
          value: item.id,
        }))}
      />
      {agentId && (
        <div className={styles.grid}>
          <Card title="已有策略">
            <Table
              rowKey="id"
              pagination={false}
              dataSource={items}
              columns={[
                { title: '策略', dataIndex: 'policyKey' },
                { title: '版本', dataIndex: 'semanticVersion' },
                {
                  title: '召回/重排',
                  render: (_, item) =>
                    `向量 ${item.vectorTopK} / 全文 ${item.ftsTopK} / RRF ${item.fusionTopK} / Rerank ${item.rerankTopK}`,
                },
                {
                  title: '最终父证据 TopK',
                  dataIndex: 'finalEvidenceTopK',
                  render: (value: number | null | undefined) => value ?? '该版本未记录',
                },
                {
                  title: '相似候选阈值',
                  dataIndex: 'similarityCandidateThreshold',
                  render: (value: number | null | undefined) => value ?? '该版本未记录',
                },
                {
                  title: '候选对 / 相邻组上限',
                  render: (_, item) =>
                    `${item.similarityPairLimit ?? '未记录'} / ${item.adjacentGroupMaxParents ?? '未记录'}`,
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  render: (value: string) => <Tag>{aiStatusLabel(value)}</Tag>,
                },
              ]}
            />
          </Card>
          <Card title="新建策略草稿">
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                rewriteQueryLimit: 3,
                vectorTopK: 20,
                ftsTopK: 20,
                fusionTopK: 20,
                rerankTopK: 8,
                contextTokenLimit: 8000,
                citationLimit: 8,
                finalEvidenceTopK: 8,
                similarityCandidateThreshold: 0.96,
                similarityPairLimit: 20,
                adjacentGroupMaxParents: 3,
              }}
            >
              <Form.Item name="policyKey" label="策略 Key" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="semanticVersion" label="版本" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              {numberFields.map((name) => (
                <Form.Item key={name} name={name} label={name} rules={[{ required: true }]}>
                  <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
              ))}
              {evidenceFields.map(({ name, label, min, max, step, help }) => (
                <Form.Item
                  key={name}
                  name={name}
                  label={label}
                  extra={help}
                  rules={[{ required: true }, { type: 'number', min, max }]}
                >
                  <InputNumber min={min} max={max} step={step} precision={step === 1 ? 0 : 2} />
                </Form.Item>
              ))}
              <Button type="primary" onClick={() => void save()}>
                保存草稿
              </Button>
            </Form>
          </Card>
        </div>
      )}
    </section>
  );
}
