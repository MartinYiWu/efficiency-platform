import { DislikeOutlined, LikeOutlined } from '@ant-design/icons';
import { Button, Input, Modal, Select, Space, message } from 'antd';
import { useState } from 'react';
import { submitFeedback } from './api';

export function FeedbackControl({ messageId }: { messageId: string }) {
  const [open, setOpen] = useState(false);
  const [reasonCode, setReasonCode] = useState<string>();
  const [comment, setComment] = useState('');
  const up = () =>
    void submitFeedback(messageId, { rating: 'UP', reasonCode: null, comment: null })
      .then(() => message.success('感谢反馈'))
      .catch((error: Error) => message.error(error.message));
  const down = async () => {
    if (!reasonCode || (reasonCode === 'OTHER' && !comment.trim())) {
      message.warning(reasonCode === 'OTHER' ? '请填写具体问题' : '请选择原因');
      return;
    }
    try {
      await submitFeedback(messageId, {
        rating: 'DOWN',
        reasonCode,
        comment: comment.trim() || null,
      });
      message.success('反馈已提交');
      setOpen(false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '提交失败');
    }
  };
  return (
    <>
      <Space>
        <Button type="text" aria-label="回答有帮助" icon={<LikeOutlined />} onClick={up} />
        <Button
          type="text"
          aria-label="回答无帮助"
          icon={<DislikeOutlined />}
          onClick={() => setOpen(true)}
        />
      </Space>
      <Modal
        title="这个回答有什么问题？"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void down()}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Select
            placeholder="选择原因"
            value={reasonCode}
            onChange={setReasonCode}
            options={[
              { value: 'INCORRECT', label: '内容错误' },
              { value: 'OUTDATED', label: '内容过期' },
              { value: 'MISSING_CITATION', label: '缺少依据' },
              { value: 'IRRELEVANT', label: '答非所问' },
              { value: 'UNCLEAR', label: '表达不清楚' },
              { value: 'OTHER', label: '其他' },
            ]}
          />
          {reasonCode === 'OTHER' && (
            <Input.TextArea
              rows={4}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="请说明具体问题"
            />
          )}
        </Space>
      </Modal>
    </>
  );
}
