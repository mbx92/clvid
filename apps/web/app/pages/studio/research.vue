<script setup lang="ts">
import type { Job, Project, ResearchVideo, VideoResearch } from '~/types/api'
import { timecode } from '~/utils/format'

const api = useApi()
const query = ref('')
const result = ref<VideoResearch | null>(null)
const selected = ref<ResearchVideo | null>(null)
const searching = ref(false)
const starting = ref(false)
const searchError = ref('')
const startError = ref('')
const settingsError = ref('')
const settingsReady = ref(false)
const aiConfigured = ref(false)
const maxClipSeconds = ref(180)
const maxSourceSeconds = ref(3600)
const language = ref('auto')
const contentProfile = ref('general')
const visualAnalysis = ref(false)
const count = ref(3)
const minSeconds = ref(50)
const maxSeconds = ref(60)
const projectName = ref('')
const pending = ref<{ projectId?: string; key: string; name: string; body: Record<string, unknown> } | null>(null)
const submittedProject = ref('')
const locked = computed(() => starting.value || !!pending.value || !!submittedProject.value)
let searchController: AbortController | null = null

async function loadSettings() {
  settingsReady.value = false
  settingsError.value = ''
  try {
    const settings = await api<{ deepseek_configured: boolean; limits: { max_clip_ms: number }; max_video_seconds: number }>('/settings')
    aiConfigured.value = settings.deepseek_configured
    maxClipSeconds.value = Math.floor(settings.limits.max_clip_ms / 1000)
    maxSourceSeconds.value = settings.max_video_seconds
    maxSeconds.value = Math.min(maxSeconds.value, maxClipSeconds.value)
    minSeconds.value = Math.min(minSeconds.value, maxSeconds.value)
    settingsReady.value = true
  } catch (e) { settingsError.value = errorMessage(e) }
}
onMounted(loadSettings)
onBeforeUnmount(() => searchController?.abort())

