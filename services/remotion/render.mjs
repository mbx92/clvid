import {open, access, unlink} from 'node:fs/promises';
import {constants} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {openBrowser, selectComposition, renderMedia, makeCancelSignal} from '@remotion/renderer';
import {readManifest, RenderInputError} from './server/manifest.mjs';
import {serveVideo} from './server/media-server.mjs';

const packageRoot = dirname(fileURLToPath(import.meta.url));
const {cancelSignal, cancel} = makeCancelSignal();
let browser, media, output, success = false, cancelled = false;
const onSignal = () => {cancelled = true; cancel(); void browser?.close({silent: true}).catch(() => {});};
process.once('SIGTERM', onSignal);
process.once('SIGINT', onSignal);
try {
  if (process.argv.length !== 3) throw new RenderInputError('invalid_manifest');
  const manifest = await readManifest(process.argv[2]);
  const serveUrl = resolve(packageRoot, 'dist/composition');
  await access(resolve(serveUrl, 'index.html'));
  // Deployment passes this path explicitly. Never download a browser during a job.
  const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE;
  if (!browserExecutable) throw new RenderInputError('browser_unavailable');
  try {await access(browserExecutable, constants.X_OK);} catch {throw new RenderInputError('browser_unavailable');}
  const reserved = await open(manifest.outputPath, 'wx');
  output = manifest.outputPath;
  await reserved.close();
  if (cancelled) throw new RenderInputError('render_cancelled');
  media = await serveVideo(manifest.videoPath);
  browser = await openBrowser('chrome', {browserExecutable, logLevel: 'error',
    onBrowserDownload: () => {throw new RenderInputError('browser_unavailable');}});
  if (cancelled) throw new RenderInputError('render_cancelled');
  const inputProps = {cues: manifest.cues, style: manifest.style, durationMs: manifest.durationMs,
    width: manifest.width, height: manifest.height, fps: manifest.fps, videoUrl: media.url};
  const composition = await selectComposition({serveUrl, id: 'ClipperVideo', inputProps, puppeteerInstance: browser, logLevel: 'error', onBrowserLog: () => {}});
  let lastProgress = -1;
  await renderMedia({composition, serveUrl, inputProps, puppeteerInstance: browser,
    codec: 'h264', pixelFormat: 'yuv420p', imageFormat: 'png', colorSpace: 'bt709',
    muted: true, crf: 18, concurrency: 2,
    outputLocation: output, logLevel: 'error', cancelSignal, onBrowserLog: () => {},
    onProgress: ({progress}) => {
      const milliseconds = Math.min(manifest.durationMs - 1, Math.floor(progress * manifest.durationMs));
      if (milliseconds - lastProgress >= 250) {lastProgress = milliseconds; process.stdout.write(`segment_end_ms=${milliseconds}\n`);}
    },
  });
  if (cancelled) throw new RenderInputError('render_cancelled');
  success = true;
  process.stdout.write(`segment_end_ms=${manifest.durationMs}\n`);
} catch (error) {
  // Avoid emitting media paths, caption text, browser URLs, or credentials.
  const code = cancelled ? 'render_cancelled' : error instanceof RenderInputError ? error.code : 'render_failed';
  process.stderr.write(`remotion_error=${code}\n`);
  process.exitCode = cancelled ? 130 : 1;
} finally {
  await browser?.close({silent: true}).catch(() => {});
  await media?.close().catch(() => {});
  if (!success && output) await unlink(output).catch(() => {});
  process.removeListener('SIGTERM', onSignal);
  process.removeListener('SIGINT', onSignal);
}
