import { Alert, Button, Empty, Typography } from 'antd';
import { useNavigate, useParams } from 'react-router';

import styles from './KnowledgeCenter.module.css';

export function KnowledgeImportPage() {
  const { baseId } = useParams();
  const navigate = useNavigate();
  if (!baseId) return <Empty description="缺少知识库标识" />;
  return (
    <section className={styles.page}>
      <Typography.Title level={2}>批量导入</Typography.Title>
      <Alert
        type="info"
        showIcon
        message="批量导入已整合到知识库详情页"
        description="在同一页面选择目录、上传多个文件、查看实时进度，并对失败条目单独重试。"
      />
      <Button
        type="primary"
        onClick={() => navigate(`/knowledge-center/knowledge-bases/${baseId}`)}
      >
        进入知识库并导入
      </Button>
    </section>
  );
}
