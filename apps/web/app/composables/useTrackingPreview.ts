import type { ComputedRef } from 'vue'
import type { Job } from '~/types/api'
import { isActive } from '~/utils/format'
import { TrackingPreviewState, trackingInputKey, type TrackingPreviewInput } from '~/utils/tracking-preview'

export function useTrackingPreview(input: ComputedRef<TrackingPreviewInput | null>) {
  const api = useApi()
  const state = shallowReactive(new TrackingPreviewState())
  const requests = new Set<AbortController>()
  let disposed = false
  const polling = new Map<string, Promise<void>>()
  watch(() => trackingInputKey(input.value), () => state.syncInput(input.value), { immediate: true, flush: 'sync' })

  const analyze = async () => {
    if (disposed || !input.value || state.submitting || state.job && isActive(state.job.status)) return
    const requestInput = { ...input.value, crop_json: { ...input.value.crop_json } }
    const token = state.begin()
    if (!token) return
    const controller = new AbortController()
    requests.add(controller)
    try {
      const job = await api<Job>(`/clips/${requestInput.clip_id}/tracking-preview`, {
        method: 'POST', signal: controller.signal,
        headers: { 'Idempotency-Key': idempotencyKey() },
        body: { start_ms: requestInput.start_ms, end_ms: requestInput.end_ms, crop_json: requestInput.crop_json },
      })
      state.accept(token, job)
    } catch (error) { if (!controller.signal.aborted) state.fail(token, errorMessage(error)) }
    finally { requests.delete(controller) }
  }

  const refresh = async () => {
    if (disposed || !state.job || !state.token()) return
    const jobId = state.job.id
    const token = state.token()!
    const pollKey = `${token.generation}:${jobId}`
    if (polling.has(pollKey)) return polling.get(pollKey)
    const controller = new AbortController()
    requests.add(controller)
    const request = (async () => {
      try { state.accept(token, await api<Job>(`/jobs/${jobId}`, { signal: controller.signal })) }
      catch (error) { if (!controller.signal.aborted) state.fail(token, errorMessage(error)) }
      finally { requests.delete(controller); polling.delete(pollKey) }
    })()
    polling.set(pollKey, request)
    return request
  }

  usePolling(refresh, () => !!state.job && isActive(state.job.status))
  onBeforeUnmount(() => {
    disposed = true
    state.dispose()
    for (const request of requests) request.abort()
    requests.clear()
    polling.clear()
  })
  return { state, analyze, refresh, acceptAction: (job: Job) => state.acceptAction(job) }
}
