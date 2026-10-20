import {
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import type { AgentDetail } from '../../entities/ai-center/model';
import { createAgentVersion, getAgent, transitionAgentVersion } from '../../features/ai-center/api';
import styles from './AiCenter.module.css';

export function AgentDetailPage() {
  const { agentId = '' } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<AgentDetail>();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const load = () =>
    getAgent(agentId)
      .then(setDetail)
      .catch((error: Error) => message.error(error.message));
  useEffect(() => {
    void load();
  }, [agentId]);
  const create = async () => {
    const value = await form.validateFields();
    await createAgentVersion(agentId, value);
    message.success('草稿版本已创建');
    setOpen(false);
    form.resetFields();
    await load();
  };
  if (!detail) return null;
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <Button type="link" onClick={() => navigate('/ai-center/agents')}>
            返回 Agent 列表
          </Button>
          <Typography.Title level={2}>{detail.definition.name}</Typography.Title>
        </div>
        <Button type="primary" onClick={() => setOpen(true)}>
          新建版本
        </Button>
      </header>
      <Descriptions
        bordered
        items={[
          { key: 'key', label: 'Agent Key', children: detail.definition.agentKey },
          { key: 'type', label: '类型', children: detail.definition.agentType },
          { key: 'status', label: '状态', children: detail.definition.status },
        ]}
      />
      <Card title="版本">
        <Table
          rowKey="id"
          pagination={false}
          dataSource={detail.versions}
          columns={[
            { title: '语义版本', dataIndex: 'semanticVersion' },
            { title: 'Graph', render: (_, item) => `${item.graphKey}@${item.graphVersion}` },
            { title: '状态', dataIndex: 'status', render: (value: string) => <Tag>{value}</Tag> },
            { title: '变更', dataIndex: 'changeSummary' },
            {
              title: '操作',
              render: (_, item) => (
                <Space>
                  {item.status === 'DRAFT' && (
                    <Button
                      size="small"
                      onClick={() => void transitionAgentVersion(item.id, 'READY').then(load)}
                    >
                      提交审核
                    </Button>
                  )}
                  <Button
                    size="small"
                    onClick={() => navigate(`/ai-center/prompts?agentId=${detail.definition.id}`)}
                  >
                    Prompt
                  </Button>
                  <Button
                    size="small"
                    onClick={() =>
                      navigate(`/ai-center/model-policies?agentId=${detail.definition.id}`)
                    }
                  >
                    策略
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Modal
        title="新建 Agent 版本"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void create()}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="semanticVersion" label="版本号" rules={[{ required: true }]}>
            <Input placeholder="1.0.1" />
          </Form.Item>
          <Form.Item name="graphKey" label="Graph Key" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="graphVersion" label="Graph 版本" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="changeSummary" label="变更说明">
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
    </section>
  );
}
