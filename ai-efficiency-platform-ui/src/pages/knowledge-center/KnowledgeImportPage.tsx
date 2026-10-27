import { Button, Empty, Result } from 'antd';
import { useNavigate, useParams } from 'react-router';

import styles from './KnowledgeCenter.module.css';

export function KnowledgeImportPage() {
  const { baseId } = useParams();
  const navigate = useNavigate();
  if (!baseId) return <Empty description="缺少知识库标识" />;
  return (
    <section className={`${styles.page} ${styles.importEntry}`}>
      <Result
        status="info"
        title="批量导入"
        subTitle="请进入知识库，在文档列表中选择目录并上传文件，随后查看处理进度。"
        extra={<Button type="primary" onClick={() => navigate(`/knowledge-center/knowledge-bases/${baseId}`)}>进入知识库并导入</Button>}
      />
    </section>
  );
}
