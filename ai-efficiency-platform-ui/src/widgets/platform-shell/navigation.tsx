export interface NavigationItem { key: string; label: string; path: string }
export type PrimarySection = 'workbench' | 'assistants' | 'knowledge' | 'management';

export const primaryItems: (NavigationItem & { section: PrimarySection })[] = [
  { key: 'workbench', label: '工作台', path: '/ai-assistants/hr/workbench', section: 'workbench' },
  { key: 'assistants', label: 'AI 助手', path: '/ai-assistants/customer-service/chat', section: 'assistants' },
  { key: 'knowledge', label: '知识中心', path: '/knowledge-center/knowledge-bases', section: 'knowledge' },
  { key: 'management', label: 'AI 管理', path: '/ai-center/agents', section: 'management' },
];

export const assistantItems: NavigationItem[] = [
  { key: 'customer-service', label: 'AI 智能客服', path: '/ai-assistants/customer-service/chat' },
  { key: 'operations', label: 'AI 内容运营助手', path: '/ai-assistants/operations/chat' },
  { key: 'hr-chat', label: 'AI 人事助手', path: '/ai-assistants/hr/chat' },
];

export const managementItems: NavigationItem[] = [
  { key: 'agents', label: 'Agent 管理', path: '/ai-center/agents' },
  { key: 'prompts', label: 'Prompt 管理', path: '/ai-center/prompts' },
  { key: 'models', label: '模型策略', path: '/ai-center/model-policies' },
  { key: 'rag', label: 'RAG 策略', path: '/ai-center/rag-policies' },
  { key: 'debug', label: 'RAG 调试', path: '/ai-center/rag-debug' },
  { key: 'evaluations', label: 'RAG 评测', path: '/ai-center/rag-evaluations' },
  { key: 'runs', label: '运行回放', path: '/ai-center/runs' },
  { key: 'feedback', label: '用户反馈', path: '/ai-center/feedback' },
];

export const hrItems: NavigationItem[] = [
  { key: 'hr-workbench', label: '工作台', path: '/ai-assistants/hr/workbench' },
  { key: 'hr-chat', label: '智能对话', path: '/ai-assistants/hr/chat' },
  { key: 'hr-positions', label: '岗位管理', path: '/ai-assistants/hr/positions' },
  { key: 'hr-resumes', label: '简历中心', path: '/ai-assistants/hr/resumes/upload' },
  { key: 'hr-matching', label: '匹配结果', path: '/ai-assistants/hr/matching' },
  { key: 'hr-interviews', label: '面试准备', path: '/ai-assistants/hr/interviews' },
  { key: 'hr-talent', label: '人才库', path: '/ai-assistants/hr/talent' },
  { key: 'hr-settings', label: '配置中心', path: '/ai-assistants/hr/settings' },
];

export interface ShellContext {
  section: PrimarySection | 'none';
  selectedKey: string;
  localLabel?: string;
  localItems?: NavigationItem[];
  isChat: boolean;
}

function selectedItem(pathname: string, items: NavigationItem[]): NavigationItem {
  return [...items].sort((a, b) => b.path.length - a.path.length).find((item) => pathname.startsWith(item.path)) ?? items[0];
}

export function resolveShellContext(pathname: string): ShellContext {
  if (!pathname.startsWith('/ai-center') && !pathname.startsWith('/knowledge-center') && !pathname.startsWith('/ai-assistants/')) {
    return { section: 'none', selectedKey: '', isChat: false };
  }
  if (pathname.startsWith('/ai-center')) {
    const selected = selectedItem(pathname, managementItems);
    return { section: 'management', selectedKey: selected.key, localLabel: 'AI 管理导航', localItems: managementItems, isChat: false };
  }
  if (pathname.startsWith('/knowledge-center')) return { section: 'knowledge', selectedKey: 'knowledge', isChat: false };
  if (pathname.startsWith('/ai-assistants/hr') || pathname.endsWith('/component-states')) {
    const selected = pathname.endsWith('/component-states') ? hrItems.find((item) => item.key === 'hr-settings')! : selectedItem(pathname, hrItems);
    const isChat = pathname.startsWith('/ai-assistants/hr/chat');
    return { section: pathname.startsWith('/ai-assistants/hr/workbench') ? 'workbench' : 'assistants', selectedKey: selected.key, localLabel: isChat ? undefined : 'AI 人事助手导航', localItems: isChat ? undefined : hrItems, isChat };
  }
  const selected = selectedItem(pathname, assistantItems);
  return { section: 'assistants', selectedKey: selected.key, isChat: true };
}
