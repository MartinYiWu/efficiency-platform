import type { AssistantChatConfig } from './HrChatPage';

export const hrChatConfig: AssistantChatConfig = {
  title: 'AI 人事助手',
  subtitle: '协助处理岗位、简历、匹配和面试准备',
  placeholder: '输入你想咨询的人事工作问题…',
  initialMessages: [
    {
      id: 'assistant-welcome',
      role: 'assistant',
      time: '10:30',
      content:
        '你好，我是 AI 人事助手。你可以直接告诉我岗位、简历或面试准备方面的需求，我会帮你梳理下一步。',
    },
    {
      id: 'user-example',
      role: 'user',
      time: '10:31',
      content: '我想为后端开发工程师准备一轮技术面试，应该从哪些方向开始？',
    },
    {
      id: 'assistant-example',
      role: 'assistant',
      time: '10:31',
      content:
        '建议先确认岗位的核心技能、工作年限和项目场景，再结合候选人的简历证据生成有针对性的面试题。你也可以告诉我目标岗位或候选人，我会继续协助梳理。',
    },
  ],
};
