<script setup lang="ts">
import { localInput, utcInput, monthCells, moveMonth, timezones, platformLabels, publicationLabels, publicationReadiness, singlePublicationAccount } from '~/utils/calendar'
const api = useApi()
const route = useRoute()
const timezone = ref('Asia/Makassar')
const today = () => localInput(new Date(), timezone.value).slice(0, 10)
const month = ref(today().slice(0, 7))
const selected = ref(today())
const posts = ref<any[]>([])
const accounts = ref<any[]>([])
const platforms = ref<any[]>([])
const connectionsLoading = ref(true)
const connectionError = ref('')
let connectionRequest = 0
const exports = ref<any[]>([])
const loading = ref(false)
const error = ref('')
const notice = ref('')
const open = ref(false)
const postStep = ref(0)
const busy = ref(false)
const formError = ref('')
const editing = ref<any>(null)
const creator = ref<any>(null)
const creatorLoading = ref(false)
const commercialDisclosure = ref(false)
let creatorRequest = 0
const cells = computed(() => monthCells(month.value))
const heading = computed(() => new Intl.DateTimeFormat('id-ID', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(month.value + '-01T00:00:00Z')))
const dayPosts = computed(() => posts.value.filter(p => localInput(p.scheduled_at, timezone.value).slice(0, 10) === selected.value))
const onDay = (day: string) => posts.value.filter(p => localInput(p.scheduled_at, timezone.value).slice(0, 10) === day)
const clock = (value: string) => localInput(value, timezone.value).slice(11)
const blank = () => ({ export_id: '', platform: 'youtube', account_id: '', title: '', caption: '', local_time: selected.value + 'T18:00',
  request_key: crypto.randomUUID(), consent: false, options: { privacy: '', audience: '', notify_subscribers: false, share_to_feed: false,
    allow_comment: false, allow_duet: false, allow_stitch: false, commercial_own: false, commercial_paid: false, aigc: false, music_consent: false } })
