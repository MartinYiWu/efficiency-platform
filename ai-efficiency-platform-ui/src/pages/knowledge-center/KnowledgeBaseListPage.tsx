import {
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import type { KnowledgeBase } from '../../entities/knowledge/model';
import { createKnowledgeBase, listKnowledgeBases } from '../../features/knowledge/api';
import { knowledgeStatusLabel, knowledgeTypeLabel, visibilityScopeLabel } from '../../features/knowledge/presentation';
import styles from './KnowledgeCenter.module.css';

export function KnowledgeBaseListPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [form] = Form.useForm();
  const load = async () => {
    setLoading(true);
    try {
      const result = await listKnowledgeBases(
        new URLSearchParams(keyword ? { keyword } : {}).toString(),
      );
      setItems(result.items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    let active = true;
    void listKnowledgeBases('')
      .then((result) => {
        if (active) setItems(result.items);
      })
      .catch((error: Error) => message.error(error.message))
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  const create = async () => {
    const value = await form.validateFields();
    try {
      const base = await createKnowledgeBase(value);
      message.success('知识库已创建');
      setOpen(false);
      form.resetFields();
      navigate(`/knowledge-center/knowledge-bases/${base.id}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建失败');
    }
  };
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <Typography.Title level={2}>知识中心</Typography.Title>
          <Typography.Text type="secondary">
            集中管理公司制度、业务流程、产品与技术文档。
          </Typography.Text>
        </div>
        <Button type="primary" onClick={() => setOpen(true)}>
          新建知识库
        </Button>
      </header>
      <div className={styles.filters}>
        <Input.Search
          placeholder="搜索知识库"
          allowClear
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onSearch={() => void load()}
          style={{ maxWidth: 360 }}
        />
      </div>
      <Spin spinning={loading}>
        {items.length ? (
          <div className={styles.cards}>
            {items.map((item) => (
              <Card
                key={item.id}
                hoverable
                onClick={() => navigate(`/knowledge-center/knowledge-bases/${item.id}`)}
                title={item.name}
                extra={<Tag color={item.status === 'ACTIVE' ? 'success' : 'default'}>{knowledgeStatusLabel(item.status)}</Tag>}
              >
                <p className={styles.cardMeta}>{item.description ?? '暂无描述'}</p>
                <Space>
                  <Tag variant="filled">{knowledgeTypeLabel(item.knowledgeType)}</Tag>
                  <span>{visibilityScopeLabel(item.visibilityScope)}</span>
                </Space>
              </Card>
            ))}
          </div>
        ) : (
          <Empty description="暂无知识库" />
        )}
      </Spin>
      <Drawer
        title="新建知识库"
        open={open}
        onClose={() => setOpen(false)}
        width={480}
        extra={
          <Button type="primary" onClick={() => void create()}>
            创建
          </Button>
        }
      >
        <Form form={form} layout="vertical" initialValues={{ knowledgeType: 'COMPANY_POLICY' }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="code"
            label="编码"
            rules={[{ required: true, pattern: /^[a-z0-9_-]+$/ }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="knowledgeType" label="知识类型" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'COMPANY_POLICY', label: '公司制度' },
                { value: 'BUSINESS_PROCESS', label: '业务流程' },
                { value: 'PRODUCT_DOCUMENTATION', label: '产品文档' },
                { value: 'TECHNICAL_DOCUMENTATION', label: '技术文档' },
              ]}
            />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Drawer>
    </section>
  );
}
