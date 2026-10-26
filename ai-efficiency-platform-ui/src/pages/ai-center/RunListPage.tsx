import { Button, Input, Select, Space, Table, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import type { AiRun } from '../../entities/ai-center/model';
import { listRuns } from '../../features/ai-center/api';
import { aiStatusLabel, answerModeLabel } from '../../features/ai-center/presentation';
import styles from './AiCenter.module.css';

export function RunListPage() {
  const [items, setItems] = useState<AiRun[]>([]);
  const [agentKey, setAgentKey] = useState('');
  const [status, setStatus] = useState('');
  const [answerMode, setAnswerMode] = useState('');
  const navigate = useNavigate();
  const load = async () => {
    const query = new URLSearchParams();
    if (agentKey) query.set('agentKey', agentKey);
    if (status) query.set('status', status);
    if (answerMode) query.set('answerMode', answerMode);
    try {
      setItems((await listRuns(query.toString())).items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    }
  };
  useEffect(() => {
    let active = true;
    void listRuns('')
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
        <Typography.Title level={2}>运行回放</Typography.Title>
        <Typography.Text type="secondary">
          默认查看全部 Agent 的结构化运行事实，可按 Agent、状态和回答模式过滤。
        </Typography.Text>
      </header>
      <div className={styles.filters}>
        <Input
          placeholder="Agent Key"
          value={agentKey}
          onChange={(event) => setAgentKey(event.target.value)}
          style={{ width: 220 }}
        />
        <Select
          allowClear
          placeholder="状态"
          value={status || undefined}
          onChange={(value) => setStatus(value ?? '')}
          style={{ width: 180 }}
          options={['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED'].map((value) => ({
            value,
            label: aiStatusLabel(value),
          }))}
        />
        <Select
          allowClear
          placeholder="回答模式"
          value={answerMode || undefined}
          onChange={(value) => setAnswerMode(value ?? '')}
          style={{ width: 200 }}
          options={['COMPANY_KNOWLEDGE', 'MIXED', 'GENERAL_ADVICE', 'INSUFFICIENT_EVIDENCE'].map((value) => ({
            value,
            label: answerModeLabel(value),
          }))}
        />
        <Button type="primary" onClick={() => void load()}>
          查询
        </Button>
      </div>
      <Table
        rowKey="id"
        dataSource={items}
        columns={[
          { title: 'Run ID', dataIndex: 'id', ellipsis: true },
          { title: '状态', dataIndex: 'status', render: (value: string) => <Tag>{aiStatusLabel(value)}</Tag> },
          {
            title: '回答模式',
            dataIndex: 'answerMode',
            render: (value: string | null) => value ? answerModeLabel(value) : '-',
          },
          { title: 'Release', dataIndex: 'agentReleaseId', ellipsis: true },
          {
            title: '开始时间',
            dataIndex: 'startedAt',
            render: (value: string | null) => value ?? '-',
          },
          {
            title: '操作',
            render: (_, item) => (
              <Space>
                <Button type="link" onClick={() => navigate(`/ai-center/runs/${item.id}`)}>
                  回放
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </section>
  );
}
