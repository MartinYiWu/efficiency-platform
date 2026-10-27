import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { PlatformShell } from './PlatformShell';

describe('PlatformShell', () => {
  it('opens customer service directly from the assistant section', () => {
    render(<MemoryRouter initialEntries={['/ai-assistants/customer-service/chat']}><PlatformShell><div>内容</div></PlatformShell></MemoryRouter>);
    expect(screen.getByRole('navigation', { name: '平台主导航' })).toHaveTextContent('AI 助手');
    expect(screen.getByRole('button', { name: 'AI 助手' })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByText('智能问答')).not.toBeInTheDocument();
  });

  it('shows platform AI center entries without a customer-service config group', () => {
    render(<MemoryRouter initialEntries={['/ai-center/agents']}><PlatformShell><div>内容</div></PlatformShell></MemoryRouter>);
    const localNav = screen.getByRole('navigation', { name: 'AI 管理导航' });
    expect(localNav).toHaveTextContent('Agent 管理');
    expect(localNav).toHaveTextContent('用户反馈');
    expect(localNav).toHaveTextContent('RAG 评测');
    expect(screen.queryByText('智能客服配置')).not.toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '平台主导航' })).toHaveTextContent('知识中心');
  });
});
