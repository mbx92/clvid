import assert from 'node:assert/strict'
import test from 'node:test'
import { drawThumbnail, thumbnailSize, thumbnailPlacement, wrapThumbnailText } from '../app/utils/thumbnail.ts'

test('thumbnail dimensions and crop preserve proportions for portrait and landscape sources', () => {
  assert.deepEqual(thumbnailSize('landscape'), [1280, 720])
  assert.deepEqual(thumbnailSize('portrait'), [720, 1280])
  assert.deepEqual(thumbnailSize('square'), [1080, 1080])
  const cover = thumbnailPlacement(720, 1280, 1280, 720, false)
  assert.equal(cover.width, 1280)
  assert.equal(cover.y, (720 - cover.height) / 2)
  const fit = thumbnailPlacement(720, 1280, 1280, 720, true)
  assert.equal(fit.height, 720)
  assert.equal(fit.width, 405)
  assert.equal(fit.x, 437.5)
  for (const invalid of [0, -1, NaN, Infinity]) assert.throws(() => thumbnailPlacement(invalid, 100, 100, 100, false))
})

test('even a title with many explicit newlines fits the image without truncation', () => {
  for (const format of ['landscape', 'portrait', 'square']) {
    const drawn = []
    const ctx = {
      font: '', fillRect() {}, drawImage() {}, strokeText() {}, save() {}, restore() {},
      measureText(text) { return { width: text.length * Number(this.font.split(' ')[1].replace('px', '')) * .6 } },
      createLinearGradient() { return { addColorStop() {} } },
      fillText(text, x, y) { drawn.push({ text, x, y, size: Number(this.font.split(' ')[1].replace('px', '')) }) },
    }
    const canvas = { width: 0, height: 0, getContext: () => ctx }
    drawThumbnail(canvas, { width: 1920, height: 1080 }, {
      format, fit: false, title: 'A\n'.repeat(90), style: 'yellow', position: 'bottom', textSize: 16,
    })
    assert.equal(drawn.length, 90)
    assert.ok(drawn.every(line => line.y - line.size / 2 > 0 && line.y + line.size / 2 < canvas.height))
  }
})

test('titles wrap without losing words, explicit line breaks or overflowing long tokens', () => {
  const measure = value => Array.from(value).length * 10
  assert.deepEqual(wrapThumbnailText('Satu dua tiga', 90, measure), ['Satu dua', 'tiga'])
  assert.deepEqual(wrapThumbnailText('Baris satu\nBaris dua', 200, measure), ['Baris satu', 'Baris dua'])
  const original = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  const lines = wrapThumbnailText(original, 50, measure)
  assert.equal(lines.join(''), original)
  assert.ok(lines.every(line => measure(line) <= 50))
  assert.deepEqual(wrapThumbnailText('  satu    dua  ', 200, measure), ['satu dua'])
  assert.deepEqual(wrapThumbnailText('😀😀😀', 20, measure), ['😀😀', '😀'])
})
