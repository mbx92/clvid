<script setup lang="ts">
import type { Cue, Job } from '~/types/api'
import { isActive, timecode } from '~/utils/format'
const props = defineProps<{ clipId:string; revision:number; cues:Cue[]; disabled:boolean; available?:boolean }>()
const emit = defineEmits<{ apply:[cues:Cue[], revision:number] }>()
const api = useApi()
const open = ref(false), submitting = ref(false), error = ref('')
const job = ref<Job|null>(null)
const busy = computed(() => submitting.value || !!job.value && isActive(job.value.status))
const result = computed(() => job.value?.status === 'succeeded' ? job.value.result_json : undefined)
const stale = computed(() => !!result.value && (props.disabled || result.value.base_revision !== props.revision))
const requests = new Set<AbortController>()
let disposed = false, polling = false, generation = 0
async function start() {
  if (props.disabled || busy.value || !props.cues.length) return
  const current = ++generation, revision = props.revision
  submitting.value = true; error.value = ''; job.value = null
  const controller = new AbortController(); requests.add(controller)
  try {
    const value = await api<Job>(`/clips/${props.clipId}/subtitles/translate`, {method:'POST',signal:controller.signal,
      headers:{'Idempotency-Key':idempotencyKey()},body:{expected_revision:revision,target_language:'id'}})
    if (!disposed && current === generation) job.value = value
  } catch(e) {if (!controller.signal.aborted) error.value = errorMessage(e)}
  finally {requests.delete(controller); submitting.value = false}
}
async function refresh() {
  if (disposed || polling || !job.value) return
  polling = true
  const current = generation, id = job.value.id, controller = new AbortController(); requests.add(controller)
  try {
    const value = await api<Job>(`/jobs/${id}`,{signal:controller.signal})
    if (!disposed && current === generation && job.value?.id === id) job.value = value
  } catch(e) {if (!controller.signal.aborted) error.value = errorMessage(e)}
  finally {requests.delete(controller); polling = false}
}
function accept(value:Job) {generation++; job.value = value}
function apply() {
  if (stale.value || !result.value?.translated_cues || !result.value.base_revision) return
  emit('apply', result.value.translated_cues.map(c=>({start_ms:c.start_ms,end_ms:c.end_ms,text:c.text})), result.value.base_revision)
  open.value = false; job.value = null
}
usePolling(refresh, () => !!job.value && isActive(job.value.status))
onBeforeUnmount(() => {disposed = true; generation++; for (const r of requests) r.abort(); requests.clear()})
</script>
<template>
  <section class="translate-tools" aria-label="Terjemahan subtitle">
    <div class="translate-heading"><div><strong>Inggris → Indonesia</strong><p>Terjemahkan teks subtitle dengan DeepSeek.</p></div><button class="button secondary small-button" :disabled="!cues.length || available === false" @click="open = true">{{ busy ? 'Proses terjemahan' : result ? 'Tinjau terjemahan' : 'Terjemahkan' }}</button></div>
    <p v-if="!cues.length" class="muted small">Buat subtitle lewat Dari audio, pilih English, lalu terjemahkan di sini.</p>
    <p v-else-if="disabled" class="muted small">Simpan perubahan dan tunggu proses subtitle selesai sebelum menerjemahkan.</p>
    <p v-if="available === false" class="muted small">Terjemahan memerlukan konfigurasi DeepSeek di server.</p>
    <AppDialog :open="open" title="Terjemahkan subtitle" description="Inggris ke Bahasa Indonesia. Audio asli dan waktu tiap subtitle tetap sama." @close="open = false">
      <div class="translation-dialog">
        <p class="muted small">Hasilnya ditinjau dahulu sebelum diterapkan ke draft. Subtitle terjemahan menggunakan mode kalimat; template Podcast akan beralih ke Minimal karena timing kata Inggris tidak cocok dengan teks Indonesia.</p>
        <JobStatus v-if="job && job.status !== 'succeeded'" :job="job" @refresh="accept" />
        <InlineError :message="error" />
        <template v-if="result?.translated_cues">
          <p role="status">{{ result.translated_cues.length }} subtitle siap ditinjau.</p>
          <p v-if="stale" class="notice">Draft atau revisi sudah berubah. Simpan perubahan lalu buat terjemahan baru.</p>
          <div class="translation-list"><article v-for="(cue,i) in result.translated_cues" :key="i"><small class="timecode">{{ timecode(cue.start_ms,true) }} – {{ timecode(cue.end_ms,true) }}</small><p v-if="result.base_revision === revision" class="original">{{ cues[i]?.text }}</p><p>{{ cue.text }}</p></article></div>
        </template>
        <p v-if="disabled && !result" class="notice">Simpan perubahan dan tunggu proses subtitle selesai dahulu.</p>
        <div class="dialog-actions"><button class="button secondary" @click="open = false">Tutup</button><button class="button secondary" :disabled="disabled || busy || available === false" @click="start">{{ result ? 'Terjemahkan ulang' : 'Mulai terjemahkan' }}</button><button v-if="result?.translated_cues" class="button primary" :disabled="stale || busy" @click="apply">Terapkan terjemahan ke draft</button></div>
      </div>
    </AppDialog>
  </section>
</template>
<style scoped>
.translate-tools { flex:none; padding:12px 16px; border-bottom:1px solid #e3e8de; background:#f5f7f1; }
.translate-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.translate-heading strong { font-size:12px; }
.translate-heading p { font-size:11px; color:#647267; margin:4px 0 0; }
.translate-tools > p { margin:8px 0 0; }
.translation-dialog { display:grid; gap:14px; }
.translation-list { max-height:360px; overflow:auto; border:1px solid #e3e8de; border-radius:8px; }
.translation-list article { padding:12px; border-bottom:1px solid #e3e8de; overflow-wrap:anywhere; }
.translation-list p { margin:7px 0 0; white-space:pre-wrap; }
.translation-list .original { color:#6e756f; font-size:12px; }
.translation-list small { color:#52665c; }
</style>
