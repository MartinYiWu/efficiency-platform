import {
  Button,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import type { AgentDetail } from '../../entities/ai-center/model';
import { createAgentVersion, getAgent, transitionAgentVersion } from '../../features/ai-center/api';
import { agentTypeLabel, aiStatusLabel } from '../../features/ai-center/presentation';
import styles from './AiCenter.module.css';
import { AiWorkspaceSection } from './AiWorkspaceSection';

export function AgentDetailPage() {
  const { agentId = '' } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<AgentDetail>();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const load = useCallback(
    () =>
      getAgent(agentId)
        .then(setDetail)
        .catch((error: Error) => message.error(error.message)),
    [agentId],
  );
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  const create = async () => {
    const value = await form.validateFields();
    await createAgentVersion(agentId, value);
    message.success('草稿版本已创建');
    setOpen(false);
    form.resetFields();
    await load();
  };
  if (!detail) return <Empty description="正在加载 Agent 详情" />;
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
      <div className={styles.objectWorkspace}>
        <Typography.Paragraph type="secondary">
          {detail.definition.description || '暂无描述'}
        </Typography.Paragraph>
        <Descriptions
          column={{ xs: 1, sm: 2, lg: 3 }}
          items={[
            { key: 'key', label: 'Agent Key', children: detail.definition.agentKey },
            { key: 'type', label: '类型', children: agentTypeLabel(detail.definition.agentType) },
            { key: 'status', label: '状态', children: aiStatusLabel(detail.definition.status) },
          ]}
        />
        <AiWorkspaceSection title="版本管理">
          <Table
            rowKey="id"
            pagination={{ pageSize: 8, hideOnSinglePage: true }}
            scroll={{ x: 780 }}
            dataSource={detail.versions}
            columns={[
              { title: '语义版本', dataIndex: 'semanticVersion' },
              { title: 'Graph', render: (_, item) => `${item.graphKey}@${item.graphVersion}` },
              {
                title: '状态',
                dataIndex: 'status',
                render: (value: string) => <Tag>{aiStatusLabel(value)}</Tag>,
              },
              { title: '变更', dataIndex: 'changeSummary' },
              {
                title: '操作',
                render: (_, item) => (
                  <Space wrap>
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
        </AiWorkspaceSection>
        <AiWorkspaceSection title="版本 / Release 证据绑定">
          {detail.evidenceBindings == null ? (
            '该版本未记录'
          ) : (
            <Table
              rowKey={(item) =>
                `${item.sourceType}:${item.sourceId}:${item.knowledgeBaseId}:${item.boundIndexReleaseId}`
              }
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              scroll={{ x: 720 }}
              dataSource={detail.evidenceBindings}
              columns={[
                { title: '来源', render: (_, item) => item.sourceType + ' · ' + item.sourceId },
                {
                  title: '可选大上下文模型',
                  dataIndex: 'largeModelName',
                  render: (value: string | null) => value ?? '未绑定',
                },
                {
                  title: '输入上限 Token',
                  dataIndex: 'maxInputTokens',
                  render: (value: number | null) => value ?? '未绑定',
                },
                {
                  title: '知识库',
                  dataIndex: 'knowledgeBaseId',
                  render: (value: string | null) => value ?? '未绑定',
                },
                {
                  title: '绑定索引',
                  dataIndex: 'boundIndexReleaseId',
                  render: (value: string | null) => value ?? '未绑定',
                },
                {
                  title: '知识库当前索引',
                  dataIndex: 'currentIndexReleaseId',
                  render: (value: string | null) => value ?? '未记录',
                },
                {
                  title: '提示',
                  render: (_, item) =>
                    item.currentIndexReleaseId &&
                    item.boundIndexReleaseId &&
                    item.currentIndexReleaseId !== item.boundIndexReleaseId ? (
                      <Tag color="warning">绑定索引落后于知识库当前发布索引</Tag>
                    ) : (
                      '—'
                    ),
                },
              ]}
            />
          )}
          <Typography.Text type="secondary">
            Release 展示冻结绑定；发布知识库新索引不会自动切换运行索引。
          </Typography.Text>
        </AiWorkspaceSection>
      </div>
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
