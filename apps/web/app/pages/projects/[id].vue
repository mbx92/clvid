<script setup lang="ts">
import { tabsKeydown } from '~/utils/accessibility'
import type { Clip, Export, Job, Page, Project, Segment, Transcript } from '~/types/api'
import { fileSize, isActive, parseTimecode, timecode } from '~/utils/format'
const route = useRoute()
const api = useApi()
const id = computed(() => String(route.params.id))
const project = ref<Project | null>(null)
const clipList = usePaginatedList<Clip>((page, pageSize) => api<Page<Clip>>(`/projects/${id.value}/clips`, { query: { page, page_size: pageSize } }))
const exportList = usePaginatedList<Export>((page, pageSize) => api<Page<Export>>(`/projects/${id.value}/exports`, { query: { page, page_size: pageSize } }))
const { items: clips, total: clipTotal, loading: clipsLoading, hasMore: moreClips } = clipList
const { items: exports, total: exportTotal, loading: exportsLoading, hasMore: moreExports } = exportList
const transcript = ref<Transcript | null>(null)
const transcriptPage = ref(1)
const transcriptQuery = ref('')
const tab = ref('clips')
const mobilePane = ref('content')
const maxClipMs = computed(() => project.value?.limits?.max_clip_ms || 180000)
const error = ref('')
const loading = ref(true)
const busy = ref(false)
const uploadOpen = ref(false)
const manualOpen = ref(false)
const manualError = ref('')
const manualTitle = ref('Klip baru')
const manualStart = ref('00:00.000')
const manualEnd = ref('00:30.000')
const processOpen = ref(false)
const language = ref('auto')
const count = ref(5)
const minSeconds = ref(30)
const maxSeconds = ref(60)
const aiConfigured = ref(true)
const processError = ref('')
const transcribeAgain = ref(false)
const renameOpen = ref(false)
const newName = ref('')
const renameError = ref('')
const video = ref<HTMLVideoElement | null>(null)
const duration = computed(() => Number(project.value?.source_asset?.metadata?.duration_ms || project.value?.duration_ms || 0))
const sourceUrl = computed(() => { const asset = project.value?.preview_asset || project.value?.source_asset; return asset?.state === 'ready' ? `/api/v1/assets/${asset.id}/content` : '' })
const canWork = computed(() => project.value?.source_asset?.state === 'ready' && duration.value > 0)
const jobs = computed(() => (project.value?.jobs || project.value?.active_jobs || []).filter(j => isActive(j.status) || j.status === 'failed' || j.status === 'cancelled'))
const selectionMessage = computed(() => project.value?.jobs?.find(j => j.kind === 'analyze' && j.status === 'succeeded')?.result_json?.message)
const filteredSegments = computed(() => transcript.value?.segments || [])
const loadTranscript = async (append = false) => {
  if (!project.value?.latest_transcript_version) return
  const result = await api<Transcript>(`/projects/${id.value}/transcripts/latest`, { query: { search: transcriptQuery.value, page: append ? transcriptPage.value + 1 : 1, page_size: 100 } })
  if (append && transcript.value) { transcript.value.segments.push(...result.segments); transcriptPage.value++ }
  else { transcript.value = result; transcriptPage.value = 1 }
}
let transcriptSearchTimer: ReturnType<typeof setTimeout> | undefined
watch(transcriptQuery, () => { clearTimeout(transcriptSearchTimer); transcriptSearchTimer = setTimeout(() => void loadTranscript().catch(e => error.value = errorMessage(e)), 300) })
onBeforeUnmount(() => clearTimeout(transcriptSearchTimer))
const load = async () => {
  try {
    const oldVersion = project.value?.latest_transcript_version
    const result = await api<Project>(`/projects/${id.value}`)
    project.value = result
    maxSeconds.value = Math.min(maxSeconds.value, maxClipMs.value / 1000); minSeconds.value = Math.min(minSeconds.value, maxSeconds.value)
    await Promise.all([clipList.refresh(), exportList.refresh()])
    if (result.latest_transcript_version && (!transcript.value || oldVersion !== result.latest_transcript_version)) await loadTranscript()
    error.value = ''
  } catch (e) { error.value = errorMessage(e) } finally { loading.value = false }
}
onMounted(async () => { await load(); try { const settings = await api('/settings'); aiConfigured.value = settings.ai_configured ?? settings.deepseek_configured ?? settings.ai?.configured ?? false } catch {} })
usePolling(load, () => (project.value?.jobs || []).some(j => isActive(j.status)) || exports.value.some(e => isActive(e.job?.status || e.status)))
const seek = (ms: number) => { mobilePane.value = 'video'; if (video.value) { video.value.currentTime = ms / 1000; video.value.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); void video.value.play().catch(() => {}) } }
const openManual = (segment?: Segment) => { manualTitle.value = 'Klip baru'; manualStart.value = timecode(segment?.start_ms || 0, true); manualEnd.value = timecode(Math.min(duration.value, segment ? Math.min(segment.start_ms + maxClipMs.value, Math.max(segment.end_ms, segment.start_ms + 5000)) : Math.min(30000, maxClipMs.value)), true); manualError.value = ''; manualOpen.value = true }
const createManual = async () => {
  const start = parseTimecode(manualStart.value); const end = parseTimecode(manualEnd.value)
  if (start === null || end === null || end <= start || start < 0 || end > duration.value || end - start < 5000 || end - start > maxClipMs.value) { manualError.value = 'Gunakan batas waktu yang valid, di dalam video, dengan durasi 5–180 detik.'; return }
  busy.value = true; manualError.value = ''
  try { const clip = await api<Clip>(`/projects/${id.value}/clips`, { method: 'POST', body: { title: manualTitle.value, start_ms: start, end_ms: end, transcript_id: transcript.value?.id || null } }); manualOpen.value = false; await navigateTo(`/clips/${clip.id}`) } catch (e) { manualError.value = errorMessage(e) } finally { busy.value = false }
}
const process = async (analyze: boolean) => {
  if (minSeconds.value < 5 || maxSeconds.value > maxClipMs.value / 1000 || minSeconds.value > maxSeconds.value) { processError.value = 'Rentang durasi harus 5–180 detik, dengan minimum tidak melebihi maksimum.'; return }
  busy.value = true; processError.value = ''
  try { await api<Job>(`/projects/${id.value}/process`, { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey() }, body: { language: language.value, count: count.value, min_duration_ms: minSeconds.value * 1000, max_duration_ms: maxSeconds.value * 1000, analyze, transcribe_again: transcribeAgain.value } }); processOpen.value = false; await load() } catch (e) { processError.value = errorMessage(e) } finally { busy.value = false }
}
const uploaded = async () => { uploadOpen.value = false; await load() }
const rename = async () => { busy.value = true; renameError.value = ''; try { await api(`/projects/${id.value}`, { method: 'PATCH', body: { name: newName.value } }); renameOpen.value = false; await load() } catch (e) { renameError.value = errorMessage(e) } finally { busy.value = false } }
</script>
<template>
  <div class="page detail-page fixed-workspace" :class="`mobile-${mobilePane}`">
    <NuxtLink to="/" class="breadcrumb"><AppIcon name="ArrowLeft" :size="16" />Proyek</NuxtLink>
    <InlineError :message="error"><button class="text-button" @click="load">Coba lagi</button></InlineError>
    <p v-if="loading" class="loading-text" role="status">Memuat proyek…</p>
    <template v-if="project">
      <header class="page-header"><div><div class="row gap-3 wrap"><h1>{{ project.name }}</h1><button class="text-button small" @click="newName = project.name; renameError = ''; renameOpen = true">Ubah nama</button><StatusBadge :status="project.status || project.lifecycle_state" /></div><p class="muted">{{ project.source_asset ? `${fileSize(project.source_asset.bytes)} · ${timecode(duration)}${project.source_asset.metadata.width ? ` · ${project.source_asset.metadata.width} × ${project.source_asset.metadata.height}` : ''}` : 'Belum ada video sumber' }}</p></div><div class="header-actions"><button v-if="canWork" class="button secondary" @click="openManual()"><AppIcon name="Plus" />Klip manual</button><button v-if="canWork" class="button primary" @click="processOpen = true"><AppIcon name="Scissors" />Buat kandidat</button><button v-else-if="!project.source_asset || ['failed', 'invalid'].includes(project.source_asset.state)" class="button primary" @click="uploadOpen = true"><AppIcon name="Upload" />Unggah video</button></div></header>
      <div v-if="jobs.length" class="jobs-panel panel" aria-live="polite"><ScrollList :items="jobs" label="pekerjaan" v-slot="{ items }"><JobStatus v-for="job in items" :key="job.id" :job="job" @refresh="load" /></ScrollList></div>
      <div class="workspace-switch" role="group" aria-label="Tampilan workspace"><button :aria-pressed="mobilePane === 'video'" @click="mobilePane = 'video'">Video sumber</button><button :aria-pressed="mobilePane === 'content'" @click="mobilePane = 'content'">Klip &amp; transkrip</button></div>
      <div class="project-workspace">
        <aside class="source-panel"><div class="source-player"><video v-if="sourceUrl" ref="video" :src="sourceUrl" controls preload="metadata" playsinline /><div v-else class="source-placeholder"><AppIcon name="Film" :size="32" /><span>{{ project.source_asset ? 'Preview tersedia setelah validasi.' : 'Unggah video untuk mulai.' }}</span></div></div><div class="source-caption"><span>Video sumber</span><span class="timecode">{{ timecode(duration) }}</span></div><p class="muted small">Preview memakai video asli atau proxy yang kompatibel. Klip final dirender dari sumber asli.</p></aside>
        <section class="project-content panel"><div class="tabs" role="tablist" @keydown="tabsKeydown" aria-label="Konten proyek"><button id="tab-clips" class="tab" :class="{ active: tab === 'clips' }" role="tab" :aria-selected="tab === 'clips'" aria-controls="project-panel" @click="tab = 'clips'">Kandidat <span class="tab-count">{{ clipTotal }}</span></button><button id="tab-transcript" class="tab" :class="{ active: tab === 'transcript' }" role="tab" :aria-selected="tab === 'transcript'" aria-controls="project-panel" @click="tab = 'transcript'">Transkrip</button><button id="tab-exports" class="tab" :class="{ active: tab === 'exports' }" role="tab" :aria-selected="tab === 'exports'" aria-controls="project-panel" @click="tab = 'exports'">Ekspor</button></div>
          <div id="project-panel" role="tabpanel" :aria-labelledby="`tab-${tab}`">
            <template v-if="tab === 'clips'"><p v-if="selectionMessage" class="section-note">{{ selectionMessage }}</p><div v-if="!clips.length" class="empty-state"><AppIcon name="Scissors" :size="25" /><h2>Belum ada klip</h2><p>{{ canWork ? 'Buat kandidat dari transkrip atau tentukan potongan secara manual.' : 'Selesaikan unggah dan validasi video terlebih dahulu.' }}</p><button v-if="canWork" class="button secondary" @click="openManual()">Buat klip manual</button></div><ScrollList v-else :items="clips" label="kandidat" v-slot="{ items, start }"><div class="clip-list"><article v-for="(clip, index) in items" :key="clip.id" class="clip-row"><span class="clip-number">{{ String(start + index + 1).padStart(2, '0') }}</span><div class="clip-copy"><div class="row gap-2 wrap"><h3>{{ clip.revision.title }}</h3><span class="origin-label">{{ clip.origin === 'manual' ? 'Manual' : 'Rekomendasi' }}</span></div><p class="muted">{{ clip.revision.reason || 'Potongan yang Anda pilih sendiri.' }}</p><span class="timecode small">{{ timecode(clip.revision.start_ms) }} – {{ timecode(clip.revision.end_ms) }} · {{ timecode(clip.revision.end_ms - clip.revision.start_ms) }}</span></div><NuxtLink class="button secondary small-button" :to="`/clips/${clip.id}`">Tinjau<AppIcon name="ArrowRight" :size="15" /></NuxtLink></article></div></ScrollList><LoadMore :loaded="clips.length" :total="clipTotal" :loading="clipsLoading" :has-more="moreClips" label="klip" button-label="Muat klip lainnya" @more="clipList.loadMore().catch(e => error = errorMessage(e))" /><p v-if="clips.length" class="section-note">Rekomendasi membantu pemilihan editorial. Tinjau konteks ucapan sebelum mengekspor.</p></template>
            <template v-if="tab === 'transcript'"><div v-if="!transcript || project.status === 'no_speech'" class="empty-state"><AppIcon name="FileText" :size="25" /><h2>{{ project.status === 'no_speech' ? 'Tidak ditemukan ucapan' : 'Transkrip belum tersedia' }}</h2><p>{{ project.status === 'no_speech' ? 'Anda tetap dapat membuat klip manual dari video.' : 'Transkripsi dijalankan di server ini dan tidak memerlukan API AI.' }}</p><button v-if="canWork" class="button secondary" @click="processOpen = true">Atur transkripsi</button></div><div v-else class="transcript-panel"><div class="transcript-toolbar"><label class="search-field"><AppIcon name="Search" :size="16" /><input v-model="transcriptQuery" type="search" placeholder="Cari seluruh transkrip" aria-label="Cari seluruh transkrip" /></label><span class="muted small">Versi {{ transcript.version }} · {{ transcript.language }}</span></div><ScrollList :items="filteredSegments" label="transkrip" v-slot="{ items }"><article v-for="segment in items" :key="segment.id" class="transcript-segment"><button class="timecode text-button" :aria-label="`Putar dari ${timecode(segment.start_ms)}`" @click="seek(segment.start_ms)">{{ timecode(segment.start_ms) }}</button><p>{{ segment.text }}</p><button class="icon-button" :aria-label="`Buat klip dari ${timecode(segment.start_ms)}`" title="Buat klip dari sini" @click="openManual(segment)"><AppIcon name="Scissors" :size="16" /></button></article></ScrollList><p v-if="!filteredSegments.length" class="empty-text">Tidak ada teks yang cocok.</p><button v-if="transcript.segments.length < transcript.total" class="button secondary load-more" @click="loadTranscript(true).catch(e => error = errorMessage(e))">Muat segmen berikutnya</button><p class="section-note">{{ transcript.segments.length }} dari {{ transcript.total }} segmen{{ transcriptQuery ? ' yang cocok' : '' }} dimuat. Klik waktu untuk berpindah ke ucapan.</p></div></template>
            <template v-if="tab === 'exports'"><ExportList :exports="exports" @refresh="load" /><LoadMore :loaded="exports.length" :total="exportTotal" :loading="exportsLoading" :has-more="moreExports" label="hasil ekspor" button-label="Muat ekspor sebelumnya" @more="exportList.loadMore().catch(e => error = errorMessage(e))" /></template>
          </div>
        </section>
      </div>
      <UploadDialog :open="uploadOpen" :project-id="project.id" :project-name="project.name" @close="uploadOpen = false" @uploaded="uploaded" />
    </template>
    <AppDialog :open="renameOpen" title="Ubah nama proyek" :busy="busy" @close="renameOpen = false"><form class="form-stack" @submit.prevent="rename"><label>Nama proyek<input v-model="newName" required maxlength="200" /></label><InlineError :message="renameError" /><div class="dialog-actions"><button type="button" class="button secondary" :disabled="busy" @click="renameOpen = false">Batal</button><button type="submit" class="button primary" :disabled="busy">Simpan nama</button></div></form></AppDialog>
    <AppDialog :open="manualOpen" title="Buat klip manual" description="Tentukan batas potongan di video sumber. Durasi klip 5–180 detik." :busy="busy" @close="manualOpen = false"><form class="form-stack" @submit.prevent="createManual"><label>Judul klip<input v-model="manualTitle" required maxlength="200" /></label><div class="form-grid"><label>Mulai<input v-model="manualStart" class="timecode" inputmode="decimal" placeholder="00:00.000" required /></label><label>Selesai<input v-model="manualEnd" class="timecode" inputmode="decimal" placeholder="00:30.000" required /></label></div><p class="muted small">Format menit:detik.milidetik. Subtitle diambil dari transkrip bila tersedia.</p><InlineError :message="manualError" /><div class="dialog-actions"><button type="button" class="button secondary" :disabled="busy" @click="manualOpen = false">Batal</button><button class="button primary" type="submit" :disabled="busy">{{ busy ? 'Membuat klip…' : 'Buat klip' }}</button></div></form></AppDialog>
    <AppDialog :open="processOpen" title="Siapkan kandidat klip" description="Pilih bahasa dan rentang durasi yang Anda perlukan." :busy="busy" @close="processOpen = false"><form class="form-stack" @submit.prevent="process(true)"><label>Bahasa ucapan<AppSelect v-model="language" label="Bahasa ucapan" :options="[{ value: 'auto', label: 'Deteksi otomatis' }, { value: 'id', label: 'Indonesia' }, { value: 'en', label: 'Inggris' }]" /></label><label v-if="transcript" class="checkbox-label"><input v-model="transcribeAgain" type="checkbox" />Buat versi transkrip baru</label><p v-if="transcript" class="muted small">{{ transcribeAgain ? 'Transkrip lama dan klip yang sudah dibuat tetap tersimpan.' : 'Transkrip tersimpan digunakan kembali untuk pemilihan kandidat.' }}</p><div class="form-grid three"><label>Jumlah kandidat<input v-model.number="count" type="number" min="1" max="20" required /></label><label>Minimum (detik)<input v-model.number="minSeconds" type="number" min="5" :max="maxClipMs / 1000" required /></label><label>Maksimum (detik)<input v-model.number="maxSeconds" type="number" min="5" :max="maxClipMs / 1000" required /></label></div><p class="privacy-note">Transkripsi diproses di server ini. Teks transkrip dikirim ke penyedia AI untuk memilih kandidat. Jumlah hasil bisa lebih sedikit jika kandidat valid terbatas.</p><p v-if="!aiConfigured" class="notice">Penyedia AI belum dikonfigurasi. Anda dapat menjalankan transkripsi dan membuat klip manual.</p><InlineError :message="processError" /><div class="dialog-actions"><button type="button" class="button secondary" :disabled="busy" @click="process(false)">{{ busy ? 'Mengantrekan…' : 'Transkripsi saja' }}</button><button type="submit" class="button primary" :disabled="busy || !aiConfigured">Buat kandidat</button></div></form></AppDialog>
  </div>
</template>
