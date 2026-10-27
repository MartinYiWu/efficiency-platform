import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { PlatformShell } from './PlatformShell';
import { resolveShellContext } from './navigation';

it('uses a top navigation and only real AI management routes', () => {
  render(
    <MemoryRouter initialEntries={['/ai-center/agents']}>
      <PlatformShell>内容</PlatformShell>
    </MemoryRouter>,
  );

  expect(screen.getByRole('navigation', { name: '平台主导航' })).toHaveTextContent('知识中心');
  expect(screen.getByRole('navigation', { name: 'AI 管理导航' })).toHaveTextContent('Agent 管理');
  expect(screen.queryByText('素材中心')).not.toBeInTheDocument();
  expect(screen.queryByPlaceholderText('搜索 AI 资产')).not.toBeInTheDocument();
  expect(screen.queryByText('沐白')).not.toBeInTheDocument();
});

it('shows HR local navigation only in the HR workspace', () => {
  render(
    <MemoryRouter initialEntries={['/ai-assistants/hr/workbench']}>
      <PlatformShell>内容</PlatformShell>
    </MemoryRouter>,
  );

  expect(screen.getByRole('navigation', { name: 'AI 人事助手导航' })).toHaveTextContent('岗位管理');
  expect(screen.getByRole('navigation', { name: '平台主导航' })).toHaveTextContent('AI 助手');
  expect(screen.queryByText('权限中心')).not.toBeInTheDocument();
});

it('highlights settings for the HR component states page', () => {
  expect(resolveShellContext('/ai-assistants/hr/component-states').selectedKey).toBe('hr-settings');
});
