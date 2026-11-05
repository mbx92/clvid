<script setup lang="ts">
import { tabsKeydown } from '~/utils/accessibility'
import { repairSubtitles } from '~/utils/repair-subtitles'
import { captionLayout, orderedCues } from '~/utils/subtitles'
import { alignHighlightWords, alignWords } from '~/utils/word-captions'
import { captionAppearance, captionMotion } from '~/utils/subtitle-style'
import { effectsError, retimeEffects } from '~/utils/remotion-effects'
import { cropTracking, cropWithMode, cropWithTracking, trackingLabel, trackingOptions } from '~/utils/framing'
import { trackingPosition, type TrackingPreviewInput } from '~/utils/tracking-preview'
import { defaultGaming, validGaming, GAMING_LABEL } from '~/utils/gaming'
import type { Clip, Crop, Cue, Export, GamingLayout, Job, Page, RemotionEffects, Revision, SourceWord, TrackingMode } from '~/types/api'
import { isActive, parseTimecode, timecode } from '~/utils/format'
const api = useApi()
const route = useRoute()
const clip = ref<Clip | null>(null)
const draft = ref<Revision | null>(null)
const saved = ref('')
const error = ref('')
const loading = ref(true)
const saving = ref(false)
const saveState = ref('Tersimpan')
const exportList = usePaginatedList<Export>((page, pageSize) => api<Page<Export>>(`/projects/${clip.value!.project_id}/exports`, { query: { clip_id: clip.value!.id, page, page_size: pageSize } }))
const { items: exports, total: exportTotal, loading: exportsLoading, hasMore: moreExports } = exportList
const exportOpen = ref(false)
const exportBusy = ref(false)
const exportError = ref('')
const resolution = ref(1080)
const conflictOpen = ref(false)
const trimOpen = ref(false)
const leaveOpen = ref(false)
const leaving = ref(false)
const leaveTo = ref('')
const trimLoss = ref(0)
const pendingBounds = ref<{ start: number; end: number } | null>(null)
const tab = ref('subtitle')
const styleTab = ref('framing')
const mobilePane = ref('preview')
const previewHelp = ref(false)
const maxClipMs = computed(() => clip.value?.limits?.max_clip_ms || 180000)
const video = ref<HTMLVideoElement | null>(null)
const gamingPreview = ref<{ draw: () => void } | null>(null)
const gamingSettings = ref<{ draw: () => void } | null>(null)
const decodedSize = ref({ width: 0, height: 0 })
const playhead = ref(0)
const playing = ref(false)
const startInput = ref('')
const endInput = ref('')
const trimError = ref('')
const sourceDuration = computed(() => clip.value?.media_duration_ms || 0)
const clipDuration = computed(() => draft.value ? draft.value.end_ms - draft.value.start_ms : 0)
const remotionVideoStyle = ref({})
const draftEffectsError = computed(() => effectsError(draft.value?.subtitle_style_json.remotion_effects, clipDuration.value))
watch(() => draft.value?.subtitle_style_json.renderer, () => { remotionVideoStyle.value = {} })
function updateEffects(effects: RemotionEffects) { if (draft.value) draft.value.subtitle_style_json = { ...draft.value.subtitle_style_json, renderer: 'remotion', remotion_effects: effects } }
const sourceUrl = computed(() => { const asset = clip.value?.preview_asset || clip.value?.source_asset; return asset ? `/api/v1/assets/${asset.id}/content` : '' })
const dirty = computed(() => !!draft.value && JSON.stringify(draft.value) !== saved.value)
const activeCue = computed(() => { const local = playhead.value - (draft.value?.start_ms || 0); return orderedCues(draft.value?.cues || []).find(cue => local >= cue.start_ms && local < cue.end_ms) })
const cueLayout = (text: string) => { const s = draft.value?.subtitle_style_json; return captionLayout(s?.uppercase ? text.toUpperCase() : text, s?.font_size || 52, s?.auto_fit ?? true) }
const timingWords = ref<SourceWord[]>([])
const timingError = ref('')
const subtitleJob = ref<Job | null>(null)
const subtitleSubmitting = ref(false)
const subtitleLoading = ref(false)
const subtitleError = ref('')
const subtitleMessage = ref('')
const subtitleResultPending = ref(false)
const subtitleLanguage = ref('auto')
const subtitleAudioOpen = ref(false)
const subtitleAudioError = ref('')
const replacesSubtitles = computed(() => !!(clip.value?.revision.cues.length || draft.value?.cues.length))
const subtitleBusy = computed(() => subtitleSubmitting.value || subtitleLoading.value || !!subtitleJob.value && isActive(subtitleJob.value.status))
const subtitleRequests = new Set<AbortController>()
let subtitleDisposed = false
let subtitlePolling = false
let subtitleExpectedRevision = 0
let subtitleGeneration = 0
let timingRequest = 0
const alignedWords = computed(() => alignWords(draft.value?.cues || [], timingWords.value, draft.value?.start_ms || 0))
const podcastTemplate = computed(() => draft.value?.subtitle_style_json.renderer === 'remotion' && draft.value?.subtitle_style_json.remotion_template === 'podcast')
const highlightedWords = computed(() => alignHighlightWords(draft.value?.cues || [], timingWords.value, draft.value?.start_ms || 0))
const missingWordTiming = computed(() => podcastTemplate.value ? highlightedWords.value.missing : alignedWords.value.missing)
const podcastTimingError = computed(() => podcastTemplate.value && draft.value?.subtitle_style_json.enabled && (missingWordTiming.value || timingError.value)
  ? 'Highlight kata belum memiliki timestamp yang cocok. Buat ulang subtitle dari suara, cocokkan teks dengan transkrip, atau pilih template lain.' : '')
