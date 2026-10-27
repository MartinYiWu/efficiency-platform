import { Result } from 'antd';

import { PlatformShell } from '../../widgets/platform-shell/PlatformShell';

export function NotFoundPage() {
  return <PlatformShell><Result status="404" title={<h1>页面不存在</h1>} subTitle="请检查访问地址后重试。" /></PlatformShell>;
}
