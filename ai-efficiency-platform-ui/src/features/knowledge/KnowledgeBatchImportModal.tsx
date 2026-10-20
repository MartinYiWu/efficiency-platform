import { Button, Modal, Progress, Select, Space, Table, Upload, message } from 'antd';
import type { UploadFile } from 'antd';
import { useEffect, useState } from 'react';

import type { IngestBatch, KnowledgeDirectory } from '../../entities/knowledge/model';
import { getImportBatch, retryImportItem, uploadDocuments } from './api';

const terminal = new Set(['SUCCEEDED', 'PARTIAL_FAILED', 'FAILED']);
interface Props {
  open: boolean;
  baseId: string;
  directories: KnowledgeDirectory[];
  initialBatchId?: string;
  onClose(): void;
  onChanged(): void;
}

export function KnowledgeBatchImportModal({
  open,
  baseId,
  directories,
  initialBatchId,
  onClose,
  onChanged,
}: Props) {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [directoryId, setDirectoryId] = useState<string>();
  const [batch, setBatch] = useState<IngestBatch>();
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!open || !initialBatchId) return;
    void getImportBatch(initialBatchId)
      .then(setBatch)
      .catch((error: Error) => message.error(error.message));
  }, [initialBatchId, open]);
  useEffect(() => {
    if (!open || !batch || terminal.has(batch.status)) return;
    const timer = window.setInterval(
      () =>
        void getImportBatch(batch.id)
          .then((next) => {
            setBatch(next);
            if (terminal.has(next.status)) onChanged();
          })
          .catch((error: Error) => message.error(error.message)),
      3000,
    );
    return () => window.clearInterval(timer);
  }, [batch, onChanged, open]);
  const submit = async () => {
    const selected = files
      .map((item) => item.originFileObj)
      .filter((file): file is NonNullable<typeof file> => Boolean(file));
    if (selected.length < 2) {
      message.warning('批量导入至少选择 2 个文件');
      return;
    }
    setLoading(true);
    try {
      setBatch(await uploadDocuments(baseId, selected, directoryId));
      onChanged();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导入失败');
    } finally {
      setLoading(false);
    }
  };
  const percent = batch
    ? Math.round(((batch.succeededCount + batch.failedCount) / Math.max(batch.totalCount, 1)) * 100)
    : 0;
  return (
    <Modal
      title="批量导入"
      open={open}
      onCancel={onClose}
      width={760}
      footer={
        batch ? (
          <Button onClick={onClose}>关闭</Button>
        ) : (
          <Button type="primary" loading={loading} onClick={submit}>
            开始导入
          </Button>
        )
      }
    >
      {!batch ? (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Select
            allowClear
            placeholder="选择目录（可选）"
            value={directoryId}
            onChange={setDirectoryId}
            options={directories.map((item) => ({ label: item.path, value: item.id }))}
          />
          <Upload.Dragger
            multiple
            beforeUpload={() => false}
            fileList={files}
            onChange={({ fileList }) => setFiles(fileList)}
            accept=".pdf,.doc,.docx,.txt,.md"
          >
            <p>选择多个文件批量导入</p>
          </Upload.Dragger>
        </Space>
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Progress
            percent={percent}
            status={batch.status === 'FAILED' ? 'exception' : undefined}
          />
          <div>
            成功 {batch.succeededCount}，失败 {batch.failedCount}，共 {batch.totalCount}
          </div>
          <Table
            rowKey="id"
            pagination={false}
            dataSource={batch.items}
            columns={[
              {
                title: '文件',
                dataIndex: 'fileId',
                render: (value: string | null) => value ?? '-',
              },
              { title: '状态', dataIndex: 'status' },
              {
                title: '错误',
                dataIndex: 'errorMessage',
                render: (value: string | null) => value ?? '-',
              },
              {
                title: '操作',
                render: (_, item) =>
                  item.status === 'FAILED' ? (
                    <Button
                      size="small"
                      onClick={() =>
                        void retryImportItem(item.id)
                          .then(() => getImportBatch(batch.id))
                          .then(setBatch)
                          .catch((error: Error) => message.error(error.message))
                      }
                    >
                      重试
                    </Button>
                  ) : null,
              },
            ]}
          />
        </Space>
      )}
    </Modal>
  );
}
