import {access, open, unlink} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {openBrowser, selectComposition, renderMedia, makeCancelSignal} from '@remotion/renderer';
import {readStoryManifest} from './server/story-manifest.mjs';
import {serveVideo} from './server/media-server.mjs';
const {cancelSignal, cancel} = makeCancelSignal();
let browser, output, success = false, cancelled = false;
const servers = [];
const stop = () => {cancelled = true; cancel(); void browser?.close({silent: true}).catch(() => {});};
process.once('SIGTERM', stop); process.once('SIGINT', stop);
try {
  if (process.argv.length !== 3) throw new Error();
  const m = await readStoryManifest(process.argv[2]);
  const serveUrl = resolve(dirname(fileURLToPath(import.meta.url)), 'dist/composition');
  const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE;
  if (!browserExecutable) throw new Error();
  await access(browserExecutable);
  const reserved = await open(m.outputPath, 'wx'); output = m.outputPath; await reserved.close();
  const assets = {};
  for (const [id, a] of Object.entries(m.assets)) {
    const server = await serveVideo(a.path, a.mime); servers.push(server); assets[id] = {url: server.url, kind: a.kind};
  }
  if (cancelled) throw new Error();
  browser = await openBrowser('chrome', {browserExecutable, logLevel: 'error', onBrowserDownload: () => {throw new Error();}});
  const inputProps = {document: m.document, assets, width: m.width, height: m.height, fps: 30};
  const composition = await selectComposition({serveUrl, id: 'StoryboardVideo', inputProps, puppeteerInstance: browser, logLevel: 'error', onBrowserLog: () => {}});
  let last = -1;
  await renderMedia({composition, serveUrl, inputProps, puppeteerInstance: browser, codec: 'h264', audioCodec: 'aac', pixelFormat: 'yuv420p', imageFormat: 'png', colorSpace: 'bt709', crf: 18, concurrency: 2, outputLocation: output, logLevel: 'error', cancelSignal, onBrowserLog: () => {},
    onProgress: ({progress}) => {const ms = Math.floor(progress * m.durationMs); if (ms - last >= 250) {last = ms; process.stdout.write(`segment_end_ms=${ms}\n`);}}});
  if (cancelled) throw new Error();
  success = true;
} catch {
  process.stderr.write('remotion_error=story_render_failed\n'); process.exitCode = cancelled ? 130 : 1;
} finally {
  await browser?.close({silent: true}).catch(() => {});
  await Promise.all(servers.map(s => s.close().catch(() => {})));
  if (!success && output) await unlink(output).catch(() => {});
  process.removeListener('SIGTERM', stop); process.removeListener('SIGINT', stop);
}
