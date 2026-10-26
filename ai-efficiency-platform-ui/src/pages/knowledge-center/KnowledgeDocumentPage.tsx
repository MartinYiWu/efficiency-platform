import {
  Button,
  Card,
  Descriptions,
  Empty,
  Space,
  Table,
  Tag,
  Timeline,
  Typography,
  Upload,
  message,
} from 'antd';
import type { UploadFile } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import type { KnowledgeDocument } from '../../entities/knowledge/model';
import { ProcessingTaskDrawer } from '../../features/knowledge/ProcessingTaskDrawer';
import { EvidenceModeSelect, type EvidenceMode } from '../../features/knowledge/EvidenceModeSelect';
import { documentSourceLabel, knowledgeStatusLabel } from '../../features/knowledge/presentation';
import {
  getDocument,
  getKnowledgeBase,
  publishDocumentVersion,
  uploadDocumentVersion,
} from '../../features/knowledge/api';
import styles from './KnowledgeCenter.module.css';

export function KnowledgeDocumentPage() {
  const { documentId = '' } = useParams();
  const navigate = useNavigate();
  const [document, setDocument] = useState<KnowledgeDocument>();
  const [taskId, setTaskId] = useState<string>();
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [knowledgeType, setKnowledgeType] = useState<string>();
  const [evidenceMode, setEvidenceMode] = useState<EvidenceMode>('FULL_ONLY');
  useEffect(() => {
    if (!document) return;
    let active = true;
    void getKnowledgeBase(document.knowledgeBaseId)
      .then((base) => {
        if (active) setKnowledgeType(base.knowledgeType);
      })
      .catch((error: Error) => message.error(error.message));
    return () => {
      active = false;
    };
  }, [document]);
  const load = async () => {
    try {
      setDocument(await getDocument(documentId));
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    }
  };
  useEffect(() => {
    let active = true;
    void getDocument(documentId)
      .then((value) => {
        if (active) setDocument(value);
      })
      .catch((error: Error) => message.error(error.message));
    return () => {
      active = false;
    };
  }, [documentId]);
  const upload = async () => {
    const file = files[0]?.originFileObj;
    if (!(file instanceof File)) {
      message.warning('请选择新版本文件');
      return;
    }
    try {
      const allowed =
        knowledgeType === 'PRODUCT_DOCUMENTATION' || knowledgeType === 'TECHNICAL_DOCUMENTATION';
      await uploadDocumentVersion(
        documentId,
        file,
        '后台手工更新版本',
        undefined,
        allowed ? evidenceMode : 'FULL_ONLY',
      );
      setFiles([]);
      message.success('新版本已提交处理');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '上传失败');
    }
  };
  if (!document) return <Empty description="正在加载文档" />;
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <Button
            type="link"
            className={styles.link}
            onClick={() =>
              navigate(`/knowledge-center/knowledge-bases/${document.knowledgeBaseId}`)
            }
          >
            返回知识库
          </Button>
          <Typography.Title level={2}>{document.title}</Typography.Title>
          <Typography.Text type="secondary">{document.documentCode}</Typography.Text>
        </div>
        <Space>
          <Upload
            beforeUpload={() => false}
            maxCount={1}
            fileList={files}
            onChange={({ fileList }) => setFiles(fileList)}
          >
            <Button>选择新版本</Button>
          </Upload>
          <Button type="primary" onClick={() => void upload()}>
            上传版本
          </Button>
        </Space>
      </header>
      <Descriptions
        bordered
        column={{ xs: 1, md: 3 }}
        items={[
          { key: 'source', label: '来源', children: documentSourceLabel(document.sourceType) },
          { key: 'status', label: '状态', children: <Tag>{knowledgeStatusLabel(document.status)}</Tag> },
          {
            key: 'published',
            label: '已发布版本',
            children: document.currentPublishedVersionId ?? '未发布',
          },
        ]}
      />
      <Card title="版本记录">
        <EvidenceModeSelect
          knowledgeType={knowledgeType}
          value={evidenceMode}
          onChange={setEvidenceMode}
        />
        <Timeline
          items={document.versions.map((version) => ({
            color:
              version.status === 'PUBLISHED'
                ? 'green'
                : version.status === 'FAILED'
                  ? 'red'
                  : 'blue',
            children: (
              <div>
                <Space>
                  <strong>V{version.versionNo}</strong>
                  <Tag>{knowledgeStatusLabel(version.status)}</Tag>
                  <span>{version.createdAt}</span>
                </Space>
                <p>{version.changeSummary ?? '未填写变更说明'}</p>
                <p>
                  冻结证据模式：
                  {version.evidenceMode === 'EXTRACTIVE_NARRATIVE'
                    ? '允许叙述性原文节选'
                    : '全文优先'}
                </p>
                <Space>
                  {version.processingTasks.map((task) => (
                    <Button key={task.id} size="small" onClick={() => setTaskId(task.id)}>
                      处理任务 {task.progressPercent}%
                    </Button>
                  ))}
                  {version.status === 'READY' && (
                    <Button
                      size="small"
                      type="primary"
                      onClick={() =>
                        void publishDocumentVersion(version.id)
                          .then(() => load())
                          .catch((error: Error) => message.error(error.message))
                      }
                    >
                      发布
                    </Button>
                  )}
                </Space>
              </div>
            ),
          }))}
        />
      </Card>
      <Card title="处理任务">
        <Table
          rowKey="id"
          pagination={false}
          dataSource={document.versions.flatMap((version) => version.processingTasks)}
          columns={[
            { title: '阶段', dataIndex: 'stage' },
            { title: '状态', dataIndex: 'status', render: (value: string) => knowledgeStatusLabel(value) },
            { title: '进度', dataIndex: 'progressPercent', render: (value: number) => `${value}%` },
            {
              title: '操作',
              render: (_, task) => (
                <Button type="link" onClick={() => setTaskId(task.id)}>
                  详情
                </Button>
              ),
            },
          ]}
        />
      </Card>
      <ProcessingTaskDrawer
        open={Boolean(taskId)}
        taskId={taskId}
        onClose={() => setTaskId(undefined)}
      />
    </section>
  );
}
