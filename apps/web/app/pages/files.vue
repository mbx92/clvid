<script setup lang="ts">
import type { MediaFile, MediaPage, MediaSummary } from '~/types/api'
import { dateTime, fileSize, timecode } from '~/utils/format'

const api = useApi()
const files = ref<MediaFile[]>([])
const summary = ref<MediaSummary>({ project_count: 0, video_count: 0, source_bytes: 0, preview_bytes: 0, export_bytes: 0, subtitle_bytes: 0, total_bytes: 0 })
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(true)
const error = ref('')
const query = ref('')
const deleteTarget = ref<MediaFile | null>(null)
const deleting = ref(false)
const deleteError = ref('')
const tableViewport = ref<HTMLElement | null>(null)
let request = 0
let debounce: ReturnType<typeof setTimeout> | undefined

const load = async (quiet = false) => {
  const current = ++request
  if (!quiet) loading.value = true
  try {
    const result = await api<MediaPage>('/media', { query: { search: query.value || undefined, page: page.value, page_size: pageSize } })
    if (current !== request) return
    files.value = result.items
    total.value = result.total
    summary.value = result.summary
    error.value = ''
  } catch (e) {
    if (current === request) error.value = errorMessage(e)
  } finally {
    if (current === request) loading.value = false
  }
}

watch(query, () => {
  clearTimeout(debounce)
  debounce = setTimeout(() => { page.value = 1; void load() }, 300)
})
watch(page, async () => { await load(); if (tableViewport.value) tableViewport.value.scrollTop = 0 })
onMounted(() => load())
onBeforeUnmount(() => clearTimeout(debounce))

const remove = async () => {
  if (!deleteTarget.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await api(`/projects/${deleteTarget.value.project_id}`, { method: 'DELETE', headers: { 'Idempotency-Key': idempotencyKey() } })
    deleteTarget.value = null
    if (files.value.length === 1 && page.value > 1) page.value--
    else await load(true)
  } catch (e) {
    deleteError.value = errorMessage(e)
  } finally {
    deleting.value = false
  }
}

const filename = (item?: MediaFile | null) => item ? String(item.source_asset?.metadata?.filename || `${item.project_name}.mp4`) : 'video'
const duration = (item: MediaFile) => Number(item.source_asset?.metadata?.duration_ms || 0)
const storageParts = computed(() => [
  { key: 'source', label: 'Video sumber', bytes: summary.value.source_bytes },
  { key: 'preview', label: 'Preview', bytes: summary.value.preview_bytes },
  { key: 'export', label: 'Hasil ekspor', bytes: summary.value.export_bytes },
  { key: 'subtitle', label: 'Subtitle', bytes: summary.value.subtitle_bytes },
])
</script>

