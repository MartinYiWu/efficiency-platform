import { Result } from 'antd';

export function NotFoundPage() {
  return <Result status="404" title={<h1>页面不存在</h1>} subTitle="请检查访问地址后重试。" />;
}
