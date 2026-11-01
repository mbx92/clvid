<script setup lang="ts">
import type { Job, Project } from '~/types/api'
import { fileSize } from '~/utils/format'
const props = defineProps<{ open: boolean; projectId?: string; projectName?: string }>()
const emit = defineEmits<{ close: []; uploaded: [projectId: string, job: Job] }>()
const api = useApi()
const { csrf } = useSession()
const name = ref('')
const file = ref<File | null>(null)
const sourceMode = ref<'file' | 'url'>('file')
const sourceUrl = ref('')
const progress = ref<number | null>(null)
const busy = ref(false)
const error = ref('')
const createdId = ref('')
const maxBytes = ref(2147483648)
let xhr: XMLHttpRequest | null = null
watch(() => props.open, async open => { if (open) { name.value = props.projectName || ''; createdId.value = props.projectId || ''; file.value = null; sourceMode.value = 'file'; sourceUrl.value = ''; error.value = ''; progress.value = null; try { const settings = await api('/settings'); maxBytes.value = settings.max_upload_bytes || maxBytes.value } catch {} } })
const chooseFile = (event: Event) => { file.value = (event.target as HTMLInputElement).files?.[0] || null; error.value = ''; if (file.value && !name.value) name.value = file.value.name.replace(/\.mp4$/i, '') }
const upload = async () => {
  if (sourceMode.value === 'file' && !file.value) { error.value = 'Pilih file MP4 terlebih dahulu.'; return }
  if (sourceMode.value === 'file' && file.value && file.value.size > maxBytes.value) { error.value = `Ukuran file melebihi batas ${fileSize(maxBytes.value)}.`; return }
  if (sourceMode.value === 'url') {
    try { const parsed = new URL(sourceUrl.value.trim()); if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error() }
    catch { error.value = 'Masukkan URL video publik yang diawali https:// atau http://.'; return }
  }
  if (!name.value.trim()) { error.value = 'Masukkan nama proyek.'; return }
  busy.value = true; error.value = ''; progress.value = 0
  try {
    if (!createdId.value) { const project = await api<Project>('/projects', { method: 'POST', body: { name: name.value.trim() } }); createdId.value = project.id }
    if (sourceMode.value === 'url') {
      const job = await api<Job>(`/projects/${createdId.value}/source-url`, { method: 'POST', body: { url: sourceUrl.value.trim() }, headers: { 'Idempotency-Key': idempotencyKey() } })
      emit('uploaded', createdId.value, job)
      return
    }
    const result = await new Promise<Job>((resolve, reject) => {
      xhr = new XMLHttpRequest()
      xhr.open('POST', `/api/v1/projects/${createdId.value}/source`)
      xhr.withCredentials = true
      xhr.setRequestHeader('X-CSRF-Token', csrf.value)
      xhr.setRequestHeader('X-Filename', encodeURIComponent(file.value!.name))
      xhr.setRequestHeader('Content-Type', 'video/mp4')
      xhr.setRequestHeader('Idempotency-Key', idempotencyKey())
      xhr.upload.onprogress = event => { progress.value = event.lengthComputable ? Math.round(event.loaded / event.total * 100) : null }
      xhr.onload = () => { let result: any; try { result = JSON.parse(xhr!.responseText) } catch {} if (xhr!.status >= 200 && xhr!.status < 300) resolve(result); else reject(new Error(result?.message || 'Upload gagal. File dapat diunggah ulang dari awal.')) }
      xhr.onerror = () => reject(new Error('Koneksi terputus. Unggah ulang file dari awal.'))
      xhr.onabort = () => reject(new Error('Upload dibatalkan. Proyek tetap tersimpan; unggah ulang file dari awal.'))
      xhr.send(file.value)
    })
    emit('uploaded', createdId.value, result)
  } catch (e) { error.value = errorMessage(e) } finally { busy.value = false; xhr = null }
}
onBeforeUnmount(() => xhr?.abort())
</script>
<template>
  <AppDialog :open="open" :title="projectId ? 'Unggah video' : 'Proyek baru'" description="Unggah file atau impor video dari tautan publik." :busy="busy" @close="emit('close')">
    <form class="form-stack" @submit.prevent="upload"><label v-if="!projectId">Nama proyek<input v-model="name" maxlength="200" required placeholder="Misalnya: Percakapan tentang desain" :disabled="busy || !!createdId" /></label>
      <div class="row gap-3" role="group" aria-label="Sumber video"><button type="button" class="button" :class="sourceMode === 'file' ? 'primary' : 'secondary'" :aria-pressed="sourceMode === 'file'" :disabled="busy" @click="sourceMode = 'file'; error = ''">File perangkat</button><button type="button" class="button" :class="sourceMode === 'url' ? 'primary' : 'secondary'" :aria-pressed="sourceMode === 'url'" :disabled="busy" @click="sourceMode = 'url'; error = ''">URL video</button></div>
      <label v-if="sourceMode === 'file'" class="upload-zone"><AppIcon name="Upload" :size="24" /><span>{{ file ? file.name : 'Pilih video MP4' }}</span><small>{{ file ? fileSize(file.size) : `Maksimal ${fileSize(maxBytes)}` }}</small><input type="file" accept="video/mp4,.mp4" :disabled="busy" @change="chooseFile" /></label>
      <template v-else><label>URL video publik<input v-model="sourceUrl" type="url" inputmode="url" maxlength="4096" required placeholder="https://www.youtube.com/watch?v=..." :disabled="busy" aria-describedby="url-help" /></label><p id="url-help" class="muted small">Tautan MP4, YouTube, TikTok, Instagram, dan situs lain yang didukung. Gunakan satu video publik yang Anda miliki atau boleh gunakan. Video privat, DRM, playlist, dan siaran langsung tidak didukung. Maksimal {{ fileSize(maxBytes) }}.</p><p class="notice">Video diunduh di server. Anda bisa meninggalkan halaman setelah impor masuk antrean.</p></template>
      <p class="privacy-note">Transkripsi diproses di server ini. Teks transkrip dikirim ke penyedia AI untuk memilih kandidat.</p>
      <p v-if="busy && sourceMode === 'url'" role="status">Mengantrekan impor video…</p>
      <div v-if="busy && sourceMode === 'file'" class="upload-progress" role="status"><div class="row between"><span>{{ progress === 100 ? 'Transfer selesai, menyimpan file…' : 'Mengunggah video…' }}</span><span v-if="progress !== null">{{ progress }}%</span></div><progress v-if="progress !== null" :value="progress" max="100" aria-label="Progress unggah video" /><p class="muted small">Biarkan halaman ini terbuka hingga transfer selesai.</p></div>
      <InlineError :message="error" />
      <div class="dialog-actions"><button v-if="busy && sourceMode === 'file'" type="button" class="button secondary" @click="xhr?.abort()">Batalkan upload</button><button v-else type="button" class="button secondary" :disabled="busy" @click="emit('close')">Tutup</button><button type="submit" class="button primary" :disabled="busy || (sourceMode === 'file' ? !file : !sourceUrl.trim())"><AppIcon name="Upload" />{{ sourceMode === 'url' ? 'Impor video' : (error && createdId ? 'Unggah ulang' : 'Unggah video') }}</button></div>
    </form>
  </AppDialog>
</template>
