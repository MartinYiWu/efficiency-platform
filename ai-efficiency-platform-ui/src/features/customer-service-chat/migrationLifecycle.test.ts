import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, h } from 'vue';
import { afterEach, expect, it, vi } from 'vitest';
import { useCustomerServiceChat } from './useCustomerServiceChat';
import * as api from './api';
import { connectCustomerServiceRun } from './sseClient';
vi.mock('./api', () => ({
  listConversations: vi.fn(),
  listMessages: vi.fn(),
  getTimeline: vi.fn(),
  getRun: vi.fn(),
  createConversation: vi.fn(),
  submitMessage: vi.fn(),
  cancelRun: vi.fn(),
  deleteConversation: vi.fn(),
  renameConversation: vi.fn(),
}));
vi.mock('./sseClient', () => ({ connectCustomerServiceRun: vi.fn() }));
afterEach(() => vi.resetAllMocks());
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
};
function setup() {
  vi.mocked(api.listConversations).mockResolvedValue({ items: [] } as never);
  vi.mocked(api.getTimeline).mockResolvedValue(null as never);
  vi.mocked(api.createConversation).mockResolvedValue({ id: 'a' } as never);
  let chat!: ReturnType<typeof useCustomerServiceChat>;
  const wrapper = mount(
    defineComponent({
      setup() {
        chat = useCustomerServiceChat();
        return () => h('div');
      },
    }),
  );
  return { chat, wrapper };
}
it('does not submit a message after unmount while conversation creation is pending', async () => {
  const created = deferred<never>();
  const { chat, wrapper } = setup();
  vi.mocked(api.createConversation).mockReturnValue(created.promise);
  await new Promise((resolve) => setTimeout(resolve, 5));
  await flushPromises();
  const sent = chat.send('离开前输入');
  await flushPromises();
  expect(api.createConversation).toHaveBeenCalledOnce();
  wrapper.unmount();
  created.resolve({ id: 'late' } as never);
  await sent;
  expect(api.submitMessage).not.toHaveBeenCalled();
  expect(connectCustomerServiceRun).not.toHaveBeenCalled();
});
it('does not consume a submitted run arriving after unmount', async () => {
  const submitted = deferred<never>();
  const { chat, wrapper } = setup();
  vi.mocked(api.submitMessage).mockReturnValue(submitted.promise);
  await new Promise((resolve) => setTimeout(resolve, 5));
  await flushPromises();
  const sent = chat.send('离开前输入');
  await flushPromises();
  expect(api.submitMessage).toHaveBeenCalledOnce();
  wrapper.unmount();
  submitted.resolve({ runId: 'late-run' } as never);
  await sent;
  expect(connectCustomerServiceRun).not.toHaveBeenCalled();
});
it('does not overwrite selected conversation with the previous run final refresh', async () => {
  const persisted = deferred<never>();
  vi.mocked(api.submitMessage).mockResolvedValue({ runId: 'r1' } as never);
  vi.mocked(api.getRun).mockResolvedValue({ status: 'SUCCEEDED' } as never);
  vi.mocked(api.listMessages).mockImplementation((id) =>
    id === 'a'
      ? persisted.promise
      : Promise.resolve([
          { message: { id: 'b-message', role: 'USER', content: 'B会话' } },
        ] as never),
  );
  vi.mocked(connectCustomerServiceRun).mockImplementation(async function* () {
    yield { id: 1, event: 'run.completed', payload: { answerMode: 'COMPANY_KNOWLEDGE' } } as never;
  });
  const { chat, wrapper } = setup();
  await new Promise((resolve) => setTimeout(resolve, 5));
  await flushPromises();
  const sent = chat.send('A问题');
  await flushPromises();
  expect(chat.state.value.status).toBe('SUCCEEDED');
  await chat.selectConversation('b');
  persisted.resolve([{ message: { id: 'old', role: 'ASSISTANT', content: 'A旧回答' } }] as never);
  await sent;
  expect(chat.state.value.conversationId).toBe('b');
  expect(chat.state.value.messages[0]?.message.id).toBe('b-message');
  wrapper.unmount();
});
it('queues stop for the current submission and never cancels the previous run', async () => {
  const second = deferred<never>();
  let count = 0;
  vi.mocked(api.submitMessage).mockImplementation(() =>
    ++count === 1 ? Promise.resolve({ runId: 'r1' } as never) : second.promise,
  );
  vi.mocked(api.getRun).mockResolvedValue({ status: 'SUCCEEDED' } as never);
  vi.mocked(api.listMessages).mockRejectedValue(new Error('no refresh'));
  vi.mocked(api.cancelRun).mockResolvedValue({ status: 'CANCELLED' } as never);
  vi.mocked(connectCustomerServiceRun).mockImplementation(async function* (runId, options) {
    if (runId === 'r1') {
      yield {
        id: 1,
        event: 'run.completed',
        payload: { answerMode: 'COMPANY_KNOWLEDGE' },
      } as never;
      return;
    }
    if (!options?.signal?.aborted)
      await new Promise<void>((resolve) =>
        options?.signal?.addEventListener('abort', () => resolve(), { once: true }),
      );
  });
  const { chat, wrapper } = setup();
  await new Promise((resolve) => setTimeout(resolve, 5));
  await flushPromises();
  await chat.send('第一问');
  const sent = chat.send('第二问');
  await flushPromises();
  await chat.cancel();
  second.resolve({ runId: 'r2' } as never);
  await flushPromises();
  expect(api.cancelRun).not.toHaveBeenCalledWith('r1');
  expect(api.cancelRun).toHaveBeenCalledWith('r2');
  expect(chat.state.value.status).toBe('CANCELLED');
  wrapper.unmount();
  await sent;
});
