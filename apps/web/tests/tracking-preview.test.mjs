import assert from 'node:assert/strict'
import test from 'node:test'
import { TrackingPreviewState, trackingInputKey, trackingPosition, trackingSpecMatches, validTrackingFrames } from '../app/utils/tracking-preview.ts'

const input = () => ({ clip_id: 'clip-a', source_asset_id: 'source-a', preview_asset_id: null,
  algorithm_signature: 'current-face-signature',
  start_ms: 1000, end_ms: 7000, crop_json: { mode: 'fill', tracking: 'face', x: 0.23, y: 0.67 } })
const frames = () => [{ t_ms: 0, x: 0.1, y: 0.2, cut: true }, { t_ms: 1000, x: 0.5, y: 0.6 },
  { t_ms: 2000, x: 0.9, y: 0.1, cut: true }, { t_ms: 3000, x: 0.3, y: 0.8 }]
const framing = () => ({ mode: 'face', method: 'yunet-face-v1', detected_frames: 36, total_frames: 36,
  detected_faces_max: 2, coverage: 1, fallback_reason: null, warnings: [], keyframes: frames() })
const succeeded = (source = input(), overrides = {}) => ({ id: 'job-a', project_id: 'project-a', kind: 'track_preview',
  stage: 'track_faces', status: 'succeeded', progress: 1,
  result_json: { tracking_spec: { ...source, analysis_version: 'tracking-preview-2', pipeline_version: 'test', source_checksum: 'source-checksum',
    preview_checksum: null, method: 'yunet-face-v1', sample_fps: 6, model_sha256: null }, framing: framing() }, ...overrides })
const approx = (actual, expected) => {
  assert.ok(Math.abs(actual.x - expected.x) < 1e-9, `${actual.x} != ${expected.x}`)
  assert.ok(Math.abs(actual.y - expected.y) < 1e-9, `${actual.y} != ${expected.y}`)
}

test('preview interpolates motion but holds the previous shot until a cut', () => {
  const fallback = { x: 0.23, y: 0.67 }
  approx(trackingPosition(frames(), 500, 4000, fallback), { x: 0.3, y: 0.4 })
  approx(trackingPosition(frames(), 1500, 4000, fallback), { x: 0.5, y: 0.6 })
  approx(trackingPosition(frames(), 1999, 4000, fallback), { x: 0.5, y: 0.6 })
  approx(trackingPosition(frames(), 2000, 4000, fallback), { x: 0.9, y: 0.1 })
  approx(trackingPosition(frames(), 2500, 4000, fallback), { x: 0.6, y: 0.45 })
})

test('pause or seek beyond the selected clip uses the stored manual fallback', () => {
  const fallback = { x: 0.23, y: 0.67 }
  assert.equal(trackingPosition(frames(), -1, 4000, fallback), fallback)
  assert.equal(trackingPosition(frames(), 4001, 4000, fallback), fallback)
  assert.equal(trackingPosition([], 1500, 4000, fallback), fallback)
  approx(trackingPosition(frames(), 4000, 4000, fallback), { x: 0.3, y: 0.8 })
  approx(trackingPosition([{ t_ms: 0, ...fallback }], 3000, 4000, fallback), fallback)
})

test('malformed keyframes cannot become CSS crop coordinates', () => {
  assert.equal(validTrackingFrames(frames(), 6000), true)
  assert.equal(validTrackingFrames([], 6000), false)
  assert.equal(validTrackingFrames([{ t_ms: 0, x: NaN, y: 0.5 }], 6000), false)
  assert.equal(validTrackingFrames([{ t_ms: 0, x: 1.1, y: 0.5 }], 6000), false)
  assert.equal(validTrackingFrames([{ t_ms: 0, x: 0.5, y: 0.5 }, { t_ms: 0, x: 0.7, y: 0.5 }], 6000), false)
  assert.equal(validTrackingFrames(frames(), 1000), false)
  assert.equal(validTrackingFrames([{ t_ms: 5, x: 0.5, y: 0.5 }], 6000), false)
  assert.equal(validTrackingFrames([{ t_ms: 0, x: 0.5, y: 0.5 }, { t_ms: 1.5, x: 0.7, y: 0.5 }], 6000), false)
  assert.equal(validTrackingFrames([{ t_ms: 0, x: 0.5, y: 0.5, cut: 'false' }], 6000), false)
  assert.equal(validTrackingFrames(Array.from({ length: 75 }, (_, i) => ({ t_ms: i, x: 0.5, y: 0.5 })), 6000), false)
  assert.equal(validTrackingFrames([null], 6000), false)
})

