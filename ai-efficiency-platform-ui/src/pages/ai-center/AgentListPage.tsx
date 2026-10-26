import { Button, Card, Empty, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import type { AgentDefinition } from '../../entities/ai-center/model';
import { listAgents } from '../../features/ai-center/api';
import { aiStatusLabel } from '../../features/ai-center/presentation';
import styles from './AiCenter.module.css';

export function AgentListPage() {
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const navigate = useNavigate();
  useEffect(() => {
    void listAgents()
      .then(setAgents)
      .catch((error: Error) => message.error(error.message));
  }, []);
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
      {agents.length ? (
        <div className={`${styles.grid} ${styles.agentGrid}`}>
          {agents.map((agent) => (
            <Card
              key={agent.id}
              title={agent.name}
              extra={<Tag color={agent.status === 'ACTIVE' ? 'success' : 'default'}>{aiStatusLabel(agent.status)}</Tag>}
              actions={[
                <Button
                  key="detail"
                  type="link"
                  onClick={() => navigate(`/ai-center/agents/${agent.id}`)}
                >
                  管理版本
                </Button>,
              ]}
            >
              <p>{agent.description ?? '暂无描述'}</p>
              <code>{agent.agentKey}</code>
            </Card>
          ))}
        </div>
      ) : (
        <Empty description="暂无 Agent" />
      )}
    </section>
  );
}
