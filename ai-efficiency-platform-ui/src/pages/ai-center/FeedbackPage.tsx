import { Button, Input, Select, Table, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import type { AiFeedback } from '../../entities/ai-center/model';
import { listFeedback } from '../../features/ai-center/api';
import styles from './AiCenter.module.css';
import { formatAiDate } from './datePresentation';

export function FeedbackPage() {
  const [items, setItems] = useState<AiFeedback[]>([]);
  const [rating, setRating] = useState('');
  const [reasonCode, setReasonCode] = useState('');
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const load = async (nextPage = 1) => {
    const query = new URLSearchParams({ page: String(nextPage), pageSize: '10' });
    if (rating) query.set('rating', rating);
    if (reasonCode) query.set('reasonCode', reasonCode);
    setLoading(true);
    try {
      const result = await listFeedback(query.toString());
      setItems(result.items);
      setTotal(result.total);
      setPage(nextPage);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    let active = true;
    void listFeedback('page=1&pageSize=10')
      .then((value) => {
        if (active) {
          setItems(value.items);
          setTotal(value.total);
        }
      })
      .catch((error: Error) => message.error(error.message));
    return () => {
      active = false;
    };
  }, []);
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <Typography.Title level={2}>用户反馈</Typography.Title>
          <Typography.Text type="secondary">
            查看内部用户对回答的当前反馈，并跳转到对应运行事实。
          </Typography.Text>
        </div>
      </header>
      <div className={styles.objectWorkspace}>
        <div className={styles.listToolbar}>
          <h3>
            反馈记录 <span>{total}</span>
          </h3>
          <div className={styles.filters}>
            <Select
              allowClear
              placeholder="评价"
              value={rating || undefined}
              onChange={(value) => setRating(value ?? '')}
              style={{ width: 160 }}
              options={[
                { value: 'UP', label: '点赞' },
                { value: 'DOWN', label: '点踩' },
              ]}
            />
            <Input
              placeholder="原因编码"
              value={reasonCode}
              onChange={(event) => setReasonCode(event.target.value)}
              style={{ width: 220 }}
            />
            <Button type="primary" onClick={() => void load()}>
              查询
            </Button>
          </div>
        </div>
        <Table
          rowKey="id"
          dataSource={items}
          loading={loading}
          scroll={{ x: 960 }}
          pagination={{
            current: page,
            pageSize: 10,
            total,
            hideOnSinglePage: true,
            showSizeChanger: false,
            onChange: (nextPage) => void load(nextPage),
          }}
          columns={[
            {
              title: '评价',
              dataIndex: 'rating',
              width: 100,
              render: (value: string) => (
                <Tag color={value === 'UP' ? 'success' : 'warning'}>
                  {value === 'UP' ? '点赞' : value === 'DOWN' ? '点踩' : value}
                </Tag>
              ),
            },
            {
              title: '原因',
              dataIndex: 'reasonCode',
              render: (value: string | null) => value ?? '-',
            },
            {
              title: '补充说明',
              dataIndex: 'comment',
              render: (value: string | null) => value ?? '-',
            },
            { title: '用户', dataIndex: 'userId' },
            { title: '时间', dataIndex: 'updatedAt', render: formatAiDate, width: 170 },
            {
              title: '操作',
              render: (_, item) => (
                <Button type="link" onClick={() => navigate(`/ai-center/runs/${item.runId}`)}>
                  查看原 Run
                </Button>
              ),
            },
          ]}
        />
      </div>
    </section>
  );
}
