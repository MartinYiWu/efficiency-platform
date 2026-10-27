import { Button, Empty, Input, Result, Table, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import type { AgentDefinition, AgentDetail } from '../../entities/ai-center/model';
import { getAgent, listAgents } from '../../features/ai-center/api';
import { agentTypeLabel, aiStatusLabel } from '../../features/ai-center/presentation';
import styles from './AiCenter.module.css';

export function AgentListPage() {
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [keyword, setKeyword] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<AgentDetail>();
  const [detailError, setDetailError] = useState('');
  const [retryKey, setRetryKey] = useState(0);
  const navigate = useNavigate();
  useEffect(() => {
    void listAgents()
      .then((items) => { setAgents(items); setSelectedId(items[0]?.id ?? ''); })
      .catch((error: Error) => message.error(error.message));
  }, []);
  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    void getAgent(selectedId).then((value) => { if (active) setDetail(value); }).catch((error: Error) => { if (active) setDetailError(error.message); });
    return () => { active = false; };
  }, [selectedId, retryKey]);
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <Typography.Title level={2}>Agent 管理</Typography.Title>
          <Typography.Text type="secondary">
            管理独立 Agent 的定义、版本、策略绑定与发布。
          </Typography.Text>
        </div>
      </header>
      <div className={styles.agentWorkspace}>
        <aside className={styles.agentSelector} aria-label="Agent 列表">
          <h3>Agent 列表 <span>{agents.length}</span></h3>
          <Input.Search allowClear placeholder="搜索 Agent 名称或标识" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          <div className={styles.agentOptions}>
            {agents.filter((agent) => `${agent.name} ${agent.agentKey}`.toLowerCase().includes(keyword.toLowerCase())).map((agent) => <button key={agent.id} type="button" className={`${styles.agentOption} ${selectedId === agent.id ? styles.agentOptionActive : ''}`} onClick={() => { setSelectedId(agent.id); setDetail(undefined); setDetailError(''); }}><span className={styles.agentMark}>AI</span><span><strong>{agent.name}</strong><small>{agent.agentKey}</small></span><Tag color={agent.status === 'ACTIVE' ? 'success' : 'default'}>{aiStatusLabel(agent.status)}</Tag></button>)}
            {agents.length === 0 && <Empty description="暂无 Agent" />}
          </div>
        </aside>
        <section className={styles.agentOverview}>
          {detail ? <>
            <div className={styles.overviewHeader}><div><h3>{detail.definition.name}</h3><p>{detail.definition.description || '暂无描述'}</p></div><Button type="primary" onClick={() => navigate(`/ai-center/agents/${detail.definition.id}`)}>管理版本</Button></div>
            <div className={styles.overviewFacts}><div><span>Agent Key</span><strong>{detail.definition.agentKey}</strong></div><div><span>类型</span><strong>{agentTypeLabel(detail.definition.agentType)}</strong></div><div><span>状态</span><strong>{aiStatusLabel(detail.definition.status)}</strong></div><div><span>创建时间</span><strong>{detail.definition.createdAt.replace('T', ' ').slice(0, 16)}</strong></div></div>
            <div className={styles.overviewSection}><h4>版本管理</h4><Table rowKey="id" pagination={{ pageSize: 6, hideOnSinglePage: true }} scroll={{ x: 620 }} dataSource={detail.versions} columns={[{ title: '版本', dataIndex: 'semanticVersion' }, { title: '状态', dataIndex: 'status', render: aiStatusLabel }, { title: '更新说明', dataIndex: 'changeSummary', render: (value: string | null) => value || '—' }, { title: '创建时间', dataIndex: 'createdAt', render: (value: string) => value.replace('T', ' ').slice(0, 16) }]} /></div>
            <div className={styles.overviewSection}><h4>版本 / Release 证据绑定</h4><Table rowKey={(item, index) => item.sourceType + item.sourceId + index} pagination={{ pageSize: 5, hideOnSinglePage: true }} scroll={{ x: 620 }} dataSource={detail.evidenceBindings ?? []} columns={[{ title: '来源类型', dataIndex: 'sourceType' }, { title: '来源标识', dataIndex: 'sourceId', ellipsis: true }, { title: '绑定索引', dataIndex: 'boundIndexReleaseId', render: (value: string | null) => value || '未绑定' }, { title: '模型', dataIndex: 'largeModelName', render: (value: string | null) => value || '未绑定' }]} /></div>
          </> : detailError ? <Result status="error" title="Agent 详情加载失败" subTitle={detailError} extra={<Button onClick={() => { setDetailError(''); setRetryKey((value) => value + 1); }}>重试</Button>} /> : <Empty description={selectedId ? '正在加载 Agent 详情' : '请选择 Agent'} />}
        </section>
      </div>
    </section>
  );
}
