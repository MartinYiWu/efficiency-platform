import { Button, Card, Descriptions, Empty, Table, Tag, Timeline, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import type { RunReplay } from '../../entities/ai-center/model';
import { getRunReplay } from '../../features/ai-center/api';
import styles from './AiCenter.module.css';

export function RunReplayPage() {
  const { runId = '' } = useParams();
  const navigate = useNavigate();
  const [replay, setReplay] = useState<RunReplay>();
  useEffect(() => {
    void getRunReplay(runId)
      .then(setReplay)
      .catch((error: Error) => message.error(error.message));
  }, [runId]);
  if (!replay) return <Empty description="正在加载运行事实" />;
  return (
    <section className={styles.page}>
      <header>
        <Button type="link" onClick={() => navigate('/ai-center/runs')}>
          返回运行列表
        </Button>
        <Typography.Title level={2}>Run 回放</Typography.Title>
      </header>
      <Descriptions
        bordered
        items={[
          { key: 'id', label: 'Run ID', children: replay.run.id },
          { key: 'status', label: '状态', children: <Tag>{replay.run.status}</Tag> },
          { key: 'mode', label: '回答模式', children: replay.run.answerMode ?? '-' },
          { key: 'release', label: 'Agent Release', children: replay.run.agentReleaseId },
        ]}
      />
      <Card title="问题">
        <div className={styles.pre}>{replay.question.content}</div>
      </Card>
      <Card title="结构化阶段">
        <Timeline
          items={replay.stages.map((stage) => ({
            color: stage.status === 'FAILED' ? 'red' : 'green',
            children: (
              <>
                <strong>{stage.stage}</strong>
                <p>{stage.publicSummary}</p>
              </>
            ),
          }))}
        />
      </Card>
      {replay.answer && (
        <Card title="最终回答">
          <div className={styles.pre}>{replay.answer.content}</div>
        </Card>
      )}
      <Card title="引用闭包">
        <Table
          rowKey="id"
          pagination={false}
          dataSource={replay.citations}
          columns={[
            { title: '#', dataIndex: 'citationNo' },
            { title: '文档', dataIndex: 'documentTitle' },
            { title: '版本', dataIndex: 'versionNo' },
            { title: '章节', dataIndex: 'sectionPath' },
            { title: '引用原文', dataIndex: 'quotedText' },
          ]}
        />
      </Card>
      {replay.run.failureMessage && (
        <Card title={replay.run.failureCode ?? '运行失败'}>{replay.run.failureMessage}</Card>
      )}
    </section>
  );
}
