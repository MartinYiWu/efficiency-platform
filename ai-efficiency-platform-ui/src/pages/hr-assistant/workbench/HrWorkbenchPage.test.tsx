import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { expect, it } from 'vitest';
import { HrWorkbenchPage } from './HrWorkbenchPage';
it('renders the five HR workbench todo categories and direct action', () => {
  render(
    <MemoryRouter>
      <HrWorkbenchPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole('heading', { name: '工作台' })).toBeInTheDocument();
  expect(screen.getByTestId('workbench-main-grid')).toHaveAttribute('data-layout', 'balanced');
  expect(screen.getByRole('button', { name: '上传简历' })).toBeInTheDocument();
  expect(screen.getByText('需要你处理')).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole('button', { name: /去处理|去查看|去配置/ })[0]);
  expect(screen.getByText('2 份简历解析置信度较低，需人工确认')).toBeInTheDocument();
}, 15000);
