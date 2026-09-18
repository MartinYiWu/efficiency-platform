import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { OperationProgress } from './OperationProgress';

describe('OperationProgress', () => {
  it('在同一个礼貌 live region 中呈现真实阶段与有效计数', () => {
    const { rerender } = render(
      <OperationProgress
        value={{
          phase: 'collecting_sources',
          label: '正在收集公开来源',
          completed: 4,
          target: 9,
        }}
      />,
    );

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-live', 'polite');
    expect(status).toHaveTextContent('正在收集公开来源');
    expect(status).toHaveTextContent('4/9');

    rerender(
      <OperationProgress value={{ phase: 'checking_evidence', label: '正在去重并核验信息' }} />,
    );
    expect(screen.getByRole('status')).toBe(status);
    expect(status).toHaveTextContent('正在去重并核验信息');
    expect(status).not.toHaveTextContent('0/0');
  });
});
