import { Button, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import type { EvaluationDataset } from '../../entities/ai-center/model';
import { createEvaluationDataset, listEvaluationDatasets } from '../../features/ai-center/api';
import { aiStatusLabel } from '../../features/ai-center/presentation';
import styles from './AiCenter.module.css';
import { formatAiDate } from './datePresentation';

export function RagEvaluationListPage() {
  const navigate = useNavigate();
  const [datasets, setDatasets] = useState<EvaluationDataset[]>([]);
  const [status, setStatus] = useState<string>();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const load = useCallback(
    () =>
      listEvaluationDatasets()
        .then(setDatasets)
        .catch((error: Error) => message.error(error.message)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const filtered = status ? datasets.filter((item) => item.status === status) : datasets;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <Typography.Title level={2}>RAG 评测</Typography.Title>
          <Typography.Text type="secondary">
            用真实知识、真实检索和真实模型调用验证智能客服效果。
          </Typography.Text>
        </div>
        <Button type="primary" onClick={() => setOpen(true)}>
          新建数据集
        </Button>
      </div>
      <div className={styles.objectWorkspace}>
        <div className={styles.listToolbar}>
          <h3>
            评测数据集 <span>{filtered.length}</span>
          </h3>
          <div className={styles.filters}>
            <Select
              allowClear
              placeholder="数据集状态"
              value={status}
              onChange={setStatus}
              style={{ width: 180 }}
              options={['DRAFT', 'ACTIVE', 'ARCHIVED'].map((value) => ({
                value,
                label: aiStatusLabel(value),
              }))}
            />
          </div>
        </div>
        <Table
          rowKey="id"
          dataSource={filtered}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          scroll={{ x: 760 }}
          columns={[
            { title: '名称', dataIndex: 'name' },
            { title: 'Agent', dataIndex: 'agentKey' },
            {
              title: '状态',
              dataIndex: 'status',
              render: (value: string) => <Tag>{aiStatusLabel(value)}</Tag>,
            },
            { title: '用例数', dataIndex: 'caseCount' },
            {
              title: '更新时间',
              dataIndex: 'updatedAt',
              render: (value: string) => formatAiDate(value),
            },
            {
              title: '操作',
              render: (_: unknown, item: EvaluationDataset) => (
                <Space>
                  <Button
                    type="link"
                    onClick={() => navigate(`/ai-center/rag-evaluations/${item.id}`)}
                  >
                    查看用例
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </div>
      <Modal
        title="新建评测数据集"
        open={open}
        okText="创建"
        onCancel={() => setOpen(false)}
        onOk={() =>
          form
            .validateFields()
            .then(async (value) => {
              await createEvaluationDataset({
                ...value,
                agentKey: 'customer-service',
                status: 'DRAFT',
              });
              setOpen(false);
              form.resetFields();
              await load();
              message.success('数据集已创建');
            })
            .catch((error) => {
              if (error instanceof Error) message.error(error.message);
            })
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
