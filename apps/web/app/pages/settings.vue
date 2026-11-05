<script setup lang="ts">
import { dateTime, fileSize } from '~/utils/format'
import { platformLabels } from '~/utils/calendar'
const api = useApi()
const route = useRoute()
const settings = ref<any>(null)
const usage = ref<any>(null)
const accounts = ref<any[]>([])
const platforms = ref<any[]>([])
const languageLabels: Record<string, string> = { auto: 'Deteksi otomatis', id: 'Indonesia', en: 'Inggris' }
const error = ref('')
const loading = ref(true)
const section = ref('limits')
const sections = [{id:'limits',label:'Batas pemrosesan'},{id:'accounts',label:'Koneksi akun'},{id:'video',label:'Video'},{id:'ai',label:'AI & layanan'},{id:'usage',label:'Pemakaian'}]
const saving = ref(false)
const socialBusy = ref(false)
const socialNotice = ref('')
const disconnecting = ref<any>(null)
const savedMessage = ref('')
const sourceMinutes = ref(60)
const fileGiB = ref(2)
const clipSeconds = ref(180)
const adoptLimits = () => { sourceMinutes.value = settings.value.max_video_seconds / 60; fileGiB.value = settings.value.max_upload_bytes / 1024 ** 3; clipSeconds.value = settings.value.max_clip_ms / 1000 }
const saveLimits = async () => {
  saving.value = true; error.value = ''; savedMessage.value = ''
  try {
    settings.value = await api('/settings', { method: 'PATCH', body: { max_video_seconds: Math.round(sourceMinutes.value * 60), max_upload_bytes: Math.round(fileGiB.value * 1024 ** 3), max_clip_ms: Math.round(clipSeconds.value * 1000) } })
    adoptLimits(); savedMessage.value = 'Batas pemrosesan tersimpan.'
  } catch (e) { error.value = errorMessage(e) } finally { saving.value = false }
}
const load = async () => { loading.value = true; try { const results = await Promise.all([api('/settings'), api('/usage'), api<any>('/social/accounts')]); settings.value = results[0]; adoptLimits(); usage.value = results[1]; accounts.value = results[2].items; platforms.value = results[2].platforms; error.value = '' } catch (e) { error.value = errorMessage(e) } finally { loading.value = false } }
async function connect(platform: string) {
  socialBusy.value = true; error.value = ''
  try { const result = await api<any>(`/social/oauth/${platform}/start`, { method: 'POST' }); window.location.assign(result.url) }
  catch (e) { error.value = errorMessage(e) } finally { socialBusy.value = false }
}
async function disconnect() {
  if (!disconnecting.value) return
  socialBusy.value = true; error.value = ''
  try { await api(`/social/accounts/${disconnecting.value.id}`, { method: 'DELETE' }); disconnecting.value = null; socialNotice.value = 'Koneksi akun dilepas.'; await load() }
  catch (e) { error.value = errorMessage(e) } finally { socialBusy.value = false }
}
onMounted(() => {
  if (typeof route.query.section === 'string' && sections.some(item => item.id === route.query.section)) section.value = route.query.section
  const status = route.query.connection
  if (status === 'connected') socialNotice.value = 'Akun berhasil dihubungkan.'
  else if (status === 'reconnected') socialNotice.value = 'Koneksi akun yang sudah ada diperbarui. Tidak ada akun baru yang ditambahkan.'
  else if (status === 'failed') socialNotice.value = 'Koneksi akun belum berhasil. Periksa izin aplikasi, callback URL, dan akun profesional atau channel.'
  else if (status === 'cancelled') socialNotice.value = 'Otorisasi dibatalkan.'
  void load()
})
</script>
<template>
  <div class="page settings-page"><header class="page-header"><div><p class="eyebrow">Instalasi lokal</p><h1>Pengaturan</h1><p class="muted">Konfigurasi pemrosesan, koneksi akun, status layanan, dan pemakaian Anda.</p></div><button class="button secondary" :disabled="loading || saving || socialBusy" @click="load"><AppIcon name="RefreshCw" :size="16" />Perbarui</button></header><InlineError :message="error" /><p v-if="loading && !settings" role="status">Memuat pengaturan…</p>
    <template v-if="settings"><div class="tool-tabs settings-tabs" role="group" aria-label="Bagian pengaturan"><button v-for="item in sections" :key="item.id" :aria-pressed="section === item.id" @click="section = item.id">{{ item.label }}</button></div><DesktopFit :fit="false"><section v-show="section === 'limits'" class="settings-section panel"><header><h2>Batas pemrosesan</h2><p class="muted">Berlaku untuk akun Anda, termasuk impor URL. Pekerjaan baru dan percobaan ulang memakai batas terbaru; pekerjaan yang sedang berjalan tetap memakai batas sebelumnya.</p></header>
      <form class="limits-form form-stack" @submit.prevent="saveLimits">
        <div class="form-grid three">
          <label>Durasi maksimum video sumber (menit)<input v-model.number="sourceMinutes" aria-label="Durasi maksimum video sumber (menit)" aria-describedby="source-limit-help" type="number" min="1" max="720" step="1" required /><small id="source-limit-help" class="muted">1–720 menit (12 jam)</small></label>
          <label>Ukuran maksimum file (GiB)<input v-model.number="fileGiB" aria-label="Ukuran maksimum file (GiB)" aria-describedby="file-limit-help" type="number" min="0.001" max="64" step="any" required /><small id="file-limit-help" class="muted">Maksimal 64 GiB</small></label>
          <label>Durasi maksimum klip (detik)<input v-model.number="clipSeconds" aria-label="Durasi maksimum klip (detik)" aria-describedby="clip-limit-help" type="number" min="5" max="600" step="1" required /><small id="clip-limit-help" class="muted">5–600 detik (10 menit)</small></label>
        </div>
        <p class="muted small">Klip tersimpan tetap tersedia bila batas diturunkan. Durasi dan ukuran yang lebih besar membutuhkan waktu pemrosesan serta ruang penyimpanan lebih banyak.</p>
        <div class="row gap-3"><button class="button primary" type="submit" :disabled="saving || loading">{{ saving ? 'Menyimpan...' : 'Simpan batas' }}</button><span v-if="savedMessage" role="status">{{ savedMessage }}</span></div>
      </form>
    </section><section v-show="section === 'accounts'" class="settings-section panel account-connections"><header><h2>Koneksi akun publikasi</h2><p class="muted">Hubungkan channel tujuan. Kalender menyiapkan usulan jadwal dan menampilkan riwayat publikasi dari akun terhubung.</p></header><p v-if="socialNotice" class="notice" role="status">{{ socialNotice }}</p>
      <div class="connection-grid"><article v-for="platform in platforms" :key="platform.id"><div class="connection-heading"><h3>{{ platformLabels[platform.id] }}</h3><span class="connection-state" :class="{ ready: platform.configured && platform.publishing_ready }" :aria-label="platform.configured && platform.publishing_ready ? 'Konfigurasi siap' : 'Konfigurasi belum siap'" /></div><p class="muted small">{{ platform.configured ? (platform.publishing_ready ? 'Konfigurasi siap; hubungkan satu atau beberapa akun tujuan.' : 'Koneksi tersedia; publikasi otomatis belum aktif.') : 'Aplikasi developer belum dikonfigurasi.' }}</p><button class="button secondary" :disabled="!platform.configured || socialBusy" @click="connect(platform.id)">{{ platform.id === 'youtube' && accounts.some(a => a.platform === 'youtube') ? 'Tambah channel YouTube' : `Hubungkan ${platformLabels[platform.id]}` }}</button><p v-if="platform.id === 'youtube'" class="muted small">Hubungkan setiap channel secara terpisah. Untuk menambah channel, pilih akun Google yang sama, lalu pilih channel atau Brand Account lainnya pada layar Google. Channel yang sudah terhubung tetap tersedia.</p><p v-for="account in accounts.filter(a => a.platform === platform.id)" :key="account.id" class="connected-account"><strong>{{ account.name }}</strong><button class="text-button" :disabled="socialBusy" @click="disconnecting = account">Lepas</button></p><p v-if="!accounts.some(a => a.platform === platform.id)" class="muted small">Belum ada akun terhubung.</p><details><summary>Persiapan koneksi</summary><p v-if="platform.id === 'youtube'">Buat project Google Cloud, aktifkan YouTube Data API, dan buat OAuth client Web. Satu email Google dapat dihubungkan berulang untuk channel atau Brand Account yang berbeda.</p><p v-else-if="platform.id === 'instagram'">Gunakan akun Instagram profesional yang terhubung ke Facebook Page. Instalasi memerlukan HTTPS publik agar Meta dapat mengambil video.</p><p v-else>TikTok Direct Post memerlukan aplikasi dan akses yang disetujui. Kalender tetap dapat digunakan sebagai draft untuk unggah manual.</p><label>Callback URL<input readonly :value="platform.callback_url" :aria-label="`Callback ${platformLabels[platform.id]}`" /></label><a :href="platform.id === 'youtube' ? 'https://console.cloud.google.com/apis/credentials' : platform.id === 'instagram' ? 'https://developers.facebook.com/apps/' : 'https://developers.tiktok.com/'" target="_blank" rel="noopener noreferrer">Buka portal developer ↗</a></details></article></div>
    </section><section v-show="section === 'video'" class="settings-section panel"><header><h2>Pemrosesan video</h2></header><dl class="definition-list"><div><dt>Bahasa default</dt><dd>{{ languageLabels[settings.default_language] || settings.default_language }}</dd></div><div><dt>Batas resolusi</dt><dd>{{ settings.max_video_width }} × {{ settings.max_video_height }} atau orientasi setara</dd></div><div><dt>Model transkripsi</dt><dd>{{ settings.whisper_model }}</dd></div><div><dt>Perangkat / komputasi</dt><dd>{{ settings.whisper_device }} / {{ settings.whisper_compute_type }}</dd></div></dl></section>
    <section v-show="section === 'ai'" class="settings-section panel"><header><h2>Rekomendasi kandidat</h2><p class="muted">Hanya teks transkrip yang dikirim ke penyedia AI.</p></header><dl class="definition-list"><div><dt>DeepSeek</dt><dd><span class="status" :class="settings.deepseek_configured ? 'status-ready' : 'status-queued'"><span class="status-dot" />{{ settings.deepseek_configured ? 'Terkonfigurasi' : 'Belum dikonfigurasi' }}</span></dd></div><div><dt>Model</dt><dd>{{ settings.deepseek_model || 'Belum dipilih' }}</dd></div></dl><p v-if="!settings.deepseek_configured" class="section-note">Pengelola dapat mengisi konfigurasi DeepSeek pada environment backend. Upload, transkripsi lokal, dan klip manual tetap tersedia.</p><details class="service-details"><summary>Status layanan</summary><dl class="definition-list"><div><dt>Database</dt><dd>{{ settings.services?.database === 'ok' || settings.services?.database === true ? 'Terhubung' : settings.services?.database === false ? 'Tidak terhubung' : settings.services?.database || 'Belum diketahui' }}</dd></div><div><dt>Antrean pemrosesan</dt><dd>{{ settings.services?.broker === 'ok' || settings.services?.broker === true ? 'Terhubung' : settings.services?.broker === false ? 'Tidak terhubung' : settings.services?.broker || 'Belum diketahui' }}</dd></div></dl></details></section>
    <section v-if="usage" v-show="section === 'usage'" class="settings-section panel"><header><h2>Pemakaian Anda</h2><p class="muted">Data proyek milik akun ini. {{ usage.scope || 'Seluruh panggilan tercatat' }}.</p></header><dl class="definition-list"><div><dt>Token input</dt><dd>{{ Number(usage.input_tokens || 0).toLocaleString('id-ID') }}</dd></div><div><dt>Token output</dt><dd>{{ Number(usage.output_tokens || 0).toLocaleString('id-ID') }}</dd></div><div><dt>Penyimpanan aset</dt><dd>{{ fileSize(usage.storage_bytes) }}</dd></div></dl><p class="section-note">Biaya uang tidak ditampilkan karena tarif belum dikonfigurasi.</p><details v-if="usage.items?.length" class="service-details"><summary>Riwayat pemakaian API</summary><ScrollList :items="usage.items as any[]" label="riwayat pemakaian" v-slot="{ items }"><article v-for="item in items" :key="item.id" class="usage-row"><div><strong>{{ item.model }}</strong><small class="muted">{{ dateTime(item.created_at) }}</small></div><span>{{ item.input_tokens || 0 }} masuk / {{ item.output_tokens || 0 }} keluar</span><span class="muted">{{ item.outcome }}</span></article></ScrollList></details></section></DesktopFit></template>
    <AppDialog :open="!!disconnecting" title="Lepas koneksi akun?" :busy="socialBusy" @close="disconnecting = null"><p>Jadwal yang belum dikirim ke {{ disconnecting?.name }} akan dibatalkan. Posting yang sudah ada di platform tidak dihapus.</p><div class="dialog-actions"><button class="button secondary" @click="disconnecting = null">Kembali</button><button class="button primary" :disabled="socialBusy" @click="disconnect">Lepas koneksi</button></div></AppDialog>
  </div>
</template>
