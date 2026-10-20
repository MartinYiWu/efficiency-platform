import { Button, Descriptions, Drawer, Progress, Space, Tag, message } from 'antd';
import { useEffect, useState } from 'react';

import type { ProcessingTask } from '../../entities/knowledge/model';
import { getProcessingTask, retryProcessingTask } from './api';

const terminal = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED']);
interface Props {
  taskId?: string;
  open: boolean;
  onClose(): void;
}

export function ProcessingTaskDrawer({ taskId, open, onClose }: Props) {
  const [task, setTask] = useState<ProcessingTask>();
  useEffect(() => {
    if (!open || !taskId) return;
    let active = true;
    const refresh = () =>
      void getProcessingTask(taskId)
        .then((value) => {
          if (active) setTask(value);
        })
        .catch((error: Error) => message.error(error.message));
    refresh();
    const timer = window.setInterval(() => {
      if (!task || !terminal.has(task.status)) refresh();
    }, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [open, task?.status, taskId]);
  return (
    <Drawer title="处理任务" open={open} onClose={onClose} width={520}>
      {task && (
        <Space direction="vertical" size={20} style={{ width: '100%' }}>
          <Progress
            percent={task.progressPercent}
            status={task.status === 'FAILED' ? 'exception' : undefined}
          />
          <Descriptions
            column={1}
            bordered
            items={[
              { key: 'status', label: '状态', children: <Tag>{task.status}</Tag> },
              { key: 'stage', label: '阶段', children: task.stage },
              { key: 'attempt', label: '执行次数', children: task.attemptNo },
              { key: 'error', label: '错误信息', children: task.errorMessage ?? '-' },
            ]}
          />
          {task.status === 'FAILED' && (
            <Button
              type="primary"
              onClick={() =>
                void retryProcessingTask(task.id)
                  .then(setTask)
                  .catch((error: Error) => message.error(error.message))
              }
            >
              重试任务
            </Button>
          )}
        </Space>
      )}
    </Drawer>
  );
}
