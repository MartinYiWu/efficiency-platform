import { act, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import type { Conversation } from '../../entities/customer-service/model';
import { CustomerServiceChatPage } from '../../pages/customer-service/CustomerServiceChatPage';
import { CustomerServiceApiError, renameConversation } from './api';
import { useCustomerServiceChat } from './useCustomerServiceChat';

const original: Conversation = {
  id: 'conversation-1', tenantId: 'dev', userId: 'user-1', title: '原始名称', status: 'ACTIVE',
  lastMessageAt: null, createdAt: '2026-10-27T00:00:00Z', updatedAt: '2026-10-27T00:00:00Z',
};
const success = (data: unknown) => new Response(JSON.stringify({ code: 'SUCCESS', data }));
const page = (title = original.title) => ({ items: [{ ...original, title }], page: 1, pageSize: 20, total: 1 });

beforeAll(() => Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() }));
afterAll(() => Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo'));

function setupChat() {
  let controller: ReadableStreamDefaultController<Uint8Array> | undefined;
  const signal = { current: undefined as AbortSignal | null | undefined };
  const fetcher = vi.fn(async (path: string, init?: RequestInit): Promise<Response> => {
    if (path === '/api/customer-service/conversations?') return success(page());
    if (path.endsWith('/messages') && init?.method === 'POST')
      return success({ conversationId: original.id, runId: 'run-1', status: 'RUNNING', agentReleaseId: 'release-1' });
    if (path.endsWith('/messages')) return success([]);
    if (path.includes('/events')) {
      signal.current = init?.signal;
      return new Response(new ReadableStream<Uint8Array>({ start(value) { controller = value; } }));
    }
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal('fetch', fetcher);
  return {
    fetcher, signal,
    emit: (id: number, stage = 'conversation_title') => controller?.enqueue(new TextEncoder().encode(
      `id: ${id}\nevent: run.progress\ndata: ${JSON.stringify({ stage, summary: '会话标题已更新' })}\n\n`,
    )),
    complete: () => controller?.enqueue(new TextEncoder().encode(
      'id: 3\nevent: run.completed\ndata: {"answerMode":"GENERAL_ADVICE"}\n\n',
    )),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('conversation title API', () => {
  it('patches the title and returns the validated server conversation', async () => {
    const updated = { ...original, title: '服务端标题' };
    const fetcher = vi.fn().mockResolvedValue(success(updated));
    vi.stubGlobal('fetch', fetcher);

    expect(await renameConversation(original.id, '请求标题')).toEqual(updated);
    expect(fetcher).toHaveBeenCalledWith(`/api/customer-service/conversations/${original.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: '请求标题' }),
    });
  });

  it('rejects malformed conversation responses rather than treating a save as successful', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(success({ ...original, unexpected: true })));
    await expect(renameConversation(original.id, '请求标题')).rejects.toMatchObject({ code: 'CLIENT_CONTRACT_MISMATCH' });
  });

  it('preserves the duplicate title business error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 'CUSTOMER_SERVICE_CONVERSATION_TITLE_DUPLICATE', message: '会话名称已存在，请使用其他标题',
    }), { status: 409 })));
    await expect(renameConversation(original.id, '重复名称')).rejects.toEqual(
      new CustomerServiceApiError('会话名称已存在，请使用其他标题', 'CUSTOMER_SERVICE_CONVERSATION_TITLE_DUPLICATE'),
    );
  });
});

describe('conversation title interactions', () => {
  it('trims a desktop rename and shows the title returned by the server', async () => {
    const user = userEvent.setup();
    const { fetcher } = setupChat();
    render(<CustomerServiceChatPage />);
    await user.click(await screen.findByRole('button', { name: '重命名会话：原始名称' }));
    const dialog = screen.getByRole('dialog', { name: '重命名会话' });
    const input = within(dialog).getByRole('textbox', { name: '会话名称' });
    expect(input).toHaveAttribute('maxlength', '80');
    await user.clear(input);
    await user.type(input, '   ');
    await user.click(within(dialog).getByRole('button', { name: /保\s*存/ }));
    expect(await within(dialog).findByText('请输入会话名称')).toBeInTheDocument();
    expect(fetcher.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(false);
    await user.clear(input);
    await user.type(input, '  用户标题  ');
    fetcher.mockResolvedValueOnce(success({ ...original, title: '服务端标题' }));
    await user.click(within(dialog).getByRole('button', { name: /保\s*存/ }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '重命名会话' })).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: '服务端标题' })).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith(`/api/customer-service/conversations/${original.id}`,
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ title: '用户标题' }) }));
  });

  it('keeps a duplicate name and the original title in the mobile history entry', async () => {
    const user = userEvent.setup();
    const { fetcher } = setupChat();
    render(<CustomerServiceChatPage />);
    await screen.findByRole('button', { name: '重命名会话：原始名称' });
    await user.click(screen.getByRole('button', { name: /历史会话$/ }));
    const mobile = await screen.findByRole('navigation', { name: '移动端历史会话' });
    await user.click(within(mobile).getByRole('button', { name: '重命名会话：原始名称' }));
    // Ant Design assigns both open dialogs the same title id in its test environment.
    const dialog = screen.getAllByRole('dialog').find((item) => within(item).queryByText('重命名会话'));
    if (!dialog) throw new Error('重命名弹窗未打开');
    const input = within(dialog).getByRole('textbox', { name: '会话名称' });
    await user.clear(input);
    await user.type(input, '重复名称');
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({
      code: 'CUSTOMER_SERVICE_CONVERSATION_TITLE_DUPLICATE', message: '会话名称已存在，请使用其他标题',
    }), { status: 409 }));
    await user.click(within(dialog).getByRole('button', { name: /保\s*存/ }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('会话名称已存在，请使用其他标题');
    expect(input).toHaveValue('重复名称');
    expect(within(mobile).getByRole('button', { name: '原始名称' })).toBeInTheDocument();
  });

  it('allows renaming while an answer streams without cancelling it', async () => {
    const user = userEvent.setup();
    const { fetcher, signal } = setupChat();
    render(<CustomerServiceChatPage />);
    await screen.findByRole('button', { name: '重命名会话：原始名称' });
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(expect.stringContaining('/messages'), undefined));
    await user.type(screen.getByRole('textbox', { name: '输入问题' }), '咨询问题');
    await user.click(screen.getByRole('button', { name: /发送$/ }));
    await screen.findByRole('button', { name: /停止$/ });
    const rename = screen.getByRole('button', { name: '重命名会话：原始名称' });
    expect(rename).toBeEnabled();
    await user.click(rename);
    const dialog = screen.getByRole('dialog', { name: '重命名会话' });
    fireEvent.change(within(dialog).getByRole('textbox', { name: '会话名称' }), { target: { value: '回答中改名' } });
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({
      code: 'CUSTOMER_SERVICE_CONVERSATION_TITLE_DUPLICATE', message: '会话名称已存在，请使用其他标题',
    }), { status: 409 }));
    await user.click(within(dialog).getByRole('button', { name: /保\s*存/ }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('会话名称已存在');
    expect(screen.getByRole('button', { name: /停止$/ })).toBeInTheDocument();
    expect(signal.current?.aborted).toBe(false);
    fetcher.mockResolvedValueOnce(success({ ...original, title: '回答中改名' }));
    await user.click(within(dialog).getByRole('button', { name: /保\s*存/ }));
    expect(await screen.findByRole('button', { name: '重命名会话：回答中改名' })).toBeEnabled();
    expect(signal.current?.aborted).toBe(false);
    expect(screen.getByRole('button', { name: /停止$/ })).toBeInTheDocument();
  });
});

describe('title progress and stale conversation lists', () => {
  it('does not change a completed answer to failed when its final list refresh fails', async () => {
    const { fetcher, complete } = setupChat();
    const { result } = renderHook(() => useCustomerServiceChat());
    await waitFor(() => expect(result.current.state.conversationId).toBe(original.id));
    let sending: Promise<void> | undefined;
    act(() => { sending = result.current.send('咨询问题'); });
    await waitFor(() => expect(result.current.state.status).toBe('STREAMING'));
    fetcher.mockResolvedValueOnce(new Response('{}', { status: 503 }))
      .mockResolvedValueOnce(success([]))
      .mockRejectedValueOnce(new Error('列表刷新失败'));
    await act(async () => { complete(); await sending; });
    expect(result.current.state.status).toBe('SUCCEEDED');
    expect(result.current.state.error).toBeUndefined();
  });

  it('refreshes titles on a phase-less title event and survives a refresh failure', async () => {
    const { fetcher, emit } = setupChat();
    const { result } = renderHook(() => useCustomerServiceChat());
    await waitFor(() => expect(result.current.state.conversationId).toBe(original.id));
    act(() => { void result.current.send('咨询问题'); });
    await waitFor(() => expect(result.current.state.status).toBe('STREAMING'));
    fetcher.mockResolvedValueOnce(success(page('自动标题')));
    act(() => emit(1));
    await waitFor(() => expect(result.current.state.conversations[0].title).toBe('自动标题'));
    fetcher.mockRejectedValueOnce(new Error('列表刷新失败'));
    act(() => emit(2));
    await waitFor(() => expect(result.current.state.sequence).toBe(2));
    expect(result.current.state.status).toBe('STREAMING');
    expect(result.current.state.error).toBeUndefined();
    expect(result.current.state.progressByRun['run-1']).toBeUndefined();
  });

  it('does not let an older delayed title refresh overwrite a saved manual name', async () => {
    const { fetcher, emit, signal } = setupChat();
    const { result } = renderHook(() => useCustomerServiceChat());
    await waitFor(() => expect(result.current.state.conversationId).toBe(original.id));
    act(() => { void result.current.send('咨询问题'); });
    await waitFor(() => expect(result.current.state.status).toBe('STREAMING'));
    let resolveList: ((response: Response) => void) | undefined;
    fetcher.mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveList = resolve; }));
    act(() => emit(1));
    await waitFor(() => expect(resolveList).toBeDefined());
    fetcher.mockResolvedValueOnce(success({ ...original, title: '手工标题' }));
    await act(async () => { await result.current.renameConversation(original.id, '手工标题'); });
    await act(async () => { resolveList?.(success(page('过期自动标题'))); });
    expect(result.current.state.conversations[0].title).toBe('手工标题');
    expect(result.current.state.conversationId).toBe(original.id);
    expect(result.current.state.status).toBe('STREAMING');
    expect(signal.current?.aborted).toBe(false);
  });
});
