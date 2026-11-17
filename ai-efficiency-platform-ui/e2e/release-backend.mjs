import { createServer } from 'node:http';
import { mkdir, writeFile, cp } from 'node:fs/promises';
import { resolve } from 'node:path';

const sharedAssets = resolve('../.local-acceptance/ui-delivery-20261103/probe-shared-assets');
await mkdir(sharedAssets, { recursive: true });
await cp(resolve('dist/assets'), sharedAssets, { recursive: true });
await writeFile(
  resolve(sharedAssets, 'previous-release-chunk.js'),
  'export const previousRelease = true;\n',
);

// Only this isolated test process implements the release probes; no business model service is used.
const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1:5194');
  if (url.pathname === '/health') {
    response.end('ok');
    return;
  }
  if (url.pathname === '/api/__release-probe/echo') {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    response.setHeader('Content-Type', 'application/json');
    response.end(
      JSON.stringify({
        method: request.method,
        path: request.url,
        body: Buffer.concat(chunks).toString(),
        contentType: request.headers['content-type'],
      }),
    );
    return;
  }
  if (url.pathname === '/api/__release-probe/events') {
    response.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'X-Accel-Buffering': 'no',
    });
    response.write(
      `id: 2\nevent: progress\ndata: ${JSON.stringify({ cursor: request.headers['last-event-id'] })}\n\n`,
    );
    const timer = setTimeout(() => response.end('id: 3\nevent: done\ndata: {}\n\n'), 900);
    response.on('close', () => clearTimeout(timer));
    return;
  }
  if (url.pathname === '/api/__release-probe/download') {
    response.writeHead(200, {
      'Content-Type': 'text/markdown; charset=utf-8',
      'Content-Disposition': "attachment; filename*=UTF-8''release-result.md",
    });
    response.end('# 已验收\n\n生产代理下载内容。\n');
    return;
  }
  response.writeHead(409, { 'Content-Type': 'application/json' });
  response.end(
    JSON.stringify({ code: 'RELEASE_PROBE_REJECTED', message: '本机测试拒绝', data: null }),
  );
});
server.listen(5194, '127.0.0.1');
for (const signal of ['SIGINT', 'SIGTERM'])
  process.on(signal, () => server.close(() => process.exit(0)));
