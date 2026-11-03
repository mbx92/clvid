import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, writeFile, rm, symlink, readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {normalizeManifest, readManifest, isWithin} from '../server/manifest.mjs';
import {parseRange, serveVideo} from '../server/media-server.mjs';

const valid = () => ({version: 1, videoPath: 'prepared/clip.mp4', outputPath: 'remotion.partial.mp4',
  width: 720, height: 1280, fps: 30, durationMs: 1000,
  cues: [{start_ms: 0, end_ms: 1000, text: 'hello'}], style: {renderer: 'remotion'}});

test('manifest strips unknown properties and accepts only local render inputs', () => {
  const manifest = normalizeManifest({...valid(), fontUrl: 'https://example.invalid/font', style: {...valid().style, backgroundImage: 'url(secret)'}});
  assert.equal(manifest.style.remotion_template, 'gaming');
  assert.equal(manifest.fontUrl, undefined);
  assert.equal(manifest.style.backgroundImage, undefined);
  assert.equal(manifest.style.animation_ms, 180);
});
test('manifest rejects invalid bounds, timestamps, CSS injection, network paths and traversal', () => {
  const changes = [{version: 2}, {fps: 60}, {width: 1080}, {durationMs: Infinity}, {durationMs: 1800001},
    {videoPath: 'https://example.invalid/a.mp4'}, {outputPath: '../out.mp4'}, {cues: new Array(10001).fill(valid().cues[0])},
    {cues: [{start_ms: 0, end_ms: 0, text: 'zero'}]}, {cues: [{start_ms: 500, end_ms: 1200, text: 'past end'}]},
    {cues: [{start_ms: 0, end_ms: 100, text: 'a'.repeat(2001)}]},
    {style: {renderer: 'remotion', text_color: 'url(a)'}}, {style: {renderer: 'remotion', enabled: 'true'}},
    {style: {renderer: 'remotion', remotion_template: 'unknown'}}, {style: {renderer: 'remotion', safe_margin: 2}}];
  for (const change of changes) assert.throws(() => normalizeManifest({...valid(), ...change}), /invalid_manifest/);
});
test('cue length uses Unicode code points like Python rather than UTF-16 units', () => {
  const text = '\u{1F600}'.repeat(2000);
  assert.equal(normalizeManifest({...valid(), cues: [{start_ms: 0, end_ms: 1000, text}]}).cues[0].text, text);
  assert.throws(() => normalizeManifest({...valid(), cues: [{start_ms: 0, end_ms: 1000, text: `${text}x`}]}), /invalid_manifest/);
});
test('effects are allowlisted and title/zoom validation rejects unsafe or invalid timelines', () => {
  const effects = {transition_in: 'fade', transition_out: 'slide', transition_ms: 300,
    intro: {enabled: true, text: 'Mulai', duration_ms: 500}, outro: {enabled: false, text: '', duration_ms: 1200},
    zooms: [{start_ms: 200, end_ms: 800, scale: 1.5, x: .5, y: .5, url: 'https://example.invalid'}]};
  const normalized = normalizeManifest({...valid(), style: {renderer: 'remotion', enabled: false, remotion_effects: effects}});
  assert.equal(normalized.style.remotion_effects.intro.text, 'Mulai');
  assert.equal(normalized.style.remotion_effects.zooms[0].url, undefined);
  const changes = [{transition_in: 'crossfade'}, {transition_ms: 99}, {transition_ms: NaN},
    {intro: {enabled: true, text: ' ', duration_ms: 500}}, {outro: {enabled: true, text: 'a'.repeat(81)}},
    {zooms: new Array(21).fill(effects.zooms[0])}, {zooms: [{...effects.zooms[0], scale: 2.1}]},
    {zooms: [{...effects.zooms[0], x: -1}]}, {zooms: [{...effects.zooms[0], start_ms: 800}]},
    {zooms: [{...effects.zooms[0], end_ms: 1001}]}];
  for (const change of changes) assert.throws(() => normalizeManifest({...valid(), style: {renderer: 'remotion', remotion_effects: {...effects, ...change}}}), /invalid_manifest/);
  assert.equal(normalizeManifest({...valid(), style: {renderer: 'remotion', remotion_effects: {...effects, intro: {...effects.intro, text: '\u{1F600}'.repeat(80)}}}}).style.remotion_effects.intro.text.length, 160);
});
test('range parsing covers prefix, suffix, open-ended, oversized and malformed ranges', () => {
  assert.equal(parseRange(undefined, 100), null);
  assert.deepEqual(parseRange('bytes=0-9', 100), {start: 0, end: 9});
  assert.deepEqual(parseRange('bytes=95-', 100), {start: 95, end: 99});
  assert.deepEqual(parseRange('bytes=-10', 100), {start: 90, end: 99});
  assert.deepEqual(parseRange('bytes=-200', 100), {start: 0, end: 99});
  assert.deepEqual(parseRange('bytes=0-999', 100), {start: 0, end: 99});
  for (const value of ['bytes=100-', 'bytes=10-5', 'bytes=-0', 'bytes=-', 'bytes=0-1,3-4', 'bytes=NaN-4', 'bytes=0-99999999999999999999']) assert.equal(parseRange(value, 100), false);
});