<template>
  <div class="page files-page">
    <header class="page-header library-header"><div><p class="eyebrow">Penyimpanan lokal</p><h1>File video</h1><p class="muted">Kelola video sumber, preview, dan hasil ekspor yang tersimpan.</p></div><button class="button secondary" :disabled="loading || deleting" @click="load()"><AppIcon name="RefreshCw" :size="16" />Perbarui</button></header>
    <section class="storage-ledger" aria-label="Ringkasan penyimpanan">
      <div class="storage-total"><span class="eyebrow">Total penyimpanan</span><strong>{{ fileSize(summary.total_bytes) }}</strong><span class="muted small">{{ summary.project_count }} sumber · {{ summary.video_count }} file video</span></div>
      <div class="storage-composition"><p class="storage-caption">Komposisi aset<span class="muted">Tersimpan di instalasi ini</span></p><div class="storage-track" role="img" :aria-label="storageParts.map(part => `${part.label}: ${fileSize(part.bytes)}`).join(', ')"><span v-for="part in storageParts" :key="part.key" :class="`storage-part-${part.key}`" :style="{ width: `${summary.total_bytes ? part.bytes / summary.total_bytes * 100 : 0}%` }" /></div><dl class="storage-legend"><div v-for="part in storageParts" :key="part.key"><dt><i :class="`storage-part-${part.key}`" />{{ part.label }}</dt><dd>{{ fileSize(part.bytes) }}</dd></div></dl></div>
    </section>
    <div class="toolbar library-toolbar"><label class="search-field"><AppIcon name="Search" /><input v-model="query" type="search" placeholder="Cari nama proyek" aria-label="Cari nama proyek" /></label><span class="result-count muted">{{ total }} video sumber</span></div>
    <InlineError :message="error"><button class="text-button" @click="load()">Coba lagi</button></InlineError>
    <div v-if="loading && !files.length" class="empty-state" role="status"><p>Memuat file video…</p></div>
    <section v-else-if="!files.length && !error" class="empty-state panel"><span class="empty-icon"><AppIcon name="HardDrive" :size="26" /></span><h2>{{ query ? 'File tidak ditemukan' : 'Belum ada video' }}</h2><p>{{ query ? 'Coba kata pencarian lain.' : 'Video yang diunggah atau diimpor akan muncul di sini.' }}</p><button v-if="query" class="button secondary" @click="query = ''">Hapus pencarian</button><NuxtLink v-else to="/" class="button primary">Buka proyek</NuxtLink></section>
    <div v-else ref="tableViewport" class="library-viewport" role="region" aria-label="Daftar file video" tabindex="0"><div class="media-table panel">
      <div class="media-table-heading"><span>Video sumber</span><span>Durasi</span><span>Semua file</span><span>Diperbarui</span><span class="sr-only">Aksi</span></div>
      <article v-for="item in files" :key="item.project_id" class="media-row">
        <NuxtLink :to="`/projects/${item.project_id}`" class="media-name"><VideoThumb :asset="item.source_asset" /><span><strong>{{ filename(item) }}</strong><small>{{ item.project_name }} · {{ item.file_count }} file terkait</small></span></NuxtLink>
        <span class="timecode media-duration">{{ duration(item) ? timecode(duration(item)) : '—' }}</span>
        <div class="media-storage"><strong>{{ fileSize(item.total_bytes) }}</strong><small class="muted">Sumber {{ fileSize(item.source_bytes) }}<template v-if="item.export_bytes"> · Ekspor {{ fileSize(item.export_bytes) }}</template></small></div>
        <time class="muted small media-date">{{ dateTime(item.updated_at) }}</time>
        <button class="icon-button delete-media" :aria-label="`Hapus video ${filename(item)}`" title="Hapus video" @click="deleteTarget = item; deleteError = ''"><AppIcon name="Trash2" :size="17" /></button>
      </article>
    </div></div>
    <div v-if="total > pageSize" class="pagination"><button class="button secondary" :disabled="page <= 1" @click="page--">Sebelumnya</button><span>Halaman {{ page }}</span><button class="button secondary" :disabled="page * pageSize >= total" @click="page++">Berikutnya</button></div>
    <p class="workspace-note"><AppIcon name="HardDrive" :size="16" />Penghapusan dijalankan di latar belakang dan ruang disk dibebaskan setelah pekerjaan selesai.</p>
    <AppDialog :open="!!deleteTarget" title="Hapus video dan proyek?" :description="`Video “${filename(deleteTarget)}” beserta proyek “${deleteTarget?.project_name}”, transkrip, klip, preview, dan seluruh hasil ekspornya akan dihapus permanen.`" :busy="deleting" @close="deleteTarget = null"><InlineError :message="deleteError" /><div class="delete-size-summary"><span>Ruang yang akan dibebaskan</span><strong>{{ fileSize(deleteTarget?.total_bytes || 0) }}</strong></div><div class="dialog-actions"><button class="button secondary" :disabled="deleting" @click="deleteTarget = null">Batal</button><button class="button danger" :disabled="deleting" @click="remove">{{ deleting ? 'Meminta penghapusan…' : 'Hapus permanen' }}</button></div></AppDialog>
  </div>
</template>
