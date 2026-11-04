import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {captionLayout} from '../src/layout';
import {captionMotion, clampFrame, cueAtFrame, frameCount} from '../src/timing';
import {defaultEffects, defaultStyle} from '../src/types';
import {titleAtTime, videoMotion} from '../src/effects';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {PodcastCaption, podcastParts} from '../src/Captions';
import {captionChunks, hasTimedStoryCaptions, storyCaptionAtFrame, type StoryCaptionSource} from '../src/story-captions';

test('story captions follow actual audio intervals, preserve silence and support seeking', () => {
  const shot: StoryCaptionSource = {narration: 'Awal. Akhir.', duration_ms: 3000, audio_id: 'voice',
    caption_audio_id: 'voice', caption_narration: 'Awal. Akhir.', show_caption: true,
    captions: [{start_ms: 300, end_ms: 800, text: 'Awal.'}, {start_ms: 2200, end_ms: 2800, text: 'Akhir.'}]};
  assert.equal(hasTimedStoryCaptions(shot), true);
  for (const [frame, expected] of [[0, undefined], [9, 'Awal.'], [23, 'Awal.'], [24, undefined],
    [65, undefined], [66, 'Akhir.'], [84, undefined], [90, undefined], [9, 'Awal.']] as const) {
    assert.equal(storyCaptionAtFrame(shot, frame, 30), expected);
  }
  assert.equal(storyCaptionAtFrame({...shot, show_caption: false}, 9, 30), undefined);
  for (const changed of [{...shot, audio_id: 'other'}, {...shot, audio_id: null}, {...shot, narration: 'Naskah baru.'}]) {
    assert.equal(hasTimedStoryCaptions(changed), false);
    assert.equal(storyCaptionAtFrame(changed, 0, 30), changed.narration);
  }
});

test('legacy story narration uses matching Unicode chunks and frame boundaries', () => {
  const narration = 'a'.repeat(60) + ' ' + '\u{1F600}'.repeat(5) + ' akhir';
  const shot: StoryCaptionSource = {narration, duration_ms: 1100, audio_id: null, show_caption: true};
  const chunks = ['a'.repeat(60), '\u{1F600}'.repeat(5) + ' akhir'];
  assert.deepEqual(captionChunks(narration), chunks);
  assert.equal(storyCaptionAtFrame(shot, 16, 30), chunks[0]);
  assert.equal(storyCaptionAtFrame(shot, 17, 30), chunks[1]);
  assert.equal(storyCaptionAtFrame(shot, 33, 30), undefined);
  assert.equal(storyCaptionAtFrame({...shot, narration: ''}, 0, 30), undefined);
});

const fixtures: {text: string; size: number; auto: boolean; wrapped: string; effective: number}[] = JSON.parse(readFileSync(new URL('../../../tests/fixtures/subtitle-layout.json', import.meta.url), 'utf8'));

test('wrapping agrees with the shared Python/Vue Unicode fixtures', () => {
  for (const fixture of fixtures) {
    assert.deepEqual(captionLayout(fixture.text, fixture.size, fixture.auto), {text: fixture.wrapped, fontSize: fixture.effective, tooLong: false});
  }
});
test('overlong captions are reported without truncating words', () => {
  const text = 'kata '.repeat(200).trim();
  const layout = captionLayout(text, 52, true);
  assert.equal(layout.tooLong, true);
  assert.equal(layout.text.replace(/\s+/g, ' '), text);
  assert.equal(captionLayout(text, 52, false).tooLong, true);
});