async function search() {
  if (searching.value || locked.value) return
  const topic = query.value.trim()
  if (topic.length < 2 || topic.length > 200) { searchError.value = 'Isi topik sepanjang 2–200 karakter.'; return }
  searching.value = true
  searchError.value = ''
  startError.value = ''
  selected.value = null
  result.value = null
  searchController = new AbortController()
  try {
    result.value = await api<VideoResearch>('/research/search', { method: 'POST', body: { query: topic, count: 6 }, signal: searchController.signal })
  } catch (e) { if (!searchController?.signal.aborted) searchError.value = errorMessage(e) }
  finally { searching.value = false; searchController = null }
}
function choose(video: ResearchVideo) {
  if (locked.value) return
  selected.value = video
  projectName.value = video.title.slice(0, 200)
  startError.value = ''
}
async function start() {
  if (starting.value || searching.value || submittedProject.value || !selected.value || !settingsReady.value || !aiConfigured.value) return
  if (!pending.value) {
    if (!projectName.value.trim()) { startError.value = 'Isi nama proyek.'; return }
    if (!Number.isInteger(count.value) || count.value < 1 || count.value > 20 || !Number.isInteger(minSeconds.value) || !Number.isInteger(maxSeconds.value) || minSeconds.value < 5 || minSeconds.value > maxSeconds.value || maxSeconds.value > maxClipSeconds.value) {
      startError.value = `Pilih 1–20 klip dan durasi 5–${maxClipSeconds.value} detik, dengan minimum tidak melebihi maksimum.`
      return
    }
    if (selected.value.duration_ms !== null && selected.value.duration_ms < minSeconds.value * 1000) { startError.value = 'Video sumber lebih pendek dari durasi minimum klip. Pilih sumber lain atau kurangi durasi klip.'; return }
    pending.value = { key: idempotencyKey(), name: projectName.value.trim(), body: { url: selected.value.url, process: {
      language: language.value, content_profile: contentProfile.value,
      visual_analysis: contentProfile.value === 'gaming' && visualAnalysis.value,
      count: count.value, min_duration_ms: minSeconds.value * 1000, max_duration_ms: maxSeconds.value * 1000,
      analyze: true, transcribe_again: false,
    } } }
  }
  starting.value = true
  startError.value = ''
  try {
    const request = pending.value
    if (!request.projectId) {
      const project = await api<Project>('/projects', { method: 'POST', body: { name: request.name } })
      request.projectId = project.id
    }
    await api<Job>(`/projects/${request.projectId}/source-url`, { method: 'POST', headers: { 'Idempotency-Key': request.key }, body: request.body })
    submittedProject.value = request.projectId
    await navigateTo(`/projects/${request.projectId}`)
  } catch (e) { startError.value = errorMessage(e) }
  finally { starting.value = false }
}
function resetAttempt() {
  if (starting.value) return
  pending.value = null
  submittedProject.value = ''
  startError.value = ''
}
const views = (value: number) => new Intl.NumberFormat('id-ID', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
</script>

<template>
  <div class="page research-page">
    <NuxtLink to="/studio" class="breadcrumb"><AppIcon name="ArrowLeft" :size="16" />Studio</NuxtLink>
    <header class="page-header"><div><p class="eyebrow">PERSIAPAN PRODUKSI</p><h1>Riset sumber video</h1><p class="muted">Cari video, periksa sumber, lalu tentukan klip yang akan diproduksi.</p></div></header>
    <ol class="research-steps" aria-label="Alur riset video"><li :class="{ current: !result }" :aria-current="!result ? 'step' : undefined"><span>01</span>Cari topik</li><li :class="{ current: !!result && !selected }" :aria-current="result && !selected ? 'step' : undefined"><span>02</span>Pilih sumber</li><li :class="{ current: !!selected }" :aria-current="selected ? 'step' : undefined"><span>03</span>Buat klip otomatis</li></ol>
    <form class="research-search panel" @submit.prevent="search">
      <label for="research-topic">Topik atau kata kunci</label>
      <div class="research-search-row"><input id="research-topic" v-model="query" type="search" minlength="2" maxlength="200" required placeholder="Contoh: podcast bisnis kopi Indonesia" :disabled="searching || locked" /><button type="submit" class="button primary" :disabled="searching || locked"><AppIcon name="Search" />{{ searching ? 'Mencari video…' : 'Cari video' }}</button></div>
      <p class="muted small">Pencarian YouTube memakai judul dan metadata. Isi video dianalisis setelah Anda memilih sumber. Video dengan durasi diketahui di atas {{ Math.round(maxSourceSeconds / 60) }} menit disaring sesuai Pengaturan.</p>
    </form>
    <InlineError :message="searchError" />
    <div class="research-workspace">
      <section class="research-results" aria-label="Hasil riset video" :aria-busy="searching">
        <div v-if="searching" class="empty-state panel" role="status"><AppIcon name="Search" :size="28" /><h2>Mencari sumber yang relevan…</h2><p>Video belum diunduh. Tunggu hasil untuk memilih sumber.</p></div>
        <template v-else-if="result">
          <div class="row between gap-3"><h2>{{ result.items.length }} sumber untuk “{{ result.query }}”</h2></div>
          <p v-if="result.message" class="notice" role="status">{{ result.message }}</p>
          <div v-if="!result.items.length" class="empty-state panel"><h2>Belum ada sumber yang cocok</h2><p>Coba kata kunci lebih spesifik atau periksa batas durasi video di Pengaturan.</p></div>
          <article v-for="video in result.items" :key="video.id" class="research-video panel" :class="{ chosen: selected?.id === video.id }">
            <div class="research-thumb"><img :src="video.thumbnail_url" alt="" loading="lazy" referrerpolicy="no-referrer" /><span v-if="video.duration_ms !== null" class="research-duration">{{ timecode(video.duration_ms) }}</span></div>
            <div class="research-video-body"><h3>{{ video.title }}</h3><p class="muted small">{{ video.channel || 'Channel tidak tersedia' }}<span v-if="video.view_count !== null"> · {{ views(video.view_count) }} tayangan</span></p><p v-if="video.description" class="research-description">{{ video.description }}</p><p v-if="video.duration_ms === null" class="muted small">Durasi akan diperiksa saat impor.</p><div class="row gap-3 wrap"><button type="button" class="button small-button" :class="selected?.id === video.id ? 'primary' : 'secondary'" :disabled="locked" :aria-pressed="selected?.id === video.id" :aria-label="`Pilih sumber: ${video.title}`" @click="choose(video)"><AppIcon v-if="selected?.id === video.id" name="Check" :size="15" />{{ selected?.id === video.id ? 'Sumber dipilih' : 'Pilih sumber' }}</button><a :href="video.url" target="_blank" rel="noopener noreferrer" class="text-button small">Tonton di YouTube ↗</a></div></div>
          </article>
        </template>
        <div v-else-if="!searchError" class="empty-state panel"><AppIcon name="Search" :size="28" /><h2>Mulai dari satu topik</h2><p>Cari percakapan, tutorial, atau gameplay. Pilih satu video yang Anda miliki atau boleh gunakan untuk membuat klip.</p></div>
      </section>

      <aside class="research-options panel" aria-label="Pengaturan klip otomatis">
        <form class="form-stack" @submit.prevent="start">
          <div><h2>Klip otomatis</h2><p class="muted small">{{ selected ? selected.title : 'Pilih sumber dari hasil pencarian.' }}</p></div>
          <InlineError :message="settingsError"><button type="button" class="text-button" @click="loadSettings">Muat pengaturan lagi</button></InlineError>
          <p v-if="settingsReady && !aiConfigured" class="notice">AI pemilih klip belum dikonfigurasi. Periksa <NuxtLink to="/settings" class="text-button">Pengaturan</NuxtLink> sebelum memulai.</p>
          <fieldset :disabled="!selected || locked" class="research-fields">
            <label>Nama proyek<input v-model="projectName" maxlength="200" required /></label>
            <div class="form-grid"><label>Jumlah klip<input v-model.number="count" type="number" min="1" max="20" step="1" required /></label><label>Bahasa video<AppSelect v-model="language" label="Bahasa video" :options="[{value:'auto',label:'Otomatis'},{value:'id',label:'Indonesia'},{value:'en',label:'English'}]" :disabled="!selected || locked" /></label></div>
            <div class="form-grid"><label>Minimum (detik)<input v-model.number="minSeconds" type="number" min="5" :max="maxClipSeconds" step="1" required /></label><label>Maksimum (detik)<input v-model.number="maxSeconds" type="number" min="5" :max="maxClipSeconds" step="1" required /></label></div>
            <label>Jenis konten<AppSelect v-model="contentProfile" label="Jenis konten" :options="[{value:'general',label:'Umum / percakapan'},{value:'gaming',label:'Game / gameplay'}]" :disabled="!selected || locked" /></label>
            <label v-if="contentProfile === 'gaming'" class="checkbox-label"><input v-model="visualAnalysis" type="checkbox" />Analisis frame video dengan AI</label>
            <p v-if="contentProfile === 'gaming' && visualAnalysis" class="muted small">Sampel gambar dikirim ke AI untuk membantu menemukan momen visual dan memakai kuota tambahan.</p>
          </fieldset>
          <p class="muted small">Video akan diimpor, ditranskripsi, lalu dibuatkan klip. Pemilihan momen memakai kuota AI server. Hasil dapat lebih sedikit jika momen yang cocok terbatas.</p>
          <InlineError :message="startError" />
          <p v-if="pending?.projectId && startError" class="muted small">Proyek sudah tersimpan. Coba lagi akan memakai permintaan yang sama, atau <NuxtLink :to="`/projects/${pending.projectId}`" class="text-button">buka proyek</NuxtLink>.</p>
          <NuxtLink v-if="submittedProject" :to="`/projects/${submittedProject}`" class="button primary">Lihat proses dan hasil</NuxtLink>
          <button v-else type="submit" class="button primary full-width" :disabled="starting || searching || !selected || !settingsReady || !aiConfigured"><AppIcon name="Scissors" />{{ starting ? 'Menyiapkan proses…' : pending ? 'Coba mulai lagi' : 'Buat klip otomatis' }}</button>
          <button v-if="pending && !starting && !submittedProject" type="button" class="text-button" @click="resetAttempt">Ubah pilihan</button>
          <p v-if="starting" role="status" class="small">Mengantrekan impor dan analisis. Setelah masuk antrean, proses tetap berjalan ketika halaman ditutup.</p>
          <p class="muted small">Hasil disimpan sebagai klip yang bisa ditinjau, diedit, lalu diekspor dari halaman proyek.</p>
        </form>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.research-page { overflow-y: auto; }
.research-page .page-header { margin: 18px 0 22px; }
.research-steps { display: flex; flex-wrap: wrap; list-style: none; padding: 0; margin: 0 0 22px; gap: 12px 32px; color: var(--color-text-muted); font-size: 12px; }
.research-steps li { display: flex; align-items: center; gap: 9px; padding-bottom: 8px; border-bottom: 2px solid transparent; }
.research-steps span { font: 11px ui-monospace, monospace; }
.research-steps li.current { color: var(--color-text); border-bottom-color: var(--color-accent); }
.research-steps li.current span { color: var(--color-accent); }
.research-search { padding: 18px 20px; display: grid; gap: 10px; margin-bottom: 22px; background: var(--color-surface); border-radius: 5px; }
.research-search > label { font-weight: 600; }
.research-search-row { display: flex; gap: 10px; }
.research-search-row input { flex: 1; }
.research-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 350px; gap: 24px; align-items: start; }
.research-results { display: grid; gap: 14px; min-width: 0; }
.research-video { display: grid; grid-template-columns: 180px minmax(0, 1fr); gap: 16px; padding: 15px; border-radius: 5px; }
.research-video.chosen { border-color: var(--color-accent); box-shadow: inset 3px 0 var(--color-accent); }
.research-thumb { position: relative; align-self: start; aspect-ratio: 16 / 9; overflow: hidden; border-radius: 5px; background: var(--color-surface-muted); }
.research-thumb img { width: 100%; height: 100%; object-fit: cover; }
.research-duration { position: absolute; right: 5px; bottom: 5px; background: #0e1012eb; color: #eceef1; padding: 3px 5px; font: 10px ui-monospace, monospace; border-radius: 2px; }
.research-video-body { display: grid; gap: 8px; min-width: 0; }
.research-video h3 { line-height: 1.4; }
.research-description { color: var(--color-text-muted); font-size: 12px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.research-options { position: sticky; top: 20px; padding: 20px; border-radius: 5px; border-top: 2px solid #68717d; }
.research-options h2 { margin-bottom: 5px; }
.research-options form > div > p { overflow-wrap: anywhere; }
.research-fields { display: grid; gap: 15px; padding: 0; border: 0; min-width: 0; margin: 0; }
.research-fields > label, .research-fields .form-grid > label { display: grid; gap: 6px; font-size: 13px; }
.research-fields .checkbox-label { display: flex; }
.research-fields .custom-select { min-width: 0; }
.research-fields { padding-block: 16px; border-block: 1px solid var(--color-border); }
.research-fields:disabled { opacity: .55; }
.research-results > .row { padding-bottom: 10px; border-bottom: 1px solid var(--color-border); }
.research-results > .row h2 { font-size: 14px; }
.research-options .form-stack { gap: 15px; }
.research-options > form > div:first-child h2 { font-size: 16px; }
@media (max-width: 1150px) { .research-video { grid-template-columns: 130px minmax(0, 1fr); } .research-workspace { grid-template-columns: minmax(0, 1fr) 310px; gap: 16px; } }
@media (max-width: 900px) { .research-workspace { grid-template-columns: 1fr; } .research-options { position: static; } .research-video { grid-template-columns: 180px minmax(0, 1fr); } }
@media (max-width: 550px) { .research-search-row { flex-direction: column; } .research-video { grid-template-columns: 1fr; } .research-search, .research-options { padding: 15px; } .research-steps { gap: 10px; font-size: 11px; } }
</style>
