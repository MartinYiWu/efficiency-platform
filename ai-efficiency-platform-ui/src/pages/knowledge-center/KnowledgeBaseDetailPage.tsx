import {
  Alert,
  Button,
  Descriptions,
  Empty,
  Input,
  Modal,
  Space,
  Table,
  Tree,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
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
  knowledgeStatusLabel,
  knowledgeTypeLabel,
  visibilityScopeLabel,
} from '../../features/knowledge/presentation';
import {
  createDirectory,
  getKnowledgeBase,
  listDirectories,
  listDocuments,
  listIndexReleases,
  rollbackIndexRelease,
  updateKnowledgeBase,
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
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchId, setBatchId] = useState<string>();
  const [isActivating, setIsActivating] = useState(false);
  const loadSequence = useRef(0);
  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    try {
      const query = new URLSearchParams({ page: String(page), pageSize: '10' });
      if (directoryId) query.set('directoryId', directoryId);
      const [nextBase, nextDirectories, nextDocuments, nextReleases] = await Promise.all([
        getKnowledgeBase(baseId),
        listDirectories(baseId),
        listDocuments(baseId, query.toString()),
        listIndexReleases(baseId),
      ]);
      if (sequence !== loadSequence.current) return;
      setBase(nextBase);
      setDirectories(nextDirectories);
      setDocuments(nextDocuments.items);
      setTotal(nextDocuments.total);
      setReleases(nextReleases);
      return true;
    } catch (error) {
      if (sequence === loadSequence.current) {
        message.error(error instanceof Error ? error.message : '加载失败');
      }
    }
  }, [baseId, directoryId, page]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => {
      window.clearTimeout(timer);
      loadSequence.current += 1;
    };
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
  const isActive = base.status === 'ACTIVE';
  const activateBase = async () => {
    setIsActivating(true);
    try {
      await updateKnowledgeBase(baseId, {
        name: base.name,
        description: base.description,
        knowledgeType: base.knowledgeType,
        status: 'ACTIVE',
      });
      if (await load()) message.success('知识库已启用');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '启用知识库失败');
    } finally {
      setIsActivating(false);
    }
  };
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
        <Space wrap>
          {(base.status === 'DRAFT' || base.status === 'DISABLED') && (
            <Button loading={isActivating} onClick={() => void activateBase()}>
              启用知识库
            </Button>
          )}
          <Button disabled={!isActive} onClick={() => setBatchOpen(true)}>
            批量导入
          </Button>
          <Button type="primary" disabled={!isActive} onClick={() => setUploadOpen(true)}>
            上传文档
          </Button>
        </Space>
      </header>
      {!isActive && (
        <Alert
          type="warning"
          showIcon
          title="知识库未启用，请先启用知识库后再上传文档或批量导入。"
        />
      )}
      <section className={styles.section} aria-labelledby="base-information">
        <div className={styles.sectionHeading}>
          <Typography.Title level={3} id="base-information">
            知识库信息
          </Typography.Title>
          <span>{base.code}</span>
        </div>
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2, lg: 4 }}
          items={[
            { key: 'type', label: '类型', children: knowledgeTypeLabel(base.knowledgeType) },
            { key: 'scope', label: '范围', children: visibilityScopeLabel(base.visibilityScope) },
            { key: 'status', label: '状态', children: knowledgeStatusLabel(base.status) },
            {
              key: 'release',
              label: '当前索引版本',
              children: base.currentIndexReleaseId ?? '未发布',
            },
          ]}
        />
      </section>
      <section className={styles.section} aria-labelledby="base-documents">
        <div className={styles.sectionHeading}>
          <Typography.Title level={3} id="base-documents">
            目录与文档
          </Typography.Title>
          <span>共 {total} 份文档</span>
        </div>
        <div className={styles.split}>
          <aside className={styles.directory} aria-label="文档目录">
            <div className={styles.directoryHeading}>
              <strong>目录</strong>
              <Button size="small" onClick={addDirectory}>
                新建目录
              </Button>
            </div>
            <Tree
              defaultExpandAll
              selectedKeys={directoryId ? [directoryId] : ['']}
              onSelect={(keys) => {
                setDirectoryId(keys[0]?.toString() || undefined);
                setPage(1);
              }}
              treeData={[
                {
                  key: '',
                  title: '全部文档',
                  children: directories.map((item) => ({ key: item.id, title: item.name })),
                },
              ]}
            />
          </aside>
          <div className={styles.tableRegion}>
            <Table<KnowledgeDocument>
              rowKey="id"
              dataSource={documents}
              scroll={{ x: 650 }}
              pagination={{
                current: page,
                pageSize: 10,
                total,
                showSizeChanger: false,
                onChange: setPage,
              }}
              locale={{ emptyText: <Empty description="当前目录暂无文档" /> }}
              columns={[
                { title: '名称', dataIndex: 'title', width: 220, ellipsis: true },
                { title: '编码', dataIndex: 'documentCode', width: 160, ellipsis: true },
                { title: '状态', dataIndex: 'status', width: 100, render: knowledgeStatusLabel },
                {
                  title: '操作',
                  width: 80,
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
          </div>
        </div>
      </section>
      <section className={styles.section} aria-labelledby="base-releases">
        <div className={styles.sectionHeading}>
          <div>
            <Typography.Title level={3} id="base-releases">
              索引版本
            </Typography.Title>
            <Typography.Text type="secondary">
              查看发布历史与各版本的文档、分块和模型信息。
            </Typography.Text>
          </div>
        </div>
        <Table<IndexRelease>
          rowKey="id"
          dataSource={releases}
          scroll={{ x: 750 }}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          columns={[
            {
              title: '版本',
              dataIndex: 'releaseNo',
              width: 80,
              render: (value: number) => `R${value}`,
            },
            { title: '状态', dataIndex: 'status', width: 100, render: knowledgeStatusLabel },
            {
              title: '文档 / 分块',
              width: 120,
              render: (_, item) => `${item.documentCount} / ${item.chunkCount}`,
            },
            { title: '模型', dataIndex: 'embeddingModel', ellipsis: true },
            {
              title: '发布时间',
              dataIndex: 'publishedAt',
              width: 180,
              render: (value: string | null) => value?.replace('T', ' ').slice(0, 16) ?? '未发布',
            },
            {
              title: '操作',
              width: 150,
              render: (_, item) =>
                item.id !== base.currentIndexReleaseId ? (
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
      </section>
      <KnowledgeUploadDrawer
        knowledgeType={base.knowledgeType}
        open={uploadOpen}
        baseId={baseId}
        directories={directories}
        onClose={() => setUploadOpen(false)}
        onSubmitted={(id) => {
          setBatchId(id);
          setBatchOpen(true);
        }}
      />
      {batchOpen && (
        <KnowledgeBatchImportModal
          open
          baseId={baseId}
          directories={directories}
          initialBatchId={batchId}
          onClose={() => {
            setBatchOpen(false);
            setBatchId(undefined);
          }}
          onChanged={load}
        />
      )}
    </section>
  );
}
