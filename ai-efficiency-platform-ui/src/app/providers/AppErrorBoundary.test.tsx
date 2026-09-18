import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AppErrorBoundary } from './AppErrorBoundary';

function ThrowingComponent(): never {
  throw new Error('render failed');
}

describe('AppErrorBoundary', () => {
  it('renders a recovery message when a child component throws', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(
      <AppErrorBoundary>
        <ThrowingComponent />
      </AppErrorBoundary>,
    );

    expect(screen.getByText('页面发生异常，请刷新后重试。')).toBeInTheDocument();
    consoleError.mockRestore();
  });
});
