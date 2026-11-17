import { defineComponent, h, nextTick } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useCustomerServiceChat } from './useCustomerServiceChat';
import * as api from './api';

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
vi.mock('./sseClient', () => ({ connectCustomerServiceRun: vi.fn(async function* () {}) }));
afterEach(() => {
  vi.clearAllMocks();
});

describe('Vue 客服状态', () => {
  it('恢复列表；拒绝预算时保留错误且不重复提交', async () => {
    vi.mocked(api.listConversations).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    });
    vi.mocked(api.createConversation).mockResolvedValue({
      id: 'c1',
      title: '新会话',
      tenantId: 'dev',
      userId: 'u1',
      status: 'ACTIVE',
      lastMessageAt: null,
      createdAt: '2026-11-03T00:00:00Z',
      updatedAt: '2026-11-03T00:00:00Z',
    });
    vi.mocked(api.submitMessage).mockRejectedValue(new Error('付费预算不可用'));
    let chat!: ReturnType<typeof useCustomerServiceChat>;
    const wrapper = mount(
      defineComponent({
        setup() {
          chat = useCustomerServiceChat();
          return () => h('div', chat.state.value.status);
        },
      }),
    );
    await new Promise((resolve) => setTimeout(resolve, 10));
    await flushPromises();
    await chat.send('问题');
    await nextTick();
    expect(chat.state.value.status).toBe('FAILED');
    expect(chat.state.value.error).toBe('付费预算不可用');
    expect(chat.busy.value).toBe(false);
    expect(api.submitMessage).toHaveBeenCalledTimes(1);
    expect(chat.state.value.messages.some((item) => item.message.role === 'ASSISTANT')).toBe(false);
    wrapper.unmount();
  });
});
