import {
  AppstoreOutlined,
  BellOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  FundProjectionScreenOutlined,
  HomeOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Avatar, Drawer, Input, Layout, Menu, type MenuProps, Typography } from 'antd';
import { type ReactNode, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

import styles from './HrAssistantShell.module.css';

interface HrAssistantShellProps {
  children: ReactNode;
}

const hrAssistantItems: MenuProps['items'] = [
  { key: 'hr-workbench', icon: <HomeOutlined />, label: '工作台' },
  { key: 'hr-chat', icon: <RobotOutlined />, label: '智能对话' },
  { key: 'hr-positions', icon: <AppstoreOutlined />, label: '岗位管理' },
  { key: 'hr-resumes', icon: <FileSearchOutlined />, label: '简历中心' },
  { key: 'hr-matching', icon: <FundProjectionScreenOutlined />, label: '匹配结果' },
  { key: 'hr-interviews', icon: <FolderOpenOutlined />, label: '面试准备' },
  { key: 'hr-talent', icon: <TeamOutlined />, label: '人才库' },
  { key: 'hr-settings', icon: <SettingOutlined />, label: '配置中心' },
];

const assistantTreeItems: MenuProps['items'] = [
  {
    key: 'ai-assistants',
    icon: <RobotOutlined />,
    label: 'AI 助手',
    children: [
      {
        key: 'ai-hr',
        icon: <TeamOutlined />,
        label: 'AI 人事助手',
        children: hrAssistantItems,
      },
      { key: 'administration', icon: <UserOutlined />, label: 'AI行政助手' },
      {
        key: 'operations',
        icon: <FundProjectionScreenOutlined />,
        label: 'AI内容运营助手',
        children: [{ key: 'operations-chat', icon: <RobotOutlined />, label: '智能对话' }],
      },
      { key: 'finance', icon: <SafetyCertificateOutlined />, label: 'AI财务助手' },
    ],
  },
];

const assistantPaths: Record<string, string> = {
  'hr-workbench': '/ai-assistants/hr/workbench',
  'hr-chat': '/ai-assistants/hr/chat',
  'hr-positions': '/ai-assistants/hr/positions',
  'hr-resumes': '/ai-assistants/hr/resumes/upload',
  'hr-matching': '/ai-assistants/hr/matching',
  'hr-interviews': '/ai-assistants/hr/interviews',
  'hr-talent': '/ai-assistants/hr/talent',
  'hr-settings': '/ai-assistants/hr/settings',
  'operations-chat': '/ai-assistants/operations/chat',
};

const hrOpenKeys = ['ai-assistants', 'ai-hr'];
const operationsOpenKeys = ['ai-assistants', 'operations'];

function NavigationContent({
  selectedKey,
  collapsed = false,
  onNavigate,
  navigationLabel,
  defaultOpenKeys,
}: {
  selectedKey: string;
  collapsed?: boolean;
  onNavigate: (key: string) => void;
  navigationLabel: string;
  defaultOpenKeys: string[];
}) {
  const [openKeys, setOpenKeys] = useState<string[]>(defaultOpenKeys);
  const handleOpenChange = (keys: string[]) => {
    if (!collapsed) setOpenKeys(keys);
  };

  return (
    <nav className={styles.navigation} aria-label={navigationLabel}>
      <div className={styles.menuGroup}>
        <Typography.Text className={styles.menuGroupTitle}>工作空间</Typography.Text>
        <Menu
          className={styles.primaryMenu}
          mode="inline"
          inlineCollapsed={collapsed}
          selectable={false}
          items={[
            { key: 'platform-workbench', icon: <HomeOutlined />, label: '工作台' },
            { key: 'ai-center', icon: <RobotOutlined />, label: 'AI中心' },
            { key: 'knowledge', icon: <FolderOpenOutlined />, label: '知识中心' },
            { key: 'assets', icon: <DatabaseOutlined />, label: '素材中心' },
          ]}
        />
      </div>
      <Menu
        className={styles.assistantMenu}
        mode="inline"
        inlineCollapsed={collapsed}
        inlineIndent={16}
        selectedKeys={[selectedKey]}
        openKeys={collapsed ? [] : openKeys}
        items={assistantTreeItems}
        onOpenChange={handleOpenChange}
        onClick={({ key }) => onNavigate(key)}
      />
      <div className={styles.menuGroup}>
        <Typography.Text className={styles.menuGroupTitle}>管理</Typography.Text>
        <Menu
          className={styles.primaryMenu}
          mode="inline"
          inlineCollapsed={collapsed}
          selectable={false}
          items={[
            { key: 'organization', icon: <TeamOutlined />, label: '组织中心' },
            { key: 'permissions', icon: <SafetyCertificateOutlined />, label: '权限中心' },
            { key: 'system', icon: <SettingOutlined />, label: '系统管理' },
            { key: 'data', icon: <FundProjectionScreenOutlined />, label: '数据中心' },
          ]}
        />
      </div>
    </nav>
  );
}

export function HrAssistantShell({ children }: HrAssistantShellProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isPositionRoute = pathname.startsWith('/ai-assistants/hr/positions');
  const isPositionListRoute = pathname === '/ai-assistants/hr/positions';
  const isPositionTemplateRoute = pathname === '/ai-assistants/hr/positions/templates';
  const isPositionDetailRoute =
    isPositionRoute &&
    !isPositionListRoute &&
    !isPositionTemplateRoute &&
    !pathname.startsWith('/ai-assistants/hr/positions/new');
  const isComponentStatesRoute = pathname === '/ai-assistants/hr/component-states';
  const isOperationsRoute = pathname.startsWith('/ai-assistants/operations');
  const selectedKey = isOperationsRoute
    ? 'operations-chat'
    : isPositionRoute
      ? 'hr-positions'
      : isComponentStatesRoute
        ? 'hr-settings'
        : pathname.startsWith('/ai-assistants/hr/chat')
          ? 'hr-chat'
          : pathname.startsWith('/ai-assistants/hr/resumes')
            ? 'hr-resumes'
            : pathname.startsWith('/ai-assistants/hr/matching')
              ? 'hr-matching'
              : pathname.startsWith('/ai-assistants/hr/interviews')
                ? 'hr-interviews'
                : pathname.startsWith('/ai-assistants/hr/talent')
                  ? 'hr-talent'
                  : pathname.startsWith('/ai-assistants/hr/settings')
                    ? 'hr-settings'
                    : 'hr-workbench';
  const breadcrumb = isOperationsRoute
    ? 'AI内容运营助手 / 智能对话'
    : isPositionListRoute
      ? 'AI人事助手 / 岗位管理'
      : isPositionTemplateRoute
        ? 'AI人事助手 / 岗位管理 / 岗位族模板库'
        : isPositionDetailRoute
          ? 'AI人事助手 / 岗位管理 / 后端开发工程师'
          : isPositionRoute
            ? 'AI人事助手 / 岗位管理 / 新建岗位'
            : isComponentStatesRoute
              ? 'AI人事助手 / 组件与状态规范'
              : pathname === '/ai-assistants/hr/chat'
                ? 'AI人事助手 / 智能对话'
                : pathname === '/ai-assistants/hr/resumes/upload'
                  ? 'AI人事助手 / 简历中心 / 上传简历'
                  : pathname.startsWith('/ai-assistants/hr/resumes/candidates/')
                    ? 'AI人事助手 / 简历中心 / 张伟_后端开发.pdf / 核对解析结果'
                    : pathname.startsWith('/ai-assistants/hr/resumes/batches/')
                      ? 'AI人事助手 / 简历中心 / 批次 20260901-001 / 解析进度'
                      : pathname.startsWith('/ai-assistants/hr/resumes')
                        ? 'AI人事助手 / 简历中心'
                        : pathname.startsWith('/ai-assistants/hr/matching')
                          ? 'AI人事助手 / 匹配结果'
                          : pathname === '/ai-assistants/hr/interviews/questions'
                            ? 'AI人事助手 / 面试准备 / 张伟 · 后端开发工程师'
                            : pathname === '/ai-assistants/hr/interviews/guide'
                              ? 'AI人事助手 / 面试准备 / 导出面试指南'
                              : pathname.startsWith('/ai-assistants/hr/interviews')
                                ? 'AI人事助手 / 面试准备'
                                : pathname.startsWith('/ai-assistants/hr/talent/')
                                  ? 'AI人事助手 / 人才库 / 张伟 / 候选人档案'
                                  : pathname.startsWith('/ai-assistants/hr/talent')
                                    ? 'AI人事助手 / 人才库'
                                    : pathname === '/ai-assistants/hr/settings/audit'
                                      ? 'AI人事助手 / 配置中心 / 操作审计'
                                      : pathname.startsWith('/ai-assistants/hr/settings')
                                        ? 'AI人事助手 / 配置中心 / 技能同义词库'
                                        : 'AI人事助手 / 工作台';
  const navigationLabel = isOperationsRoute ? 'AI 内容运营助手导航' : 'AI 人事助手导航';
  const defaultOpenKeys = isOperationsRoute ? operationsOpenKeys : hrOpenKeys;
  const searchPlaceholder = isOperationsRoute ? '搜索内容、素材、活动' : '搜索候选人、岗位';
  const userRole = isOperationsRoute ? '运营负责人' : '招聘负责人';
  const navigateWithinAssistant = (key: string) => {
    const path = assistantPaths[key];
    if (path) navigate(path);
  };

  return (
    <Layout className={`${styles.shell} ${sidebarCollapsed ? styles.shellCollapsed : ''}`}>
      <aside className={styles.desktopSider} aria-label="左侧主导航">
        <div className={styles.brand}>
          <span className={styles.brandMark}>AI</span>
          <Typography.Text strong className={styles.brandName}>
            AI效能平台
          </Typography.Text>
          <button
            className={styles.sidebarToggle}
            type="button"
            aria-label={sidebarCollapsed ? '展开左侧导航' : '收合左侧导航'}
            title={sidebarCollapsed ? '展开左侧导航' : '收合左侧导航'}
            onClick={() => setSidebarCollapsed((current) => !current)}
          >
            {sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>
        </div>
        <NavigationContent
          key={isOperationsRoute ? 'operations-navigation' : 'hr-navigation'}
          selectedKey={selectedKey}
          collapsed={sidebarCollapsed}
          onNavigate={navigateWithinAssistant}
          navigationLabel={navigationLabel}
          defaultOpenKeys={defaultOpenKeys}
        />
      </aside>
      <Drawer
        className={styles.mobileDrawer}
        title="AI效能平台"
        placement="left"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <NavigationContent
          key={isOperationsRoute ? 'operations-drawer-navigation' : 'hr-drawer-navigation'}
          selectedKey={selectedKey}
          onNavigate={(key) => {
            navigateWithinAssistant(key);
            if (assistantPaths[key]) setDrawerOpen(false);
          }}
          navigationLabel={navigationLabel}
          defaultOpenKeys={defaultOpenKeys}
        />
      </Drawer>
      <Layout className={styles.workspace}>
        <header className={styles.topBar}>
          <button
            className={styles.menuButton}
            type="button"
            aria-label="打开人事助手导航"
            onClick={() => setDrawerOpen(true)}
          >
            <AppstoreOutlined />
          </button>
          <Typography.Text className={styles.breadcrumb}>{breadcrumb}</Typography.Text>
          <Input
            className={styles.search}
            prefix={<SearchOutlined />}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
          />
          <div className={styles.userActions}>
            <button className={styles.iconButton} type="button" aria-label="消息通知">
              <BellOutlined />
            </button>
            <Avatar className={styles.avatar}>沐</Avatar>
            <Typography.Text strong className={styles.userName}>
              沐白
            </Typography.Text>
            <Typography.Text className={styles.roleTag}>{userRole}</Typography.Text>
          </div>
        </header>
        <main className={styles.content}>{children}</main>
      </Layout>
    </Layout>
  );
}
