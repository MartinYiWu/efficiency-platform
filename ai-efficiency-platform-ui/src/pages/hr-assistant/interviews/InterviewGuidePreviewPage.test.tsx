import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';

import { InterviewGuidePreviewPage } from './InterviewGuidePreviewPage';

it('keeps AI score fields locked out of the interview guide and records sensitive exports', () => {
  render(
    <MemoryRouter>
      <InterviewGuidePreviewPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: '导出面试指南' })).toBeInTheDocument();
  expect(screen.getByText('AI 匹配分数')).toBeInTheDocument();
  expect(screen.getByText(/面试指南不包含 AI 匹配分数与评级/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('radio', { name: /包含脱敏/ }));
  expect(screen.getByText('包含联系方式的导出操作将被记录')).toBeInTheDocument();
});
