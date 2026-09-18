import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { InterviewQuestionSetPage } from './InterviewQuestionSetPage';

it('renders traceable interview questions and supports expanding a question', () => {
  render(
    <MemoryRouter>
      <InterviewQuestionSetPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: '面试题集' })).toBeInTheDocument();
  expect(screen.getByTestId('question-workspace')).toHaveAttribute('data-layout', 'editor-first');
  expect(screen.getAllByRole('button', { name: '导出面试指南' }).length).toBeGreaterThan(0);
  expect(screen.getByText('17 题 · 58 分钟')).toBeInTheDocument();
  expect(screen.getAllByText(/主导了订单系统重构/).length).toBeGreaterThan(0);
  fireEvent.click(screen.getAllByRole('button', { name: /B1.*Redis/ })[0]);
  expect(screen.getByText(/简历中未体现 Redis 经验/)).toBeInTheDocument();
});
