import {
  Button,
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
      </header>
      <section className={styles.section} aria-labelledby="document-information">
        <div className={styles.sectionHeading}>
          <Typography.Title level={3} id="document-information">
            文档信息
          </Typography.Title>
        </div>
        <Descriptions
          column={{ xs: 1, md: 3 }}
          items={[
            { key: 'source', label: '来源', children: documentSourceLabel(document.sourceType) },
            {
              key: 'status',
              label: '状态',
              children: <Tag>{knowledgeStatusLabel(document.status)}</Tag>,
            },
            {
              key: 'published',
              label: '已发布版本',
              children: document.currentPublishedVersionId ?? '未发布',
            },
          ]}
        />
      </section>
      <div className={styles.versionUploadBar}>
        <div>
          <strong>更新文档版本</strong>
          <p>选择处理方式和文件，提交后在下方查看版本与处理任务。</p>
        </div>
        <EvidenceModeSelect
          knowledgeType={knowledgeType}
          value={evidenceMode}
          onChange={setEvidenceMode}
        />
        <Space wrap>
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
      </div>
      <section className={styles.section} aria-labelledby="document-versions">
        <div className={styles.sectionHeading}>
          <Typography.Title level={3} id="document-versions">
            版本记录
          </Typography.Title>
          <span>共 {document.versions.length} 个版本</span>
        </div>
        {document.versions.length ? (
          <Timeline
            items={document.versions.map((version) => ({
              color:
                version.status === 'PUBLISHED'
                  ? 'green'
                  : version.status === 'FAILED'
                    ? 'red'
                    : 'blue',
              content: (
                <div className={styles.versionItem}>
                  <Space wrap>
                    <strong>V{version.versionNo}</strong>
                    <Tag>{knowledgeStatusLabel(version.status)}</Tag>
                    <time dateTime={version.createdAt} title={version.createdAt}>
                      {version.createdAt.replace('T', ' ').slice(0, 16)}
                    </time>
                  </Space>
                  <p>{version.changeSummary ?? '未填写变更说明'}</p>
                  <p>
                    冻结证据模式：
                    {version.evidenceMode === 'EXTRACTIVE_NARRATIVE'
                      ? '允许叙述性原文节选'
                      : '全文优先'}
                  </p>
                  <Space wrap>
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
        ) : (
          <Empty description="暂无版本记录" />
        )}
      </section>
      <section className={styles.section} aria-labelledby="document-tasks">
        <div className={styles.sectionHeading}>
          <Typography.Title level={3} id="document-tasks">
            处理任务
          </Typography.Title>
        </div>
        <Table
          rowKey="id"
          pagination={false}
          scroll={{ x: 580 }}
          dataSource={document.versions.flatMap((version) =>
            version.processingTasks.map((task) => ({ ...task, versionNo: version.versionNo })),
          )}
          columns={[
            { title: '文档版本', dataIndex: 'versionNo', render: (value: number) => `V${value}` },
            { title: '阶段', dataIndex: 'stage' },
            {
              title: '状态',
              dataIndex: 'status',
              render: (value: string) => knowledgeStatusLabel(value),
            },
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
      </section>
      <section className={styles.section} aria-labelledby="document-source">
        <div className={styles.sectionHeading}>
          <div>
            <Typography.Title level={3} id="document-source">
              原文与引用信息
            </Typography.Title>
            <Typography.Text type="secondary">
              按版本核对原文文件标识与格式，已发布版本标识见文档信息。
            </Typography.Text>
          </div>
        </div>
        <Table
          rowKey="id"
          dataSource={document.versions}
          pagination={false}
          scroll={{ x: 660 }}
          columns={[
            {
              title: '版本',
              dataIndex: 'versionNo',
              width: 80,
              render: (value: number) => `V${value}`,
            },
            { title: '原文文件标识', dataIndex: 'fileId', ellipsis: true },
            { title: '文件格式', dataIndex: 'contentType', width: 220, ellipsis: true },
            {
              title: '生效日期',
              dataIndex: 'effectiveDate',
              width: 140,
              render: (value: string | null) => value ?? '未设置',
            },
          ]}
        />
      </section>
      <ProcessingTaskDrawer
        open={Boolean(taskId)}
        taskId={taskId}
        onClose={() => setTaskId(undefined)}
      />
    </section>
  );
}
