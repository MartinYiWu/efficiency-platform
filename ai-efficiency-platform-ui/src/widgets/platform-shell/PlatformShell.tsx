import { AppstoreOutlined, BellOutlined, MenuFoldOutlined, MenuUnfoldOutlined, SearchOutlined } from '@ant-design/icons';
import { Avatar, Drawer, Input, Layout, Menu, Typography } from 'antd';
import { type ReactNode, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

import styles from '../hrAssistantShell/HrAssistantShell.module.css';
import { assistantItems, managementItems, navigationPaths, resolveShellContext, workspaceItems } from './navigation';

function Navigation({ collapsed = false, close }: { collapsed?: boolean; close?: () => void }) {
  const navigate = useNavigate(); const context = resolveShellContext(useLocation().pathname);
  const [openKeys, setOpenKeys] = useState(context.openKeys);
  const go = (key: string) => { const path = navigationPaths[key]; if (path) { navigate(path); close?.(); } };
  const menu = (items: typeof workspaceItems, selectable = true) => <Menu mode="inline" inlineCollapsed={collapsed} inlineIndent={16} items={items} selectedKeys={selectable ? [context.selectedKey] : []} openKeys={collapsed ? [] : openKeys} onOpenChange={setOpenKeys} onClick={({ key }) => go(key)} />;
  return <nav className={styles.navigation} aria-label={context.navigationLabel}>
    <div className={styles.menuGroup}><Typography.Text className={styles.menuGroupTitle}>工作空间</Typography.Text>{menu(workspaceItems)}</div>
    <div className={styles.assistantMenu}>{menu(assistantItems)}</div>
    <div className={styles.menuGroup}><Typography.Text className={styles.menuGroupTitle}>管理</Typography.Text>{menu(managementItems, false)}</div>
  </nav>;
}

export function PlatformShell({ children }: { children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false); const [collapsed, setCollapsed] = useState(false);
  const context = resolveShellContext(useLocation().pathname);
  return <Layout className={`${styles.shell} ${collapsed ? styles.shellCollapsed : ''}`}>
    <aside className={styles.desktopSider} aria-label="左侧主导航"><div className={styles.brand}><span className={styles.brandMark}>AI</span><Typography.Text strong className={styles.brandName}>AI效能平台</Typography.Text><button className={styles.sidebarToggle} type="button" aria-label={collapsed ? '展开左侧导航' : '收合左侧导航'} onClick={() => setCollapsed((value) => !value)}>{collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}</button></div><Navigation collapsed={collapsed} /></aside>
    <Drawer className={styles.mobileDrawer} title="AI效能平台" placement="left" open={drawerOpen} onClose={() => setDrawerOpen(false)}><Navigation close={() => setDrawerOpen(false)} /></Drawer>
    <Layout className={styles.workspace}><header className={styles.topBar}><button className={styles.menuButton} type="button" aria-label="打开平台导航" onClick={() => setDrawerOpen(true)}><AppstoreOutlined /></button><Typography.Text className={styles.breadcrumb}>{context.breadcrumb}</Typography.Text><Input className={styles.search} prefix={<SearchOutlined />} placeholder={context.searchPlaceholder} aria-label={context.searchPlaceholder} /><div className={styles.userActions}><button className={styles.iconButton} type="button" aria-label="消息通知"><BellOutlined /></button><Avatar className={styles.avatar}>沐</Avatar><Typography.Text strong className={styles.userName}>沐白</Typography.Text><Typography.Text className={styles.roleTag}>{context.userRole}</Typography.Text></div></header><main className={styles.content}>{children}</main></Layout>
  </Layout>;
}
