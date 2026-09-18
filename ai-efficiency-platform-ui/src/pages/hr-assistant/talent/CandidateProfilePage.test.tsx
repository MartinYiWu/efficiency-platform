import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { CandidateProfilePage } from './CandidateProfilePage';

it('renders the candidate profile with masked contacts and structured profile tab', () => {
  render(
    <MemoryRouter>
      <CandidateProfilePage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: '张伟' })).toBeInTheDocument();
  expect(screen.getByText('138****5678')).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: '结构化档案' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('分布式订单系统重构')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '查看匹配结果' })).toBeInTheDocument();
});
