import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';
import { TalentSearchPage } from './TalentSearchPage';
it('filters the talent library without exposing hiring decisions', () => {
  render(
    <MemoryRouter>
      <TalentSearchPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: '人才库' })).toBeInTheDocument();
  expect(screen.getByTestId('talent-results')).toHaveAttribute('data-height', 'content');
  fireEvent.click(screen.getByRole('button', { name: /搜索/ }));
  expect(screen.getByText(/当前筛选出.*34 位/)).toBeInTheDocument();
  expect(screen.getByText('张伟')).toBeInTheDocument();
}, 15000);

it('paginates candidate results with a distinct second page', () => {
  render(
    <MemoryRouter>
      <TalentSearchPage />
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByTitle('2'));

  expect(screen.getByText(/第 2 页/)).toBeInTheDocument();
  expect(screen.queryByText('张伟')).not.toBeInTheDocument();
  expect(screen.getByText('刘敏')).toBeInTheDocument();
});
