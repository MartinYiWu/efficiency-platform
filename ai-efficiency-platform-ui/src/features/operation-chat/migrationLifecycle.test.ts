import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, h } from 'vue';
import { afterEach, expect, it, vi } from 'vitest';
import { useOperationChat } from './useOperationChat';
const success = (data: unknown) =>
  new Response(JSON.stringify({ code: 'SUCCESS', data }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
afterEach(() => {
  window.history.replaceState(null, '', '/');
  vi.restoreAllMocks();
});
it('clears restore busy state when a restored active run is stopped', async () => {
  window.history.replaceState(null, '', '/?conversationId=c');
  const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const target = String(input);
    if (target.endsWith('/conversations/c'))
      return Promise.resolve(success({ conversationId: 'c' }));
    if (target.endsWith('/messages'))
      return Promise.resolve(
        success({
          messages: [
            { messageId: 'm', role: 'user', content: '问题', runId: 'r', createdAt: '2026-10-20' },
          ],
        }),
      );
    if (target.endsWith('/artifacts')) return Promise.resolve(success({ artifacts: [] }));
    if (target.endsWith('/runs/r'))
      return Promise.resolve(success({ runId: 'r', status: 'running', lastEventSequence: 1 }));
    if (target.endsWith('/cancel'))
      return Promise.resolve(success({ runId: 'r', status: 'cancelled' }));
    if (target.includes('/events?'))
      return Promise.resolve(
        new Response(
          new ReadableStream({
            start(controller) {
              init?.signal?.addEventListener('abort', () => controller.close(), { once: true });
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        ),
      );
    throw new Error(target);
  });
  let chat!: ReturnType<typeof useOperationChat>;
  const wrapper = mount(
    defineComponent({
      setup() {
        chat = useOperationChat({ baseUrl: 'http://offline.test', fetcher });
        return () => h('div');
      },
    }),
  );
  await flushPromises();
  expect(chat.state.value.runId).toBe('r');
  await chat.cancel();
  await flushPromises();
  expect(chat.state.value.status).toBe('cancelled');
  expect(chat.isRestoring.value).toBe(false);
  expect(chat.isBusy.value).toBe(false);
  wrapper.unmount();
});
