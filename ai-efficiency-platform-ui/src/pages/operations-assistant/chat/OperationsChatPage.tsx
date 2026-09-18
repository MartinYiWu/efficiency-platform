import { ArrowLeftOutlined, RobotOutlined, SendOutlined, StopOutlined } from '@ant-design/icons';
import { Avatar, Button, Card, Input, Typography } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';

import {
  OperationProgress,
  StreamingAssistantContent,
  useOperationChat,
} from '../../../features/operation-chat';
import { OperationDelivery } from '../../../widgets/operation-delivery';
import styles from './OperationsChatPage.module.css';

export function OperationsChatPage() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState('');
  const messageViewportRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLElement>(null);
  const followUpFocusRef = useRef<'awaiting-control' | 'stop-focused' | null>(null);
  const { state, sendMessage, cancel, isBusy } = useOperationChat();
  const currentAssistantMessage =
    state.messages.at(-1)?.role === 'assistant' ? state.messages.at(-1) : null;
  const isActivelyStreaming = state.status === 'submitting' || state.status === 'streaming';
  const showThinking =
    isActivelyStreaming && !(currentAssistantMessage?.content.trim().length ?? false);
  const assistantDisplayMode = (messageId: string): 'typing' | 'complete' | 'frozen' => {
    const message = state.messages.find((item) => item.id === messageId);
    if (message?.frozen) return 'frozen';
    if (currentAssistantMessage?.id !== messageId) return 'complete';
    if (isActivelyStreaming) return 'typing';
    return state.status === 'succeeded' || state.status === 'degraded_succeeded'
      ? 'complete'
      : 'frozen';
  };
  const submit = () => {
    const message = draft.trim();
    if (!message || isBusy) return;
    setDraft('');
    void sendMessage(message);
  };
  useEffect(() => {
    if (!followUpFocusRef.current) return;
    const animationFrame = requestAnimationFrame(() => {
      const focusState = followUpFocusRef.current;
      if (!focusState) return;

      if (isBusy) {
        if (focusState === 'stop-focused') return;
        const stopButton = composerRef.current?.querySelector<HTMLButtonElement>(
          'button[aria-label="停止生成"]',
        );
        if (stopButton) {
          stopButton.focus();
          followUpFocusRef.current = 'stop-focused';
        }
        return;
      }

      if (focusState === 'stop-focused' && document.activeElement !== document.body) {
        followUpFocusRef.current = null;
        return;
      }

      const deliveries = messageViewportRef.current?.querySelectorAll<HTMLElement>(
        'section[aria-label="运营交付"]',
      );
      const latestDelivery = deliveries?.item((deliveries?.length ?? 0) - 1);
      const target =
        latestDelivery?.querySelector<HTMLElement>('button:not(:disabled)') ??
        composerRef.current?.querySelector<HTMLTextAreaElement>('textarea[aria-label="输入消息"]');
      if (target) {
        target.focus();
        followUpFocusRef.current = null;
      }
    });
    return () => cancelAnimationFrame(animationFrame);
  }, [isBusy, state.deliverableSets.length, state.error, state.status]);
  return (
    <section className={styles.page} aria-labelledby="operations-chat-title">
      <header className={styles.header}>
        <Button
          className={styles.backButton}
          type="text"
          icon={<ArrowLeftOutlined />}
          aria-label="返回上一页"
          onClick={() => navigate(-1)}
        />
        <Avatar className={styles.assistantAvatar} icon={<RobotOutlined />} size={48} />
        <div>
          <Typography.Title id="operations-chat-title" level={1} className={styles.title}>
            AI 内容运营助手
          </Typography.Title>
          <Typography.Text className={styles.subtitle}>
            协助处理选题、内容创作、活动策划和复盘
          </Typography.Text>
        </div>
      </header>
      <div
        ref={messageViewportRef}
        className={styles.messageViewport}
        role="log"
        aria-label="运营助手对话消息"
        aria-live="polite"
      >
        <div className={styles.messageList}>
          <div className={styles.messageGroup}>
            <time>现在</time>
            <div className={styles.assistantMessageRow}>
              <Avatar className={styles.messageAvatar} icon={<RobotOutlined />} size={34} />
              <div className={styles.assistantBubble}>
                你好，我是 AI
                内容运营助手。请告诉我目标、渠道和受众，我会协助梳理可直接使用的运营内容。
              </div>
            </div>
          </div>
          {state.messages.map((message) => (
            <div className={styles.messageGroup} key={message.id}>
              <time>
                {new Intl.DateTimeFormat('zh-CN', {
                  hour: '2-digit',
                  minute: '2-digit',
                  hour12: false,
                }).format(message.createdAt)}
              </time>
              <div
                className={
                  message.role === 'user' ? styles.userMessageRow : styles.assistantMessageRow
                }
              >
                {message.role === 'assistant' && (
                  <Avatar className={styles.messageAvatar} icon={<RobotOutlined />} size={34} />
                )}
                <div
                  className={message.role === 'user' ? styles.userBubble : styles.assistantBubble}
                >
                  {message.role === 'assistant' ? (
                    <StreamingAssistantContent
                      key={message.id}
                      content={message.content}
                      mode={assistantDisplayMode(message.id)}
                    />
                  ) : (
                    message.content
                  )}
                </div>
                {message.role === 'user' && (
                  <Avatar className={styles.userAvatar} size={34}>
                    沐
                  </Avatar>
                )}
              </div>
            </div>
          ))}
          {showThinking && (
            <div className={styles.messageGroup} aria-label="助手正在思考">
              <div className={styles.assistantMessageRow}>
                <Avatar className={styles.messageAvatar} icon={<RobotOutlined />} size={34} />
                <div className={`${styles.assistantBubble} ${styles.thinkingIndicator}`}>
                  <span className={styles.thinkingDot} />
                  <span className={styles.thinkingDot} />
                  <span className={styles.thinkingDot} />
                </div>
              </div>
            </div>
          )}
          {state.clarification && (
            <Card size="small" title="需要补充信息" aria-label="澄清问题">
              <Typography.Paragraph>{state.clarification.question}</Typography.Paragraph>
              {state.clarification.fields.length > 0 && (
                <Typography.Text type="secondary">
                  请补充：{state.clarification.fields.join('、')}
                </Typography.Text>
              )}
            </Card>
          )}
          {state.visiblePhase && isBusy && (
            <div className={styles.deliveryProgress}>
              <OperationProgress value={state.visiblePhase} />
            </div>
          )}
          {state.deliverableSets.map((set, setIndex) => (
            <OperationDelivery
              key={`${set.contract_version}-${setIndex}`}
              onSubmitNextAction={(message) => {
                followUpFocusRef.current = 'awaiting-control';
                void sendMessage(message);
              }}
              value={set}
            />
          ))}
          {state.error && (
            <Typography.Text type="danger" role="alert">
              {state.error}
            </Typography.Text>
          )}
          {state.status === 'cancelling' && (
            <Typography.Text type="secondary">正在停止当前任务…</Typography.Text>
          )}
        </div>
      </div>
      <footer ref={composerRef} className={styles.composer} aria-label="消息输入">
        <Input.TextArea
          aria-label="输入消息"
          autoSize={{ minRows: 1, maxRows: 4 }}
          value={draft}
          placeholder="输入你想咨询的内容运营问题…"
          onChange={(event) => setDraft(event.target.value)}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        {isBusy ? (
          <Button
            danger
            icon={<StopOutlined />}
            aria-label="停止生成"
            onClick={() => void cancel()}
          >
            停止
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            disabled={!draft.trim()}
            aria-label="发送消息"
            onClick={submit}
          >
            发送
          </Button>
        )}
      </footer>
    </section>
  );
}
