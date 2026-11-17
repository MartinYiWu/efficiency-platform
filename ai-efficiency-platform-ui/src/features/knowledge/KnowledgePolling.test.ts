import { afterEach, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import Antd from 'ant-design-vue';
import Batch from './KnowledgeBatchImportModal.vue';
import Task from './ProcessingTaskDrawer.vue';
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});
const response = (data: unknown) =>
  new Response(JSON.stringify({ code: 'SUCCESS', data }), { status: 200 });
it('批量导入每三秒刷新、终态停止并通知父页', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  const batch = {
    id: 'b1',
    knowledgeBaseId: 'kb',
    importMode: 'BATCH',
    totalCount: 2,
    succeededCount: 0,
    failedCount: 0,
    status: 'RUNNING',
    createdAt: '',
    finishedAt: null,
    items: [],
  };
  const fetch = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(response(batch))
    .mockResolvedValue(response({ ...batch, status: 'SUCCEEDED', succeededCount: 2 }));
  const wrapper = mount(Batch, {
    props: { open: true, baseId: 'kb', directories: [], initialBatchId: 'b1' },
    global: { plugins: [Antd] },
  });
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(3000);
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(wrapper.emitted('changed')).toBeTruthy();
  await vi.advanceTimersByTimeAsync(6000);
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});
it('处理任务关闭后停止轮询', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
  const task = {
    id: 't1',
    documentVersionId: 'v1',
    agentTaskId: null,
    stage: 'PARSE',
    status: 'RUNNING',
    attemptNo: 1,
    progressPercent: 20,
    errorCode: null,
    errorMessage: null,
    startedAt: null,
    finishedAt: null,
  };
  const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => response(task));
  const wrapper = mount(Task, { props: { open: true, taskId: 't1' }, global: { plugins: [Antd] } });
  await flushPromises();
  await vi.advanceTimersByTimeAsync(3000);
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(2);
  await wrapper.setProps({ open: false });
  await vi.advanceTimersByTimeAsync(6000);
  await flushPromises();
  expect(fetch).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});
