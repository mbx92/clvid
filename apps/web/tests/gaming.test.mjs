import assert from 'node:assert/strict'
import test from 'node:test'
import { cornerRegion, defaultGaming, drawGaming, editRegion, gamingTopHeight, moveRegion, panelPlacement, panelSourceRegion, pixelRegion, resizeRegion, validGaming, validRegion } from '../app/utils/gaming.ts'
import { cropTracking, cropWithMode } from '../app/utils/framing.ts'
import { TrackingPreviewState, trackingInputKey } from '../app/utils/tracking-preview.ts'

test('gaming is explicit, preserves legacy crop coordinates and strips its data on return to single framing', () => {
  const legacy = Object.freeze({ mode: 'fill', x: .31, y: .67 })
  const gaming = cropWithMode(legacy, 'gaming')
  assert.equal(gaming.mode, 'gaming'); assert.equal(gaming.tracking, 'static')
  assert.equal(gaming.x, legacy.x); assert.equal(gaming.y, legacy.y)
  assert.deepEqual(legacy, { mode: 'fill', x: .31, y: .67 })
  assert.equal(validGaming(gaming.gaming), true)
  for (const mode of ['fill', 'fit']) {
    const restored = cropWithMode(gaming, mode)
    assert.equal(Object.hasOwn(restored, 'gaming'), false)
    assert.equal(restored.tracking, 'static')
  }
  const next = cropWithMode(legacy, 'gaming')
  gaming.gaming.facecam.x = .2
  assert.equal(next.gaming.facecam.x, 0)
})

test('gaming cannot attach or automatically queue a podcast tracking analysis', () => {
  const input = { clip_id: 'clip', source_asset_id: 'source', preview_asset_id: null,
    start_ms: 0, end_ms: 8000, crop_json: cropWithMode({ mode: 'fill', tracking: 'speaker', x: .5, y: .5 }, 'gaming') }
  assert.equal(cropTracking(input.crop_json), 'static')
  assert.equal(trackingInputKey(input), null)
  const state = new TrackingPreviewState()
  state.syncInput(input)
  assert.equal(state.begin(), null); assert.equal(state.job, null)
})

test('region dragging and resizing remain inside source bounds with minimum dimensions', () => {
  const original = Object.freeze({ x: .2, y: .3, width: .25, height: .25 })
  assert.deepEqual(moveRegion(original, 9, -9), { x: .75, y: 0, width: .25, height: .25 })
  assert.deepEqual(resizeRegion(original, 'nw', 9, 9), { x: .43, y: .53, width: .02, height: .02 })
  assert.deepEqual(editRegion(original, 'width', 2), { ...original, width: .8 })
  assert.deepEqual(editRegion(original, 'x', NaN), original)
  for (const corner of ['nw', 'ne', 'sw', 'se']) {
    assert.equal(validRegion(cornerRegion(corner)), true)
    for (let i = -100; i <= 100; i++) assert.equal(validRegion(resizeRegion(original, corner, i / 77, -i / 89)), true)
  }
})

test('invalid saved regions or top panel ratios are rejected rather than drawn', () => {
  const layout = defaultGaming()
  assert.equal(validGaming(layout), true)
  for (const bad of [{ x: -.01 }, { width: .01 }, { x: .9, width: .2 }, { y: NaN }]) {
    assert.equal(validGaming({ ...layout, facecam: { ...layout.facecam, ...bad } }), false)
  }
  for (const ratio of [.14, .46, Infinity]) assert.equal(validGaming({ ...layout, facecam_height: ratio }), false)
})

test('source region expands to integer boundaries and panel height matches both exports', () => {
  assert.deepEqual(pixelRegion({ x: .123, y: .241, width: .222, height: .333 }, 1920, 1080),
    { x: 236, y: 260, width: 427, height: 360 })
  assert.deepEqual(pixelRegion({ x: 0, y: 0, width: 1, height: 1 }, 1920, 1080),
    { x: 0, y: 0, width: 1920, height: 1080 })
  assert.equal(gamingTopHeight(1280, .28), 358)
  assert.equal(gamingTopHeight(1920, .28), 538)
})

test('fit preserves HUD with even-floor padding and fill clips centered without changing panel boundary', () => {
  const source = { x: 0, y: 0, width: 960, height: 540 }
  const panel = { x: 0, y: 358, width: 720, height: 922 }
  assert.deepEqual(panelPlacement(source, panel, 'fit'), { x: 0, y: 616, width: 720, height: 404 })
  assert.deepEqual(panelPlacement(source, panel, 'fill'), panel)
  assert.deepEqual(panelSourceRegion(source, panel, 'fill'), { x: 269, y: 0, width: 422, height: 540 })
  assert.deepEqual(panelSourceRegion(source, panel, 'fit'), source)
  const thin = { x: 10, y: 20, width: 38, height: 1080 }
  assert.deepEqual(panelSourceRegion(thin, { x: 0, y: 0, width: 1080, height: 538 }, 'fill'), { x: 10, y: 550, width: 38, height: 19 })
})

test('one decoded frame supplies both panels, with canonical source quantization mapped to proxy', () => {
  const calls = []
  const context = { fillRect() {}, save() {}, beginPath() {}, rect() {}, clip() {}, restore() {}, drawImage: (...args) => calls.push(args) }
  const canvas = { width: 0, height: 0, getContext: () => context }
  const video = { readyState: 2, videoWidth: 960, videoHeight: 540 }
  const layout = defaultGaming()
  layout.facecam_fit = 'fit'
  layout.facecam = { x: .123, y: .241, width: .222, height: .333 }
  assert.equal(drawGaming(canvas, video, layout, 1920, 1080, 720), true)
  assert.equal(calls.length, 2)
  assert.equal(calls[0][0], video); assert.equal(calls[1][0], video)
  assert.deepEqual(calls[0].slice(1, 5), [118, 130, 213.5, 180])
  assert.deepEqual([canvas.width, canvas.height], [720, 1280])
  calls.length = 0
  assert.equal(drawGaming(canvas, { ...video, readyState: 1 }, layout, 1920, 1080), false)
  assert.equal(calls.length, 0)
})
