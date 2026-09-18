import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { ResumeProgressPage } from './ResumeProgressPage';

it('renders parsing progress with failure isolation and confirmation actions', () => {
  render(
    <MemoryRouter>
      <ResumeProgressPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole('heading', { name: '解析进度' })).toBeInTheDocument();
  expect(screen.getByLabelText('解析进度 12 / 19')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '中止解析' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '去确认' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '查看原因' })).toBeInTheDocument();
});

it('renders the specified completion state when the batch is complete', () => {
  render(
    <MemoryRouter
      initialEntries={['/ai-assistants/hr/resumes/batches/20260901-001?state=completed']}
    >
      <ResumeProgressPage />
    </MemoryRouter>,
  );

  expect(screen.getByText('解析完成')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '查看匹配结果' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '处理待确认项（2）' })).toBeInTheDocument();
});
