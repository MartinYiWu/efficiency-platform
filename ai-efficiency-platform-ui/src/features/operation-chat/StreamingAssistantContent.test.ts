import { render, screen } from '@testing-library/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import StreamingAssistantContent from './StreamingAssistantContent.vue';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe('Vue 权威正文逐字展示', () => {
  it('按Unicode字素显示，停止后冻结当前可见部分', async () => {
    vi.useFakeTimers();
    const { rerender } = render(StreamingAssistantContent, {
      props: { content: '你👨‍👩‍👧‍👦好', mode: 'typing' },
    });
    await vi.advanceTimersByTimeAsync(48);
    expect(screen.getByLabelText('助手回复')).toHaveTextContent('你👨‍👩‍👧‍👦');
    await rerender({ content: '你👨‍👩‍👧‍👦好', mode: 'frozen' });
    await vi.advanceTimersByTimeAsync(240);
    expect(screen.getByLabelText('助手回复')).toHaveTextContent(/^你👨‍👩‍👧‍👦$/);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('终态先到仍显示剩余正文，完成后清理timer', async () => {
    vi.useFakeTimers();
    const { rerender } = render(StreamingAssistantContent, {
      props: { content: '你好', mode: 'typing' },
    });
    await rerender({ mode: 'complete' });
    await vi.advanceTimersByTimeAsync(48);
    expect(screen.getByLabelText('助手回复')).toHaveTextContent('你好');
    expect(vi.getTimerCount()).toBe(0);
  });
  it('恢复的历史消息初始完整展示，减少动态效果时直接更新正文', async () => {
    const { unmount } = render(StreamingAssistantContent, {
      props: { content: '历史', mode: 'frozen' },
    });
    expect(screen.getByLabelText('助手回复')).toHaveTextContent('历史');
    unmount();
    vi.stubGlobal('matchMedia', () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { rerender } = render(StreamingAssistantContent, {
      props: { content: '首段', mode: 'typing' },
    });
    expect(screen.getByLabelText('助手回复')).toHaveTextContent('首段');
    await rerender({ content: '完整正文', mode: 'complete' });
    expect(screen.getByLabelText('助手回复')).toHaveTextContent('完整正文');
  });
});
