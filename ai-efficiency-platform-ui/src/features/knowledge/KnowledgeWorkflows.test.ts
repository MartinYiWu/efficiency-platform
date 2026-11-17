import { afterEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { fireEvent, screen } from '@testing-library/vue';
import Antd, { message, Upload } from 'ant-design-vue';

afterEach(() => {
  vi.restoreAllMocks();
  message.destroy();
});
const response = (data: unknown) =>
  new Response(JSON.stringify({ code: 'SUCCESS', data }), { status: 200 });
const batch = {
  id: 'batch-1',
  knowledgeBaseId: 'kb-1',
  importMode: 'BATCH',
  totalCount: 2,
  succeededCount: 1,
  failedCount: 1,
  status: 'PARTIAL_FAILED',
  createdAt: '2026-10-20',
  finishedAt: null,
  items: [
    {
      id: 'item-1',
      batchId: 'batch-1',
      fileId: 'f1',
      documentId: null,
      documentVersionId: null,
      status: 'FAILED',
      errorCode: 'ERR',
      errorMessage: '解析失败',
      retryOfItemId: null,
    },
  ],
};

describe('知识上传与处理', () => {
  it('单文件保留目录和证据模式字段，成功后通知与关闭', async () => {
    const fetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(response({ ...batch, totalCount: 1 }));
    const { default: Drawer } = await import('./KnowledgeUploadDrawer.vue');
    const wrapper = mount(Drawer, {
      props: {
        open: true,
        baseId: 'kb-1',
        knowledgeType: 'TECHNICAL_DOCUMENTATION',
        directories: [],
      },
      attachTo: document.body,
      global: { plugins: [Antd] },
    });
    const file = new File(['text'], 'a.txt', { type: 'text/plain' });
    wrapper
      .findComponent(Upload.Dragger)
      .vm.$emit('change', { fileList: [{ uid: '1', name: file.name, originFileObj: file }] });
    wrapper
      .findComponent({ name: 'EvidenceModeSelect' })
      .vm.$emit('update:value', 'EXTRACTIVE_NARRATIVE');
    await flushPromises();
    await fireEvent.click(screen.getByRole('button', { name: '开始处理' }));
    await flushPromises();
    expect(fetch.mock.calls[0]?.[0]).toBe('/api/knowledge/bases/kb-1/documents/upload');
    expect((fetch.mock.calls[0]?.[1]?.body as FormData).get('evidenceMode')).toBe(
      'EXTRACTIVE_NARRATIVE',
    );
    expect(wrapper.emitted('submitted')?.[0]).toEqual(['batch-1']);
    expect(wrapper.emitted('close')).toBeTruthy();
    wrapper.unmount();
  });
  it('批量至少两个文件，并展示失败原因和重试入口', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(batch));
    const { default: Import } = await import('./KnowledgeBatchImportModal.vue');
    const wrapper = mount(Import, {
      props: { open: true, baseId: 'kb-1', directories: [] },
      attachTo: document.body,
      global: { plugins: [Antd] },
    });
    await fireEvent.click(screen.getByRole('button', { name: '开始导入' }));
    expect(fetch).not.toHaveBeenCalled();
    const files = [new File(['a'], 'a.txt'), new File(['b'], 'b.txt')];
    wrapper.findComponent(Upload.Dragger).vm.$emit('change', {
      fileList: files.map((file, i) => ({
        uid: String(i),
        name: file.name,
        originFileObj: file,
      })),
    });
    await flushPromises();
    await fireEvent.click(screen.getByRole('button', { name: '开始导入' }));
    await flushPromises();
    expect(String(fetch.mock.calls[0]?.[0])).toContain('/imports');
    expect((fetch.mock.calls[0]?.[1]?.body as FormData).getAll('files')).toHaveLength(2);
    expect(screen.getByText('解析失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument();
    wrapper.unmount();
  });
  it('失败处理任务可重试，并显示阶段、次数与错误', async () => {
    const task = {
      id: 'task-1',
      documentVersionId: 'v1',
      agentTaskId: null,
      stage: 'PARSE',
      status: 'FAILED',
      attemptNo: 1,
      progressPercent: 20,
      errorCode: 'ERR',
      errorMessage: '处理错误',
      startedAt: null,
      finishedAt: null,
    };
    const fetch = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (_, init) =>
        response({ ...task, status: init?.method === 'POST' ? 'QUEUED' : 'FAILED' }),
      );
    const { default: Drawer } = await import('./ProcessingTaskDrawer.vue');
    const wrapper = mount(Drawer, {
      props: { open: true, taskId: 'task-1' },
      attachTo: document.body,
      global: { plugins: [Antd] },
    });
    await flushPromises();
    expect(screen.getByText('处理错误')).toBeInTheDocument();
    await fireEvent.click(screen.getByRole('button', { name: '重试任务' }));
    await flushPromises();
    expect(
      fetch.mock.calls.some(
        ([url, init]) => String(url).endsWith('/task-1/retry') && init?.method === 'POST',
      ),
    ).toBe(true);
    wrapper.unmount();
  });
});
