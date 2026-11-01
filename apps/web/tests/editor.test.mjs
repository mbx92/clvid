import assert from 'node:assert/strict'
import test from 'node:test'
import { captionLayout } from '../app/utils/subtitles.ts'
import { captionAppearance, subtitlePresets } from '../app/utils/subtitle-style.ts'
import { parseTimecode, timecode } from '../app/utils/format.ts'

test('timecode preserves millisecond precision across an hour boundary', () => {
  assert.equal(timecode(3661123, true), '01:01:01.123')
  assert.equal(parseTimecode('01:01:01.123'), 3661123)
  assert.equal(parseTimecode('00:07,125'), 7125)
  assert.equal(parseTimecode('00:90'), null)
  assert.equal(parseTimecode('-00:03'), null)
})

test('caption preview keeps all spoken text and balances the same two lines as render', () => {
  const layout = captionLayout('Subtitle koreksi — hasil ekspor nyata.', 52)
  assert.equal(layout.text, 'Subtitle koreksi —\nhasil ekspor nyata.')
  assert.equal(layout.fontSize, 52)
  assert.equal(layout.tooLong, false)
})

test('long captions are reported rather than silently truncated', () => {
  const input = 'Koreksi subtitle yang sangat panjang '.repeat(12).trim()
  const layout = captionLayout(input, 52)
  assert.equal(layout.tooLong, true)
  assert.equal(layout.text.replace('\n', ' '), input)
  assert.equal(layout.text.split('\n').length, 2)
})

test('line breaking preserves Unicode characters when no word boundary exists', () => {
  const input = 'é𐐀'.repeat(30)
  const layout = captionLayout(input, 52)
  assert.equal(layout.text.replace('\n', ''), input)
  assert.equal(Array.from(layout.text.split('\n')[0]).length, 30)
})

test('manual subtitle sizes stay exact while automatic sizing remains explicit', () => {
  const text = 'Ukuran teks berubah sesuai pilihan'
  assert.ok(captionLayout(text, 100).fontSize < 100)
  const manual = captionLayout(text, 100, false)
  assert.equal(manual.fontSize, 100)
  assert.equal(manual.tooLong, false)
  assert.equal(manual.text.replaceAll('\n', ' '), text)
  assert.ok(manual.text.split('\n').length <= 4)
  assert.equal(captionLayout(text.repeat(10), 100, false).tooLong, true)
  assert.equal(captionLayout('abcdefghijklm abcdefghijklmnopq', 100, false).text, 'abcdefghijklm\nabcdefghijklm\nnopq')
  const yellow = subtitlePresets.find(p => p.name === 'Kuning').style
  const css = captionAppearance(yellow)
  assert.equal(css.color, '#FFE600')
  assert.equal(css.fontWeight, '700')
  assert.ok(css.WebkitTextStroke.includes('#111111'))
})