test('podcast highlight follows spoken word indices, silence and backward seeking while retaining the sentence', () => {
  const text = 'BUAT ROKOK GITU DEPAN\nGEDUNG';
  const wordSpans = [{start_ms: 100, end_ms: 400, start_word: 0, end_word: 1},
    {start_ms: 500, end_ms: 900, start_word: 1, end_word: 2},
    {start_ms: 1000, end_ms: 1400, start_word: 4, end_word: 5}];
  const render = (timeMs: number) => renderToStaticMarkup(createElement(PodcastCaption, {text, scale: 1, wordSpans, timeMs}));
  const markup = render(600);
  assert.equal((markup.match(/data-podcast-highlight/g) || []).length, 1);
  assert.match(markup, /data-podcast-word="1" data-active="true"/);
  assert.equal(markup.replace(/<[^>]+>/g, ''), text);
  assert.match(markup, /background:#FFFFFF/);
  assert.match(markup, /rotate\(-3deg\)/);
  assert.match(render(1100), /data-podcast-word="4" data-active="true"/);
  for (const t of [0, 400, 450, 900, 1400]) assert.ok(!render(t).includes('data-podcast-highlight'));
  assert.equal(render(600), markup);
  assert.match(render(150), /data-podcast-word="0" data-active="true"/);
  const escaped = renderToStaticMarkup(createElement(PodcastCaption, {text: '<script> & aman', scale: 2 / 3, timeMs: 0}));
  assert.ok(!escaped.includes('<script>'));
  assert.ok(escaped.includes('&lt;script&gt;'));
  assert.ok(!escaped.includes('data-podcast-highlight'));
  assert.equal(renderToStaticMarkup(createElement(PodcastCaption, {text: '', scale: 1, timeMs: 0})), '');
  assert.deepEqual(podcastParts('YA YA\nGEDUNG', 'YA YA GEDUNG').filter(part => part.word !== null).map(part => part.word), [0, 1, 2]);
  assert.deepEqual(podcastParts('PANJANG\nSEKALI YA', 'PANJANGSEKALI YA').filter(part => part.word !== null).map(part => part.word), [0, 0, 1]);
});
test('frame count covers fractional ending frames and seek remains bounded', () => {
  assert.equal(frameCount(1001, 30), 31);
  assert.equal(clampFrame(30.99, 1001, 30), 30);
  assert.equal(clampFrame(300, 1000, 30), 29);
  assert.equal(clampFrame(-10, 1000, 30), 0);
  assert.equal(clampFrame(NaN, 1000, 30), 0);
});
test('absolute cue clock handles gaps, scrubbing backwards, and exclusive cue ends', () => {
  const cues = [{start_ms: 0, end_ms: 1000, text: 'first'}, {start_ms: 1000, end_ms: 1500, text: 'second'}, {start_ms: 2000, end_ms: 3000, text: 'third'}];
  assert.equal(cueAtFrame(cues, 29, 30)?.text, 'first');
  assert.equal(cueAtFrame(cues, 30, 30)?.text, 'second');
  assert.equal(cueAtFrame(cues, 50, 30), undefined);
  assert.equal(cueAtFrame(cues, 60, 30)?.text, 'third');
  assert.equal(cueAtFrame(cues, 15, 30)?.text, 'first');
  assert.equal(cueAtFrame(cues, 90, 30), undefined);
});
test('unsorted overlapping timeline cues match stable export ordering without mutating drafts', () => {
  const cues = [{start_ms: 2000, end_ms: 4000, text: 'A'}, {start_ms: 4000, end_ms: 6000, text: 'B'},
    {start_ms: 0, end_ms: 3000, text: 'C'}, {start_ms: 0, end_ms: 3000, text: 'D'}];
  const original = [...cues];
  const exported = [...cues].sort((a, b) => a.start_ms - b.start_ms);
  assert.equal(cueAtFrame(cues, 75, 30)?.text, 'C');
  assert.equal(cueAtFrame(cues, 75, 30), cueAtFrame(exported, 75, 30));
  assert.equal(cueAtFrame(cues, 105, 30)?.text, 'A');
  assert.deepEqual(cues, original);
});
test('minimal preserves ordinary animations and top/bottom motion direction', () => {
  const minimalStyle = {...defaultStyle, remotion_template: 'minimal' as const};
  assert.deepEqual(captionMotion(minimalStyle, 0, 1000, 30), {opacity: 1, scale: 1, y: 0});
  const pop = captionMotion({...minimalStyle, animation: 'pop'}, 0, 1000, 30);
  assert.equal(pop.scale, .85);
  assert.equal(pop.opacity, 0);
  const bottom = captionMotion({...minimalStyle, animation: 'rise'}, 90, 1000, 30);
  const top = captionMotion({...minimalStyle, animation: 'rise', position: 'top'}, 90, 1000, 30);
  assert.equal(bottom.y, -top.y);
  assert.equal(bottom.opacity, .5);
});
test('gaming and cinematic effects are deterministic under scrubbing and short cues', () => {
  for (const remotion_template of ['gaming', 'cinematic'] as const) {
    const style = {...defaultStyle, remotion_template};
    const first = captionMotion(style, 100, 1000, 30);
    assert.deepEqual(captionMotion({...style, animation_ms: 500}, 100, 1000, 30), first);
    captionMotion(style, 900, 1000, 30);
    assert.deepEqual(captionMotion(style, 100, 1000, 30), first);
    for (const duration of [1, 20, 1000]) {
      for (const time of [0, duration / 2, duration]) {
        const motion = captionMotion(style, time, duration, 30);
        assert.ok(Object.values(motion).every(Number.isFinite));
        assert.ok(motion.opacity >= 0 && motion.opacity <= 1);
      }
    }
  }
});

test('default video motion preserves framing and transition endpoints fade/slide without affecting duration', () => {
  assert.deepEqual(videoMotion(undefined, 500, 1000), {opacity: 1, transform: 'translateX(0%) scale(1)', transformOrigin: '50% 50%'});
  const effects = {...defaultEffects, transition_in: 'slide' as const, transition_out: 'slide' as const};
  assert.equal(videoMotion(effects, 0, 1000).opacity, 0);
  assert.equal(videoMotion(effects, 0, 1000).transform, 'translateX(6%) scale(1)');
  assert.equal(videoMotion(effects, 150, 1000).opacity, .5);
  assert.equal(videoMotion(effects, 500, 1000).opacity, 1);
  assert.equal(videoMotion(effects, 1000, 1000).transform, 'translateX(-6%) scale(1)');
  const short = videoMotion(effects, 50, 100);
  assert.equal(short.opacity, 1);
  assert.equal(short.transform, 'translateX(0%) scale(1)');
});
test('zoom envelopes ramp smoothly, preserve requested focus and release outside exclusive ranges', () => {
  const effects = {...defaultEffects, zooms: [{start_ms: 1000, end_ms: 2000, scale: 2, x: .25, y: .75}]};
  assert.equal(videoMotion(effects, 999, 3000).transform, 'translateX(0%) scale(1)');
  assert.equal(videoMotion(effects, 1125, 3000).transform, 'translateX(0%) scale(1.5)');
  assert.equal(videoMotion(effects, 1500, 3000).transform, 'translateX(0%) scale(2)');
  assert.equal(videoMotion(effects, 1500, 3000).transformOrigin, '25% 75%');
  assert.equal(videoMotion(effects, 1875, 3000).transform, 'translateX(0%) scale(1.5)');
  assert.equal(videoMotion(effects, 2000, 3000).transform, 'translateX(0%) scale(1)');
  assert.deepEqual(videoMotion(effects, 1125, 3000), videoMotion(effects, 1125, 3000));
});
test('overlapping zooms select the strongest effective scale and very short ranges remain finite', () => {
  const effects = {...defaultEffects, zooms: [
    {start_ms: 0, end_ms: 1000, scale: 1.5, x: .2, y: .4},
    {start_ms: 500, end_ms: 1000, scale: 2, x: .8, y: .6},
  ]};
  assert.equal(videoMotion(effects, 501, 1000).transformOrigin, '20% 40%');
  assert.equal(videoMotion(effects, 750, 1000).transformOrigin, '80% 60%');
  const short = {...defaultEffects, zooms: [{start_ms: 0, end_ms: 2, scale: 2, x: 0, y: 1}]};
  assert.equal(videoMotion(short, 1, 2).transform, 'translateX(0%) scale(2)');
});
test('title timing clamps to the clip, preserves gaps and gives outro precedence during overlap', () => {
  const effects = {...defaultEffects, intro: {enabled: true, text: 'Mulai', duration_ms: 1000}, outro: {enabled: true, text: 'Selesai', duration_ms: 1000}};
  assert.equal(titleAtTime(effects, 500, 5000)?.title.text, 'Mulai');
  assert.equal(titleAtTime(effects, 1000, 5000), null);
  assert.equal(titleAtTime(effects, 4500, 5000)?.title.text, 'Selesai');
  assert.equal(titleAtTime(effects, 5000, 5000), null);
  const overlap = titleAtTime(effects, 250, 500)!;
  assert.equal(overlap.title.text, 'Selesai');
  assert.equal(overlap.startMs, 0); assert.equal(overlap.endMs, 500);
  assert.equal(titleAtTime({...effects, intro: {...effects.intro, text: ' '}, outro: {...effects.outro, enabled: false}}, 100, 5000), null);
});
