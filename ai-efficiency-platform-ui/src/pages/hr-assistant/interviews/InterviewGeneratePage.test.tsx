import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { InterviewGeneratePage } from './InterviewGeneratePage';

it('renders the interview question configuration and lets the user adjust its scope', () => {
  render(
    <MemoryRouter>
      <InterviewGeneratePage />
    </MemoryRouter>,
  );

  expect(screen.getByRole('heading', { name: '生成面试题' })).toBeInTheDocument();
  expect(screen.getByText('张伟')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /技术面试官/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  fireEvent.click(screen.getByRole('button', { name: '复试' }));
  fireEvent.click(screen.getByRole('button', { name: /层级题量分配（60分钟）/ }));

  expect(screen.getByRole('button', { name: '复试' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByText('合计 17 题 · 预估 58 分钟')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /开始生成/ })).toBeEnabled();
});
