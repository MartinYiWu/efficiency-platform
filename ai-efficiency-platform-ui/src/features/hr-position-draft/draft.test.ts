import { expect, it, vi, afterEach } from 'vitest';
import { loadPositionDraft, savePositionDraft } from './model';
afterEach(() => vi.unstubAllGlobals());
it('草稿保存使用服务端版本并保留409冲突，不假报保存成功', async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        code: 'HR_VERSION_CONFLICT',
        message: '草稿已被其他人修改',
        traceId: 'draft-1',
      }),
      { status: 409 },
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  await expect(
    savePositionDraft({
      positionId: 'p1',
      name: '岗位',
      family: 'TECHNOLOGY',
      departmentId: 'd1',
      level: 'P6',
      jdText: '',
      lastStep: 'BASIC',
      scoring: null,
      hardConditions: [],
      criteria: [],
      version: 3,
    }),
  ).rejects.toThrow('草稿已被其他人修改');
  expect(JSON.parse(fetcher.mock.calls[0][1].body).version).toBe(3);
  expect(fetcher.mock.calls[0][1].method).toBe('PUT');
});
it('恢复草稿仅GET指定岗位，不创建新岗位', async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ code: 'HR_NOT_FOUND', message: '岗位不存在' }), {
      status: 404,
    }),
  );
  vi.stubGlobal('fetch', fetcher);
  await expect(loadPositionDraft('p1')).rejects.toThrow('岗位不存在');
  expect(fetcher.mock.calls[0][0]).toBe('/api/hr/positions/p1/draft');
});
