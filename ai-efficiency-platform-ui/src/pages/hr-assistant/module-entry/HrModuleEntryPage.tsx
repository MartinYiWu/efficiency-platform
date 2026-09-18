import { AppstoreOutlined } from '@ant-design/icons';
import { Card, Typography } from 'antd';

import styles from './HrModuleEntryPage.module.css';

export function HrModuleEntryPage({
  title,
  description,
  nextPage,
}: {
  title: string;
  description: string;
  nextPage: string;
}) {
  return (
    <div className={styles.page}>
      <Typography.Title level={1}>{title}</Typography.Title>
      <Typography.Text type="secondary">{description}</Typography.Text>
      <Card className={styles.card}>
        <AppstoreOutlined />
        <Typography.Title level={2}>{title}页面准备中</Typography.Title>
        <Typography.Paragraph>
          该模块将严格按照 UI 设计稿逐页接入。下一张计划开发页面：{nextPage}。
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
