import { ArrowLeftOutlined, RobotOutlined, SendOutlined } from '@ant-design/icons';
import { Avatar, Button, Input, Typography } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { hrChatConfig } from './HrChatConfig';
import styles from './HrChatPage.module.css';

export interface AssistantChatMessage {
  id: string;
  role: 'assistant' | 'user';
  content: string;
  time: string;
}

export interface AssistantChatConfig {
  title: string;
  subtitle: string;
  placeholder: string;
  initialMessages: AssistantChatMessage[];
}

export function AssistantChatPage({ config }: { config: AssistantChatConfig }) {
  const navigate = useNavigate();
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState(config.initialMessages);

  const sendMessage = () => {
    const content = draft.trim();
    if (!content) return;

    setMessages((current) => [
      ...current,
      {
        id: `user-${Date.now()}`,
        role: 'user',
        content,
        time: new Intl.DateTimeFormat('zh-CN', {
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        }).format(new Date()),
      },
    ]);
    setDraft('');
  };

  return (
    <section className={styles.page} aria-labelledby="assistant-chat-title">
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
          <Typography.Title id="assistant-chat-title" level={1} className={styles.title}>
            {config.title}
          </Typography.Title>
          <Typography.Text className={styles.subtitle}>{config.subtitle}</Typography.Text>
        </div>
      </header>

      <div className={styles.messageViewport} role="log" aria-label="对话消息" aria-live="polite">
        <div className={styles.messageList}>
          {messages.map((message) => (
            <div className={styles.messageGroup} key={message.id}>
              <time>{message.time}</time>
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
                  {message.content}
                </div>
                {message.role === 'user' && (
                  <Avatar className={styles.userAvatar} size={34}>
                    沐
                  </Avatar>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <footer className={styles.composer} aria-label="消息输入">
        <Input.TextArea
          aria-label="输入消息"
          autoSize={{ minRows: 1, maxRows: 4 }}
          value={draft}
          placeholder={config.placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              sendMessage();
            }
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          disabled={!draft.trim()}
          aria-label="发送消息"
          onClick={sendMessage}
        >
          发送
        </Button>
      </footer>
    </section>
  );
}

export function HrChatPage() {
  return <AssistantChatPage config={hrChatConfig} />;
}
