import { Button, Card, Empty, Input, Select, Space, Steps, Table, Typography, message } from 'antd';
import { useEffect, useState } from 'react';

import type {
  AgentDefinition,
  AgentDetail,
  AgentRelease,
  DebugView,
  RagPolicy,
} from '../../entities/ai-center/model';
import {
  executeRagDebug,
  getAgent,
  listAgentReleases,
  listAgents,
  listPolicies,
} from '../../features/ai-center/api';
import styles from './AiCenter.module.css';

export function RagDebugPage() {
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [agentId, setAgentId] = useState('');
  const [detail, setDetail] = useState<AgentDetail>();
  const [policies, setPolicies] = useState<RagPolicy[]>([]);
  const [releases, setReleases] = useState<AgentRelease[]>([]);
  const [agentReleaseId, setAgentReleaseId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [policyId, setPolicyId] = useState('');
  const [baseId, setBaseId] = useState('');
  const [releaseId, setReleaseId] = useState('');
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<DebugView>();
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    void listAgents().then(setAgents);
  }, []);
  const selectAgent = async (id: string) => {
    setAgentId(id);
    setVersionId('');
    setPolicyId('');
    setAgentReleaseId('');
    setResult(undefined);
    try {
      const agent = agents.find((item) => item.id === id);
      if (!agent) return;
      const [nextDetail, nextPolicies, nextReleases] = await Promise.all([
        getAgent(id),
        listPolicies(id),
        listAgentReleases(agent.agentKey),
      ]);
      setDetail(nextDetail);
      setPolicies(nextPolicies.ragPolicies);
      setReleases(nextReleases);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    }
  };
  const run = async () => {
    if (
      !agentId ||
      !agentReleaseId ||
      !versionId ||
      !policyId ||
      !baseId ||
      !releaseId ||
      !question.trim()
    ) {
      message.warning('请完整填写调试输入');
      return;
    }
    const agent = agents.find((item) => item.id === agentId);
    if (!agent) return;
    setLoading(true);
    try {
      setResult(
        await executeRagDebug({
          agentKey: agent.agentKey,
          question,
          agentReleaseId,
          agentVersionId: versionId,
          ragPolicyVersionId: policyId,
          knowledgeBindings: [{ knowledgeBaseId: baseId, indexReleaseId: releaseId }],
        }),
      );
    } catch (error) {
      message.error(error instanceof Error ? error.message : '调试失败');
    } finally {
      setLoading(false);
    }
  };
  return (
    <section className={styles.page}>
      <header>
        <Typography.Title level={2}>RAG 调试</Typography.Title>
        <Typography.Text type="secondary">
          只展示结构化执行阶段和证据摘要，不展示隐藏思维链或完整 Prompt。
        </Typography.Text>
      </header>
      <div className={styles.threeColumns}>
        <Card className={styles.panel} title="调试输入">
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Select
              placeholder="Agent"
              value={agentId || undefined}
              onChange={(value) => void selectAgent(value)}
              options={agents.map((item) => ({ label: item.name, value: item.id }))}
            />
            <Select
              placeholder="ACTIVE Release"
              value={agentReleaseId || undefined}
              onChange={(value) => {
                setAgentReleaseId(value);
                const release = releases.find((item) => item.id === value);
                if (release) setVersionId(release.agentVersionId);
              }}
              options={releases
                .filter((item) => item.releaseStatus === 'ACTIVE')
                .map((item) => ({ label: `${item.environment} · ${item.id}`, value: item.id }))}
            />
            <Select
              placeholder="Agent 版本"
              value={versionId || undefined}
              onChange={setVersionId}
              options={detail?.versions.map((item) => ({
                label: `${item.semanticVersion} · ${item.status}`,
                value: item.id,
              }))}
            />
            <Select
              placeholder="RAG 策略"
              value={policyId || undefined}
              onChange={setPolicyId}
              options={policies.map((item) => ({
                label: `${item.policyKey}@${item.semanticVersion}`,
                value: item.id,
              }))}
            />
            <Input
              placeholder="知识库 ID"
              value={baseId}
              onChange={(event) => setBaseId(event.target.value)}
            />
            <Input
              placeholder="索引 Release ID"
              value={releaseId}
              onChange={(event) => setReleaseId(event.target.value)}
            />
            <Input.TextArea
              rows={8}
              placeholder="输入真实问题"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
            <Button type="primary" loading={loading} onClick={() => void run()}>
              执行调试
            </Button>
          </Space>
        </Card>
        <Card className={styles.panel} title="执行阶段">
          {result ? (
            <Steps
              direction="vertical"
              status={result.status === 'FAILED' ? 'error' : 'finish'}
              items={result.stages.map((stage) => ({
                title: stage.stage_key,
                description: stage.public_summary,
                status:
                  stage.status === 'FAILED'
                    ? 'error'
                    : stage.status === 'SUCCEEDED'
                      ? 'finish'
                      : 'process',
              }))}
            />
          ) : (
            <Empty description="执行后显示真实阶段" />
          )}
        </Card>
        <Card className={styles.panel} title="召回 Chunk">
          {result ? (
            <Table
              size="small"
              rowKey="chunk_id"
              pagination={false}
              dataSource={result.stages.flatMap((stage) => stage.evidence)}
              columns={[
                { title: '章节', dataIndex: 'section_path' },
                { title: '分数', dataIndex: 'score', render: (value: number) => value.toFixed(3) },
                { title: '摘要', dataIndex: 'excerpt' },
              ]}
            />
          ) : (
            <Empty description="暂无证据" />
          )}
        </Card>
      </div>
      {result?.error_message && (
        <Card title={result.error_code ?? '调试失败'}>{result.error_message}</Card>
      )}
      {result?.answer_markdown && (
        <Card title={`回答模式：${result.answer_mode}`}>
          <div className={styles.pre}>{result.answer_markdown}</div>
        </Card>
      )}
    </section>
  );
}
