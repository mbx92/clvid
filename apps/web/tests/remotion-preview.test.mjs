import assert from 'node:assert/strict'
import test from 'node:test'
import { remotionFrame } from '../app/utils/remotion-preview.ts'
import { applySubtitlePreset, podcastSubtitlePreset, subtitleDefaults, subtitlePresets } from '../app/utils/subtitle-style.ts'
import { captionLayout } from '../app/utils/subtitles.ts'
import { effectsError, intervalDrag, remotionEffects, retimeEffects, zoomAt } from '../app/utils/remotion-effects.ts'

test('Remotion preview follows export frames and clamps both ends of the clip', () => {
  assert.equal(remotionFrame(-500, 5000), 0)
  assert.equal(remotionFrame(0, 5000), 0)
  assert.equal(remotionFrame(33, 5000), 0)
  assert.equal(remotionFrame(34, 5000), 1)
  assert.equal(remotionFrame(1250, 5000), 37)
  assert.equal(remotionFrame(5000, 5000), 149)
  assert.equal(remotionFrame(10000, 5000), 149)
  assert.equal(remotionFrame(5000, 5010), 150)
  assert.equal(remotionFrame(1000, 0), 0)
  assert.equal(remotionFrame(NaN, 5000), 0)
})

test('old subtitle styles keep the standard renderer without changing their appearance', () => {
  const legacy = { enabled: false, font_size: 52, background: true, position: 'bottom', safe_margin: .15 }
  const normalized = { ...subtitleDefaults, ...legacy }
  assert.equal(normalized.renderer, 'ffmpeg')
  assert.equal(normalized.remotion_template, 'gaming')
  assert.equal(normalized.enabled, false)
  assert.equal(normalized.font_size, 52)
  assert.equal(normalized.background, true)
})

test('every typography preset preserves a selected Remotion template and placement', () => {
  const style = { enabled: false, renderer: 'remotion', remotion_template: 'cinematic', font_size: 52, background: true, position: 'top', safe_margin: .23 }
  for (const preset of subtitlePresets) {
    const applied = applySubtitlePreset(style, preset.style)
    assert.equal(applied.renderer, 'remotion')
    assert.equal(applied.remotion_template, 'cinematic')
    assert.equal(applied.position, 'top')
    assert.equal(applied.safe_margin, .23)
    assert.equal(applied.enabled, true)
    assert.equal(applied.text_color, preset.style.text_color)
  }
})

test('podcast reference preset enables Remotion and wraps the reference caption without losing words', () => {
  const s = podcastSubtitlePreset.style
  assert.equal(s.renderer, 'remotion')
  assert.equal(s.remotion_template, 'podcast')
  assert.ok(s.enabled && s.bold && s.italic && s.uppercase)
  assert.equal(s.text_color, '#FFE600')
  assert.equal(s.background, false)
  assert.equal(s.position, 'bottom')
  assert.deepEqual(captionLayout('BUAT ROKOK GITU DEPAN GEDUNG', s.font_size, s.auto_fit),
    { text: 'BUAT ROKOK GITU DEPAN\nGEDUNG', fontSize: 64, tooLong: false })
})

test('effect defaults are isolated and zooms stay within the current clip', () => {
  const first = remotionEffects(), second = remotionEffects()
  first.intro.enabled = true; first.zooms.push(zoomAt(4900, 5000))
  assert.equal(second.intro.enabled, false)
  assert.deepEqual(second.zooms, [])
  assert.deepEqual(first.zooms[0], { start_ms: 4900, end_ms: 5000, scale: 1.2, x: .5, y: .5 })
  assert.deepEqual(zoomAt(6000, 5000), first.zooms[0])
  assert.equal(effectsError(first, 5000), 'Isi teks intro terlebih dahulu.')
  first.intro.text = 'Hook'
  assert.equal(effectsError(first, 5000), '')
})

test('timeline dragging clamps movement and resizing without losing text or zoom strength', () => {
  const cue = { start_ms: 1000, end_ms: 2000, text: 'Awas!' }
  assert.deepEqual(intervalDrag(cue, -5000, 5000, 'move'), { ...cue, start_ms: 0, end_ms: 1000 })
  assert.deepEqual(intervalDrag(cue, 10000, 5000, 'move'), { ...cue, start_ms: 4000, end_ms: 5000 })
  assert.deepEqual(intervalDrag(cue, 10000, 5000, 'start'), { ...cue, start_ms: 1900 })
  assert.deepEqual(intervalDrag(cue, -5000, 5000, 'end'), { ...cue, end_ms: 1100 })
  assert.deepEqual(intervalDrag({ ...cue, scale: 1.4 }, 134, 5000, 'move'), { ...cue, start_ms: 1130, end_ms: 2130, scale: 1.4 })
})

test('trim shifts zooms with source time and removes only the out-of-range portions', () => {
  const effects = remotionEffects({ zooms: [zoomAt(1000, 10000), zoomAt(5000, 10000), zoomAt(9000, 10000)] })
  const changed = retimeEffects(effects, 10000, 12000, 18000)
  assert.deepEqual(changed.zooms, [{ start_ms: 0, end_ms: 500, scale: 1.2, x: .5, y: .5 }, { start_ms: 3000, end_ms: 4500, scale: 1.2, x: .5, y: .5 }])
  assert.equal(effects.zooms[0].start_ms, 1000)
  assert.equal(retimeEffects(undefined, 10000, 12000, 18000), undefined)
})
