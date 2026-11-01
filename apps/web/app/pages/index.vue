<script setup lang="ts">
import type { Page, Project } from '~/types/api'
import { dateTime, isActive, timecode } from '~/utils/format'
const api = useApi()
const projects = ref<Project[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const tableViewport = ref<HTMLElement | null>(null)
let request = 0
const loading = ref(true)
const error = ref('')
const query = ref('')
const status = ref('')
const uploadOpen = ref(false)
const deleteTarget = ref<Project | null>(null)
const deleting = ref(false)
const deleteError = ref('')
const filterOptions = [{ value: '', label: 'Semua status' }, { value: 'ready', label: 'Siap ditinjau' }, { value: 'validating', label: 'Memvalidasi video' }, { value: 'transcribing', label: 'Memproses transkrip' }, { value: 'analyzing', label: 'Memilih kandidat' }, { value: 'failed', label: 'Gagal' }, { value: 'empty', label: 'Belum ada video' }, { value: 'no_speech', label: 'Tidak ditemukan ucapan' }]
const load = async (quiet = false) => {
  const current = ++request
  if (!quiet) loading.value = true
  try { const result = await api<Page<Project>>('/projects', { query: { search: query.value || undefined, status: status.value || undefined, page: page.value, page_size: pageSize } }); if (current !== request) return; projects.value = result.items; total.value = result.total; error.value = '' } catch (e) { if (current === request) error.value = errorMessage(e) } finally { if (current === request) loading.value = false }
}
let debounce: ReturnType<typeof setTimeout> | undefined
watch(query, () => { clearTimeout(debounce); debounce = setTimeout(() => { page.value = 1; void load() }, 300) })
watch(status, () => { page.value = 1; void load() })
watch(page, async () => { await load(); if (tableViewport.value) tableViewport.value.scrollTop = 0 })
onMounted(() => load())
onBeforeUnmount(() => clearTimeout(debounce))
usePolling(() => load(true), () => projects.value.some(p => p.active_jobs?.some(j => isActive(j.status)) || ['processing', 'validating', 'deleting'].includes(p.status)))
const uploaded = async (id: string) => { uploadOpen.value = false; await navigateTo(`/projects/${id}`) }
const remove = async () => { if (!deleteTarget.value) return; deleting.value = true; deleteError.value = ''; try { await api(`/projects/${deleteTarget.value.id}`, { method: 'DELETE', headers: { 'Idempotency-Key': idempotencyKey() } }); deleteTarget.value = null; await load(true) } catch (e) { deleteError.value = errorMessage(e) } finally { deleting.value = false } }
const duration = (p: Project) => p.source_asset?.metadata?.duration_ms || p.duration_ms || 0
</script>
<template>
  <div class="page projects-page">
    <header class="page-header"><div><p class="eyebrow">Pustaka video</p><h1>Proyek</h1><p class="muted">Pilih momen, rapikan klip, lalu ekspor.</p></div><button class="button primary" @click="uploadOpen = true"><AppIcon name="Plus" />Proyek baru</button></header>
    <div class="toolbar"><label class="search-field"><AppIcon name="Search" /><input v-model="query" type="search" placeholder="Cari nama proyek" aria-label="Cari nama proyek" /></label><AppSelect v-model="status" :options="filterOptions" label="Filter status" /><span class="result-count muted">{{ total }} proyek</span></div>
    <InlineError :message="error"><button class="text-button" @click="load()">Coba lagi</button></InlineError>
    <div v-if="loading && !projects.length" class="empty-state" role="status"><p>Memuat proyek…</p></div>
    <section v-else-if="!projects.length && !error" class="empty-state panel"><span class="empty-icon"><AppIcon name="FolderOpen" :size="28" /></span><h2>{{ query || status ? 'Tidak ada proyek yang cocok' : 'Belum ada proyek' }}</h2><p>{{ query || status ? 'Coba kata pencarian atau status lain.' : 'Unggah video pertama untuk mulai membuat klip.' }}</p><button v-if="!query && !status" class="button primary" @click="uploadOpen = true"><AppIcon name="Upload" />Unggah video</button><button v-else class="button secondary" @click="query = ''; status = ''">Hapus filter</button></section>
    <div v-else-if="projects.length" ref="tableViewport" class="library-viewport" role="region" aria-label="Daftar proyek" tabindex="0"><div class="project-table panel">
      <div class="project-table-heading"><span>Nama proyek</span><span>Durasi</span><span>Status</span><span>Diperbarui</span><span class="sr-only">Aksi</span></div>
      <article v-for="project in projects" :key="project.id" class="project-row"><NuxtLink :to="`/projects/${project.id}`" class="project-name"><VideoThumb :asset="project.preview_asset || project.source_asset" /><span><strong>{{ project.name }}</strong><small>{{ project.clip_count || 0 }} klip</small></span></NuxtLink><span class="timecode project-duration">{{ duration(project) ? timecode(duration(project)) : '—' }}</span><div class="project-status"><StatusBadge :status="project.status || project.lifecycle_state" /></div><time class="muted small project-date">{{ dateTime(project.updated_at) }}</time><button class="icon-button delete-project" :aria-label="`Hapus proyek ${project.name}`" @click="deleteTarget = project; deleteError = ''"><AppIcon name="Trash2" :size="17" /></button></article>
    </div>
    </div>
    <div v-if="total > pageSize" class="pagination"><button class="button secondary" :disabled="page <= 1" @click="page--">Sebelumnya</button><span>Halaman {{ page }}</span><button class="button secondary" :disabled="page * pageSize >= total" @click="page++">Berikutnya</button></div>
    <p class="workspace-note"><AppIcon name="Film" :size="16" />Video sumber dan hasil tersimpan privat di instalasi ini.</p>
    <UploadDialog :open="uploadOpen" @close="uploadOpen = false; load(true)" @uploaded="uploaded" />
    <AppDialog :open="!!deleteTarget" title="Hapus proyek?" :description="`Proyek “${deleteTarget?.name}”, video sumber, transkrip, klip, dan seluruh hasil ekspornya akan dihapus. Tindakan ini tidak dapat dibatalkan.`" :busy="deleting" @close="deleteTarget = null"><InlineError :message="deleteError" /><div class="dialog-actions"><button class="button secondary" :disabled="deleting" @click="deleteTarget = null">Batal</button><button class="button danger" :disabled="deleting" @click="remove">{{ deleting ? 'Meminta penghapusan…' : 'Hapus proyek' }}</button></div></AppDialog>
  </div>
</template>