test('opening tracking or manual revisions never queues analysis automatically', () => {
  const state = new TrackingPreviewState()
  state.syncInput(input())
  assert.equal(state.submitting, false)
  assert.equal(state.job, null)
  assert.equal(state.framing, null)
  state.syncInput({ ...input(), crop_json: { mode: 'fill', x: 0.2, y: 0.5 } })
  assert.equal(state.begin(), null)
  assert.equal(trackingInputKey({ ...input(), crop_json: { ...input().crop_json, mode: 'fit' } }), null)
})

test('title and subtitle corrections preserve a matching analysis without mutating input', () => {
  const source = input()
  Object.freeze(source.crop_json)
  const state = new TrackingPreviewState()
  state.syncInput(source)
  const token = state.begin()
  assert.equal(state.accept(token, succeeded(source)), true)
  const result = state.framing
  assert.equal(state.syncInput({ ...source, title: 'Corrected title', cues: [{ text: 'Corrected speech' }] }), false)
  assert.equal(state.framing, result)
  assert.deepEqual(source.crop_json, { mode: 'fill', tracking: 'face', x: 0.23, y: 0.67 })
})

test('source, range, mode and fallback edits invalidate crop immediately and reject late responses', () => {
  const variants = [
    { ...input(), source_asset_id: 'source-b' },
    { ...input(), preview_asset_id: 'proxy-b' },
    { ...input(), algorithm_signature: 'new-model-signature' },
    { ...input(), start_ms: 1500 },
    { ...input(), end_ms: 6500 },
    { ...input(), crop_json: { ...input().crop_json, tracking: 'speaker' } },
    { ...input(), crop_json: { ...input().crop_json, x: 0.4 } },
    { ...input(), crop_json: { ...input().crop_json, y: 0.8 } },
    { ...input(), crop_json: { ...input().crop_json, mode: 'fit' } },
  ]
  for (const changed of variants) {
    const state = new TrackingPreviewState()
    state.syncInput(input())
    const token = state.begin()
    state.accept(token, succeeded())
    state.syncInput(changed)
    assert.equal(state.framing, null)
    assert.equal(state.accept(token, succeeded()), false)
    assert.equal(state.framing, null)
  }
})

test('a late queued response never attaches an obsolete job to the current input', () => {
  const state = new TrackingPreviewState()
  state.syncInput(input())
  const oldRequest = state.begin()
  state.syncInput({ ...input(), crop_json: { ...input().crop_json, x: 0.4 } })
  state.syncInput({ ...input(), crop_json: { ...input().crop_json, x: 0.45 } })
  assert.equal(state.invalidated, true)
  assert.equal(state.backgroundWork, true)
  assert.equal(state.accept(oldRequest, succeeded(input(), { status: 'queued', result_json: {} })), false)
  assert.equal(state.job, null)
  assert.equal(state.submitting, false)
})

test('cancelled jobs clear crop and can accept an explicitly retried attempt', () => {
  const state = new TrackingPreviewState()
  state.syncInput(input())
  const token = state.begin()
  state.accept(token, succeeded(input(), { status: 'running', result_json: {} }))
  state.accept(token, succeeded(input(), { status: 'cancel_requested', result_json: {} }))
  assert.equal(state.job.status, 'cancel_requested')
  assert.equal(state.framing, null)
  state.accept(token, succeeded(input(), { status: 'cancelled', result_json: {} }))
  assert.equal(state.job.status, 'cancelled')
  state.accept(token, succeeded(input(), { status: 'queued', result_json: {} }))
  state.accept(token, succeeded())
  assert.ok(state.framing)
})

