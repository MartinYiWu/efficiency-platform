import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { MatchResultsPage } from './MatchResultsPage';

it('renders match results and keeps AI guidance distinct from a hiring decision', () => {
  render(
    <MemoryRouter>
      <MatchResultsPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: /后端开发工程师（P6）/ })).toBeInTheDocument();
  expect(
    screen.getByText('本结果由 AI 辅助生成，仅供参考。最终判断请结合面试与人工评估。'),
  ).toBeInTheDocument();
  expect(screen.getByText('张伟')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /查看并打捞 →/ })).toBeInTheDocument();
}, 15000);

it('opens the weight recalculation dialog with a valid total and impact preview', () => {
  render(
    <MemoryRouter>
      <MatchResultsPage />
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByRole('button', { name: '调整权重重算' }));

  expect(screen.getByText('调整后的预计变化')).toBeInTheDocument();
  expect(screen.getByText('合计 100%')).toBeInTheDocument();
  expect(screen.getByText(/历史匹配结果会保留/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '确认并重算' })).toBeEnabled();
}, 35_000);

it('paginates matching rows instead of rendering static pagination text', () => {
  render(
    <MemoryRouter>
      <MatchResultsPage />
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByTitle('2'));

  expect(screen.getByText(/第 2 页/)).toBeInTheDocument();
  expect(screen.queryByText('张伟')).not.toBeInTheDocument();
  expect(screen.getByText('周涛')).toBeInTheDocument();
});
