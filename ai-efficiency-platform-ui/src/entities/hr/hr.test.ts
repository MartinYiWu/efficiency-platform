import { afterEach, expect, it, vi } from 'vitest';
import { hrRequest, factsSchema } from './index';

afterEach(() => vi.unstubAllGlobals());
it('拒绝业务失败且保留traceId，不将失败当作空数据', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ code: 'HR_PERMISSION_DENIED', message: '无权访问', traceId: 't-1' }),
          { status: 403 },
        ),
      ),
  );
  await expect(hrRequest('/candidates/c/facts', factsSchema)).rejects.toThrow('无权访问 · t-1');
});
it('拒绝不完整的事实响应，不能混入演示数据', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ code: 'SUCCESS', data: { candidateId: 'c' } })),
      ),
  );
  await expect(hrRequest('/candidates/c/facts', factsSchema)).rejects.toThrow(
    '服务响应格式不符合约定',
  );
});
