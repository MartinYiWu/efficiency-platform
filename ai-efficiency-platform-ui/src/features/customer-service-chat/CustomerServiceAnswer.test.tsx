import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CustomerServiceAnswer } from './CustomerServiceAnswer';

describe('answer source labels', () => {
  it('shows a single clear general advice label without a repeated warning', () => {
    render(
      <CustomerServiceAnswer
        content="建议先整理问题清单。"
        mode="GENERAL_ADVICE"
        citations={[]}
        streaming={false}
        onCitation={vi.fn()}
      />,
    );
    expect(screen.getByText('通用建议（非公司制度）')).toBeInTheDocument();
    expect(
      screen.queryByText('以下为通用建议，不代表公司制度或正式流程。'),
    ).not.toBeInTheDocument();
    expect(screen.getByText('建议先整理问题清单。')).toBeInTheDocument();
  });

  it('preserves the company and general sections of a mixed answer', () => {
    render(
      <CustomerServiceAnswer
        content={'## 公司资料\n\n请按已发布流程办理。\n\n## 通用建议\n\n可以提前准备材料。'}
        mode="MIXED"
        citations={[]}
        streaming={false}
        onCitation={vi.fn()}
      />,
    );
    expect(screen.getByRole('heading', { name: '公司资料' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '通用建议' })).toBeInTheDocument();
  });
});
