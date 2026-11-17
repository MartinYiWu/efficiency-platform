import { waitFor } from '@testing-library/vue';
import { mountComposable as renderHook, flushUpdate as act } from '../../test/composable';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useCustomerServiceChat } from './useCustomerServiceChat';

const fixtures = vi.hoisted(() => ({
  terminal: 'run.failed' as 'run.failed' | 'run.cancelled',
  listMessages: vi.fn(),
  hold: false,
  cancelRun: vi.fn(),
}));
vi.mock('./api', () => ({
  listConversations: vi.fn().mockResolvedValue({ items: [] }),
  createConversation: vi.fn().mockResolvedValue({ id: 'c' }),
  submitMessage: vi.fn().mockResolvedValue({ runId: 'r' }),
  getRun: vi.fn().mockResolvedValue({ status: 'FAILED' }),
  listMessages: fixtures.listMessages,
  getTimeline: vi.fn(),
  cancelRun: fixtures.cancelRun,
  deleteConversation: vi.fn(),
  renameConversation: vi.fn(),
}));
vi.mock('./sseClient', () => ({
  connectCustomerServiceRun: async function* (_runId: string, options: { signal: AbortSignal }) {
    if (fixtures.hold) {
      await new Promise<void>((resolve) =>
        options.signal.addEventListener('abort', () => resolve(), { once: true }),
      );
      return;
    }
    yield fixtures.terminal === 'run.failed'
      ? {
          id: 1,
          event: 'run.failed',
          payload: { errorCode: 'RUN_EXHAUSTED', errorMessage: '本次问答预算已耗尽' },
        }
      : { id: 1, event: 'run.cancelled', payload: {} };
  },
}));

beforeEach(() => {
  fixtures.hold = false;
  fixtures.cancelRun.mockResolvedValue({ status: 'CANCELLED' });
  fixtures.listMessages.mockRejectedValue(new Error('synthetic refresh unavailable'));
});

describe('paid budget terminal handling', () => {
  it('keeps receiving the actual terminal when cancellation is not confirmed by Java', async () => {
    fixtures.hold = true;
    fixtures.cancelRun.mockResolvedValue({ status: 'RUNNING' });
    const { result, unmount } = renderHook(() => useCustomerServiceChat());
    let sent: Promise<void>;
    act(() => {
      sent = result.current.send('synthetic question');
    });
    await waitFor(() => expect(result.current.state.status).toBe('STREAMING'));
    await act(async () => result.current.cancel());
    expect(result.current.state.status).toBe('STREAMING');
    expect(
      result.current.state.messages.find((item) => item.message.role === 'ASSISTANT')?.message
        .status,
    ).toBe('STREAMING');
    unmount();
    await sent!;
  });
  it('marks the message cancelled when the user stops before a terminal event arrives', async () => {
    fixtures.hold = true;
    const { result } = renderHook(() => useCustomerServiceChat());
    let sent: Promise<void>;
    act(() => {
      sent = result.current.send('synthetic question');
    });
    await waitFor(() => expect(result.current.state.status).toBe('STREAMING'));
    await act(async () => {
      await result.current.cancel();
      await sent;
    });
    expect(result.current.state.status).toBe('CANCELLED');
    expect(
      result.current.state.messages.find((item) => item.message.role === 'ASSISTANT')?.message
        .status,
    ).toBe('CANCELLED');
  });
  it.each([
    ['run.failed', 'FAILED'],
    ['run.cancelled', 'CANCELLED'],
  ] as const)('keeps %s terminal even when persisted refresh fails', async (event, status) => {
    fixtures.terminal = event;
    const { result } = renderHook(() => useCustomerServiceChat());
    await new Promise((resolve) => setTimeout(resolve, 5));
    await act(async () => result.current.send('synthetic question'));
    await waitFor(() => expect(result.current.state.status).toBe(status));
    const answer = result.current.state.messages.find((item) => item.message.role === 'ASSISTANT');
    expect(answer?.message.status).toBe(status);
    expect(answer?.message.answerMode).toBeNull();
    expect(result.current.busy).toBe(false);
    if (status === 'FAILED') expect(result.current.state.error).toContain('RUN_EXHAUSTED');
  });
});
