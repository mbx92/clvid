import {createServer} from 'node:http';
import {open} from 'node:fs/promises';
import {randomBytes} from 'node:crypto';
import {Readable} from 'node:stream';

async function* readRange(file, start, end) {
  let position = start;
  while (position <= end) {
    const buffer = Buffer.allocUnsafe(Math.min(128 * 1024, end - position + 1));
    const {bytesRead} = await file.read(buffer, 0, buffer.length, position);
    if (!bytesRead) throw new Error('Media unavailable');
    position += bytesRead;
    yield buffer.subarray(0, bytesRead);
  }
}

/** Only a single byte range is needed by Chromium and OffthreadVideo. */
export function parseRange(header, size) {
  if (header === undefined) return null;
  if (typeof header !== 'string') return false;
  const match = /^bytes=(\d*)-(\d*)$/.exec(header);
  if (!match || (!match[1] && !match[2]) || size <= 0) return false;
  let start, end;
  if (!match[1]) {
    const suffix = Number(match[2]);
    if (!Number.isSafeInteger(suffix) || suffix <= 0) return false;
    start = Math.max(0, size - suffix); end = size - 1;
  } else {
    start = Number(match[1]); end = match[2] ? Number(match[2]) : size - 1;
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start >= size || end < start) return false;
    end = Math.min(end, size - 1);
  }
  return {start, end};
}

/** No directory serving: the token resolves to this already-open file only. */
export async function serveVideo(videoPath, mime = 'video/mp4') {
  const file = await open(videoPath, 'r');
  const stat = await file.stat();
  const route = `/${randomBytes(32).toString('hex')}/video.mp4`;
  const streams = new Set();
  const server = createServer((req, res) => {
    const headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'};
    if (req.url !== route) {res.writeHead(404, headers); res.end(); return;}
    if (req.method !== 'GET' && req.method !== 'HEAD') {res.writeHead(405, {...headers, Allow: 'GET, HEAD'}); res.end(); return;}
    const range = parseRange(req.headers.range, stat.size);
    if (range === false) {res.writeHead(416, {...headers, 'Content-Range': `bytes */${stat.size}`}); res.end(); return;}
    const start = range?.start ?? 0, end = range?.end ?? stat.size - 1;
    res.writeHead(range ? 206 : 200, {...headers, 'Content-Type': mime, 'Accept-Ranges': 'bytes',
      'Access-Control-Allow-Origin': '*', 'Content-Length': end - start + 1,
      ...(range ? {'Content-Range': `bytes ${start}-${end}/${stat.size}`} : {})});
    if (req.method === 'HEAD') {res.end(); return;}
    // A FileHandle ReadStream can close its shared descriptor on destroy. Use
    // explicit positional reads so cancelled/concurrent ranges stay independent.
    const stream = Readable.from(readRange(file, start, end));
    streams.add(stream);
    stream.once('close', () => streams.delete(stream));
    stream.once('error', () => res.destroy());
    res.once('close', () => stream.destroy());
    stream.pipe(res);
  });
  server.requestTimeout = 30000;
  server.headersTimeout = 10000;
  try {
    await new Promise((resolve, reject) => {server.once('error', reject); server.listen(0, '127.0.0.1', resolve);});
  } catch (error) {await file.close(); throw error;}
  let closed = false;
  return {
    url: `http://127.0.0.1:${server.address().port}${route}`,
    async close() {
      if (closed) return;
      closed = true;
      for (const stream of streams) stream.destroy();
      await new Promise(resolve => {server.close(resolve); server.closeAllConnections();});
      await file.close();
    },
  };
}
