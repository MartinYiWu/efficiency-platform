import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { PlatformShell } from './PlatformShell';

describe('PlatformShell', () => {
  it('keeps customer service as a direct second-level assistant link', () => {
    render(<MemoryRouter initialEntries={['/ai-assistants/customer-service/chat']}><PlatformShell><div>内容</div></PlatformShell></MemoryRouter>);
    expect(screen.getByRole('menuitem', { name: /AI 智能客服/ })).toBeInTheDocument();
    expect(screen.queryByText('智能问答')).not.toBeInTheDocument();
  });

  it('shows platform AI center entries without a customer-service config group', () => {
    render(<MemoryRouter initialEntries={['/ai-center/agents']}><PlatformShell><div>内容</div></PlatformShell></MemoryRouter>);
    expect(screen.getByText('Agent 管理')).toBeVisible();
    expect(screen.getByText('用户反馈')).toBeVisible();
    expect(screen.getByText('RAG 评测')).toBeVisible();
    expect(screen.queryByText('智能客服配置')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '收合左侧导航' }));
    expect(screen.getByRole('button', { name: '展开左侧导航' })).toBeInTheDocument();
  });
});
