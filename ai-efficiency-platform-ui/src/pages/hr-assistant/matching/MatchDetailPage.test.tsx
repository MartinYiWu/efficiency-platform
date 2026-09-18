import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { MatchDetailPage } from './MatchDetailPage';

it('renders traceable evidence and a guarded contact reveal action', () => {
  render(
    <MemoryRouter>
      <MatchDetailPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: '张伟', level: 1 })).toBeInTheDocument();
  expect(screen.getAllByText('硬性条件校验').length).toBeGreaterThan(1);
  expect(screen.getAllByRole('button', { name: '查看原文位置 →' }).length).toBeGreaterThan(0);
  expect(screen.getByRole('button', { name: '查看完整联系方式' })).toBeInTheDocument();
});
