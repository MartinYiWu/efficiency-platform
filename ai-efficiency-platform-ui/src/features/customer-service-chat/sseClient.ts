import type { CustomerServiceSseEvent } from '../../entities/customer-service/model';
import { customerServiceSseSchema } from '../../entities/customer-service/schemas';

function parseBlock(block: string): CustomerServiceSseEvent | null {
  let id = 0;
  let event = '';
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('id:')) id = Number(line.slice(3).trim());
    else if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  }
  if (!Number.isInteger(id) || id < 1 || !event || !data.length) return null;
  try {
    return customerServiceSseSchema.parse({ id, event, payload: JSON.parse(data.join('\n')) });
  } catch {
    return null;
  }
}
export function parseCustomerServiceSse(chunk: string) {
  return chunk
    .split(/\r?\n\r?\n/)
    .map(parseBlock)
    .filter((item): item is CustomerServiceSseEvent => item !== null);
}
export async function* connectCustomerServiceRun(
  runId: string,
  options: {
    afterSequence?: number;
    signal?: AbortSignal;
    fetcher?: typeof fetch;
    maxReconnects?: number;
  } = {},
): AsyncGenerator<CustomerServiceSseEvent> {
  const fetcher = options.fetcher ?? fetch;
  let cursor = options.afterSequence ?? 0;
  let reconnects = 0;
  const seen = new Set<number>();
  while (!options.signal?.aborted && reconnects <= (options.maxReconnects ?? 3)) {
    const response = await fetcher(
      `/api/customer-service/runs/${encodeURIComponent(runId)}/events?afterSequence=${cursor}`,
      {
        headers: {
          Accept: 'text/event-stream',
          ...(cursor ? { 'Last-Event-ID': String(cursor) } : {}),
        },
        signal: options.signal,
      },
    );
    if (!response.ok || !response.body) throw new Error(`SSE 请求失败（${response.status}）`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (true) {
        const result = await reader.read();
        if (result.done) break;
        buffer += decoder.decode(result.value, { stream: true });
        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() ?? '';
        for (const part of parts) {
          const value = parseBlock(part);
          if (!value || value.id <= cursor || seen.has(value.id)) {
            if (value)
              console.warn('customer_service_sse_event_ignored', {
                runId,
                sequence: value.id,
                cursor,
              });
            continue;
          }
          seen.add(value.id);
          cursor = value.id;
          yield value;
          if (['run.completed', 'run.failed', 'run.cancelled'].includes(value.event)) return;
        }
      }
    } finally {
      reader.releaseLock();
    }
    reconnects += 1;
  }
  if (!options.signal?.aborted) throw new Error('SSE_RECONNECT_EXHAUSTED');
}
