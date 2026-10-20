import { Button, Input, Select, Table, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import type { AiFeedback } from '../../entities/ai-center/model';
import { listFeedback } from '../../features/ai-center/api';
import styles from './AiCenter.module.css';

export function FeedbackPage() {
  const [items, setItems] = useState<AiFeedback[]>([]);
  const [rating, setRating] = useState('');
  const [reasonCode, setReasonCode] = useState('');
  const navigate = useNavigate();
  const load = async () => {
    const query = new URLSearchParams();
    if (rating) query.set('rating', rating);
    if (reasonCode) query.set('reasonCode', reasonCode);
    try {
      setItems((await listFeedback(query.toString())).items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    }
  };
  useEffect(() => {
    let active = true;
    void listFeedback('')
      .then((value) => {
        if (active) setItems(value.items);
      })
      .catch((error: Error) => message.error(error.message));
    return () => {
      active = false;
    };
  }, []);
  return (
    <section className={styles.page}>
      <header>
        <Typography.Title level={2}>用户反馈</Typography.Title>
        <Typography.Text type="secondary">
          查看内部用户对回答的当前反馈，并跳转到对应运行事实。
        </Typography.Text>
      </header>
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
      <Table
        rowKey="id"
        dataSource={items}
        columns={[
          { title: '评价', dataIndex: 'rating' },
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
          { title: '时间', dataIndex: 'updatedAt' },
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
    </section>
  );
}
