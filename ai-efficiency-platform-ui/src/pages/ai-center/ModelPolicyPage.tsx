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

import type { AgentDefinition, ModelPolicy } from '../../entities/ai-center/model';
import { listAgents, listPolicies, saveModelPolicy } from '../../features/ai-center/api';
import styles from './AiCenter.module.css';

export function ModelPolicyPage() {
  const [params] = useSearchParams();
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [agentId, setAgentId] = useState(params.get('agentId') ?? '');
  const [items, setItems] = useState<ModelPolicy[]>([]);
  const [form] = Form.useForm();
  useEffect(() => {
    void listAgents().then(setAgents);
  }, []);
  useEffect(() => {
    if (agentId)
      void listPolicies(agentId)
        .then((value) => setItems(value.modelPolicies))
        .catch((error: Error) => message.error(error.message));
    else setItems([]);
  }, [agentId]);
  const save = async () => {
    const value = await form.validateFields();
    try {
      await saveModelPolicy({ id: null, ownerAgentId: agentId, ...value, checksum: null });
      message.success('模型策略草稿已创建');
      form.resetFields();
      setItems((await listPolicies(agentId)).modelPolicies);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败');
    }
  };
  return (
    <section className={styles.page}>
      <header>
        <Typography.Title level={2}>模型策略</Typography.Title>
        <Typography.Text type="secondary">
          策略严格归属于所选 Agent，创建后不可改变归属。
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
                { title: '模型', render: (_, item) => `${item.provider}/${item.modelName}` },
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
                temperature: 0.2,
                topP: 0.9,
                maxInputTokens: 32000,
                maxOutputTokens: 4096,
                connectTimeoutMs: 10000,
                readTimeoutMs: 120000,
                maxRetries: 1,
              }}
            >
              <Form.Item name="policyKey" label="策略 Key" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="semanticVersion" label="版本" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="provider" label="Provider" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="modelName" label="模型" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              {[
                'temperature',
                'topP',
                'maxInputTokens',
                'maxOutputTokens',
                'connectTimeoutMs',
                'readTimeoutMs',
                'maxRetries',
              ].map((name) => (
                <Form.Item key={name} name={name} label={name} rules={[{ required: true }]}>
                  <InputNumber style={{ width: '100%' }} />
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
