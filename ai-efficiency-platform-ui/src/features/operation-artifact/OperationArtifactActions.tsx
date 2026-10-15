import { CopyOutlined, DownloadOutlined, EyeOutlined } from '@ant-design/icons';
import { Button, Space, message } from 'antd';

import { artifactUrl } from '../operation-chat/api';
import type { OperationArtifactSummary } from '../operation-chat/types';

interface OperationArtifactActionsProps {
  artifact: OperationArtifactSummary;
  baseUrl: string;
}

export function OperationArtifactActions({ artifact, baseUrl }: OperationArtifactActionsProps) {
  const [messageApi, contextHolder] = message.useMessage();
  const copy = async () => {
    try {
      const response = await fetch(artifactUrl(baseUrl, artifact.artifactId, 'copy'));
      if (!response.ok) throw new Error(`copy failed: ${response.status}`);
      const content = await response.text();
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
      await navigator.clipboard.writeText(content);
      void messageApi.success('已复制成稿');
    } catch {
      void messageApi.error('复制失败，请使用下载功能');
    }
  };

  const isWechat = artifact.platform === 'wechat_official_account';
  return (
    <Space wrap aria-label={`${isWechat ? '公众号' : '平台'}文章操作`}>
      {contextHolder}
      <Button icon={<CopyOutlined />} onClick={() => void copy()}>
        复制成稿
      </Button>
      {isWechat && (
        <Button
          icon={<EyeOutlined />}
          onClick={() =>
            window.open(
              artifactUrl(baseUrl, artifact.artifactId, 'wechat-html'),
              '_blank',
              'noopener,noreferrer',
            )
          }
        >
          微信预览
        </Button>
      )}
      <Button
        download
        href={artifactUrl(baseUrl, artifact.artifactId, 'download')}
        icon={<DownloadOutlined />}
      >
        下载 Markdown
      </Button>
    </Space>
  );
}
