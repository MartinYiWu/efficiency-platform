import { Alert, Button, Empty, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import type { KnowledgeBase, KnowledgeDirectory } from '../../entities/knowledge/model';
import { getKnowledgeBase, listDirectories } from '../../features/knowledge/api';
import { KnowledgeBatchImportModal } from '../../features/knowledge/KnowledgeBatchImportModal';
import styles from './KnowledgeCenter.module.css';

export function KnowledgeImportPage() {
  const { baseId = '' } = useParams();
  const navigate = useNavigate();
  const [base, setBase] = useState<KnowledgeBase>();
  const [directories, setDirectories] = useState<KnowledgeDirectory[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!baseId) return;
    let active = true;
    void Promise.all([getKnowledgeBase(baseId), listDirectories(baseId)])
      .then(([nextBase, nextDirectories]) => {
        if (active) {
          setBase(nextBase);
          setDirectories(nextDirectories);
        }
      })
      .catch((error: Error) => message.error(error.message));
    return () => {
      active = false;
    };
  }, [baseId]);
  if (!baseId) return <Empty description="缺少知识库标识" />;
  if (!base) return <Empty description="正在加载知识库" />;
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <Button
            type="link"
            className={styles.link}
            onClick={() => navigate(`/knowledge-center/knowledge-bases/${baseId}`)}
          >
            返回知识库
          </Button>
          <Typography.Title level={2}>批量导入</Typography.Title>
          <Typography.Text type="secondary">{base.name}</Typography.Text>
        </div>
        <Button type="primary" disabled={base.status !== 'ACTIVE'} onClick={() => setOpen(true)}>
          选择文件并导入
        </Button>
      </header>
      {base.status !== 'ACTIVE' && (
        <Alert
          type="warning"
          showIcon
          title="知识库未启用，请返回知识库启用后再批量导入。"
          action={
            <Button onClick={() => navigate(`/knowledge-center/knowledge-bases/${baseId}`)}>
              返回知识库启用
            </Button>
          }
        />
      )}
      <section className={styles.section} aria-labelledby="import-files">
        <div className={styles.sectionHeading}>
          <Typography.Title level={3} id="import-files">
            目录与文件
          </Typography.Title>
        </div>
        <Typography.Paragraph>
          选择目标目录并上传至少 2 个文件，支持 PDF、Word、TXT 和
          Markdown。单个文档请在知识库中使用“上传文档”。
        </Typography.Paragraph>
      </section>
      <section className={styles.section} aria-labelledby="import-tasks">
        <div className={styles.sectionHeading}>
          <Typography.Title level={3} id="import-tasks">
            处理任务
          </Typography.Title>
        </div>
        <Typography.Paragraph type="secondary">
          提交后在导入窗口查看本批文件的进度、结果与失败原因，并可重试失败项。
        </Typography.Paragraph>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="选择文件并提交后显示本次导入进度"
        />
      </section>
      {open && (
        <KnowledgeBatchImportModal
          open
          baseId={baseId}
          directories={directories}
          onClose={() => setOpen(false)}
          onChanged={() => {}}
        />
      )}
    </section>
  );
}