const form = ref<ReturnType<typeof blank> | null>(null)
const chosenExport = computed(() => exports.value.find(e => e.id === form.value?.export_id))
const availableAccounts = computed(() => accounts.value.filter(a => a.platform === form.value?.platform && a.connected !== false))
const readiness = computed(() => publicationReadiness(form.value?.platform || 'youtube', form.value?.account_id || '', accounts.value, platforms.value))
const ready = computed(() => !connectionsLoading.value && !connectionError.value && readiness.value.ready)
const privacyOptions = computed(() => form.value?.platform === 'tiktok' ? (creator.value?.privacy_level_options || []).map((value: string) => ({ value, label: ({ SELF_ONLY: 'Hanya saya', PUBLIC_TO_EVERYONE: 'Semua orang', MUTUAL_FOLLOW_FRIENDS: 'Teman', FOLLOWER_OF_CREATOR: 'Pengikut' } as Record<string, string>)[value] || value })) : [{ value: 'private', label: 'Privat' }, { value: 'unlisted', label: 'Tidak publik' }, { value: 'public', label: 'Publik' }])
const exportOptions = computed(() => exports.value.map(item => ({ value: item.id, label: `${item.title} / revisi ${item.revision}` })))
const platformOptions = Object.entries(platformLabels).map(([value, label]) => ({ value, label }))
const accountOptions = computed(() => [{ value: '', label: 'Belum dipilih (draft)' }, ...availableAccounts.value.map(account => ({ value: account.id, label: account.name }))])
const allowedPrivacyOptions = computed(() => privacyOptions.value.map((option: { value: string; label: string }) => ({ ...option, disabled: form.value?.platform === 'tiktok' && form.value.options.commercial_paid && option.value === 'SELF_ONLY' })))
async function refreshConnections() {
  const request = ++connectionRequest
  connectionsLoading.value = true
  try {
    const result = await api<any>('/social/accounts')
    if (request !== connectionRequest) return false
    accounts.value = result.items; platforms.value = result.platforms; connectionError.value = ''
    return true
  } catch {
    if (request === connectionRequest) connectionError.value = 'Status koneksi akun gagal dimuat. Coba periksa lagi.'
    return false
  } finally { if (request === connectionRequest) connectionsLoading.value = false }
}
async function load() {
  loading.value = true
  try {
    const result = await Promise.all([refreshConnections(), api<any>('/social/exports'), api<any>('/social/posts', { query: { start: utcInput(cells.value[0]! + 'T00:00', timezone.value), end: utcInput(new Date(Date.parse(cells.value[41]! + 'T00:00Z') + 86400000).toISOString().slice(0, 10) + 'T00:00', timezone.value) } })])
    exports.value = result[1].items
    posts.value = result[2].items.sort((a: any, b: any) => Date.parse(a.scheduled_at) - Date.parse(b.scheduled_at) || Date.parse(a.created_at) - Date.parse(b.created_at) || a.id.localeCompare(b.id))
    error.value = ''
  } catch (e) { error.value = errorMessage(e) } finally { loading.value = false }
}
onMounted(() => {
  void load().then(() => { if (typeof route.query.export === 'string' && exports.value.some(e => e.id === route.query.export)) { newPost(); form.value!.export_id = route.query.export; exportChanged() } })
})
watch([month, timezone], load)
watch(month, value => { if (!selected.value.startsWith(value)) selected.value = value + '-01' })
usePolling(load, () => !open.value && posts.value.some(p => ['scheduled', 'uploading', 'processing'].includes(p.status)))
function newPost() {
  postStep.value = 0; editing.value = null; form.value = blank(); formError.value = ''; creator.value = null; commercialDisclosure.value = false; open.value = true
  const draft = form.value
  void refreshConnections().then(ok => { if (ok && open.value && form.value === draft && !draft.account_id) draft.account_id = singlePublicationAccount(draft.platform, accounts.value) })
}
function editPost(post: any) {
  postStep.value = 0; editing.value = post; form.value = { ...blank(), ...post, account_id: post.account_id || '', local_time: localInput(post.scheduled_at, timezone.value), consent: false, options: { ...blank().options, ...post.options, audience: post.options.audience || '' } }
  commercialDisclosure.value = !!(post.options.commercial_own || post.options.commercial_paid)
  formError.value = ''; open.value = true
  void refreshConnections()
}
function platformChanged() {
  if (!form.value) return
  form.value.account_id = singlePublicationAccount(form.value.platform, accounts.value); form.value.options = blank().options; creator.value = null; form.value.consent = false; commercialDisclosure.value = false
}
watch(commercialDisclosure, value => { if (!value && form.value) { form.value.options.commercial_own = false; form.value.options.commercial_paid = false } })
watch(() => form.value?.account_id, async (id) => {
  const request = ++creatorRequest; creator.value = null; creatorLoading.value = false
  if (!id || form.value?.platform !== 'tiktok') return
  creatorLoading.value = true
  try { const result = await api<any>(`/social/accounts/${id}/creator-info`); if (request === creatorRequest) creator.value = result }
  catch (e) { if (request === creatorRequest) formError.value = errorMessage(e) }
  finally { if (request === creatorRequest) creatorLoading.value = false }
})
function exportChanged() { if (form.value && chosenExport.value && !form.value.title) form.value.title = chosenExport.value.title.slice(0, 100) }
async function save(status: 'draft' | 'scheduled') {
  if (!form.value) return
  if (!form.value.export_id) { formError.value = 'Pilih video hasil ekspor terlebih dahulu.'; postStep.value = 0; return }
  busy.value = true; formError.value = ''
  try {
    const f = form.value
    const body = { export_id: f.export_id, platform: f.platform, account_id: f.account_id || null, title: f.title, caption: f.caption,
      scheduled_at: utcInput(f.local_time, timezone.value), timezone: timezone.value, status, options: { ...f.options, audience: f.options.audience || null }, consent: f.consent, request_key: f.request_key, expected_version: editing.value?.version || null }
    await api(editing.value ? `/social/posts/${editing.value.id}` : '/social/posts', { method: editing.value ? 'PATCH' : 'POST', body })
    selected.value = f.local_time.slice(0, 10); month.value = selected.value.slice(0, 7)
    open.value = false; notice.value = status === 'draft' ? 'Draft kalender tersimpan.' : 'Publikasi terjadwal. Komputer dan Docker harus tetap berjalan.'; await load()
  } catch (e) { formError.value = errorMessage(e) } finally { busy.value = false }
}
async function action(post: any, name: string) {
  try { await api(`/social/posts/${post.id}/${name}`, { method: 'POST' }); await load() } catch (e) { error.value = errorMessage(e) }
}
</script>
<template>
  <div class="page calendar-page">
    <header class="page-header"><div><p class="eyebrow">Publikasi konten</p><h1>Kalender</h1><p class="muted">Rencanakan YouTube, Instagram Reels, dan TikTok dari hasil ekspor klip.</p></div><button class="button primary" @click="newPost"><AppIcon name="Plus" />Tambah jadwal</button></header>
    <InlineError :message="error" /><p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <div class="calendar-body"><section class="panel calendar-panel"><header class="calendar-toolbar"><div class="row gap-3"><button class="icon-button" aria-label="Bulan sebelumnya" @click="month = moveMonth(month, -1)"><AppIcon name="ChevronLeft" /></button><h2>{{ heading }}</h2><button class="icon-button" aria-label="Bulan berikutnya" @click="month = moveMonth(month, 1)"><AppIcon name="ChevronRight" /></button><button class="text-button" @click="month = today().slice(0, 7); selected = today()">Hari ini</button></div><label><span class="sr-only">Zona waktu kalender</span><AppSelect v-model="timezone" label="Zona waktu kalender" :options="timezones" /></label></header>
      <div class="calendar-week"><span v-for="day in ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']" :key="day">{{ day }}</span></div>
      <div class="calendar-grid"><button v-for="day in cells" :key="day" class="calendar-cell" :class="{ outside: !day.startsWith(month), selected: day === selected, today: day === today() }" :aria-label="`${day}, ${onDay(day).length} publikasi`" :aria-pressed="day === selected" @click="selected = day"><span class="day-number">{{ Number(day.slice(-2)) }}</span><span v-for="post in onDay(day).slice(0, 2)" :key="post.id" class="calendar-event" :class="post.platform"><span>{{ clock(post.scheduled_at) }}</span> {{ post.title }}</span><small v-if="onDay(day).length > 2">+{{ onDay(day).length - 2 }} lainnya</small></button></div>
    </section>
    <section class="calendar-agenda"><header><h2>{{ new Intl.DateTimeFormat('id-ID', { dateStyle: 'full', timeZone: 'UTC' }).format(new Date(selected + 'T00:00:00Z')) }}</h2><span class="muted small">{{ dayPosts.length }} publikasi · {{ timezones.find(z => z.value === timezone)?.label }}</span></header><p v-if="loading && !posts.length" role="status">Memuat kalender…</p><div v-else-if="!dayPosts.length" class="panel empty-state compact"><AppIcon name="CalendarDays" :size="28" /><h3>Belum ada rencana pada tanggal ini</h3><p>Pilih Tambah jadwal untuk menyiapkan publikasi.</p></div>
      <ScrollList :key="selected" :items="dayPosts" label="agenda" v-slot="{ items }"><article v-for="post in items" :key="post.id" class="panel agenda-post"><div class="agenda-time">{{ clock(post.scheduled_at) }}</div><div class="agenda-main"><span class="muted small">{{ platformLabels[post.platform] }} · {{ post.account_name || 'Akun belum dipilih' }}</span><h3>{{ post.title }}</h3><p>{{ post.caption }}</p><span class="status" :class="`status-${post.status === 'published' ? 'ready' : post.status}`">{{ publicationLabels[post.status] }}</span><span v-if="post.platform === 'youtube' && post.options.privacy" class="muted small"> · {{ post.options.privacy }}</span><p v-if="post.error_message" class="error-text">{{ post.error_message }}</p></div><div class="agenda-actions"><button v-if="['draft', 'scheduled'].includes(post.status)" class="button secondary small-button" @click="editPost(post)">Edit jadwal</button><button v-if="['draft', 'scheduled', 'failed'].includes(post.status)" class="text-button" @click="action(post, 'cancel')">Batalkan</button><button v-if="post.status === 'uncertain'" class="button secondary small-button" @click="action(post, 'check')">Periksa status</button><button v-if="['failed', 'cancelled'].includes(post.status)" class="text-button" @click="action(post, 'draft')">Kembalikan ke draft</button><a v-if="post.remote_url" :href="post.remote_url" target="_blank" rel="noopener noreferrer" class="button secondary small-button">Lihat hasil ↗</a><a v-if="post.preview_url" :href="post.preview_url + '?download=true'" class="text-button">Unduh MP4</a></div></article></ScrollList>
    </section></div>
    <p class="muted small calendar-footnote">Waktu jadwal adalah waktu mulai pengiriman. Proses upload, moderasi, dan pemrosesan platform dapat membuat video tampil lebih lambat. Komputer dan Docker perlu tetap menyala; jadwal yang terlewat saat mati akan diproses setelah layanan kembali aktif.</p>
    <AppDialog :open="open" :title="editing ? 'Edit jadwal publikasi' : 'Jadwal publikasi baru'" :busy="busy" wide @close="open = false"><form v-if="form" class="social-post-form form-stack" @submit.prevent="save('scheduled')"><InlineError :message="formError" /><p v-if="!exports.length" class="notice">Belum ada hasil ekspor. Ekspor klip menjadi MP4 terlebih dahulu.</p><div class="tool-tabs" role="group" aria-label="Bagian jadwal"><button type="button" :aria-pressed="postStep === 0" @click="postStep = 0">Video & jadwal</button><button type="button" :aria-pressed="postStep === 1" @click="postStep = 1">Opsi publikasi</button></div><div v-show="postStep === 0" class="social-step"><div class="form-grid"><label>Video hasil ekspor<AppSelect v-model="form.export_id" label="Video hasil ekspor" placeholder="Pilih hasil ekspor" required :options="exportOptions" @update:model-value="exportChanged" /></label><label>Platform<AppSelect v-model="form.platform" label="Platform publikasi" :options="platformOptions" @update:model-value="platformChanged" /></label><label>Akun tujuan<AppSelect v-model="form.account_id" label="Akun tujuan" :options="accountOptions" :disabled="connectionsLoading" /></label><label>Tanggal dan jam · {{ timezones.find(z => z.value === timezone)?.label }}<input v-model="form.local_time" type="datetime-local" required aria-label="Tanggal dan jam publikasi" /></label></div>
      <video v-if="chosenExport" class="social-video-preview" :src="chosenExport.preview_url" controls preload="metadata" playsinline />
      <label>Judul<input v-model="form.title" required maxlength="100" aria-label="Judul publikasi" /></label><label>Caption / deskripsi<textarea v-model="form.caption" rows="3" :maxlength="form.platform === 'youtube' ? 5000 : 2200" aria-label="Caption publikasi" /></label>
      </div><div v-show="postStep === 1" class="social-step"><div v-if="form.platform !== 'instagram'" class="form-grid"><label>Visibilitas<AppSelect v-model="form.options.privacy" label="Visibilitas publikasi" placeholder="Pilih visibilitas" :options="allowedPrivacyOptions" /></label><label v-if="form.platform === 'youtube'">Audiens<AppSelect v-model="form.options.audience" label="Audiens YouTube" placeholder="Pilih audiens" :options="[{ value: 'general', label: 'Bukan khusus anak-anak' }, { value: 'kids', label: 'Dibuat untuk anak-anak' }]" /></label></div>
      <label v-if="form.platform === 'youtube'" class="checkbox-label"><input v-model="form.options.notify_subscribers" type="checkbox" />Beri tahu subscriber</label><label v-if="form.platform === 'instagram'" class="checkbox-label"><input v-model="form.options.share_to_feed" type="checkbox" />Tampilkan Reel juga di feed</label>
      <template v-if="form.platform === 'tiktok'"><p v-if="creatorLoading" role="status">Memeriksa izin kreator TikTok…</p><p v-if="creator" class="muted small">Tujuan: {{ creator.creator_nickname }} · maksimal {{ creator.max_video_post_duration_sec }} detik</p><div class="social-checks"><label class="checkbox-label"><input v-model="form.options.allow_comment" type="checkbox" :disabled="!creator || creator.comment_disabled" />Izinkan komentar</label><label class="checkbox-label"><input v-model="form.options.allow_duet" type="checkbox" :disabled="!creator || creator.duet_disabled" />Izinkan Duet</label><label class="checkbox-label"><input v-model="form.options.allow_stitch" type="checkbox" :disabled="!creator || creator.stitch_disabled" />Izinkan Stitch</label></div><label class="checkbox-label"><input v-model="commercialDisclosure" type="checkbox" />Konten mempromosikan merek, produk, atau layanan</label><template v-if="commercialDisclosure"><label class="checkbox-label"><input v-model="form.options.commercial_own" type="checkbox" />Promosi merek/usaha sendiri (Promotional content)</label><label class="checkbox-label"><input v-model="form.options.commercial_paid" type="checkbox" :disabled="form.options.privacy === 'SELF_ONLY'" />Kemitraan merek pihak ketiga (Paid partnership)</label><p v-if="form.options.privacy === 'SELF_ONLY'" class="muted small">Kemitraan berbayar tidak dapat menggunakan visibilitas Hanya saya.</p><p v-if="form.options.commercial_paid || form.options.commercial_own" class="notice">Video akan diberi label {{ form.options.commercial_paid ? 'Paid partnership' : 'Promotional content' }}.</p><p v-else class="muted small">Pilih merek sendiri, pihak ketiga, atau keduanya untuk menjadwalkan.</p></template><label class="checkbox-label"><input v-model="form.options.music_consent" type="checkbox" />Saya menyetujui <a href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en" target="_blank" rel="noopener noreferrer">Music Usage Confirmation TikTok</a>.</label></template>
      <label v-if="form.platform !== 'instagram'" class="checkbox-label"><input v-model="form.options.aigc" type="checkbox" />Video memuat konten sintetis / dibuat AI yang perlu dilabeli</label>
      </div><p v-if="connectionsLoading" class="notice" role="status">Memeriksa koneksi akun...</p><p v-else-if="connectionError" class="notice" role="alert">{{ connectionError }} <button type="button" class="text-button" @click="refreshConnections">Periksa lagi</button></p><p v-else-if="!readiness.ready" class="notice">{{ readiness.message }} <NuxtLink v-if="readiness.manageConnection" to="/settings?section=accounts">Kelola koneksi akun di Pengaturan.</NuxtLink><button v-else type="button" class="text-button" @click="postStep = 0">Pilih akun tujuan</button></p><label class="checkbox-label"><input v-model="form.consent" type="checkbox" />Saya menyetujui pengiriman video dan metadata ini ke akun tujuan pada waktu yang dipilih.</label><div class="dialog-actions"><button type="button" class="button secondary" :disabled="busy || !form.export_id || !form.title || !form.local_time" @click="save('draft')">Simpan draft</button><button class="button primary" type="submit" :disabled="busy || !ready || !form.export_id || !form.title.trim() || !form.local_time || !form.consent || creatorLoading || (form.platform === 'tiktok' && (!creator || !form.options.music_consent || !form.options.privacy || (commercialDisclosure && !form.options.commercial_own && !form.options.commercial_paid)))">Jadwalkan publikasi</button></div></form></AppDialog>
  </div>
</template>
