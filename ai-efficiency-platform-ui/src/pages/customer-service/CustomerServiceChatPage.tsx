import {
  DeleteOutlined,
  HistoryOutlined,
  PlusOutlined,
  ReadOutlined,
  SendOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { Button, Drawer, Input, Popconfirm, Typography } from 'antd';
import { useEffect, useRef, useState } from 'react';

import type { Citation } from '../../entities/customer-service/model';
import { CitationDrawer } from '../../features/customer-service-chat/CitationDrawer';
import { CustomerServiceAnswer } from '../../features/customer-service-chat/CustomerServiceAnswer';
import { CustomerServiceProgress } from '../../features/customer-service-chat/CustomerServiceProgress';
import { FeedbackControl } from '../../features/customer-service-chat/FeedbackControl';
import { useCustomerServiceChat } from '../../features/customer-service-chat/useCustomerServiceChat';
import styles from './CustomerServiceChatPage.module.css';

export function CustomerServiceChatPage() {
  const { state, busy, send, cancel, selectConversation, newConversation, removeConversation } =
    useCustomerServiceChat();
  const [draft, setDraft] = useState('');
  const [citation, setCitation] = useState<Citation>();
  const [historyOpen, setHistoryOpen] = useState(false);
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
  const historyItems = state.conversations.map((item) => (
    <div key={item.id} className={`${styles.conversationRow} ${item.id === state.conversationId ? styles.conversationActive : ''}`}>
      <button type="button" className={styles.conversation} disabled={busy}
        onClick={() => { void selectConversation(item.id); setHistoryOpen(false); }} title={item.title || '新对话'}>
        {item.title || '新对话'}
      </button>
      <Popconfirm title="删除这条会话？" description="删除后将从历史列表移除。"
        okText="删除" cancelText="取消" okButtonProps={{ danger: true }}
        onConfirm={() => void removeConversation(item.id)}>
        <Button type="text" size="small" disabled={busy} icon={<DeleteOutlined />}
          aria-label={`删除会话：${item.title || '新对话'}`} />
      </Popconfirm>
    </div>
  ));
  return (
    <section className={styles.page}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarTitle}>智能客服</div>
        <Button
          block
          type="primary"
          icon={<PlusOutlined />}
          disabled={busy}
          onClick={() => void newConversation()}
        >
          新建对话
        </Button>
        <Button className={styles.mobileHistoryButton} icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>历史会话</Button>
        <div className={styles.historyTitle}>历史会话 <span>{state.conversations.length}</span></div>
        <nav className={styles.historyList} aria-label="历史会话">
          {historyItems}
        </nav>
      </aside>
      <main className={styles.chat}>
        <header className={styles.chatHeader}>
          <span className={styles.headerAvatar} aria-hidden="true"><ReadOutlined /></span>
          <div>
            <Typography.Title level={4}>AI 智能客服</Typography.Title>
            <Typography.Text type="secondary">公司知识与工作问题，随时提问</Typography.Text>
          </div>
        </header>
        <div className={styles.messages} ref={viewport} role="log">
          {state.messages.length === 0 && <div className={styles.empty}><span className={styles.emptyIcon}><ReadOutlined /></span><h2>从一个问题开始</h2><p>查询公司制度、业务流程、产品和技术资料。</p></div>}
          {state.messages.map((item) => (
            <article
              key={item.message.id}
              className={`${styles.row} ${item.message.role === 'USER' ? styles.userRow : ''}`}
            >
              {item.message.role === 'ASSISTANT' && <span className={styles.assistantAvatar} aria-hidden="true"><ReadOutlined /></span>}
              <div className={styles.messageContent}>
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
        <div className={styles.composer} role="form" aria-label="发送消息">
          <div className={styles.composerBox}>
            <Input.TextArea
              aria-label="输入问题"
              autoSize={{ minRows: 1, maxRows: 5 }}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="输入你的问题…"
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
            />
            <div className={styles.composerActions}>
              <span>Enter 发送 · Shift + Enter 换行</span>
              {busy ? (
                <Button danger icon={<StopOutlined />} onClick={() => void cancel()}>停止</Button>
              ) : (
                <Button type="primary" icon={<SendOutlined />} disabled={!draft.trim()}
                  onClick={submit}>发送</Button>
              )}
            </div>
          </div>
        </div>
      </main>
      <Drawer title="历史会话" placement="left" width={300} open={historyOpen} onClose={() => setHistoryOpen(false)}><nav className={styles.mobileHistoryList} aria-label="移动端历史会话">{historyItems}</nav></Drawer>
      <CitationDrawer citation={citation} onClose={() => setCitation(undefined)} />
    </section>
  );
}
