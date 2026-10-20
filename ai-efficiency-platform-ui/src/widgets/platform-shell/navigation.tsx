import {
  AppstoreOutlined, DatabaseOutlined, ExperimentOutlined, FileSearchOutlined,
  FolderOpenOutlined, FundProjectionScreenOutlined, HomeOutlined, MessageOutlined,
  RobotOutlined, SafetyCertificateOutlined, SettingOutlined, TeamOutlined, UserOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';

export const assistantItems: MenuProps['items'] = [{
  key: 'ai-assistants', icon: <RobotOutlined />, label: 'AI 助手', children: [
    { key: 'customer-service', icon: <MessageOutlined />, label: 'AI 智能客服' },
    { key: 'ai-hr', icon: <TeamOutlined />, label: 'AI 人事助手', children: [
      { key: 'hr-workbench', icon: <HomeOutlined />, label: '工作台' },
      { key: 'hr-chat', icon: <RobotOutlined />, label: '智能对话' },
      { key: 'hr-positions', icon: <AppstoreOutlined />, label: '岗位管理' },
      { key: 'hr-resumes', icon: <FileSearchOutlined />, label: '简历中心' },
      { key: 'hr-matching', icon: <FundProjectionScreenOutlined />, label: '匹配结果' },
      { key: 'hr-interviews', icon: <FolderOpenOutlined />, label: '面试准备' },
      { key: 'hr-talent', icon: <TeamOutlined />, label: '人才库' },
      { key: 'hr-settings', icon: <SettingOutlined />, label: '配置中心' },
    ] },
    { key: 'administration', icon: <UserOutlined />, label: 'AI行政助手' },
    { key: 'operations', icon: <FundProjectionScreenOutlined />, label: 'AI内容运营助手', children: [
      { key: 'operations-chat', icon: <RobotOutlined />, label: '智能对话' },
    ] },
    { key: 'finance', icon: <SafetyCertificateOutlined />, label: 'AI财务助手' },
  ],
}];

export const workspaceItems: MenuProps['items'] = [
  { key: 'platform-workbench', icon: <HomeOutlined />, label: '工作台' },
  { key: 'knowledge-bases', icon: <FolderOpenOutlined />, label: '知识中心' },
  { key: 'ai-center', icon: <RobotOutlined />, label: 'AI 中心', children: [
    { key: 'ai-agents', label: 'Agent 管理' }, { key: 'ai-prompts', label: 'Prompt 管理' },
    { key: 'ai-models', label: '模型策略' }, { key: 'ai-rag', label: 'RAG 策略' },
    { key: 'ai-debug', icon: <ExperimentOutlined />, label: 'RAG 调试' },
    { key: 'ai-runs', label: '运行回放' }, { key: 'ai-feedback', label: '用户反馈' },
  ] },
  { key: 'assets', icon: <DatabaseOutlined />, label: '素材中心' },
];

export const managementItems: MenuProps['items'] = [
  { key: 'organization', icon: <TeamOutlined />, label: '组织中心' },
  { key: 'permissions', icon: <SafetyCertificateOutlined />, label: '权限中心' },
  { key: 'system', icon: <SettingOutlined />, label: '系统管理' },
  { key: 'data', icon: <FundProjectionScreenOutlined />, label: '数据中心' },
];

export const navigationPaths: Record<string, string> = {
  'customer-service': '/ai-assistants/customer-service/chat',
  'knowledge-bases': '/knowledge-center/knowledge-bases',
  'ai-agents': '/ai-center/agents', 'ai-prompts': '/ai-center/prompts',
  'ai-models': '/ai-center/model-policies', 'ai-rag': '/ai-center/rag-policies',
  'ai-debug': '/ai-center/rag-debug', 'ai-runs': '/ai-center/runs', 'ai-feedback': '/ai-center/feedback',
  'hr-workbench': '/ai-assistants/hr/workbench', 'hr-chat': '/ai-assistants/hr/chat',
  'hr-positions': '/ai-assistants/hr/positions', 'hr-resumes': '/ai-assistants/hr/resumes/upload',
  'hr-matching': '/ai-assistants/hr/matching', 'hr-interviews': '/ai-assistants/hr/interviews',
  'hr-talent': '/ai-assistants/hr/talent', 'hr-settings': '/ai-assistants/hr/settings',
  'operations-chat': '/ai-assistants/operations/chat',
};

export interface ShellContext { selectedKey: string; openKeys: string[]; breadcrumb: string; navigationLabel: string; searchPlaceholder: string; userRole: string }

export function resolveShellContext(pathname: string): ShellContext {
  if (pathname.startsWith('/ai-assistants/customer-service')) return { selectedKey: 'customer-service', openKeys: ['ai-assistants'], breadcrumb: 'AI 智能客服', navigationLabel: 'AI 智能客服导航', searchPlaceholder: '搜索会话', userRole: '内部员工' };
  if (pathname.startsWith('/knowledge-center')) return { selectedKey: 'knowledge-bases', openKeys: [], breadcrumb: '知识中心', navigationLabel: '知识中心导航', searchPlaceholder: '搜索知识库和文档', userRole: '平台管理员' };
  if (pathname.startsWith('/ai-center')) {
    const selected = Object.entries(navigationPaths).find(([, path]) => pathname.startsWith(path))?.[0] ?? 'ai-agents';
    return { selectedKey: selected, openKeys: ['ai-center'], breadcrumb: 'AI 中心', navigationLabel: 'AI 中心导航', searchPlaceholder: '搜索 AI 资产', userRole: '平台管理员' };
  }
  if (pathname.startsWith('/ai-assistants/operations')) return { selectedKey: 'operations-chat', openKeys: ['ai-assistants', 'operations'], breadcrumb: 'AI内容运营助手 / 智能对话', navigationLabel: 'AI 内容运营助手导航', searchPlaceholder: '搜索内容、素材、活动', userRole: '运营负责人' };
  const selected = pathname.startsWith('/ai-assistants/hr/positions') ? 'hr-positions' : pathname.startsWith('/ai-assistants/hr/resumes') ? 'hr-resumes' : pathname.startsWith('/ai-assistants/hr/matching') ? 'hr-matching' : pathname.startsWith('/ai-assistants/hr/interviews') ? 'hr-interviews' : pathname.startsWith('/ai-assistants/hr/talent') ? 'hr-talent' : pathname.startsWith('/ai-assistants/hr/settings') || pathname.endsWith('/component-states') ? 'hr-settings' : pathname.startsWith('/ai-assistants/hr/chat') ? 'hr-chat' : 'hr-workbench';
  const breadcrumb = pathname.endsWith('/component-states') ? 'AI人事助手 / 组件与状态规范' : pathname === '/ai-assistants/hr/resumes/upload' ? 'AI人事助手 / 简历中心 / 上传简历' : selected === 'hr-positions' ? 'AI人事助手 / 岗位管理' : selected === 'hr-chat' ? 'AI人事助手 / 智能对话' : 'AI人事助手 / 工作台';
  return { selectedKey: selected, openKeys: ['ai-assistants', 'ai-hr'], breadcrumb, navigationLabel: 'AI 人事助手导航', searchPlaceholder: '搜索候选人、岗位', userRole: '招聘负责人' };
}
