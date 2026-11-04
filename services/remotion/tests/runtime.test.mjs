import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, writeFile, rm, symlink, readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {normalizeManifest, readManifest, isWithin} from '../server/manifest.mjs';
import {parseRange, serveVideo} from '../server/media-server.mjs';
import {readStoryManifest, validateStoryCaptions} from '../server/story-manifest.mjs';

test('story caption manifest rejects overlapping, excessive, malformed and truncated timings', () => {
  const shot = {duration_ms: 3000, caption_audio_id: 'voice', caption_narration: 'Awal. Akhir.',
    captions: [{start_ms: 300, end_ms: 800, text: 'Awal.'}, {start_ms: 2200, end_ms: 2800, text: 'Akhir.'}]};
  assert.doesNotThrow(() => validateStoryCaptions(shot));
  assert.doesNotThrow(() => validateStoryCaptions({duration_ms: 3000}));
  // Old source references are retained for the UI; playback disregards their timing.
  assert.doesNotThrow(() => validateStoryCaptions({...shot, audio_id: 'new'}));
  for (const mutation of [
    x => {x.captions[0].start_ms = -1;},
    x => {x.captions[0].start_ms = '300';},
    x => {x.captions[0].end_ms = 300;},
    x => {x.captions[1].start_ms = 799;},
    x => {x.captions[1].end_ms = 3001;},
    x => {x.captions[0].text = ' ';},
    x => {x.captions[0].text = 'x'.repeat(201);},
    x => {x.captions[0].html = '<b>x</b>';},
    x => {x.captions = null;},
    x => {x.captions = Array.from({length: 201}, (_, i) => ({start_ms: i, end_ms: i + 1, text: 'x'}));},
    x => {x.duration_ms = 2000;},
    x => {x.caption_audio_id = {};},
    x => {x.caption_narration = 'x'.repeat(601);},
  ]) assert.throws(() => {const changed = structuredClone(shot); mutation(changed); validateStoryCaptions(changed);}, /invalid_story_manifest/);
});

test('story manifest validates themes, durations, and confines all media to the job', async t => {
  const root = await mkdtemp(path.join(tmpdir(), 'story-manifest-'));
  t.after(() => rm(root, {recursive: true, force: true}));
  const file = path.join(root, 'story.json');
  const m = {version:1,width:720,height:1280,fps:30,outputPath:path.join(root,'out.mp4'),assets:{},document:{
    theme:{background:'#132923',foreground:'#ffffff',accent:'#ccff44',font:'sans',motion:'rise',align:'left',font_size:72,uppercase:false},
    scenes:[{id:'one',layout:'title',duration_ms:1000,media_start_ms:0,show_caption:true,title:'Hello',text:'',narration:'',asset_id:null,audio_id:null}]}};
  await writeFile(file, JSON.stringify(m));
  assert.equal((await readStoryManifest(file)).durationMs, 1000);
  for(const mutation of [
    x => {x.document.theme.background = 'url(https://example.invalid)';},
    x => {x.document.scenes[0].duration_ms = -1000;},
    x => {x.outputPath = path.join(root,'..','outside.mp4');},
    x => {x.document.scenes[0].asset_id = 'missing';},
    x => {x.assets.bad = {kind:'image',mime:'image/png',path:'/etc/passwd'};},
  ]) {
    const invalid = structuredClone(m); mutation(invalid); await writeFile(file, JSON.stringify(invalid));
    await assert.rejects(readStoryManifest(file), /invalid_story_manifest/);
  }
  const image = path.join(root,'image.png'); await writeFile(image, 'fixture');
  const server = await serveVideo(image, 'image/png');
  t.after(() => server.close());
  assert.equal((await fetch(server.url)).headers.get('content-type'), 'image/png');
});

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

test('podcast reference template is accepted for server rendering', () => {
  const manifest = normalizeManifest({...valid(), style: {renderer: 'remotion', remotion_template: 'podcast',
    bold: true, italic: true, uppercase: true, background: false, text_color: '#FFE600'}});
  assert.equal(manifest.style.remotion_template, 'podcast');
  assert.equal(manifest.style.italic, true);
});

test('manifest preserves word timing and rejects out-of-cue times, token ranges and overlaps', () => {
  const span = {start_ms: 100, end_ms: 500, start_word: 0, end_word: 1};
  const cue = {...valid().cues[0], text: 'hello world', word_spans: [span]};
  assert.deepEqual(normalizeManifest({...valid(), cues: [cue]}).cues[0].word_spans, [span]);
  for (const spans of [[{...span, start_ms: -1}], [{...span, end_ms: 1001}], [{...span, end_ms: 100}],
    [{...span, start_word: -1}], [{...span, end_word: 3}], [{...span, end_word: 0}],
    [span, {...span, start_ms: 400, end_ms: 700, start_word: 1, end_word: 2}],
    [span, {...span, start_ms: 600, end_ms: 700}], new Array(2001).fill(span)]) {
    assert.throws(() => normalizeManifest({...valid(), cues: [{...cue, word_spans: spans}]}), /invalid_manifest/);
  }
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
import {validateStoryVisual} from '../server/story-manifest.mjs';

test('story illustrations validate bounded recipes and reject arbitrary assets or code', () => {
  const visual = {kind:'coffee_reveal',items:[],motion:'gentle',reveal_ms:2000};
  assert.doesNotThrow(() => validateStoryVisual(visual));
  assert.doesNotThrow(() => validateStoryVisual({...visual,kind:'steps',items:[{icon:'cup',label:'Seduh'}]}));
  for (const change of [{kind:'photo'}, {url:'https://example.org'}, {reveal_ms:-1}, {motion:'script'}, {items:[{icon:'html',label:'x'}]}, {items:[{icon:'box',label:'x'.repeat(33)}]}]) {
    assert.throws(() => validateStoryVisual({...visual,...change}), /invalid_story_manifest/);
  }
});
