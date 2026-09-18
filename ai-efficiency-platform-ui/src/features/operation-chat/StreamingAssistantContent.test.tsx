import { act, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { StreamingAssistantContent } from './StreamingAssistantContent';

type DisplayMode = 'typing' | 'complete' | 'frozen';

function contentProps(
  content: string,
  mode: DisplayMode,
): ComponentProps<typeof StreamingAssistantContent> {
  return { content, mode };
}

describe('StreamingAssistantContent', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('按 Unicode 字素逐个显示权威正文，且不把原始 HTML 渲染为元素', async () => {
    vi.useFakeTimers();
    const { container } = render(
      <StreamingAssistantContent {...contentProps('你👨‍👩‍👧‍👦好<script>危险</script>', 'typing')} />,
    );

    expect(screen.getByLabelText('助手回复')).toHaveTextContent('');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(24);
    });
    expect(screen.getByLabelText('助手回复')).toHaveTextContent('你');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(24);
    });
    expect(screen.getByLabelText('助手回复')).toHaveTextContent('你👨‍👩‍👧‍👦');
    expect(container.querySelector('script')).toBeNull();
  });

  it('减少动态效果时直接显示当前权威正文', () => {
    vi.stubGlobal('matchMedia', () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { rerender } = render(<StreamingAssistantContent {...contentProps('首段', 'typing')} />);

    expect(screen.getByLabelText('助手回复')).toHaveTextContent('首段');
    rerender(<StreamingAssistantContent {...contentProps('完整正文', 'complete')} />);
    expect(screen.getByLabelText('助手回复')).toHaveTextContent('完整正文');
  });

  it('stream_done 先到时仍继续追赶权威正文，并在完成后清理 timer', async () => {
    vi.useFakeTimers();
    const { rerender } = render(<StreamingAssistantContent {...contentProps('你好', 'typing')} />);

    rerender(<StreamingAssistantContent {...contentProps('你好', 'complete')} />);
    expect(screen.getByLabelText('助手回复')).toBeEmptyDOMElement();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(48);
    });
    expect(screen.getByLabelText('助手回复')).toHaveTextContent('你好');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('取消后冻结已可见部分，不瞬间揭示尚未显示的全文', async () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <StreamingAssistantContent {...contentProps('完整正文', 'typing')} />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(24);
    });
    expect(screen.getByLabelText('助手回复')).toHaveTextContent(/^完$/);

    rerender(<StreamingAssistantContent {...contentProps('完整正文', 'frozen')} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(240);
    });
    expect(screen.getByLabelText('助手回复')).toHaveTextContent(/^完$/);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('助手 Markdown 外链以 noopener 和 noreferrer 安全打开', () => {
    vi.stubGlobal('matchMedia', () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    render(
      <StreamingAssistantContent
        {...contentProps('[安全链接](https://example.test)', 'complete')}
      />,
    );

    expect(screen.getByRole('link', { name: '安全链接' })).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('link', { name: '安全链接' })).toHaveAttribute(
      'rel',
      expect.stringContaining('noopener'),
    );
    expect(screen.getByRole('link', { name: '安全链接' })).toHaveAttribute(
      'rel',
      expect.stringContaining('noreferrer'),
    );
  });
});
