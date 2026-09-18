import type { StreamEventName, StreamEventV1 } from './types';

export interface SseClientOptions {
  baseUrl: string;
  tenantId: string;
  lastEventId?: string | null;
  signal?: AbortSignal;
  fetcher?: typeof fetch;
  maxReconnects?: number;
}
const streamNames = new Set<StreamEventName>([
  'run_started',
  'intent_detected',
  'clarification_required',
  'phase_started',
  'research_started',
  'research_completed',
  'content_generation_started',
  'content_generation_completed',
  'quality_checked',
  'assistant_started',
  'assistant_delta',
  'deliverable',
  'usage_update',
  'stream_error',
  'stream_done',
]);
const isAborted = (signal?: AbortSignal) => signal?.aborted === true;

function parseEventBlock(block: string): StreamEventV1 | null {
  let transportId = '';
  let transportEvent = '';
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('id:')) transportId = line.slice(3).trim();
    else if (line.startsWith('event:')) transportEvent = line.slice(6).trim();
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  }
  if (!transportId || !transportEvent || data.length === 0) return null;
  try {
    const parsed: unknown = JSON.parse(data.join('\n'));
    if (!parsed || typeof parsed !== 'object') return null;
    const value = parsed as Record<string, unknown>;
    if (
      value.contract_version !== 'run.stream.event/1' ||
      typeof value.event !== 'string' ||
      !streamNames.has(value.event as StreamEventName) ||
      typeof value.run_id !== 'string' ||
      typeof value.sequence !== 'number' ||
      !Number.isInteger(value.sequence) ||
      value.sequence < 1 ||
      !value.payload ||
      typeof value.payload !== 'object'
    )
      return null;
    // id/event 是 SSE 传输元数据；业务事件以已校验的 data envelope 为准。
    return {
      id: String(value.sequence),
      event: value.event as StreamEventName,
      contract_version: 'run.stream.event/1',
      run_id: value.run_id,
      sequence: value.sequence,
      payload: value.payload as Record<string, unknown>,
    };
  } catch {
    return null;
  }
}

export function parseSseChunk(chunk: string): StreamEventV1[] {
  return chunk
    .split(/\r?\n\r?\n/)
    .map(parseEventBlock)
    .filter((event): event is StreamEventV1 => event !== null);
}

export async function* connectRunStream(
  runId: string,
  options: SseClientOptions,
): AsyncGenerator<StreamEventV1> {
  const fetcher = options.fetcher ?? fetch;
  let cursor = options.lastEventId ? Number(options.lastEventId) : 0;
  let reconnects = 0;
  let completed = false;
  const seen = new Set<number>();
  while (!completed && reconnects <= (options.maxReconnects ?? 3)) {
    if (isAborted(options.signal)) return;
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
      'X-Tenant-ID': options.tenantId,
    };
    if (cursor > 0) headers['Last-Event-ID'] = String(cursor);
    try {
      const response = await fetcher(
        `${options.baseUrl.replace(/\/$/, '')}/v1/runs/${encodeURIComponent(runId)}/events`,
        { method: 'GET', headers, signal: options.signal },
      );
      if (!response.ok) throw new Error(`SSE 请求失败（${response.status}）`);
      if (!response.body) throw new Error('SSE 响应缺少可读流');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let reachedEof = false;
      try {
        while (true) {
          const result = await reader.read();
          if (result.done) {
            reachedEof = true;
            break;
          }
          buffer += decoder.decode(result.value, { stream: true });
          const parts = buffer.split(/\r?\n\r?\n/);
          buffer = parts.pop() ?? '';
          for (const part of parts) {
            const event = parseEventBlock(part);
            if (
              !event ||
              event.run_id !== runId ||
              event.sequence <= cursor ||
              seen.has(event.sequence)
            )
              continue;
            seen.add(event.sequence);
            cursor = event.sequence;
            yield event;
            if (event.event === 'stream_done') {
              completed = true;
              return;
            }
          }
        }
        buffer += decoder.decode();
        const event = parseEventBlock(buffer);
        if (
          event &&
          event.run_id === runId &&
          event.sequence > cursor &&
          !seen.has(event.sequence)
        ) {
          seen.add(event.sequence);
          cursor = event.sequence;
          yield event;
          if (event.event === 'stream_done') {
            completed = true;
            return;
          }
        }
      } finally {
        if (!reachedEof) await reader.cancel().catch(() => undefined);
        reader.releaseLock();
      }
      if (!completed) reconnects += 1;
    } catch (error) {
      if (isAborted(options.signal)) return;
      if (reconnects >= (options.maxReconnects ?? 3))
        throw new Error('SSE_RECONNECT_EXHAUSTED', { cause: error });
      reconnects += 1;
    }
  }
  if (!completed && !isAborted(options.signal)) throw new Error('SSE_RECONNECT_EXHAUSTED');
}
