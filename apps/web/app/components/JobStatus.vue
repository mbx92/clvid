<script setup lang="ts">
import type { Job } from '~/types/api'
import { dateTime, isActive, stageLabels } from '~/utils/format'
import { elapsedLabel, jobElapsedMs } from '~/utils/jobs'
const props = defineProps<{ job: Job }>()
const emit = defineEmits<{ refresh: [job: Job] }>()
const api = useApi()
const busy = ref(false)
const error = ref('')
const act = async (action: 'cancel' | 'retry') => { busy.value = true; error.value = ''; try { const result = await api<Job>(`/jobs/${props.job.id}/${action}`, { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey() } }); emit('refresh', result) } catch (e) { error.value = errorMessage(e) } finally { busy.value = false } }
const progress = computed(() => props.job.progress == null ? null : Math.min(100, Math.max(0, props.job.progress * 100)))
const now = ref(Date.now())
const elapsed = computed(() => jobElapsedMs(props.job, now.value))
let elapsedTimer: ReturnType<typeof setInterval> | undefined
const updateClock = () => {
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = undefined
  now.value = Date.now()
  if (['running', 'cancel_requested'].includes(props.job.status) && props.job.started_at && !document.hidden) {
    elapsedTimer = setInterval(() => { now.value = Date.now() }, 1000)
  }
}
watch(() => [props.job.status, props.job.started_at, props.job.finished_at], () => { if (import.meta.client) updateClock() })
onMounted(() => { updateClock(); document.addEventListener('visibilitychange', updateClock) })
onBeforeUnmount(() => { if (elapsedTimer) clearInterval(elapsedTimer); if (import.meta.client) document.removeEventListener('visibilitychange', updateClock) })
</script>
<template>
  <div class="job-row">
    <div class="job-main"><div class="row gap-2"><span class="job-stage">{{ stageLabels[job.stage] || job.stage }}</span><StatusBadge :status="job.status" /></div><small v-if="job.started_at && job.status !== 'queued'" class="muted">Dimulai {{ dateTime(job.started_at) }}<span v-if="elapsed !== null" aria-live="off"> · {{ isActive(job.status) ? 'Berjalan' : 'Durasi' }} {{ elapsedLabel(elapsed) }}</span></small><p v-if="job.error_message" class="error-text">{{ job.error_message }}</p><div v-if="job.status === 'running' && progress !== null" class="progress-line"><progress :value="progress" max="100" :aria-label="stageLabels[job.stage] || 'Kemajuan pemrosesan'" /><span>{{ Math.round(progress) }}%</span></div><p v-else-if="job.status === 'running'" class="muted small">Sedang dikerjakan di server. Persentase belum tersedia.</p><p v-if="job.status === 'cancel_requested'" class="muted small">Menunggu proses berhenti dengan aman.</p></div>
    <button v-if="isActive(job.status) && job.status !== 'cancel_requested'" class="button small-button secondary" :disabled="busy" @click="act('cancel')">Batalkan</button>
    <button v-if="job.status === 'failed' || job.status === 'cancelled'" class="button small-button secondary" :disabled="busy" @click="act('retry')"><AppIcon name="RefreshCw" :size="15" />Coba lagi</button>
    <InlineError :message="error" />
  </div>
</template>
