import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';
import { AuditPage } from './AuditPage';
it('shows traceable sensitive actions and expands their details', () => {
  render(
    <MemoryRouter>
      <AuditPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: '操作审计' })).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole('button', { name: '展开' })[0]);
  expect(screen.getByText(/候选人具备 4 年 Java 后端经验/)).toBeInTheDocument();
}, 15000);

it('paginates audit rows with a distinct second page', () => {
  render(
    <MemoryRouter>
      <AuditPage />
    </MemoryRouter>,
  );

  fireEvent.click(screen.getByTitle('2'));

  expect(screen.getByText(/第 2 页/)).toBeInTheDocument();
  expect(screen.queryByText('吴磊 · 后端开发工程师')).not.toBeInTheDocument();
  expect(screen.getByText('某候选人')).toBeInTheDocument();
});