async function openAudioRecovery() {
  if (!clip.value || !draft.value || saving.value || subtitleBusy.value || exportBusy.value) return
  subtitleAudioError.value = ''
  exportOpen.value = false
  // Finish closing the export dialog before opening another focus trap.
  await nextTick()
  if (!subtitleDisposed) subtitleAudioOpen.value = true
}
const displayCues = computed(() => orderedCues(podcastTemplate.value ? highlightedWords.value.cues : draft.value?.subtitle_style_json.display_mode === 'words' ? alignedWords.value.events : draft.value?.cues || []))
const displayCue = computed(() => { const local = playhead.value - (draft.value?.start_ms || 0); return displayCues.value.find(cue => local >= cue.start_ms && local < cue.end_ms) })
const activeCaption = computed(() => cueLayout(displayCue.value?.text || ''))
watch(() => [draft.value?.start_ms, draft.value?.end_ms], async () => {
  const request = ++timingRequest
  timingError.value = ''
  if (!draft.value || !clip.value) return
  if (draft.value.start_ms === clip.value.revision.start_ms && draft.value.end_ms === clip.value.revision.end_ms) {
    timingWords.value = clip.value.revision.source_words || []; return
  }
  timingWords.value = []
  try {
    const result = await api<{ source_words: SourceWord[] }>(`/clips/${clip.value.id}/subtitle-words`, { query: { start_ms: draft.value.start_ms, end_ms: draft.value.end_ms } })
    if (request === timingRequest) timingWords.value = result.source_words
  } catch (e) { if (request === timingRequest) timingError.value = errorMessage(e) }
})
const captionStyle = computed(() => draft.value ? captionAppearance(draft.value.subtitle_style_json) : {})
const captionAnimation = computed(() => draft.value && displayCue.value ? captionMotion(draft.value.subtitle_style_json, playhead.value - draft.value.start_ms - displayCue.value.start_ms, displayCue.value.end_ms - displayCue.value.start_ms) : {})
const oversizedCues = computed(() => draft.value?.subtitle_style_json.enabled ? displayCues.value.filter(cue => cueLayout(cue.text).tooLong).length : 0)
const subtitleRepair = ref<ReturnType<typeof repairSubtitles> | null>(null)
const repairBase = ref('')
function proposeSubtitleRepair() {
  if (!draft.value || saving.value) return
  try {
    subtitleRepair.value = repairSubtitles(draft.value.cues, draft.value.subtitle_style_json, timingWords.value, draft.value.start_ms)
    repairBase.value = JSON.stringify(draft.value)
    exportOpen.value = false
  } catch (e) {error.value = errorMessage(e)}
}
function applySubtitleRepair() {
  if (!draft.value || !subtitleRepair.value || saving.value || JSON.stringify(draft.value) !== repairBase.value) return
  const result = subtitleRepair.value
  draft.value.cues = result.cues
  draft.value.subtitle_style_json = result.style
  subtitleRepair.value = null; exportError.value = ''; tab.value = 'subtitle'
  subtitleMessage.value = 'Ukuran subtitle telah disesuaikan' + (result.splitCount ? ` dan ${result.splitCount} cue panjang dipecah` : '') + '. Tinjau preview lalu simpan perubahan.'
}
const enlarged = computed(() => { const metadata = clip.value?.source_asset?.metadata; return metadata && Number(metadata.display_width || metadata.width) < resolution.value })
const style = computed(() => draft.value?.subtitle_style_json)
const tracking = computed<TrackingMode>({
  get: () => cropTracking(draft.value?.crop_json),
  set: value => { if (draft.value) draft.value.crop_json = cropWithTracking(draft.value.crop_json, value) },
})
const framingMode = computed<Crop['mode']>({
  get: () => draft.value?.crop_json.mode || 'fill',
  set: value => { if (draft.value) draft.value.crop_json = cropWithMode(draft.value.crop_json, value) },
})
const gaming = computed<GamingLayout>({
  get: () => draft.value?.crop_json.gaming || defaultGaming(),
  set: value => { if (draft.value?.crop_json.mode === 'gaming') draft.value.crop_json.gaming = value },
})
const sourceSize = computed(() => {
  const metadata = clip.value?.source_asset?.metadata
  return { width: Number(metadata?.display_width || metadata?.width || decodedSize.value.width),
    height: Number(metadata?.display_height || metadata?.height || decodedSize.value.height) }
})
function redrawGaming() { gamingPreview.value?.draw(); gamingSettings.value?.draw() }
watch(framingMode, () => { void nextTick(redrawGaming) }, { flush: 'post' })
const trackingInput = computed<TrackingPreviewInput | null>(() => {
  if (!draft.value || !clip.value?.source_asset) return null
  return { clip_id: clip.value.id, source_asset_id: clip.value.source_asset.id, preview_asset_id: clip.value.preview_asset?.id || null,
    algorithm_signature: tracking.value === 'static' ? null : clip.value.tracking_signatures?.[tracking.value] || null,
    start_ms: draft.value.start_ms, end_ms: draft.value.end_ms, crop_json: { ...draft.value.crop_json } }
})
const previewTracking = useTrackingPreview(trackingInput)
const trackingAnalysis = previewTracking.state
const trackingReady = computed(() => !!trackingAnalysis.framing)
const trackingBusy = computed(() => trackingAnalysis.submitting || !!trackingAnalysis.job && isActive(trackingAnalysis.job.status))
const videoPosition = computed(() => {
  const fallback = { x: draft.value?.crop_json.x ?? 0.5, y: draft.value?.crop_json.y ?? 0.5 }
  if (!draft.value || tracking.value === 'static' || !trackingAnalysis.framing) return fallback
  return trackingPosition(trackingAnalysis.framing.keyframes, playhead.value - draft.value.start_ms, clipDuration.value, fallback)
})
const subtitlePosition = computed(() => style.value?.position === 'top' ? { top: `${style.value.safe_margin * 100}%` } : { bottom: `${(style.value?.safe_margin || 0.15) * 100}%` })
const adopt = (value: Clip) => { ++timingRequest; timingError.value = ''; clip.value = value; draft.value = JSON.parse(JSON.stringify(value.revision)); timingWords.value = value.revision.source_words || []; saved.value = JSON.stringify(draft.value); startInput.value = timecode(value.revision.start_ms, true); endInput.value = timecode(value.revision.end_ms, true); saveState.value = 'Tersimpan'; playhead.value = value.revision.start_ms; subtitleResultPending.value = false }
function applyTranslation(cues: Cue[], revision: number) {
  if (!draft.value || !clip.value || dirty.value || saving.value || subtitleBusy.value || clip.value.revision.revision !== revision) return
  draft.value.cues = cues
  draft.value.subtitle_style_json = { ...draft.value.subtitle_style_json, enabled: true, display_mode: 'sentence',
    ...(draft.value.subtitle_style_json.remotion_template === 'podcast' ? {remotion_template: 'minimal' as const} : {}) }
  subtitleMessage.value = 'Terjemahan diterapkan ke draft. Simpan untuk memakai subtitle Indonesia pada ekspor MP4 dan SRT.'
  tab.value = 'subtitle'
}
const load = async () => { try { const result = await api<Clip>(`/clips/${route.params.id}`); adopt(result); await loadExports(); error.value = '' } catch (e) { error.value = errorMessage(e) } finally { loading.value = false } }
const loadExports = async () => { if (clip.value) await exportList.refresh() }
onMounted(load)
usePolling(loadExports, () => exports.value.some(e => isActive(e.job?.status || e.status)))
const acceptSubtitleJob = async (job: Job) => {
  if (subtitleDisposed) return
  subtitleJob.value = job
  subtitleError.value = ''
  if (job.status !== 'succeeded' || !clip.value) return
  subtitleMessage.value = job.result_json?.message || 'Pemeriksaan audio selesai.'
  subtitleLoading.value = true
  const controller = new AbortController()
  subtitleRequests.add(controller)
  try {
    const result = await api<Clip>(`/clips/${clip.value.id}`, { signal: controller.signal })
    if (subtitleDisposed) return
    // A completion may arrive while the user edits or saves another revision.
    // Never replace that draft, including changes made during this GET.
    if (dirty.value || saving.value || clip.value.revision.revision !== subtitleExpectedRevision) {
      subtitleResultPending.value = result.revision.revision !== clip.value.revision.revision
      return
    }
    const current = playhead.value
    adopt(result)
    playhead.value = current
  } catch (e) {
    if (!controller.signal.aborted) { subtitleError.value = errorMessage(e); subtitleResultPending.value = true }
  } finally { subtitleRequests.delete(controller); subtitleLoading.value = false }
}
const generateSubtitles = async (replaceExisting = false) => {
  if (!clip.value || !draft.value || dirty.value || saving.value || subtitleBusy.value) return
  if (!replaceExisting && (draft.value.cues.length || clip.value.revision.cues.length)) {
    subtitleAudioOpen.value = true
    return
  }
  subtitleAudioOpen.value = false
  tab.value = 'subtitle'
  const generation = ++subtitleGeneration
  subtitleSubmitting.value = true
  subtitleJob.value = null
  subtitleError.value = ''; subtitleMessage.value = ''; subtitleResultPending.value = false
  subtitleExpectedRevision = clip.value.revision.revision
  const controller = new AbortController()
  subtitleRequests.add(controller)
  try {
    const job = await api<Job>(`/clips/${clip.value.id}/subtitles/generate`, {
      method: 'POST', signal: controller.signal, headers: { 'Idempotency-Key': idempotencyKey() },
      body: { expected_revision: subtitleExpectedRevision, language: subtitleLanguage.value, ...(replaceExisting ? { replace_existing: true } : {}) },
    })
    if (generation === subtitleGeneration) await acceptSubtitleJob(job)
  } catch (e) { if (!controller.signal.aborted && generation === subtitleGeneration) subtitleError.value = errorMessage(e) }
  finally { subtitleRequests.delete(controller); subtitleSubmitting.value = false }
}
const refreshSubtitleJob = async () => {
  if (subtitleDisposed || subtitlePolling || !subtitleJob.value) return
  subtitlePolling = true
  const generation = subtitleGeneration
  const jobId = subtitleJob.value.id
  const controller = new AbortController()
  subtitleRequests.add(controller)
  try {
    const job = await api<Job>(`/jobs/${jobId}`, { signal: controller.signal })
    if (generation === subtitleGeneration && subtitleJob.value?.id === jobId) await acceptSubtitleJob(job)
  } catch (e) { if (!controller.signal.aborted && generation === subtitleGeneration) subtitleError.value = errorMessage(e) }
  finally { subtitleRequests.delete(controller); subtitlePolling = false }
}
const acceptSubtitleAction = async (job: Job) => {
  // A poll started before cancel/retry must not restore the previous status.
  subtitleGeneration++
  await acceptSubtitleJob(job)
}
usePolling(refreshSubtitleJob, () => !!subtitleJob.value && isActive(subtitleJob.value.status))
onBeforeUnmount(() => {
  subtitleDisposed = true
  for (const request of subtitleRequests) request.abort()
  subtitleRequests.clear()
})
watch(dirty, value => { if (value) saveState.value = 'Belum tersimpan' })
const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => { if (import.meta.client) window.removeEventListener('beforeunload', beforeUnload) })
onBeforeRouteLeave(to => { if (dirty.value && !leaving.value) { leaveTo.value = to.fullPath; leaveOpen.value = true; return false } })
const discardLeave = async () => { leaving.value = true; leaveOpen.value = false; await navigateTo(leaveTo.value) }
const validateDraft = () => {
  if (!draft.value) return false
  if (draftEffectsError.value) { error.value = draftEffectsError.value; return false }
  if (!draft.value.title.trim()) { error.value = 'Judul klip tidak boleh kosong.'; return false }
  if (draft.value.crop_json.mode === 'gaming' && !validGaming(draft.value.crop_json.gaming)) { error.value = 'Periksa area facecam dan gameplay: keduanya harus berada di dalam video.'; return false }
  for (const cue of draft.value.cues) { if (!cue.text.trim() || cue.start_ms < 0 || cue.end_ms <= cue.start_ms || cue.end_ms > clipDuration.value) { error.value = 'Periksa subtitle: teks wajib diisi, awal harus sebelum akhir, dan waktunya berada di dalam klip.'; return false } }
  return true
}
const save = async (onConflict?: () => Promise<void>) => {
  if (!draft.value || !clip.value || !validateDraft()) return false
  saving.value = true; saveState.value = 'Menyimpan…'; error.value = ''
  try {
    const d = draft.value
    const result = await api<Clip>(`/clips/${clip.value.id}`, { method: 'PATCH', body: { expected_revision: clip.value.revision.revision, title: d.title, start_ms: d.start_ms, end_ms: d.end_ms, crop_json: d.crop_json, subtitle_style_json: d.subtitle_style_json, cues: d.cues.map(({ start_ms, end_ms, text }) => ({ start_ms, end_ms, text })) } })
    const current = playhead.value; adopt(result); playhead.value = current; saveState.value = 'Tersimpan'; return true
  } catch (e: any) { saveState.value = 'Gagal menyimpan'; if (e.status === 409 || e.statusCode === 409) { if (onConflict) await onConflict(); else conflictOpen.value = true } else error.value = errorMessage(e); return false } finally { saving.value = false }
}
const saveAndLeave = async () => { if (await save()) { leaving.value = true; leaveOpen.value = false; await navigateTo(leaveTo.value) } }
const saveAndGenerateSubtitles = async () => {
  if (!clip.value || !draft.value || saving.value || subtitleBusy.value) return
  subtitleAudioError.value = ''
  if (dirty.value && !await save(async () => {
    subtitleAudioOpen.value = false
    await nextTick()
    if (!subtitleDisposed) conflictOpen.value = true
  })) {
    if (!conflictOpen.value) subtitleAudioError.value = error.value || 'Perubahan belum berhasil disimpan. Coba kembali sebelum membuat subtitle.'
    return
  }
  if (!subtitleDisposed) await generateSubtitles(replacesSubtitles.value)
}
const togglePlay = () => { if (!video.value || !draft.value) return; if (video.value.paused) { if (video.value.currentTime * 1000 < draft.value.start_ms || video.value.currentTime * 1000 >= draft.value.end_ms - 80) video.value.currentTime = draft.value.start_ms / 1000; void video.value.play().catch(() => { error.value = 'Video tidak dapat diputar. Periksa apakah preview sudah siap.' }) } else video.value.pause() }
const seek = (ms: number) => { if (video.value) video.value.currentTime = ms / 1000; playhead.value = ms }
const onFrame = (milliseconds: number) => {
  if (!video.value || !draft.value) return
  playhead.value = milliseconds
  redrawGaming()
  if (playing.value && milliseconds >= draft.value.end_ms) {
    playing.value = false
    video.value.pause()
    frameClock.stop()
    seek(draft.value.end_ms)
  }
}
const frameClock = useVideoFrameClock(video, onFrame)
const onTime = () => {
  if (!playing.value || typeof video.value?.requestVideoFrameCallback !== 'function' || document.hidden) frameClock.sync()
}
const onPlay = () => { playing.value = true; frameClock.start() }
const onPause = () => { playing.value = false; frameClock.stop(); frameClock.sync() }
const onSeeking = () => { frameClock.stop(); frameClock.sync() }
const onSeeked = () => { frameClock.sync(); if (!video.value?.paused) frameClock.start() }
const onLoaded = () => { if (video.value) decodedSize.value = { width: video.value.videoWidth, height: video.value.videoHeight }; if (draft.value) seek(draft.value.start_ms) }
const applyBounds = (start: number, end: number) => {
  if (!draft.value) return
  const oldStart = draft.value.start_ms
  const adjustedEffects = retimeEffects(draft.value.subtitle_style_json.remotion_effects, oldStart, start, end)
  if (adjustedEffects) draft.value.subtitle_style_json.remotion_effects = adjustedEffects
  draft.value.cues = draft.value.cues.map(cue => ({ ...cue, start_ms: Math.max(0, oldStart + cue.start_ms - start), end_ms: Math.min(end - start, oldStart + cue.end_ms - start) })).filter(cue => cue.end_ms > cue.start_ms)
  draft.value.start_ms = start; draft.value.end_ms = end
  startInput.value = timecode(start, true); endInput.value = timecode(end, true)
  seek(Math.max(start, Math.min(playhead.value, end))); trimOpen.value = false; pendingBounds.value = null; trimError.value = ''
}
const proposeBounds = () => {
  if (!draft.value) return
  const start = parseTimecode(startInput.value); const end = parseTimecode(endInput.value)
  if (start === null || end === null || start < 0 || end > sourceDuration.value || end - start < 5000 || end - start > maxClipMs.value) { trimError.value = 'Batas klip harus berada di dalam video, dengan durasi 5–180 detik.'; return }
  trimLoss.value = draft.value.cues.filter(cue => draft.value!.start_ms + cue.end_ms <= start || draft.value!.start_ms + cue.start_ms >= end).length
  if (trimLoss.value) { pendingBounds.value = { start, end }; trimOpen.value = true } else applyBounds(start, end)
}
const timelineBounds = (start: number, end: number) => { startInput.value = timecode(start, true); endInput.value = timecode(end, true); proposeBounds() }
const useCurrent = (edge: 'start' | 'end') => { if (edge === 'start') startInput.value = timecode(playhead.value, true); else endInput.value = timecode(playhead.value, true); proposeBounds() }
const keyboard = (event: KeyboardEvent) => {
  const el = event.target as HTMLElement
  if (el.closest('input,textarea,button,[role="dialog"],[contenteditable="true"]') || event.ctrlKey || event.altKey || event.metaKey) return
  if (event.code === 'Space') { event.preventDefault(); togglePlay() }
  if (event.key.toLowerCase() === 'i') { event.preventDefault(); useCurrent('start') }
  if (event.key.toLowerCase() === 'o') { event.preventDefault(); useCurrent('end') }
}
const addCue = () => { if (!draft.value) return; const start = Math.max(0, Math.min(clipDuration.value - 1000, playhead.value - draft.value.start_ms)); draft.value.cues.push({ start_ms: start, end_ms: Math.min(clipDuration.value, start + 3000), text: '' }); draft.value.cues.sort((a, b) => a.start_ms - b.start_ms) }
const cueTime = (cue: Cue, edge: 'start_ms' | 'end_ms', event: Event) => { const value = parseTimecode((event.target as HTMLInputElement).value); if (value !== null) cue[edge] = value; else { error.value = 'Format waktu subtitle tidak valid. Gunakan mm:ss.mmm.'; (event.target as HTMLInputElement).value = timecode(cue[edge], true) } }
const startExport = async () => {
  if (!clip.value) return
  if (oversizedCues.value) { exportError.value = 'Ada subtitle terlalu panjang. Gunakan Sesuaikan subtitle, lalu simpan sebelum ekspor.'; return }
  exportBusy.value = true; exportError.value = ''
  try { await api(`/clips/${clip.value.id}/exports`, { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey() }, body: { revision: clip.value.revision.revision, resolution: resolution.value } }); exportOpen.value = false; tab.value = 'exports'; await loadExports() } catch (e) { exportError.value = errorMessage(e) } finally { exportBusy.value = false }
}
const exportClick = () => { exportError.value = ''; exportOpen.value = true }
</script>
<template>
  <div class="editor-page fixed-workspace" :class="`mobile-${mobilePane}`" @keydown="keyboard">
    <InlineError :message="error || draftEffectsError"><button v-if="draftEffectsError" class="text-button" @click="tab = 'style'; styleTab = 'effects'; mobilePane = 'tools'">Periksa efek video</button></InlineError>
    <p v-if="loading" class="loading-text" role="status">Memuat editor…</p>
    <template v-if="draft && clip">
      <header class="editor-header"><div class="editor-heading"><NuxtLink :to="`/projects/${clip.project_id}`" class="icon-button" aria-label="Kembali ke proyek"><AppIcon name="ArrowLeft" /></NuxtLink><div><label class="sr-only" for="clip-title">Judul klip</label><input id="clip-title" v-model="draft.title" :disabled="saving" class="title-input" maxlength="200" /><div class="row gap-2 small"><span>Revisi {{ clip.revision.revision }}</span><span class="save-status" :class="{ unsaved: dirty }" role="status">{{ saveState }}</span></div></div></div><div class="header-actions"><button class="button secondary" :disabled="saving || !dirty || !!draftEffectsError" @click="save()"><AppIcon name="Save" />{{ saving ? 'Menyimpan…' : 'Simpan' }}</button><button class="button primary" :disabled="saving" @click="exportClick"><AppIcon name="Download" />Ekspor</button></div></header>
      <div class="workspace-switch" role="group" aria-label="Tampilan workspace"><button :aria-pressed="mobilePane === 'preview'" @click="mobilePane = 'preview'">Preview</button><button :aria-pressed="mobilePane === 'tools'" @click="mobilePane = 'tools'">Alat editor</button></div>
      <div class="editor-grid" :inert="saving || undefined" :aria-busy="saving">
        <section class="editor-workspace" aria-label="Preview dan batas klip" tabindex="0"><div class="player-matte"><div class="portrait-frame" :style="{ '--subtitle-size': `${activeCaption.fontSize / 10.8}cqw` }"><div class="framing-preview" :style="remotionVideoStyle"><video ref="video" :src="sourceUrl" :class="{ 'gaming-decoder': framingMode === 'gaming' }" :aria-hidden="framingMode === 'gaming' || undefined" preload="metadata" playsinline :style="{ objectFit: draft.crop_json.mode === 'fill' ? 'cover' : 'contain', objectPosition: `${videoPosition.x * 100}% ${videoPosition.y * 100}%` }" @loadedmetadata="onLoaded" @loadeddata="redrawGaming" @timeupdate="onTime" @play="onPlay" @pause="onPause" @ended="onPause" @seeking="onSeeking" @seeked="onSeeked" /><GamingPreview v-if="framingMode === 'gaming'" ref="gamingPreview" :video="video" :layout="gaming" :source-width="sourceSize.width" :source-height="sourceSize.height" :output-width="resolution" /></div><RemotionCaption v-if="draft.subtitle_style_json.renderer === 'remotion'" :cues="displayCues" :subtitle-style="draft.subtitle_style_json" :duration-ms="clipDuration" :time-ms="playhead - draft.start_ms" @video-style="remotionVideoStyle = $event" /><div v-else-if="draft.subtitle_style_json.enabled && displayCue && !activeCaption.tooLong" class="caption-preview" :class="{ 'caption-box': draft.subtitle_style_json.background }" :style="{ ...subtitlePosition, ...captionStyle, ...captionAnimation }">{{ activeCaption.text }}</div></div><span class="preview-label">Preview · 9:16</span></div>
          <div class="playback-bar"><button class="icon-button playback-button" :aria-label="playing ? 'Jeda video' : 'Putar video'" @click="togglePlay"><AppIcon :name="playing ? 'Pause' : 'Play'" :size="20" /></button><span class="timecode">{{ timecode(playhead, true) }}</span><span class="muted small">/ {{ timecode(sourceDuration) }}</span><span class="playback-help">Space putar/jeda · I masuk · O keluar</span></div>
          <div class="timeline"><label class="sr-only" for="playhead">Posisi playback video sumber</label><input id="playhead" type="range" min="0" :max="sourceDuration" step="10" :value="playhead" @input="seek(Number(($event.target as HTMLInputElement).value))" /><div class="selected-range" :style="{ left: `${draft.start_ms / sourceDuration * 100}%`, width: `${clipDuration / sourceDuration * 100}%` }" /><div class="time-ruler"><span>{{ timecode(0) }}</span><span>{{ timecode(sourceDuration / 2) }}</span><span>{{ timecode(sourceDuration) }}</span></div></div>
          <div class="trim-controls"><div><label for="trim-start">Masuk</label><input id="trim-start" v-model="startInput" class="timecode" inputmode="decimal" /><button class="text-button small" @click="useCurrent('start')">Gunakan posisi sekarang</button></div><div><label for="trim-end">Keluar</label><input id="trim-end" v-model="endInput" class="timecode" inputmode="decimal" /><button class="text-button small" @click="useCurrent('end')">Gunakan posisi sekarang</button></div><div class="trim-summary"><span class="muted small">Durasi klip</span><strong class="timecode">{{ timecode(clipDuration, true) }}</strong><button class="button secondary small-button" @click="proposeBounds">Terapkan batas</button></div></div><InlineError :message="trimError" />
          <div class="editor-footer"><NuxtLink :to="`/projects/${clip.project_id}`" class="text-button source-link">Buka transkrip sumber</NuxtLink><button class="text-button" @click="previewHelp = true">Panduan preview</button></div>
        </section>
        <aside class="editor-panel"><div class="tabs" role="tablist" @keydown="tabsKeydown" aria-label="Panel editor"><button id="editor-tab-subtitle" class="tab" :class="{ active: tab === 'subtitle' }" role="tab" :aria-selected="tab === 'subtitle'" aria-controls="editor-panel-content" @click="tab = 'subtitle'">Subtitle <span class="tab-count">{{ draft.cues.length }}</span></button><button id="editor-tab-style" class="tab" :class="{ active: tab === 'style' }" role="tab" :aria-selected="tab === 'style'" aria-controls="editor-panel-content" @click="tab = 'style'">Tampilan</button><button id="editor-tab-timeline" class="tab" :class="{ active: tab === 'timeline' }" role="tab" :aria-selected="tab === 'timeline'" aria-controls="editor-panel-content" @click="tab = 'timeline'">Timeline</button><button id="editor-tab-exports" class="tab" :class="{ active: tab === 'exports' }" role="tab" :aria-selected="tab === 'exports'" aria-controls="editor-panel-content" @click="tab = 'exports'">Ekspor</button></div>
          <div id="editor-panel-content" class="editor-panel-content" role="tabpanel" :aria-labelledby="`editor-tab-${tab}`">
            <SubtitleTranslate v-show="tab === 'subtitle' || tab === 'timeline'" :clip-id="clip.id" :revision="clip.revision.revision" :cues="clip.revision.cues" :disabled="dirty || saving || subtitleBusy" :available="clip.translation_available" @apply="applyTranslation" />
            <div v-if="tab === 'subtitle'" class="subtitle-editor">
              <div class="subtitle-toolbar">
                <div><h2>Teks subtitle</h2><p>Edit teks dan waktu pada klip ini.</p></div>
                <button class="button secondary small-button" aria-label="Buat subtitle dari audio" :disabled="dirty || saving || subtitleBusy" @click="openAudioRecovery"><AppIcon :name="subtitleBusy ? 'Clock3' : 'FileText'" :size="16" />{{ subtitleBusy ? 'Memproses' : 'Dari audio' }}</button>
              </div>
              <p v-if="dirty" class="subtitle-save-hint"><AppIcon name="CircleAlert" :size="14" /><span>Simpan perubahan terlebih dahulu untuk membuat subtitle dari audio.</span></p>
              <div v-if="oversizedCues" class="notice subtitle-fit-notice"><span>{{ oversizedCues }} subtitle terlalu panjang pada ukuran ini.</span><button class="button secondary small-button" :disabled="saving" @click="proposeSubtitleRepair">Sesuaikan subtitle</button></div>
              <div v-if="!draft.cues.length" class="subtitle-empty">
                <span class="subtitle-empty-icon"><AppIcon name="FileText" :size="24" /></span>
                <h2>Belum ada subtitle</h2>
                <p>Gunakan <strong>Dari audio</strong> untuk mengenali ucapan, atau tambahkan teks secara manual.</p>
              </div>
              <div v-if="subtitleJob || subtitleError || subtitleMessage" class="subtitle-recovery-status" aria-live="polite">
                <JobStatus v-if="subtitleJob && subtitleJob.status !== 'succeeded'" :job="subtitleJob" @refresh="acceptSubtitleAction" />
                <p v-if="subtitleMessage" class="notice" role="status">{{ subtitleMessage }}</p>
                <p v-if="subtitleResultPending" class="notice">Subtitle selesai, tetapi editor memiliki perubahan lain. Perubahan Anda tetap dipertahankan. <button class="text-button" @click="conflictOpen = true">Tinjau revisi terbaru</button></p>
                <InlineError :message="subtitleError" />
              </div><ScrollList :items="draft.cues" label="subtitle" v-slot="{ items, start }"><article v-for="(cue, offset) in items" :key="(start + offset)" class="cue-row" :class="{ 'cue-active': activeCue === cue }"><div class="cue-top"><button class="cue-number text-button" :aria-label="`Putar subtitle ${(start + offset) + 1}`" @click="seek(draft.start_ms + cue.start_ms)">{{ String((start + offset) + 1).padStart(2, '0') }}</button><label class="sr-only" :for="`cue-start-${(start + offset)}`">Mulai subtitle {{ (start + offset) + 1 }}</label><input :id="`cue-start-${(start + offset)}`" class="timecode cue-time" :value="timecode(cue.start_ms, true)" @change="cueTime(cue, 'start_ms', $event)" /><span class="muted">–</span><label class="sr-only" :for="`cue-end-${(start + offset)}`">Akhir subtitle {{ (start + offset) + 1 }}</label><input :id="`cue-end-${(start + offset)}`" class="timecode cue-time" :value="timecode(cue.end_ms, true)" @change="cueTime(cue, 'end_ms', $event)" /><button class="icon-button" :aria-label="`Hapus subtitle ${(start + offset) + 1}`" @click="draft.cues.splice((start + offset), 1)"><AppIcon name="X" :size="15" /></button></div><label class="sr-only" :for="`cue-text-${(start + offset)}`">Teks subtitle {{ (start + offset) + 1 }}</label><textarea :id="`cue-text-${(start + offset)}`" v-model="cue.text" rows="2" maxlength="2000" /><p v-if="draft.subtitle_style_json.display_mode !== 'words' && cueLayout(cue.text).tooLong" class="error-text">Teks terlalu panjang. Gunakan Sesuaikan subtitle di atas atau pendekkan teks ini.</p></article></ScrollList><button class="button secondary add-cue" @click="addCue"><AppIcon name="Plus" :size="16" />Tambah subtitle</button></div>
            <DesktopFit v-if="tab === 'style'" :fit="styleTab === 'framing'"><div class="style-editor"><div class="tool-tabs" role="group" aria-label="Pengaturan tampilan"><button :aria-pressed="styleTab === 'framing'" @click="styleTab = 'framing'">Framing</button><button :aria-pressed="styleTab === 'caption'" @click="styleTab = 'caption'">Gaya subtitle</button><button :aria-pressed="styleTab === 'effects'" @click="styleTab = 'effects'">Efek video</button></div><section v-show="styleTab === 'framing'" class="settings-group"><h2 class="sr-only">Framing</h2>
              <label>Mode video<AppSelect v-model="framingMode" label="Mode framing" :options="[{ value: 'fill', label: 'Isi frame (crop)' }, { value: 'fit', label: 'Tampilkan seluruh video' }, { value: 'gaming', label: GAMING_LABEL }]" /></label>
              <template v-if="framingMode === 'fill'">
                <label>Pelacakan<AppSelect v-model="tracking" label="Pelacakan frame" :options="trackingOptions" /></label>
                <p v-if="tracking === 'static'" class="muted small">Satu posisi manual berlaku sepanjang klip.</p>
                <template v-else>
                  <p v-if="tracking === 'face'" class="muted small">Mengikuti satu wajah yang terlihat. Mode ini tidak memilih pembicara berdasarkan suara.</p>
                  <p v-else class="muted small">Model audio-visual memperkirakan wajah yang sedang berbicara dari kecocokan suara dan gerak bibir.</p>
                  <p class="muted small">Atur posisi manual di bawah sebagai cadangan saat pelacakan tidak tersedia.</p>
                  <p v-if="tracking === 'speaker'" class="notice">Pilihan pembicara dapat keliru, terutama saat suara bertumpuk atau wajah kurang jelas. Tinjau preview dan MP4 sebelum digunakan.</p>
                  <div class="tracking-preview-controls">
                    <button class="button secondary" :disabled="trackingBusy" @click="previewTracking.analyze()">{{ trackingAnalysis.submitting ? 'Mengantrekan analisis...' : 'Analisis preview' }}</button>
                    <p v-if="trackingReady" class="tracking-ready" role="status"><AppIcon name="Check" :size="15" />Preview pelacakan siap</p>
                    <p v-else-if="trackingAnalysis.invalidated" class="muted small">Pengaturan framing atau rentang berubah. Jalankan analisis preview lagi.</p>
                    <p v-else-if="trackingBusy" class="muted small">Analisis berjalan di server. Preview sementara memakai posisi manual.</p>
                    <p v-else class="muted small">Preview memakai posisi manual. Jalankan analisis untuk melihat framing bergerak.</p>
                    <p v-if="trackingAnalysis.backgroundWork" class="muted small">Analisis sebelumnya mungkin masih berjalan di server; hasilnya tidak dipakai untuk pengaturan ini. Pekerjaan dapat dibatalkan dari halaman proyek.</p>
                    <div v-if="trackingAnalysis.job && !trackingReady" class="tracking-preview-job" aria-live="polite"><JobStatus :job="trackingAnalysis.job" @refresh="previewTracking.acceptAction" /></div>
                    <InlineError :message="trackingAnalysis.error" />
                    <FramingInfo v-if="trackingReady" :framing="trackingAnalysis.framing || undefined" />
                  </div>
                </template>
                <label>{{ tracking === 'static' ? 'Posisi horizontal' : 'Posisi cadangan horizontal' }} <span class="muted">{{ Math.round(draft.crop_json.x * 100) }}%</span><input v-model.number="draft.crop_json.x" type="range" min="0" max="1" step="0.01" /></label>
                <label>{{ tracking === 'static' ? 'Posisi vertikal' : 'Posisi cadangan vertikal' }} <span class="muted">{{ Math.round(draft.crop_json.y * 100) }}%</span><input v-model.number="draft.crop_json.y" type="range" min="0" max="1" step="0.01" /></label>
                <button class="text-button" @click="draft.crop_json.x = 0.5; draft.crop_json.y = 0.5">Kembalikan ke tengah</button>
              </template>
              <GamingSettings v-else-if="framingMode === 'gaming'" ref="gamingSettings" v-model="gaming" :video="video" />
              <p v-else class="muted small">Seluruh video ditampilkan tanpa crop. Pelacakan tersedia pada mode Isi frame.</p></section><section v-show="styleTab === 'caption'" class="settings-group"><h2 class="sr-only">Subtitle</h2><SubtitleSettings v-model="draft.subtitle_style_json" :effective-size="activeCaption.fontSize" :oversized-cues="oversizedCues" :missing-timing="missingWordTiming" :timing-error="timingError" :recovery-busy="saving || subtitleBusy" @repair="proposeSubtitleRepair" @recover="openAudioRecovery" /></section><section v-if="styleTab === 'effects'" class="settings-group"><h2 class="sr-only">Efek video</h2><RemotionEffectsSettings v-model="draft.subtitle_style_json" :duration-ms="clipDuration" :time-ms="playhead - draft.start_ms" @seek="seek(draft.start_ms + $event)" @timeline="tab = 'timeline'" /></section></div></DesktopFit>
            <div v-if="tab === 'timeline'" class="subtitle-toolbar timeline-audio-toolbar"><div><h2>Subtitle dari audio</h2><p>Gunakan rentang klip yang tersimpan.</p></div><button class="button secondary small-button" aria-label="Buat subtitle dari audio" :disabled="dirty || saving || subtitleBusy" @click="openAudioRecovery"><AppIcon name="FileText" :size="16" />Dari audio</button></div>
            <p v-if="tab === 'timeline' && dirty" class="subtitle-save-hint">Simpan perubahan terlebih dahulu untuk membuat subtitle dari audio.</p>
            <ClipTimeline v-if="tab === 'timeline'" v-model:cues="draft.cues" :effects="draft.subtitle_style_json.remotion_effects" :remotion="draft.subtitle_style_json.renderer === 'remotion'" :duration-ms="clipDuration" :start-ms="draft.start_ms" :end-ms="draft.end_ms" :source-duration-ms="sourceDuration" :time-ms="playhead - draft.start_ms" :max-clip-ms="maxClipMs" @update:effects="updateEffects" @seek="seek(draft.start_ms + $event)" @bounds="timelineBounds" @enable-remotion="draft.subtitle_style_json = { ...draft.subtitle_style_json, renderer: 'remotion' }" /><template v-if="tab === 'exports'"><ExportList :exports="exports" :current-revision="clip.revision.revision" @refresh="loadExports" /><LoadMore :loaded="exports.length" :total="exportTotal" :loading="exportsLoading" :has-more="moreExports" label="hasil ekspor klip ini" button-label="Muat ekspor sebelumnya" @more="exportList.loadMore().catch(e => error = errorMessage(e))" /></template>
          </div>
        </aside>
      </div>
    </template>
    <AppDialog :open="subtitleAudioOpen" :title="replacesSubtitles ? 'Buat ulang subtitle dari audio?' : 'Buat subtitle dari audio'" description="Kenali ucapan dan waktu tiap kata pada rentang klip ini." :busy="saving || subtitleBusy" @close="subtitleAudioOpen = false">
      <div class="audio-dialog-content">
        <div class="audio-clip-range"><span><AppIcon name="Scissors" :size="16" />{{ dirty ? 'Rentang setelah disimpan' : 'Rentang tersimpan' }}</span><strong class="timecode">{{ timecode(draft?.start_ms || 0, true) }} &ndash; {{ timecode(draft?.end_ms || 0, true) }}</strong></div>
        <label class="audio-language">Bahasa ucapan<AppSelect v-model="subtitleLanguage" :disabled="saving || subtitleBusy" label="Bahasa subtitle dari audio" :options="[{ value: 'auto', label: 'Deteksi otomatis' }, { value: 'id', label: 'Bahasa Indonesia' }, { value: 'en', label: 'English' }]" /></label>
        <p v-if="replacesSubtitles" class="notice audio-replace-notice"><strong>Subtitle lama akan diganti.</strong> Termasuk koreksi teks dan waktu yang sudah Anda buat. Jika ucapan tidak terdeteksi, subtitle lama tetap dipertahankan.</p>
        <p v-else class="muted small">Audio tanpa ucapan dapat menghasilkan subtitle kosong. Teks hasil pengenalan bisa Anda edit setelah proses selesai.</p>
        <p v-if="dirty" class="notice">Perubahan Anda akan disimpan dahulu, termasuk gaya subtitle dan koreksi teks. Hasil dari audio akan mengganti subtitle pada revisi berikutnya; revisi sebelumnya tetap tersimpan.</p>
        <InlineError :message="subtitleAudioError" />
      </div>
      <div class="dialog-actions"><button class="button secondary" :disabled="saving || subtitleBusy" @click="subtitleAudioOpen = false">Batal</button><button class="button primary" :disabled="saving || subtitleBusy" @click="saveAndGenerateSubtitles"><AppIcon name="FileText" :size="16" />{{ saving ? 'Menyimpan perubahan...' : dirty ? 'Simpan dan buat ulang subtitle' : replacesSubtitles ? 'Ganti subtitle dari audio' : 'Mulai buat subtitle' }}</button></div>
    </AppDialog>
    <AppDialog :open="!!subtitleRepair" title="Sesuaikan subtitle" description="Teks tetap utuh. Perubahan diterapkan ke draft sebelum disimpan." @close="subtitleRepair = null">
      <div v-if="subtitleRepair" class="form-stack">
        <p>Ukuran otomatis akan diaktifkan. {{ subtitleRepair.splitCount ? `${subtitleRepair.splitCount} cue panjang dipecah menjadi beberapa bagian.` : 'Semua cue dapat ditampilkan tanpa mengubah waktu.' }}</p>
        <p v-if="subtitleRepair.estimatedCount" class="notice">{{ subtitleRepair.estimatedCount }} cue tidak memiliki timing kata yang cocok. Waktu bagian baru diperkirakan secara proporsional dalam rentang cue asli. Tinjau hasilnya di timeline.</p>
        <p v-else-if="subtitleRepair.splitCount" class="muted small">Pemisahan mengikuti timing kata asli. Awal dan akhir cue tetap berada dalam rentang semula.</p>
        <p v-if="subtitleRepair.fallback" class="notice">Mode kata per kata dialihkan ke kalimat. Jika memakai Podcast, template beralih ke Minimal karena timing kata tidak tersedia.</p>
        <p v-if="subtitleRepair.unresolved" class="error-text">{{ subtitleRepair.unresolved }} cue masih perlu dipendekkan manual karena memiliki kata terlalu panjang atau durasi terlalu singkat.</p>
        <p>{{ draft?.cues.length }} cue menjadi {{ subtitleRepair.cues.length }} cue</p>
        <div class="subtitle-fit-preview"><p v-for="(cue,i) in subtitleRepair.cues.slice(0,6)" :key="i"><small class="timecode">{{ timecode(cue.start_ms,true) }} &ndash; {{ timecode(cue.end_ms,true) }}</small><br/>{{ cue.text }}</p><p v-if="subtitleRepair.cues.length > 6" class="muted small">{{ subtitleRepair.cues.length - 6 }} cue lainnya dapat ditinjau setelah diterapkan.</p></div>
        <div class="dialog-actions"><button class="button secondary" @click="subtitleRepair = null">Batal</button><button class="button primary" :disabled="saving || JSON.stringify(draft) !== repairBase" @click="applySubtitleRepair">Terapkan penyesuaian</button></div>
      </div>
    </AppDialog>
    <AppDialog :open="previewHelp" title="Panduan preview" @close="previewHelp = false"><p>Preview mengikuti posisi playback sumber. Batas Masuk dan Keluar menentukan potongan hasil ekspor.</p><p>Untuk pelacakan wajah atau pembicara, jalankan Analisis preview setelah mengubah pengaturan. Mode Gaming langsung menampilkan dua area sumber.</p><p>Periksa MP4 akhir untuk tampilan subtitle dan timing hasil render.</p><div class="dialog-actions"><button class="button primary" @click="previewHelp = false">Tutup</button></div></AppDialog>
    <AppDialog :open="exportOpen" title="Ekspor klip" :description="`Render menggunakan revisi ${clip?.revision.revision} yang tersimpan.`" :busy="exportBusy" @close="exportOpen = false"><div class="form-stack"><p v-if="dirty" class="notice">Ada perubahan yang belum tersimpan. Simpan dahulu agar perubahan masuk ke hasil ekspor.</p><label>Resolusi<AppSelect v-model="resolution" label="Resolusi ekspor" :options="[{ value: 1080, label: '1080 × 1920 · 30 fps' }, { value: 720, label: '720 × 1280 · 30 fps' }]" /></label><p class="muted small">Framing: {{ framingMode === 'gaming' ? GAMING_LABEL : framingMode === 'fit' ? 'Tampilkan seluruh video' : trackingLabel(tracking) }}.<span v-if="tracking !== 'static'"> {{ trackingReady ? 'Analisis preview yang cocok dipakai kembali saat render.' : 'Pelacakan dianalisis saat render jika belum ada hasil yang cocok.' }} Tinjau MP4 final.</span></p><p class="muted small">MP4 H.264/AAC dan subtitle SRT. Subtitle SRT tetap tersedia meskipun burn-in dinonaktifkan.</p><p v-if="enlarged" class="notice">Sumber beresolusi lebih kecil. Video akan diperbesar tanpa menambah detail.</p><div v-if="oversizedCues" class="notice subtitle-fit-notice"><span>Ada subtitle yang perlu disesuaikan agar muat.</span><button class="button secondary small-button" @click="proposeSubtitleRepair">Sesuaikan subtitle</button></div><InlineError :message="exportError || podcastTimingError"><button v-if="podcastTimingError" class="button secondary small-button" :disabled="saving || subtitleBusy || exportBusy" @click="openAudioRecovery">Perbaiki dari audio</button></InlineError><div class="dialog-actions"><button class="button secondary" :disabled="exportBusy" @click="exportOpen = false">Batal</button><button v-if="dirty" class="button primary" :disabled="saving || !!draftEffectsError" @click="save().then(ok => { if (!ok) exportOpen = false })">Simpan perubahan</button><button v-else class="button primary" :disabled="exportBusy || !!oversizedCues || !!podcastTimingError" @click="startExport">{{ exportBusy ? 'Mengantrekan render…' : 'Mulai ekspor' }}</button></div></div></AppDialog>
    <AppDialog :open="conflictOpen" title="Revisi sudah berubah" description="Klip memiliki revisi tersimpan yang lebih baru. Perubahan Anda masih ada di editor ini. Muat revisi terbaru untuk menggantinya atau kembali untuk menyalin koreksi terlebih dahulu." @close="conflictOpen = false"><div class="dialog-actions"><button class="button secondary" @click="conflictOpen = false">Kembali ke perubahan saya</button><button class="button primary" @click="conflictOpen = false; load()">Muat revisi terbaru</button></div></AppDialog>
    <AppDialog :open="trimOpen" title="Sesuaikan subtitle dengan batas baru?" :description="`${trimLoss} cue berada di luar batas baru dan tidak akan masuk revisi ini. Teks cue yang masih berada di dalam klip dipertahankan, dan waktunya disesuaikan.`" @close="trimOpen = false"><div class="dialog-actions"><button class="button secondary" @click="trimOpen = false; startInput = timecode(draft?.start_ms, true); endInput = timecode(draft?.end_ms, true)">Batal</button><button class="button primary" @click="pendingBounds && applyBounds(pendingBounds.start, pendingBounds.end)">Terapkan batas dan cue</button></div></AppDialog>
    <AppDialog :open="leaveOpen" title="Perubahan belum tersimpan" description="Simpan perubahan sebelum meninggalkan editor atau lanjutkan tanpa menyimpannya." :busy="saving" @close="leaveOpen = false"><div class="dialog-actions"><button class="button secondary" :disabled="saving" @click="discardLeave">Tinggalkan perubahan</button><button class="button primary" :disabled="saving" @click="saveAndLeave">Simpan dan lanjutkan</button></div></AppDialog>
  </div>
