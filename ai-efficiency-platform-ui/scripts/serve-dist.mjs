import { createServer, request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';
import { createReadStream } from 'node:fs';
import { realpath, stat } from 'node:fs/promises';
import { dirname, extname, isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = await realpath(resolve(projectRoot, process.env.RELEASE_DIST_DIR || 'dist'));
const sharedAssets = process.env.RELEASE_ASSETS_DIR
  ? await realpath(resolve(process.env.RELEASE_ASSETS_DIR))
  : null;
await stat(resolve(root, 'index.html'));
const port = Number(process.env.RELEASE_PORT || 5193);
if (!Number.isInteger(port) || port < 1 || port > 65535)
  throw new Error('RELEASE_PORT must be a valid port');
const target = process.env.RELEASE_API_TARGET ? new URL(process.env.RELEASE_API_TARGET) : null;
if (
  target &&
  (!['http:', 'https:'].includes(target.protocol) ||
    target.username ||
    target.password ||
    target.pathname !== '/' ||
    target.search ||
    target.hash)
)
  throw new Error('RELEASE_API_TARGET must be an HTTP origin without credentials');
const hopByHop = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);
function headersWithoutHop(headers) {
  const excluded = new Set([
    ...hopByHop,
    ...(headers.connection || '').split(',').map((name) => name.trim().toLowerCase()),
  ]);
  return Object.fromEntries(
    Object.entries(headers).filter(([name]) => !excluded.has(name.toLowerCase())),
  );
}
const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json',
};
function sendJson(response, status, code) {
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  response.end(JSON.stringify({ code, message: code, data: null }));
}
function insideRoot(path, base = root) {
  const part = relative(base, path);
  return part !== '..' && !part.startsWith(`..${sep}`) && !isAbsolute(part);
}
function proxy(request, response) {
  if (!target) {
    sendJson(response, 503, 'RELEASE_API_UNCONFIGURED');
    return;
  }
  const transport = target.protocol === 'https:' ? httpsRequest : httpRequest;
  const outgoing = transport(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || undefined,
      method: request.method,
      path: request.url,
      headers: { ...headersWithoutHop(request.headers), host: target.host },
    },
    (incoming) => {
      response.writeHead(incoming.statusCode || 502, headersWithoutHop(incoming.headers));
      response.flushHeaders();
      incoming.on('error', () => response.destroy());
      incoming.pipe(response);
    },
  );
  outgoing.on('error', () => {
    if (!response.headersSent) sendJson(response, 502, 'RELEASE_API_UNAVAILABLE');
    else response.destroy();
  });
  request.on('aborted', () => outgoing.destroy());
  response.on('close', () => {
    if (!response.writableFinished) outgoing.destroy();
  });
  request.pipe(outgoing);
}
const server = createServer(async (request, response) => {
  response.setHeader('X-Content-Type-Options', 'nosniff');
  if (!request.url?.startsWith('/') || request.url.startsWith('//')) {
    sendJson(response, 400, 'INVALID_REQUEST_TARGET');
    return;
  }
  let pathname;
  try {
    pathname = decodeURIComponent(request.url.split('?')[0]);
  } catch {
    sendJson(response, 400, 'INVALID_PATH');
    return;
  }
  if (pathname.includes('\0') || pathname.includes('\\') || pathname.split('/').includes('..')) {
    sendJson(response, 403, 'PATH_NOT_ALLOWED');
    return;
  }
  if (pathname === '/api' || pathname.startsWith('/api/')) {
    proxy(request, response);
    return;
  }
  if (!['GET', 'HEAD'].includes(request.method)) {
    response.setHeader('Allow', 'GET, HEAD');
    sendJson(response, 405, 'METHOD_NOT_ALLOWED');
    return;
  }
  const servingRoot = sharedAssets && pathname.startsWith('/assets/') ? sharedAssets : root;
  let filename = resolve(
    servingRoot,
    `.${sharedAssets && pathname.startsWith('/assets/') ? pathname.slice('/assets'.length) : pathname}`,
  );
  if (!insideRoot(filename, servingRoot)) {
    sendJson(response, 403, 'PATH_NOT_ALLOWED');
    return;
  }
  let info;
  try {
    info = await stat(filename);
    if (!info.isFile()) info = undefined;
  } catch (error) {
    if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') {
      sendJson(response, 500, 'STATIC_READ_FAILED');
      return;
    }
  }
  if (!info) {
    const htmlRequest = (request.headers.accept || '').includes('text/html');
    if (
      extname(pathname) ||
      pathname.startsWith('/assets/') ||
      (!htmlRequest && pathname !== '/')
    ) {
      sendJson(response, 404, 'STATIC_NOT_FOUND');
      return;
    }
    filename = resolve(root, 'index.html');
    info = await stat(filename);
  }
  try {
    const actual = await realpath(filename);
    if (!insideRoot(actual, servingRoot)) {
      sendJson(response, 403, 'PATH_NOT_ALLOWED');
      return;
    }
    const extension = extname(actual).toLowerCase();
    response.setHeader('Content-Type', mime[extension] || 'application/octet-stream');
    response.setHeader('Content-Length', info.size);
    response.setHeader(
      'Cache-Control',
      pathname.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache',
    );
    if (request.method === 'HEAD') {
      response.end();
      return;
    }
    const stream = createReadStream(actual);
    stream.on('error', () => {
      if (!response.headersSent) sendJson(response, 500, 'STATIC_READ_FAILED');
      else response.destroy();
    });
    stream.pipe(response);
  } catch {
    if (!response.headersSent) sendJson(response, 500, 'STATIC_READ_FAILED');
    else response.destroy();
  }
});
server.listen(port, '127.0.0.1', () =>
  process.stdout.write(`Production preview ready at http://127.0.0.1:${port}\n`),
);
for (const signal of ['SIGINT', 'SIGTERM'])
  process.on(signal, () => {
    server.close(() => process.exit(0));
    server.closeIdleConnections();
  });
