import { DatabaseOutlined } from '@ant-design/icons';
import { Button, Drawer, Form, Input, Select, Spin, Table, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import type { KnowledgeBase } from '../../entities/knowledge/model';
import { createKnowledgeBase, listKnowledgeBases } from '../../features/knowledge/api';
import {
  knowledgeStatusLabel,
  knowledgeTypeLabel,
  visibilityScopeLabel,
} from '../../features/knowledge/presentation';
import styles from './KnowledgeCenter.module.css';

export function KnowledgeBaseListPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [submittedKeyword, setSubmittedKeyword] = useState('');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [form] = Form.useForm();
  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({ page: String(page), pageSize: '10' });
    if (submittedKeyword) query.set('keyword', submittedKeyword);
    if (typeFilter !== 'ALL') query.set('knowledgeType', typeFilter);
    void listKnowledgeBases(query.toString())
      .then((result) => {
        if (active) {
          setItems(result.items);
          setTotal(result.total);
        }
      })
      .catch((error: Error) => message.error(error.message))
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [page, submittedKeyword, typeFilter]);
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
      <div className={styles.catalogLayout}>
        <aside className={styles.catalogFilters} aria-label="资料分类">
          <strong>资料分类</strong>
          {[
            ['ALL', '全部资料'],
            ['COMPANY_POLICY', '公司制度'],
            ['BUSINESS_PROCESS', '业务流程'],
            ['PRODUCT_DOCUMENTATION', '产品文档'],
            ['TECHNICAL_DOCUMENTATION', '技术文档'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={typeFilter === value}
              className={`${styles.filterItem} ${typeFilter === value ? styles.filterActive : ''}`}
              onClick={() => {
                if (value !== typeFilter || page !== 1) {
                  setLoading(true);
                  setPage(1);
                  setTypeFilter(value);
                }
              }}
            >
              {label}
            </button>
          ))}
        </aside>
        <div className={styles.catalogResults}>
          <div className={styles.filters}>
            <Input.Search
              className={styles.search}
              placeholder="搜索知识库名称或描述"
              allowClear
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onSearch={(value) => {
                const next = value.trim();
                if (next !== submittedKeyword || page !== 1) {
                  setLoading(true);
                  setPage(1);
                  setSubmittedKeyword(next);
                }
              }}
            />
            <span className={styles.resultCount}>共 {total} 个知识库</span>
          </div>
          <Spin spinning={loading}>
            <Table<KnowledgeBase>
              rowKey="id"
              dataSource={items}
              pagination={{
                current: page,
                pageSize: 10,
                total,
                showSizeChanger: false,
                onChange: (value) => {
                  if (value !== page) {
                    setLoading(true);
                    setPage(value);
                  }
                },
              }}
              scroll={{ x: 850 }}
              onRow={(item) => ({
                onClick: () => navigate(`/knowledge-center/knowledge-bases/${item.id}`),
                className: styles.clickableRow,
              })}
              columns={[
                {
                  title: '知识库名称',
                  dataIndex: 'name',
                  key: 'name',
                  width: 235,
                  render: (name: string, item) => (
                    <span className={styles.baseName}>
                      <span className={styles.baseIcon}>
                        <DatabaseOutlined />
                      </span>
                      <span title={name}>
                        <strong>{name}</strong>
                        <small>{item.code}</small>
                      </span>
                    </span>
                  ),
                },
                {
                  title: '描述',
                  dataIndex: 'description',
                  key: 'description',
                  width: 225,
                  ellipsis: true,
                  render: (value: string | null) => value || '—',
                },
                {
                  title: '类型',
                  dataIndex: 'knowledgeType',
                  key: 'knowledgeType',
                  width: 105,
                  render: knowledgeTypeLabel,
                },
                {
                  title: '可见范围',
                  dataIndex: 'visibilityScope',
                  key: 'visibilityScope',
                  width: 105,
                  render: visibilityScopeLabel,
                },
                {
                  title: '更新时间',
                  dataIndex: 'updatedAt',
                  key: 'updatedAt',
                  width: 160,
                  render: (value: string) => (value ? value.replace('T', ' ').slice(0, 16) : '—'),
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  key: 'status',
                  width: 90,
                  render: (value: string) => (
                    <Tag color={value === 'ACTIVE' ? 'success' : 'default'}>
                      {knowledgeStatusLabel(value)}
                    </Tag>
                  ),
                },
                {
                  title: '操作',
                  key: 'action',
                  width: 75,
                  render: (_, item) => (
                    <Button
                      type="link"
                      onClick={(event) => {
                        event.stopPropagation();
                        navigate(`/knowledge-center/knowledge-bases/${item.id}`);
                      }}
                    >
                      查看
                    </Button>
                  ),
                },
              ]}
            />
          </Spin>
        </div>
      </div>
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
