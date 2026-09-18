import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { FilteredResumesPage } from './FilteredResumesPage';

it('renders retained filtered resumes and an accountable manual-release entry', () => {
  render(
    <MemoryRouter>
      <FilteredResumesPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: '被硬性条件过滤的简历' })).toBeInTheDocument();
  expect(screen.getByText('吴磊')).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: '人工放行此条件并评分' }).length).toBeGreaterThan(0);
  expect(screen.getByText(/所有被过滤的简历都保留在系统中，不会被删除/)).toBeInTheDocument();
});

it('requires a documented reason before an allowed hard condition can be released', () => {
  render(
    <MemoryRouter>
      <FilteredResumesPage />
    </MemoryRouter>,
  );

  fireEvent.click(screen.getAllByRole('button', { name: '人工放行此条件并评分' })[0]);

  expect(screen.getByText('放行后的预计变化')).toBeInTheDocument();
  expect(screen.getByText('不允许放行')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '确认放行并重新评分' })).toBeDisabled();

  fireEvent.change(screen.getByPlaceholderText(/请说明放行理由/), {
    target: { value: '候选人具备可迁移的 Java 后端经验，建议人工复核。' },
  });

  expect(screen.getByRole('button', { name: '确认放行并重新评分' })).toBeEnabled();
});
