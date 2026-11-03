import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { captionLayout } from '../app/utils/subtitles.ts'
import { captionMotion, subtitlePresets } from '../app/utils/subtitle-style.ts'

test('subtitle wrapping uses shared browser/export fixtures', () => {
  const fixtures = JSON.parse(readFileSync(new URL('../../../tests/fixtures/subtitle-layout.json', import.meta.url), 'utf8'))
  for (const item of fixtures) assert.deepEqual(captionLayout(item.text, item.size, item.auto), { text: item.wrapped, fontSize: item.effective, tooLong: false })
})

test('subtitle effects use video time and reset correctly when scrubbing', () => {
  const fade = { animation: 'fade', animation_ms: 300, position: 'bottom' }
  assert.equal(captionMotion(fade, 0, 1500).opacity, 0)
  assert.equal(captionMotion(fade, 150, 1500).opacity, .5)
  assert.equal(captionMotion(fade, 400, 1500).opacity, 1)
  assert.equal(captionMotion(fade, 1425, 1500).opacity, .5)
  assert.equal(captionMotion(fade, 1500, 1500).opacity, 0)
  assert.equal(captionMotion(fade, 150, 1500).opacity, .5)
  assert.equal(captionMotion(fade, 15, 90).opacity, .5)
  assert.equal(captionMotion({ ...fade, animation: 'none' }, 0, 1500).opacity, 1)
  const scale = Number(captionMotion({ ...fade, animation: 'pop' }, 150, 1500).transform.match(/scale\(([^)]+)\)/)[1])
  assert.ok(Math.abs(scale - .925) < 1e-8)
  assert.match(captionMotion({ ...fade, animation: 'rise', position: 'top' }, 0, 1500).transform, /translateY\(-/)
  assert.match(captionMotion({ ...fade, animation: 'rise' }, 300, 1500).transform, /translateY\(0cqw\)/)
})

test('cinematic and gaming presets include exportable effects without requiring word timestamps', () => {
  for (const name of ['Sinematik', 'Gaming impact', 'Komedi pop']) {
    const preset = subtitlePresets.find(item => item.name === name)
    assert.ok(preset)
    assert.notEqual(preset.style.animation, 'none')
    assert.equal(preset.style.display_mode, 'sentence')
  }
})
