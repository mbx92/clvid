import assert from 'node:assert/strict'
import test from 'node:test'
import { cropTracking, cropWithMode, cropWithTracking, framingNotices, speakerSwitchCount, trackingLabel } from '../app/utils/framing.ts'
import { elapsedLabel, jobElapsedMs } from '../app/utils/jobs.ts'
import { stageLabels } from '../app/utils/format.ts'

test('opening an existing crop leaves its revision unchanged and uses manual framing', () => {
  const original = Object.freeze({ mode: 'fill', x: 0.2, y: 0.65 })
  assert.equal(cropTracking(original), 'static')
  assert.equal(Object.hasOwn(original, 'tracking'), false)
  const edited = cropWithTracking(original, 'speaker')
  assert.equal(edited.tracking, 'speaker')
  assert.equal(edited.x, original.x)
  assert.equal(edited.y, original.y)
  assert.equal(Object.hasOwn(original, 'tracking'), false)
})

test('showing the entire video turns tracking off without changing fallback position', () => {
  const original = { mode: 'fill', tracking: 'face', x: 0.1, y: 0.8 }
  const fitted = cropWithMode(original, 'fit')
  assert.deepEqual(fitted, { mode: 'fit', tracking: 'static', x: 0.1, y: 0.8 })
  assert.equal(original.tracking, 'face')
  assert.equal(cropTracking({ ...original, mode: 'fit' }), 'static')
  assert.equal(cropWithTracking(fitted, 'speaker').tracking, 'static')
})

test('final exports expose a fallback once without presenting speaker estimates as certainty', () => {
  const reason = 'Wajah tidak terdeteksi; posisi manual digunakan.'
  assert.deepEqual(framingNotices({ fallback_reason: reason, warnings: [reason, '', 'Tinjau MP4 final.'] }), [reason, 'Tinjau MP4 final.'])
  assert.match(trackingLabel('speaker'), /perkiraan/)
  assert.equal(stageLabels.track_faces, 'Menganalisis gerak wajah')
})

test('elapsed processing time uses UTC timestamps and freezes at actual completion', () => {
  const now = Date.parse('2026-11-01T00:02:05Z')
  const started = { started_at: '2026-11-01T00:00:00', status: 'running' }
  assert.equal(jobElapsedMs(started, now), 125000)
  assert.equal(elapsedLabel(jobElapsedMs(started, now)), '2 mnt 5 dtk')
  assert.equal(jobElapsedMs({ ...started, status: 'succeeded', finished_at: '2026-11-01T00:00:30Z' }, now), 30000)
  assert.equal(jobElapsedMs({ ...started, status: 'cancel_requested' }, now), 125000)
})

test('queued retries and incomplete terminal timestamps do not invent elapsed work', () => {
  const now = Date.parse('2026-11-01T00:02:05Z')
  assert.equal(jobElapsedMs({ status: 'queued', started_at: '2026-11-01T00:00:00Z' }, now), null)
  assert.equal(jobElapsedMs({ status: 'succeeded', started_at: '2026-11-01T00:00:00Z' }, now), null)
  assert.equal(jobElapsedMs({ status: 'running', started_at: 'invalid' }, now), null)
  assert.equal(jobElapsedMs({ status: 'running', started_at: '2026-11-01T00:03:00Z' }, now), 0)
})

test('speaker switch counts distinguish a zero-switch result from missing legacy metadata', () => {
  const result = { mode: 'speaker', fallback_reason: null, warnings: [], speaker_switches: 0 }
  assert.equal(speakerSwitchCount(result), 0)
  assert.match(framingNotices(result)[0], /Tidak ada perpindahan pembicara/)
  assert.equal(speakerSwitchCount({ ...result, speaker_switches: 3 }), 3)
  assert.deepEqual(framingNotices({ ...result, speaker_switches: 3 }), [])
  for (const count of [undefined, -1, NaN, 1.5, '2']) {
    assert.equal(speakerSwitchCount({ ...result, speaker_switches: count }), null)
  }
  assert.equal(speakerSwitchCount({ ...result, mode: 'face' }), null)
})