async function fixture(t) {
  const base = await mkdtemp(path.join(tmpdir(), 'clipper-remotion-'));
  t.after(() => {
    assert.ok(isWithin(path.resolve(tmpdir()), path.resolve(base)));
    return rm(base, {recursive: true, force: true});
  });
  const root = path.join(base, 'job');
  await mkdir(path.join(root, 'prepared'), {recursive: true});
  await writeFile(path.join(root, 'prepared/clip.mp4'), Buffer.from('0123456789'));
  const manifest = path.join(root, 'render.json');
  await writeFile(manifest, JSON.stringify(valid()));
  return {base, root, manifest};
}

test('manifest confines paths and refuses overwriting existing outputs', async t => {
  const {root, manifest, base} = await fixture(t);
  const normalized = await readManifest(manifest);
  assert.equal(normalized.videoPath, path.join(root, 'prepared/clip.mp4'));
  assert.equal(isWithin(root, path.join(base, 'job-other/a.mp4')), false);
  await writeFile(path.join(root, 'remotion.partial.mp4'), 'keep me');
  await assert.rejects(readManifest(manifest), /invalid_manifest/);
  assert.equal(await readFile(path.join(root, 'remotion.partial.mp4'), 'utf8'), 'keep me');
});
test('manifest rejects oversized input before parsing', async t => {
  const {manifest} = await fixture(t);
  await writeFile(manifest, ' '.repeat(2 * 1024 * 1024 + 1));
  await assert.rejects(readManifest(manifest), /invalid_manifest/);
});
test('video and output directory symlinks cannot escape the job', async t => {
  const {root, manifest, base} = await fixture(t);
  const outside = path.join(base, 'outside');
  await mkdir(outside);
  await writeFile(path.join(outside, 'clip.mp4'), 'secret');
  // Windows directory junctions need no developer-mode symlink permission.
  await symlink(outside, path.join(root, 'escape'), process.platform === 'win32' ? 'junction' : 'dir');
  await writeFile(manifest, JSON.stringify({...valid(), videoPath: 'escape/clip.mp4'}));
  await assert.rejects(readManifest(manifest), /invalid_manifest/);
  await writeFile(manifest, JSON.stringify({...valid(), outputPath: 'escape/output.mp4'}));
  await assert.rejects(readManifest(manifest), /invalid_manifest/);
});
test('media server exposes one tokenized file, supports HEAD/ranges and rejects other requests', async t => {
  const {root} = await fixture(t);
  const media = await serveVideo(path.join(root, 'prepared/clip.mp4'));
  t.after(() => media.close());
  const url = new URL(media.url);
  assert.equal(url.hostname, '127.0.0.1');
  assert.match(url.pathname, /^\/[a-f0-9]{64}\/video\.mp4$/);
  const full = await fetch(media.url);
  assert.equal(full.status, 200); assert.equal(await full.text(), '0123456789');
  const head = await fetch(media.url, {method: 'HEAD'});
  assert.equal(head.status, 200); assert.equal(head.headers.get('content-length'), '10'); assert.equal(await head.text(), '');
  const range = await fetch(media.url, {headers: {Range: 'bytes=2-5'}});
  assert.equal(range.status, 206); assert.equal(range.headers.get('content-range'), 'bytes 2-5/10'); assert.equal(await range.text(), '2345');
  const invalid = await fetch(media.url, {headers: {Range: 'bytes=100-'}});
  assert.equal(invalid.status, 416);
  assert.equal((await fetch(`${url.origin}/prepared/clip.mp4`)).status, 404);
  assert.equal((await fetch(`${media.url}?file=elsewhere`)).status, 404);
  assert.equal((await fetch(media.url, {method: 'POST'})).status, 405);
  await media.close();
  await assert.rejects(fetch(media.url));
});
