<script lang="ts">
import { defineComponent, ref, type PropType } from 'vue';
import { useRouter } from 'vue-router';
import { v as hrNode } from '../hrVnodes';
import { ArrowLeftOutlined, SendOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons-vue';
import { Avatar, Button, Input, Typography } from 'ant-design-vue';
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
export const AssistantChatPage = defineComponent({
  name: 'AssistantChatPage',
  inheritAttrs: false,
  props: Object.fromEntries(['config'].map((key) => [key, {}])) as {
    [
      K in keyof {
        config: AssistantChatConfig;
      }
    ]-?: {
      type: PropType<
        {
          config: AssistantChatConfig;
        }[K]
      >;
      required: true;
    };
  },
  setup(props) {
    const router = useRouter();
    const navigate = (to: string | number) =>
      typeof to === 'number' ? router.go(to) : router.push(to);
    const draft = ref('');
    const setDraft = (
      next: typeof draft.value | ((current: typeof draft.value) => typeof draft.value),
    ) => {
      draft.value = typeof next === 'function' ? next(draft.value) : next;
    };
    const messages = ref(props.config.initialMessages);
    const setMessages = (
      next: typeof messages.value | ((current: typeof messages.value) => typeof messages.value),
    ) => {
      messages.value = typeof next === 'function' ? next(messages.value) : next;
    };
    return () => {
      const { config } = props;
      const sendMessage = () => {
        const content = draft.value.trim();
        if (!content) return;
        setMessages((current: AssistantChatMessage[]) => [
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
      return hrNode(
        'section',
        { className: [styles.page, 'ui-page'], 'aria-labelledby': 'assistant-chat-title' },
        hrNode(
          'header',
          { className: styles.header },
          hrNode(Button, {
            className: styles.backButton,
            type: 'text',
            icon: hrNode(ArrowLeftOutlined, null),
            'aria-label': '返回上一页',
            onClick: () => navigate(-1),
          }),
          hrNode(Avatar, {
            className: styles.assistantAvatar,
            size: 44,
            icon: hrNode(TeamOutlined, null),
          }),
          hrNode(
            'div',
            null,
            hrNode(
              Typography.Title,
              { id: 'assistant-chat-title', level: 1, className: styles.title },
              config.title,
            ),
            hrNode(
              Typography.Text,
              { className: styles.subtitle },
              config.subtitle,
              ' · 演示界面 ',
            ),
          ),
        ),
        hrNode(
          'div',
          {
            className: styles.messageViewport,
            role: 'log',
            'aria-label': '对话消息',
            'aria-live': 'polite',
          },
          hrNode(
            'div',
            { className: styles.messageList },
            messages.value.map((message: AssistantChatMessage) =>
              hrNode(
                'div',
                { className: styles.messageGroup, key: message.id },
                hrNode('time', null, message.time),
                hrNode(
                  'div',
                  {
                    className:
                      message.role === 'user' ? styles.userMessageRow : styles.assistantMessageRow,
                  },
                  message.role === 'assistant' &&
                    hrNode(Avatar, {
                      className: styles.messageAvatar,
                      size: 32,
                      icon: hrNode(TeamOutlined, null),
                    }),
                  hrNode(
                    'div',
                    {
                      className:
                        message.role === 'user' ? styles.userBubble : styles.assistantBubble,
                    },
                    message.content,
                  ),
                  message.role === 'user' &&
                    hrNode(
                      Avatar,
                      { className: styles.userAvatar, size: 34 },
                      hrNode(UserOutlined, null),
                    ),
                ),
              ),
            ),
          ),
        ),
        hrNode(
          'footer',
          { className: styles.composer, 'aria-label': '消息输入' },
          hrNode(Input.TextArea, {
            'aria-label': '输入消息',
            autoSize: { minRows: 1, maxRows: 4 },
            value: draft.value,
            placeholder: config.placeholder,
            onChange: (event: { target: HTMLInputElement }) => setDraft(event.target.value),
            onPressEnter: (event: KeyboardEvent) => {
              if (!event.shiftKey) {
                event.preventDefault();
                sendMessage();
              }
            },
          }),
          hrNode(
            Button,
            {
              type: 'primary',
              icon: hrNode(SendOutlined, null),
              disabled: !draft.value.trim(),
              'aria-label': '发送消息',
              onClick: sendMessage,
            },
            ' 发送 ',
          ),
        ),
      );
    };
  },
});
export const HrChatPage = defineComponent({
  name: 'HrChatPage',
  inheritAttrs: false,
  props: {},
  setup() {
    return () => {
      return hrNode(AssistantChatPage, { config: hrChatConfig });
    };
  },
});
export default HrChatPage;
</script>
