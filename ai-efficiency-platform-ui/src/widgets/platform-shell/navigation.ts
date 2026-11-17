export interface NavigationEntry {
  key: string;
  label: string;
  path?: string;
  children?: NavigationEntry[];
}
export const navigation: NavigationEntry[] = [
  { key: 'workbench', label: '工作台', path: '/ai-assistants/hr/workbench' },
  {
    key: 'assistants',
    label: 'AI 助手',
    children: [
      {
        key: 'customer-service',
        label: 'AI 智能客服',
        path: '/ai-assistants/customer-service/chat',
      },
      { key: 'operations', label: 'AI 内容运营助手', path: '/ai-assistants/operations/chat' },
      { key: 'hr-chat', label: 'AI 人事助手', path: '/ai-assistants/hr/chat' },
    ],
  },
  {
    key: 'hr',
    label: '人事工作台',
    children: [
      { key: 'hr-positions', label: '岗位管理', path: '/ai-assistants/hr/positions' },
      { key: 'hr-resumes', label: '简历中心', path: '/ai-assistants/hr/resumes' },
      { key: 'hr-matching', label: '匹配结果', path: '/ai-assistants/hr/matching' },
      { key: 'hr-interviews', label: '面试准备', path: '/ai-assistants/hr/interviews' },
      { key: 'hr-talent', label: '人才库', path: '/ai-assistants/hr/talent' },
      { key: 'hr-settings', label: '配置中心', path: '/ai-assistants/hr/settings' },
    ],
  },
  { key: 'knowledge', label: '知识中心', path: '/knowledge-center/knowledge-bases' },
  {
    key: 'management',
    label: 'AI 管理',
    children: [
      { key: 'memories', label: '记忆中心', path: '/ai-center/memories' },
      { key: 'agents', label: 'Agent 管理', path: '/ai-center/agents' },
      { key: 'prompts', label: 'Prompt 管理', path: '/ai-center/prompts' },
      { key: 'models', label: '模型策略', path: '/ai-center/model-policies' },
      { key: 'rag', label: 'RAG 策略', path: '/ai-center/rag-policies' },
      { key: 'debug', label: 'RAG 调试', path: '/ai-center/rag-debug' },
      { key: 'evaluations', label: 'RAG 评测', path: '/ai-center/rag-evaluations' },
      { key: 'runs', label: '运行回放', path: '/ai-center/runs' },
      { key: 'feedback', label: '用户反馈', path: '/ai-center/feedback' },
    ],
  },
];
export const leafNavigation = navigation.flatMap((item) => item.children ?? [item]);
export function selectedNavigation(path: string) {
  return [...leafNavigation]
    .sort((a, b) => (b.path?.length ?? 0) - (a.path?.length ?? 0))
    .find((item) => item.path && path.startsWith(item.path));
}
