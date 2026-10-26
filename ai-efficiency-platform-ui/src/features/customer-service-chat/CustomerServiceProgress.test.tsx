import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';

import { CustomerServiceProgress } from './CustomerServiceProgress';

it('shows only actual stages and collapses a completed run', () => {
  render(
    <CustomerServiceProgress
      status="SUCCEEDED"
      steps={[{ sequence: 3, stage: 'retrieval', phase: 'COMPLETED', summary: '资料查找完成' }]}
    />,
  );
  expect(screen.getByText('处理过程')).toBeInTheDocument();
  expect(screen.getByText('资料查找完成')).toBeInTheDocument();
  expect(screen.getByText('处理过程').closest('details')).not.toHaveAttribute('open');
  expect(screen.queryByText('依据核对完成')).not.toBeInTheDocument();
});

it('keeps a failed run visible without claiming completion', () => {
  render(
    <CustomerServiceProgress
      status="FAILED"
      steps={[{ sequence: 2, stage: 'intent', phase: 'STARTED', summary: '正在理解问题' }]}
    />,
  );
  expect(screen.getByText('本次回答未完成，请重试')).toBeInTheDocument();
  expect(screen.getByText('处理过程').closest('details')).not.toHaveAttribute('open');
  expect(screen.queryByText('已理解问题')).not.toBeInTheDocument();
});
