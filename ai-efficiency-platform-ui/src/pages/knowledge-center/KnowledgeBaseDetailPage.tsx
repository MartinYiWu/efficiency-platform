import {
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Modal,
  Space,
  Table,
  Tabs,
  Tree,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import type {
  IndexRelease,
  KnowledgeBase,
  KnowledgeDirectory,
  KnowledgeDocument,
} from '../../entities/knowledge/model';
import { KnowledgeBatchImportModal } from '../../features/knowledge/KnowledgeBatchImportModal';
import { KnowledgeUploadDrawer } from '../../features/knowledge/KnowledgeUploadDrawer';
import {
  createDirectory,
  getKnowledgeBase,
  listDirectories,
  listDocuments,
  listIndexReleases,
  rollbackIndexRelease,
} from '../../features/knowledge/api';
import styles from './KnowledgeCenter.module.css';

export function KnowledgeBaseDetailPage() {
  const { baseId = '' } = useParams();
  const navigate = useNavigate();
  const [base, setBase] = useState<KnowledgeBase>();
  const [directories, setDirectories] = useState<KnowledgeDirectory[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [releases, setReleases] = useState<IndexRelease[]>([]);
  const [directoryId, setDirectoryId] = useState<string>();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchId, setBatchId] = useState<string>();
  const load = useCallback(async () => {
    try {
      const [nextBase, nextDirectories, nextDocuments, nextReleases] = await Promise.all([
        getKnowledgeBase(baseId),
        listDirectories(baseId),
        listDocuments(baseId, new URLSearchParams(directoryId ? { directoryId } : {}).toString()),
        listIndexReleases(baseId),
      ]);
      setBase(nextBase);
      setDirectories(nextDirectories);
      setDocuments(nextDocuments.items);
      setReleases(nextReleases);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载失败');
    }
  }, [baseId, directoryId]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  const addDirectory = () => {
    let name = '';
    Modal.confirm({
      title: '新建目录',
      content: (
        <Input
          placeholder="目录名称"
          onChange={(event) => {
            name = event.target.value;
          }}
        />
      ),
      onOk: async () => {
        if (!name.trim()) throw new Error('请输入目录名称');
        await createDirectory(baseId, {
          name: name.trim(),
          parentId: directoryId ?? null,
          sortNo: directories.length + 1,
        });
        message.success('目录已创建');
        await load();
      },
    });
  };
  if (!base) return <Empty description="正在加载知识库" />;
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <Button
            type="link"
            className={styles.link}
            onClick={() => navigate('/knowledge-center/knowledge-bases')}
          >
            返回知识中心
          </Button>
          <Typography.Title level={2}>{base.name}</Typography.Title>
          <Typography.Text type="secondary">{base.description ?? '暂无描述'}</Typography.Text>
        </div>
        <Space>
          <Button onClick={() => setBatchOpen(true)}>批量导入</Button>
          <Button type="primary" onClick={() => setUploadOpen(true)}>
            上传文档
          </Button>
        </Space>
      </header>
      <Descriptions
        bordered
        size="small"
        column={{ xs: 1, sm: 2, lg: 4 }}
        items={[
          { key: 'type', label: '类型', children: base.knowledgeType },
          { key: 'scope', label: '范围', children: base.visibilityScope },
          { key: 'status', label: '状态', children: base.status },
          {
            key: 'release',
            label: '当前索引版本',
            children: base.currentIndexReleaseId ?? '未发布',
          },
        ]}
      />
      <div className={styles.split}>
        <Card
          className={styles.directory}
          title="目录"
          extra={
            <Button size="small" onClick={addDirectory}>
              新建
            </Button>
          }
        >
          <Tree
            defaultExpandAll
            selectedKeys={directoryId ? [directoryId] : []}
            onSelect={(keys) => setDirectoryId(keys[0]?.toString())}
            treeData={[
              {
                key: '',
                title: '全部文档',
                children: directories.map((item) => ({ key: item.id, title: item.name })),
              },
            ]}
          />
        </Card>
        <Tabs
          items={[
            {
              key: 'documents',
              label: `文档（${documents.length}）`,
              children: documents.length ? (
                <Table
                  rowKey="id"
                  dataSource={documents}
                  pagination={false}
                  columns={[
                    { title: '名称', dataIndex: 'title' },
                    { title: '编码', dataIndex: 'documentCode' },
                    { title: '状态', dataIndex: 'status' },
                    { title: '版本数', render: (_, item) => item.versions.length },
                    {
                      title: '操作',
                      render: (_, item) => (
                        <Button
                          type="link"
                          onClick={() => navigate(`/knowledge-center/documents/${item.id}`)}
                        >
                          查看
                        </Button>
                      ),
                    },
                  ]}
                />
              ) : (
                <Empty description="当前目录暂无文档" />
              ),
            },
            {
              key: 'releases',
              label: '索引版本',
              children: (
                <Table
                  rowKey="id"
                  dataSource={releases}
                  pagination={false}
                  columns={[
                    {
                      title: '版本',
                      dataIndex: 'releaseNo',
                      render: (value: number) => `R${value}`,
                    },
                    { title: '状态', dataIndex: 'status' },
                    {
                      title: '文档/分块',
                      render: (_, item) => `${item.documentCount}/${item.chunkCount}`,
                    },
                    { title: '模型', dataIndex: 'embeddingModel' },
                    {
                      title: '操作',
                      render: (_, item) =>
                        item.status !== 'ACTIVE' ? (
                          <Button
                            type="link"
                            onClick={() =>
                              void rollbackIndexRelease(item.id)
                                .then(() => load())
                                .catch((error: Error) => message.error(error.message))
                            }
                          >
                            回滚到此版本
                          </Button>
                        ) : (
                          '当前版本'
                        ),
                    },
                  ]}
                />
              ),
            },
          ]}
        />
      </div>
      <KnowledgeUploadDrawer
        open={uploadOpen}
        baseId={baseId}
        directories={directories}
        onClose={() => setUploadOpen(false)}
        onSubmitted={(id) => {
          setBatchId(id);
          setBatchOpen(true);
        }}
      />
      <KnowledgeBatchImportModal
        open={batchOpen}
        baseId={baseId}
        directories={directories}
        initialBatchId={batchId}
        onClose={() => {
          setBatchOpen(false);
          setBatchId(undefined);
        }}
        onChanged={load}
      />
    </section>
  );
}
