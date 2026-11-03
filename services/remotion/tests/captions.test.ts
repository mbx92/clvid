import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {captionLayout} from '../src/layout';
import {captionMotion, clampFrame, cueAtFrame, frameCount} from '../src/timing';
import {defaultEffects, defaultStyle} from '../src/types';
import {titleAtTime, videoMotion} from '../src/effects';

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