test('cached results require the matching server spec and unmounted editors ignore results', () => {
  const state = new TrackingPreviewState()
  state.syncInput(input())
  let token = state.begin()
  state.accept(token, succeeded())
  const previous = state.framing
  token = state.begin()
  assert.equal(state.framing, previous)
  state.accept(token, succeeded())
  assert.ok(state.framing)
  const wrongSpec = succeeded({ ...input(), start_ms: 500 })
  assert.equal(trackingSpecMatches(input(), wrongSpec.result_json.tracking_spec), false)
  state.accept(token, wrongSpec)
  assert.equal(state.framing, null)
  assert.match(state.error, /tidak sesuai/)
  state.dispose()
  assert.equal(state.accept(token, succeeded()), false)
  assert.equal(state.framing, null)
})

test('explicit retry and cancellation supersede older in-flight status polls', () => {
  const state = new TrackingPreviewState()
  state.syncInput(input())
  const token = state.begin()
  state.accept(token, succeeded(input(), { status: 'running', result_json: {} }))
  assert.equal(state.acceptAction(succeeded(input(), { status: 'cancelled', result_json: {} })), true)
  assert.equal(state.accept(token, succeeded(input(), { status: 'running', result_json: {} })), false)
  const beforeRetry = state.token()
  assert.equal(state.acceptAction(succeeded(input(), { status: 'queued', result_json: {} })), true)
  assert.equal(state.accept(beforeRetry, succeeded(input(), { status: 'cancelled', result_json: {} })), false)
  assert.equal(state.job.status, 'queued')
  state.syncInput({ ...input(), start_ms: 1500 })
  assert.equal(state.acceptAction(succeeded()), false)
  assert.equal(state.job, null)
})

test('a completed no-face analysis is ready but keeps the explicit manual fallback notice', () => {
  const state = new TrackingPreviewState()
  state.syncInput(input())
  const token = state.begin()
  const job = succeeded()
  job.result_json.framing = { ...framing(), detected_frames: 0, coverage: 0,
    fallback_reason: 'Wajah tidak terdeteksi; posisi manual digunakan.', keyframes: [{ t_ms: 0, x: 0.23, y: 0.67 }] }
  state.accept(token, job)
  assert.ok(state.framing)
  assert.match(state.framing.fallback_reason, /posisi manual/)
})

test('obsolete or unsigned analysis cannot be restored after a model update', () => {
  for (const obsolete of [undefined, 'old-speaker-signature']) {
    const state = new TrackingPreviewState()
    state.syncInput(input())
    const token = state.begin()
    const job = succeeded()
    job.result_json.tracking_spec.algorithm_signature = obsolete
    assert.equal(trackingSpecMatches(input(), job.result_json.tracking_spec), false)
    assert.equal(state.accept(token, job), true)
    assert.equal(state.framing, null)
    assert.match(state.error, /Versi pelacakan berubah/)
  }
  const legacy = { ...input(), algorithm_signature: undefined }
  assert.equal(trackingSpecMatches(legacy, succeeded(legacy).result_json.tracking_spec), false)
})

test('changing the server model signature invalidates applied paths and in-flight responses', () => {
  const state = new TrackingPreviewState()
  state.syncInput(input())
  const oldToken = state.begin()
  state.accept(oldToken, succeeded())
  assert.ok(state.framing)
  const changed = { ...input(), algorithm_signature: 'new-face-signature' }
  assert.notEqual(trackingInputKey(input()), trackingInputKey(changed))
  state.syncInput(changed)
  assert.equal(state.framing, null)
  assert.equal(state.accept(oldToken, succeeded()), false)
  assert.equal(state.accept(state.begin(), succeeded(changed)), true)
  assert.ok(state.framing)
})
