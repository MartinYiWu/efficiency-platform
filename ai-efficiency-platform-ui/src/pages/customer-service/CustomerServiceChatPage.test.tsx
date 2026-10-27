import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MessageView } from '../../entities/customer-service/model';
import type { CustomerServiceChatState } from '../../features/customer-service-chat/useCustomerServiceChat';
import { CustomerServiceChatPage } from './CustomerServiceChatPage';

const chat = vi.hoisted(() => ({
  state: {
    conversations: [],
    messages: [],
    status: 'IDLE',
    sequence: 0,
    progressByRun: {},
  } as CustomerServiceChatState,
  send: vi.fn(),
}));
vi.mock('../../features/customer-service-chat/useCustomerServiceChat', () => ({
  useCustomerServiceChat: () => ({
    ...chat,
    busy: false,
    cancel: vi.fn(),
    selectConversation: vi.fn(),
    newConversation: vi.fn(),
    removeConversation: vi.fn(),
    renameConversation: vi.fn(),
  }),
}));

const answer = (content: string): MessageView => ({
  message: {
    id: 'local-answer',
    conversationId: 'c',
    tenantId: 'dev',
    role: 'ASSISTANT',
    content,
    status: 'STREAMING',
    answerMode: 'GENERAL_ADVICE',
    runId: 'r',
    clientRequestId: null,
    createdAt: '2026-10-27T00:00:00Z',
  },
  citations: [],
});

beforeAll(() =>
  Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
    configurable: true,
    writable: true,
    value: vi.fn(),
  }),
);

beforeEach(() => {
  chat.state = {
    conversations: [],
    conversationId: 'c',
    messages: [answer('第一段')],
    status: 'IDLE',
    sequence: 0,
    progressByRun: {},
  };
  chat.send.mockReset();
});

describe('customer service message scrolling', () => {
  it('keeps a reader position during output and offers a return to latest', () => {
    const { rerender } = render(<CustomerServiceChatPage />);
    const log = screen.getByRole('log');
    Object.defineProperties(log, {
      scrollHeight: { configurable: true, value: 1200 },
      clientHeight: { configurable: true, value: 300 },
      scrollTop: { configurable: true, writable: true, value: 200 },
    });
    const scrollTo = vi.fn();
    log.scrollTo = scrollTo;
    fireEvent.scroll(log);
    chat.state = { ...chat.state, messages: [answer('第一段\n\n第二段')] };
    rerender(<CustomerServiceChatPage />);
    expect(scrollTo).not.toHaveBeenCalled();
    expect(log.scrollTop).toBe(200);
    fireEvent.click(screen.getByRole('button', { name: '回到最新消息' }));
    expect(scrollTo).toHaveBeenCalledWith({ top: 1200, behavior: 'auto' });
    expect(screen.queryByRole('button', { name: '回到最新消息' })).not.toBeInTheDocument();
    scrollTo.mockClear();
    chat.state = { ...chat.state, messages: [answer('继续输出')] };
    rerender(<CustomerServiceChatPage />);
    expect(scrollTo).toHaveBeenCalledWith({ top: 1200, behavior: 'auto' });
  });

  it('resumes following when the user sends from an older reading position', () => {
    const { rerender } = render(<CustomerServiceChatPage />);
    const log = screen.getByRole('log');
    Object.defineProperties(log, {
      scrollHeight: { configurable: true, value: 1200 },
      clientHeight: { configurable: true, value: 300 },
      scrollTop: { configurable: true, writable: true, value: 100 },
    });
    const scrollTo = vi.fn();
    log.scrollTo = scrollTo;
    fireEvent.scroll(log);
    fireEvent.change(screen.getByRole('textbox', { name: '输入问题' }), {
      target: { value: '新问题' },
    });
    fireEvent.click(screen.getByRole('button', { name: /发送$/ }));
    expect(chat.send).toHaveBeenCalledWith('新问题');
    chat.state = { ...chat.state, messages: [answer('新问题的回答')] };
    rerender(<CustomerServiceChatPage />);
    expect(scrollTo).toHaveBeenCalledWith({ top: 1200, behavior: 'auto' });
  });

  it('follows a selected conversation and follows output while already at the bottom', () => {
    const { rerender } = render(<CustomerServiceChatPage />);
    const log = screen.getByRole('log');
    Object.defineProperties(log, {
      scrollHeight: { configurable: true, value: 1200 },
      clientHeight: { configurable: true, value: 300 },
      scrollTop: { configurable: true, writable: true, value: 900 },
    });
    const scrollTo = vi.fn();
    log.scrollTo = scrollTo;
    fireEvent.scroll(log);
    chat.state = { ...chat.state, messages: [answer('追加输出')] };
    rerender(<CustomerServiceChatPage />);
    expect(scrollTo).toHaveBeenCalledWith({ top: 1200, behavior: 'auto' });
    log.scrollTop = 100;
    fireEvent.scroll(log);
    scrollTo.mockClear();
    chat.state = { ...chat.state, conversationId: 'other', messages: [answer('另一会话')] };
    rerender(<CustomerServiceChatPage />);
    expect(scrollTo).toHaveBeenCalledWith({ top: 1200, behavior: 'auto' });
    expect(screen.queryByRole('button', { name: '回到最新消息' })).not.toBeInTheDocument();
  });
});
