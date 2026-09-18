import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PageContainer } from './PageContainer';

describe('PageContainer', () => {
  it('renders the page title and content', () => {
    render(
      <PageContainer title="测试页面">
        <p>页面内容</p>
      </PageContainer>,
    );

    expect(screen.getByRole('heading', { name: '测试页面' })).toBeInTheDocument();
    expect(screen.getByText('页面内容')).toBeInTheDocument();
  });

  it('renders title actions before scrollable page content', () => {
    render(
      <PageContainer title="页面标题" actions={<button>主要操作</button>}>
        <p>长内容</p>
      </PageContainer>,
    );

    expect(screen.getByRole('button', { name: '主要操作' })).toBeInTheDocument();
    expect(screen.getByTestId('page-container-actions')).toHaveAttribute('data-sticky', 'true');
  });
});