</template>
<style scoped>
.subtitle-fit-notice { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; }
.subtitle-fit-preview { max-height:240px; overflow:auto; overflow-wrap:anywhere; }
.subtitle-fit-preview p { padding:8px 0; border-bottom:1px solid var(--color-border); margin:0; }
.framing-preview { position: absolute; inset: 0; }
.editor-panel > .tabs { gap: 14px; }
.subtitle-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--color-border); flex: none; }
.subtitle-toolbar h2 { font-size: 13px; line-height: 1.4; margin: 0; }
.subtitle-toolbar p { font-size: 11px; color: var(--color-text-muted); margin: 4px 0 0; }
.subtitle-toolbar .button { flex: none; min-height: 36px; }
.subtitle-save-hint { display: flex; align-items: flex-start; gap: 7px; margin: 0; padding: 10px 16px; background: #2b261e; color: #dbc39b; font-size: 11px; line-height: 1.5; flex: none; }
.subtitle-save-hint svg { flex: none; margin-top: 1px; }
.subtitle-empty { padding: 28px 24px; text-align: center; flex: none; }
.subtitle-empty-icon { display: inline-flex; padding: 12px; margin-bottom: 12px; border-radius: 12px; background: var(--color-surface-muted); color: var(--color-positive); }
.subtitle-empty h2 { font-size: 15px; margin: 0 0 8px; }
.subtitle-empty p { max-width: 280px; margin: 0 auto; font-size: 12px; line-height: 1.7; color: var(--color-text-muted); }
.subtitle-recovery-status { flex: none; max-height: 35%; overflow-y: auto; padding: 10px 16px; border-bottom: 1px solid var(--color-border); }
.subtitle-recovery-status :deep(.job-row) { padding: 8px 0; }
.subtitle-recovery-status .notice { margin: 0; }
.audio-dialog-content { display: grid; gap: 18px; margin-top: 20px; }
.audio-clip-range { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; padding: 12px 14px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface-muted); font-size: 12px; }
.audio-clip-range > span { display: inline-flex; align-items: center; gap: 8px; color: var(--color-text-muted); }
.audio-clip-range strong { font-size: 12px; white-space: nowrap; }
.audio-language { display: grid; gap: 8px; margin: 0; }
.audio-dialog-content p { margin: 0; }
.audio-replace-notice strong { display: block; margin-bottom: 3px; }
@media (max-width: 760px) {
  .subtitle-toolbar { padding: 12px 14px; gap: 8px; }
  .subtitle-empty { padding: 24px 20px; }
  .audio-clip-range { align-items: flex-start; flex-direction: column; }
}
</style>
