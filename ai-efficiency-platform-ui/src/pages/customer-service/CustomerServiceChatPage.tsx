import {
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Divider, Empty, Input, Space, Typography } from 'antd';
import { useEffect, useRef, useState } from 'react';

import type { Citation } from '../../entities/customer-service/model';
import { CitationDrawer } from '../../features/customer-service-chat/CitationDrawer';
import { CustomerServiceAnswer } from '../../features/customer-service-chat/CustomerServiceAnswer';
import { CustomerServiceProgress } from '../../features/customer-service-chat/CustomerServiceProgress';
import { FeedbackControl } from '../../features/customer-service-chat/FeedbackControl';
import { useCustomerServiceChat } from '../../features/customer-service-chat/useCustomerServiceChat';
import styles from './CustomerServiceChatPage.module.css';

export function CustomerServiceChatPage() {
  const { state, busy, send, cancel, selectConversation, newConversation } =
    useCustomerServiceChat();
  const [draft, setDraft] = useState('');
  const [citation, setCitation] = useState<Citation>();
  const viewport = useRef<HTMLDivElement>(null);
  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: 'smooth' });
  }, [state.messages, state.progressByRun]);
  const submit = () => {
    const value = draft.trim();
    if (!value || busy) return;
    setDraft('');
    void send(value);
  };
  return (
    <section className={styles.page}>
      <aside className={styles.sidebar}>
        <Button
          block
          type="primary"
          icon={<PlusOutlined />}
          disabled={busy}
          onClick={() => void newConversation()}
        >
          新建对话
        </Button>
        <Divider />
        <Typography.Text type="secondary">历史会话</Typography.Text>
        <div>
          {state.conversations.map((item) => (
            <Button
              key={item.id}
              type={item.id === state.conversationId ? 'primary' : 'text'}
              className={styles.conversation}
              disabled={busy}
              onClick={() => void selectConversation(item.id)}
            >
              {item.title || '新对话'}
            </Button>
          ))}
        </div>
      </aside>
      <main className={styles.chat}>
        <header className={styles.chatHeader}>
          <Typography.Title level={3}>AI 智能客服</Typography.Title>
          <Typography.Text type="secondary">查询公司制度、业务流程、产品与技术资料</Typography.Text>
        </header>
        <div className={styles.messages} ref={viewport} role="log">
          {state.messages.length === 0 && <Empty description="可以直接输入你的问题" />}
          {state.messages.map((item) => (
            <article
              key={item.message.id}
              className={`${styles.row} ${item.message.role === 'USER' ? styles.userRow : ''}`}
            >
              <Avatar icon={item.message.role === 'USER' ? <UserOutlined /> : <RobotOutlined />} />
              <div>
                <div
                  className={`${styles.bubble} ${item.message.role === 'USER' ? styles.userBubble : ''}`}
                >
                  {item.message.role === 'USER' ? (
                    item.message.content
                  ) : (
                    <>
                      <CustomerServiceProgress
                        steps={item.message.runId ? state.progressByRun[item.message.runId] ?? [] : []}
                        status={item.message.status === 'COMPLETED' ? 'SUCCEEDED' : item.message.status}
                        pending={state.status === 'SUBMITTING' && item.message.id.startsWith('local-assistant-')}
                      />
                      <CustomerServiceAnswer
                        content={item.message.content}
                        mode={item.message.answerMode}
                        citations={item.citations}
                        streaming={item.message.status === 'STREAMING' && Boolean(item.message.runId && state.progressByRun[item.message.runId]?.some((step) => step.stage === 'answer'))}
                        onCitation={setCitation}
                      />
                    </>
                  )}
                </div>
                {item.message.role === 'ASSISTANT' &&
                  item.message.status === 'COMPLETED' &&
                  !item.message.id.startsWith('local-') && (
                    <FeedbackControl messageId={item.message.id} />
                  )}
              </div>
            </article>
          ))}
        </div>
        {state.error && (
          <div className={styles.error} role="alert">
            {state.error}
            {state.traceId ? ` · Trace ID: ${state.traceId}` : ''}
          </div>
        )}
        <footer className={styles.composer}>
          <Input.TextArea
            aria-label="输入问题"
            autoSize={{ minRows: 1, maxRows: 5 }}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="请输入你想了解的公司制度、流程、产品或技术问题"
            onPressEnter={(event) => {
              if (!event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
          />
          {busy ? (
            <Button danger icon={<StopOutlined />} onClick={() => void cancel()}>
              停止
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<SendOutlined />}
              disabled={!draft.trim()}
              onClick={submit}
            >
              发送
            </Button>
          )}
        </footer>
      </main>
      <aside className={styles.context}>
        <Typography.Title level={5}>使用说明</Typography.Title>
        <Typography.Paragraph>
          回答会明确区分公司知识与通用建议。公司知识回答提供可追溯引用。
        </Typography.Paragraph>
        <Typography.Title level={5}>当前状态</Typography.Title>
        <Space direction="vertical">
          <span>{state.status}</span>
          {state.runId && (
            <Typography.Text copyable={{ text: state.runId }}>Run ID</Typography.Text>
          )}
        </Space>
      </aside>
      <CitationDrawer citation={citation} onClose={() => setCitation(undefined)} />
    </section>
  );
}
