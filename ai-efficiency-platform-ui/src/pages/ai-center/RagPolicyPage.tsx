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
    if (agentId)
      void listPolicies(agentId)
        .then((value) => setItems(value.ragPolicies))
        .catch((error: Error) => message.error(error.message));
    else setItems([]);
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
                  render: (_, item) => `${item.fusionTopK}/${item.rerankTopK}`,
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  render: (value: string) => <Tag>{value}</Tag>,
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
