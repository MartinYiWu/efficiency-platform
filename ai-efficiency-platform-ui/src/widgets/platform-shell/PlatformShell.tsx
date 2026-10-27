import { ApiOutlined, AppstoreOutlined, AuditOutlined, BarChartOutlined, BookOutlined, CommentOutlined, DatabaseOutlined, ExperimentOutlined, FileSearchOutlined, FileTextOutlined, FolderOpenOutlined, HomeOutlined, MenuOutlined, MessageOutlined, SettingOutlined, TeamOutlined } from '@ant-design/icons';
import { Drawer } from 'antd';
import { type ReactNode, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

import styles from './PlatformShell.module.css';
import { assistantItems, type NavigationItem, primaryItems, resolveShellContext } from './navigation';

const navIcons: Record<string, ReactNode> = {
  workbench: <HomeOutlined />, assistants: <MessageOutlined />, knowledge: <FolderOpenOutlined />, management: <SettingOutlined />,
  agents: <ApiOutlined />, prompts: <FileTextOutlined />, models: <AppstoreOutlined />, rag: <DatabaseOutlined />,
  debug: <ExperimentOutlined />, evaluations: <BarChartOutlined />, runs: <AuditOutlined />, feedback: <CommentOutlined />,
  'customer-service': <MessageOutlined />, operations: <BookOutlined />, 'hr-chat': <TeamOutlined />,
  'hr-workbench': <HomeOutlined />, 'hr-positions': <AppstoreOutlined />, 'hr-resumes': <FileSearchOutlined />,
  'hr-matching': <BarChartOutlined />, 'hr-interviews': <FileTextOutlined />, 'hr-talent': <TeamOutlined />, 'hr-settings': <SettingOutlined />,
};

function NavigationLinks({ items, selectedKey, onNavigate }: { items: NavigationItem[]; selectedKey: string; onNavigate?: () => void }) {
  const navigate = useNavigate();
  return <>{items.map((item) => <button key={item.key} type="button" className={`${styles.navLink} ${selectedKey === item.key ? styles.active : ''}`} aria-current={selectedKey === item.key ? 'page' : undefined} onClick={() => { navigate(item.path); onNavigate?.(); }}><span className={styles.navIcon} aria-hidden="true">{navIcons[item.key]}</span>{item.label}</button>)}</>;
}

export function PlatformShell({ children }: { children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const context = resolveShellContext(useLocation().pathname);
  const mobileItems = [...primaryItems, ...assistantItems, ...(context.localItems ?? [])];

  return <div className={`${styles.shell} ${context.isChat ? styles.chatShell : ''}`}>
    <header className={styles.header}>
      <button className={styles.mobileMenuButton} type="button" aria-label="打开平台导航" onClick={() => setDrawerOpen(true)}><MenuOutlined /></button>
      <button className={styles.brand} type="button" onClick={() => navigate('/ai-assistants/hr/workbench')} aria-label="AI效能平台，返回工作台"><span className={styles.brandMark}><AppstoreOutlined /></span><span>AI效能平台</span></button>
      <nav className={styles.primaryNav} aria-label="平台主导航">{primaryItems.map((item) => <button key={item.key} type="button" className={`${styles.primaryLink} ${context.section === item.section ? styles.primaryActive : ''}`} aria-current={context.section === item.section ? 'page' : undefined} onClick={() => navigate(item.path)}><span aria-hidden="true">{navIcons[item.key]}</span>{item.label}</button>)}</nav>
      <span className={styles.headerCaption}>内部用户</span>
    </header>
    {context.isChat && <nav className={styles.assistantTabs} aria-label="AI 助手导航"><NavigationLinks items={assistantItems} selectedKey={context.selectedKey} /></nav>}
    <div className={styles.body}>
      {context.localItems && <aside className={styles.localSidebar}><div className={styles.localHeading}>{context.localLabel === 'AI 人事助手导航' ? 'AI 人事助手 · 演示数据' : 'AI 管理'}</div><nav className={styles.localNav} aria-label={context.localLabel}><NavigationLinks items={context.localItems} selectedKey={context.selectedKey} /></nav></aside>}
      <main className={styles.content}>{children}</main>
    </div>
    <Drawer className={styles.mobileDrawer} title="AI效能平台" placement="left" open={drawerOpen} onClose={() => setDrawerOpen(false)}><nav className={styles.mobileNav} aria-label="移动端平台导航"><NavigationLinks items={mobileItems} selectedKey={context.selectedKey} onNavigate={() => setDrawerOpen(false)} /></nav></Drawer>
  </div>;
}
