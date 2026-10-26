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
