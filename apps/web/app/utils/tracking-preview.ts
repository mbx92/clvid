import type { Crop, FramingMetadata, Job, TrackingSpec } from '~/types/api'
import { cropTracking } from './framing.ts'

export interface TrackingPreviewInput {
  clip_id: string
  source_asset_id: string
  preview_asset_id: string | null
  algorithm_signature?: string | null
  start_ms: number
  end_ms: number
  crop_json: Crop
}
export interface PreviewRequestToken { generation: number; key: string }
type Position = { x: number; y: number }
type Keyframe = FramingMetadata['keyframes'][number]

export function trackingInputKey(input: TrackingPreviewInput | null): string | null {
  if (!input || !input.clip_id || !input.source_asset_id || input.end_ms <= input.start_ms || cropTracking(input.crop_json) === 'static') return null
  return JSON.stringify([input.clip_id, input.source_asset_id, input.preview_asset_id, input.start_ms, input.end_ms,
    input.crop_json.mode, cropTracking(input.crop_json), input.crop_json.x, input.crop_json.y, input.algorithm_signature || null])
}

export function trackingSpecMatches(input: TrackingPreviewInput, spec?: TrackingSpec): boolean {
  if (!spec || !input.algorithm_signature || input.algorithm_signature !== spec.algorithm_signature) return false
  return input.source_asset_id === spec.source_asset_id && input.preview_asset_id === spec.preview_asset_id &&
    input.start_ms === spec.start_ms && input.end_ms === spec.end_ms && spec.crop_json?.mode === 'fill' &&
    cropTracking(input.crop_json) === cropTracking(spec.crop_json) &&
    Math.abs(input.crop_json.x - spec.crop_json.x) < 0.000001 && Math.abs(input.crop_json.y - spec.crop_json.y) < 0.000001
}

export function validTrackingFrames(frames: Keyframe[], durationMs: number): boolean {
  const limit = Math.min(7202, Math.ceil(durationMs / 1000 * 12) + 2)
  return Number.isFinite(durationMs) && durationMs > 0 && Array.isArray(frames) && frames.length > 0 && frames.length <= limit && frames.every((frame, index) =>
    frame && Number.isInteger(frame.t_ms) && frame.t_ms >= 0 && frame.t_ms <= durationMs &&
    (index !== 0 || frame.t_ms === 0) && (frame.cut === undefined || typeof frame.cut === 'boolean') &&
    Number.isFinite(frame.x) && frame.x >= 0 && frame.x <= 1 &&
    Number.isFinite(frame.y) && frame.y >= 0 && frame.y <= 1 &&
    (index === 0 || frame.t_ms > frames[index - 1]!.t_ms))
}

/** A cut belongs to the next keyframe: hold the old shot until that timestamp. */
export function trackingPosition(frames: Keyframe[], localMs: number, durationMs: number, fallback: Position): Position {
  if (!frames.length || !Number.isFinite(localMs) || localMs < 0 || localMs > durationMs) return fallback
  const first = frames[0]!
  if (localMs <= first.t_ms) return { x: first.x, y: first.y }
  let low = 0; let high = frames.length - 1
  while (low < high) {
    const middle = Math.ceil((low + high) / 2)
    if (frames[middle]!.t_ms <= localMs) low = middle
    else high = middle - 1
  }
  const left = frames[low]!
  const right = frames[low + 1]
  if (!right || right.cut || right.t_ms <= left.t_ms) return { x: left.x, y: left.y }
  const amount = (localMs - left.t_ms) / (right.t_ms - left.t_ms)
  return { x: left.x + (right.x - left.x) * amount, y: left.y + (right.y - left.y) * amount }
}

/** Result ownership is local to the current input; server jobs can be shared across tabs. */
export class TrackingPreviewState {
  input: TrackingPreviewInput | null = null
  key: string | null = null
  job: Job | null = null
  framing: FramingMetadata | null = null
  submitting = false
  invalidated = false
  backgroundWork = false
  error = ''
  private generation = 0

  syncInput(input: TrackingPreviewInput | null): boolean {
    const key = trackingInputKey(input)
    if (key === this.key) return false
    const hadAnalysis = !!this.framing || !!this.job || this.submitting
    this.backgroundWork = this.backgroundWork || this.submitting || !!this.job && ['queued', 'running', 'cancel_requested'].includes(this.job.status)
    this.invalidated = (hadAnalysis || this.invalidated) && key !== null
    this.input = input ? { ...input, crop_json: { ...input.crop_json } } : null
    this.key = key
    this.generation++
    this.job = null
    this.framing = null
    this.error = ''
    this.submitting = false
    return true
  }

  begin(): PreviewRequestToken | null {
    if (!this.key) return null
    this.generation++
    this.submitting = true
    this.invalidated = false
    this.backgroundWork = false
    this.error = ''
    this.job = null
    return this.token()
  }

  token(): PreviewRequestToken | null { return this.key ? { generation: this.generation, key: this.key } : null }
  isCurrent(token: PreviewRequestToken): boolean { return token.generation === this.generation && token.key === this.key }

  accept(token: PreviewRequestToken, job: Job): boolean {
    if (!this.isCurrent(token)) return false
    this.submitting = false
    this.job = job
    this.error = ''
    if (job.status !== 'succeeded') { this.framing = null; return true }
    const result = job.result_json
    const duration = this.input!.end_ms - this.input!.start_ms
    if (!result?.framing || !trackingSpecMatches(this.input!, result.tracking_spec) ||
        result.framing.mode !== cropTracking(this.input!.crop_json) || !validTrackingFrames(result.framing.keyframes, duration)) {
      this.framing = null
      this.error = !this.input!.algorithm_signature || this.input!.algorithm_signature !== result?.tracking_spec?.algorithm_signature
        ? 'Versi pelacakan berubah. Muat ulang klip, lalu jalankan analisis preview kembali.'
        : 'Hasil analisis tidak sesuai sumber atau pengaturan preview. Jalankan analisis kembali.'
      return true
    }
    this.framing = result.framing
    return true
  }

  fail(token: PreviewRequestToken, message: string): void {
    if (!this.isCurrent(token)) return
    this.submitting = false
    this.error = message
  }

  acceptAction(job: Job): boolean {
    if (!this.key || this.job?.id !== job.id) return false
    // Cancel/retry responses supersede GETs started before that explicit action.
    this.generation++
    return this.accept(this.token()!, job)
  }

  dispose(): void {
    this.generation++
    this.key = null
    this.input = null
    this.job = null
    this.framing = null
    this.submitting = false
  }
}
