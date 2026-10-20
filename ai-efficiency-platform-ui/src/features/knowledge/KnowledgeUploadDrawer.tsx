import { Button, Drawer, Select, Space, Upload, message } from 'antd';
import type { UploadFile } from 'antd';
import { useState } from 'react';

import type { KnowledgeDirectory } from '../../entities/knowledge/model';
import { uploadDocuments } from './api';

interface Props {
  open: boolean;
  baseId: string;
  directories: KnowledgeDirectory[];
  onClose(): void;
  onSubmitted(batchId: string): void;
}

export function KnowledgeUploadDrawer({ open, baseId, directories, onClose, onSubmitted }: Props) {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [directoryId, setDirectoryId] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    const selected = files
      .map((item) => item.originFileObj)
      .filter((file): file is NonNullable<typeof file> => Boolean(file));
    if (selected.length !== 1) {
      message.warning('请选择 1 个文件');
      return;
    }
    setSubmitting(true);
    try {
      const batch = await uploadDocuments(baseId, selected, directoryId);
      message.success('文件已提交处理');
      onSubmitted(batch.id);
      setFiles([]);
      onClose();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '上传失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      title="上传文档"
      open={open}
      onClose={onClose}
      width={480}
      extra={
        <Button type="primary" loading={submitting} onClick={submit}>
          开始处理
        </Button>
      }
    >
      <Space direction="vertical" size={20} style={{ width: '100%' }}>
        <Select
          allowClear
          placeholder="选择目录（可选）"
          value={directoryId}
          onChange={setDirectoryId}
          options={directories.map((item) => ({ label: item.path, value: item.id }))}
        />
        <Upload.Dragger
          beforeUpload={() => false}
          maxCount={1}
          fileList={files}
          onChange={({ fileList }) => setFiles(fileList)}
          accept=".pdf,.doc,.docx,.txt,.md"
        >
          <p>拖拽文件到这里，或点击选择</p>
          <p>支持 PDF、Word、TXT、Markdown</p>
        </Upload.Dragger>
      </Space>
    </Drawer>
  );
}
