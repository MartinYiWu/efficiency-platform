import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { ResumeCorrectionPage } from './ResumeCorrectionPage';

it('renders the low-confidence correction workspace with guarded continuation', () => {
  render(
    <MemoryRouter>
      <ResumeCorrectionPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole('heading', { name: '核对解析结果' })).toBeInTheDocument();
  expect(screen.getByText('本份简历解析置信度较低，请核对标记项后再进行匹配')).toBeInTheDocument();
  expect(screen.getByText(/4 项需确认/)).toBeInTheDocument();
  screen.getAllByRole('button', { name: '确认并继续匹配' }).forEach((button) => {
    expect(button).toBeDisabled();
  });
  expect(screen.getByRole('button', { name: '跳过，按现有结果继续' })).toBeInTheDocument();
}, 15_000);
