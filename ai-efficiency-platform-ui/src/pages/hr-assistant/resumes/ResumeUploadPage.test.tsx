import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { ResumeUploadPage } from './ResumeUploadPage';

describe('ResumeUploadPage', () => {
  it('keeps the upload workspace and its primary action as named landmarks', () => {
    render(
      <MemoryRouter>
        <ResumeUploadPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('region', { name: '简历上传工作区' })).toBeInTheDocument();
    expect(screen.getByRole('contentinfo', { name: '上传操作' })).toHaveTextContent(
      '开始上传并解析',
    );
  });
});
