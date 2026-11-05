<script setup lang="ts">
import { platformLabels, timezones, publicationReadiness } from '~/utils/calendar'
const props = defineProps<{ accounts: any[]; platforms: any[] }>()
const emit = defineEmits<{ edit: [post: any]; changed: [] }>()
const api = useApi()
const opened = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const items = ref<any[]>([])
const hasMore = ref(false)
const offset = ref(0)
const settings = ref({ enabled: true, timezone: 'Asia/Makassar', times: ['18:00'], account_ids: [] as string[] })
const timesText = ref('18:00')
const dateLabel = (post: any) => new Intl.DateTimeFormat('id-ID', { dateStyle: 'full', timeStyle: 'short', timeZone: post.timezone }).format(new Date(post.scheduled_at))
function blocked(post: any) {
  if (Date.parse(post.scheduled_at) <= Date.now() + 10000) return 'Jadwal sudah lewat. Edit waktu sebelum menyetujui.'
  const readiness = publicationReadiness(post.platform, post.account_id, props.accounts, props.platforms)
  if (!readiness.ready) return readiness.message
  if (post.platform === 'tiktok' && (!post.options.privacy || !post.options.music_consent)) return 'Edit untuk memilih privasi dan konfirmasi musik TikTok.'
  return ''
}
async function refresh() {
  try {
    const result = await api<any>('/social/approvals', { query: { offset: offset.value } })
    items.value = result.items; hasMore.value = result.has_more
  } catch (e) { error.value = errorMessage(e) }
}
defineExpose({ refresh })
async function initialize() {
  loading.value = true
  try {
    settings.value = await api<any>('/social/automation'); timesText.value = settings.value.times.join(', ')
    await api('/social/automation/scan', { method: 'POST' }); await refresh()
  } catch (e) { error.value = errorMessage(e) } finally { loading.value = false }
}
onMounted(initialize)
usePolling(refresh, () => !busy.value)
async function saveSettings() {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    settings.value = await api<any>('/social/automation', { method: 'PUT', body: { ...settings.value, times: timesText.value.split(',').map(t => t.trim()).filter(Boolean) } })
    await api('/social/automation/scan', { method: 'POST' }); offset.value = 0; await refresh(); emit('changed')
    notice.value = 'Pengaturan disimpan. Usulan yang sudah ada tetap memakai jadwalnya; Anda dapat mengeditnya.'
  } catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
async function decide(post: any, approve: boolean) {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await api(`/social/posts/${post.id}/${approve ? 'approve' : 'cancel'}`, { method: 'POST', ...(approve ? { body: { expected_version: post.version, consent: true } } : {}) })
    notice.value = approve ? 'Disetujui. Video akan dikirim otomatis pada jadwal tersebut.' : 'Usulan ditolak. Klip ini tidak akan diusulkan ulang untuk akun yang sama.'
    await refresh(); emit('changed')
  } catch (e) { error.value = errorMessage(e); await refresh() } finally { busy.value = false }
}
async function edit(post: any) { opened.value = false; await nextTick(); emit('edit', post) }
async function page(delta: number) { offset.value = Math.max(0, offset.value + delta * 50); await refresh() }
</script>

<template>
  <section class="automation-banner" aria-label="Publikasi otomatis">
    <div class="automation-count" aria-hidden="true">{{ loading ? '--' : String(items.length).padStart(2, '0') }}<small v-if="hasMore">+</small></div>
    <div class="automation-summary"><div class="automation-title"><strong>Menunggu persetujuan</strong><span class="automation-mode" :class="{ paused: !settings.enabled }"><i />{{ settings.enabled ? 'Otomatis aktif' : 'Otomatis dijeda' }}</span></div><p class="muted small">{{ loading ? 'Memeriksa video siap tayang...' : `${items.length}${hasMore ? '+' : ''} usulan pada halaman ini menunggu persetujuan` }}</p></div>
    <button class="button primary small-button" @click="opened = true">Tinjau &amp; approve<AppIcon name="ArrowRight" :size="15" /></button>
    <p v-if="error && !opened" class="error-text automation-banner-error" role="alert">{{ error }}</p>
    <AppDialog :open="opened" title="Persetujuan publikasi otomatis" :busy="busy" wide @close="opened = false">
      <div class="form-stack automation-review">
        <p class="review-intro">Video hasil ekspor dan jadwal tujuan disiapkan otomatis. Periksa kontennya, lalu setujui untuk memulai pengiriman sesuai jadwal.</p>
        <InlineError :message="error" /><p v-if="notice" class="notice" role="status">{{ notice }}</p>
        <details class="automation-settings"><summary><AppIcon name="Settings2" :size="16" /><span>Pengaturan jadwal otomatis</span><AppIcon name="ChevronDown" :size="15" /></summary>
          <form class="form-stack" @submit.prevent="saveSettings">
            <label class="checkbox-label"><input v-model="settings.enabled" type="checkbox" />Buat usulan otomatis dari ekspor selesai</label>
            <div class="form-grid"><label>Zona waktu<AppSelect v-model="settings.timezone" label="Zona waktu otomatis" :options="timezones" /></label><label>Jam tayang setiap hari<input v-model="timesText" placeholder="12:00, 18:00" required aria-label="Jam tayang otomatis" /><small class="muted">Pisahkan dengan koma, maksimal 6 slot.</small></label></div>
            <fieldset><legend>Akun tujuan usulan</legend><p class="muted small">Kosong berarti semua akun terhubung. Setiap akun mendapat jadwal sendiri.</p><label v-for="account in accounts" :key="account.id" class="checkbox-label"><input v-model="settings.account_ids" :value="account.id" type="checkbox" />{{ account.name }} &middot; {{ platformLabels[account.platform] }}</label></fieldset>
            <p class="muted small">Menjeda hanya menghentikan usulan baru. Jadwal yang sudah disetujui tetap berjalan.</p>
            <button class="button secondary" :disabled="busy">Simpan pengaturan</button>
          </form>
        </details>
        <p v-if="!accounts.length" class="notice">Hubungkan akun tujuan satu kali di <NuxtLink to="/settings?section=accounts">Pengaturan akun</NuxtLink>. Setelah itu hasil ekspor akan masuk antrean otomatis.</p>
        <div v-else-if="!items.length" class="review-empty"><AppIcon name="Check" :size="24" /><h3>Antrean tinjauan kosong</h3><p>Hasil ekspor MP4 baru akan muncul di sini. Sistem memeriksa video setiap menit.</p></div>
        <article v-for="post in items" :key="post.id" class="automation-card" :class="{ 'without-preview': !post.preview_url }">
          <div v-if="post.preview_url" class="review-monitor"><span class="review-monitor-label">Preview ekspor</span><video :src="post.preview_url" controls preload="none" playsinline class="social-video-preview" :aria-label="`Preview ${post.title}`" /></div>
          <div class="review-content">
            <div class="review-destination"><span>{{ platformLabels[post.platform] }}</span><strong>{{ post.account_name || 'Akun belum dipilih' }}</strong></div>
            <h3>{{ post.title }}</h3>
            <div v-if="post.caption" class="review-caption"><span class="review-field-label">Caption / deskripsi</span><p>{{ post.caption }}</p></div>
            <div class="review-schedule"><AppIcon name="Clock3" :size="16" /><div><span class="review-field-label">Jadwal pengiriman</span><strong>{{ dateLabel(post) }}</strong><small>{{ post.timezone }}</small></div></div>
            <p v-if="post.platform === 'youtube'" class="review-options">Visibilitas: {{ post.options.privacy === 'public' ? 'Publik' : post.options.privacy }} &middot; {{ post.options.audience === 'kids' ? 'Dibuat untuk anak-anak' : 'Bukan khusus anak-anak' }} &middot; Label AI: {{ post.options.aigc ? 'Ya' : 'Tidak' }}</p>
            <p v-if="blocked(post)" class="notice">{{ blocked(post) }}</p>
            <div class="review-actions"><button class="button primary" :disabled="busy || !!blocked(post)" @click="decide(post, true)">Setujui &amp; jadwalkan</button><button class="button secondary" :disabled="busy" @click="edit(post)">Edit</button><button class="text-button review-reject" :disabled="busy" @click="decide(post, false)">Tolak</button></div>
          </div>
        </article>
        <div v-if="offset || hasMore" class="review-pagination"><button class="button secondary small-button" :disabled="busy || !offset" @click="page(-1)">Sebelumnya</button><span>Halaman {{ offset / 50 + 1 }}</span><button class="button secondary small-button" :disabled="busy || !hasMore" @click="page(1)">Berikutnya</button></div>
      </div>
    </AppDialog>
  </section>
</template>

<style scoped>
.automation-banner { flex: none; display: flex; align-items: center; gap: 16px; padding: 13px 16px; margin-bottom: 12px; border: 1px solid var(--color-border); border-left: 2px solid var(--color-accent); border-radius: 4px; background: var(--color-surface); }
.automation-count { display: flex; align-items: baseline; min-width: 34px; color: var(--color-accent); font: 23px ui-monospace, SFMono-Regular, Consolas, monospace; font-variant-numeric: tabular-nums; letter-spacing: -1px; }
.automation-count small { font-size: 12px; }
.automation-summary { flex: 1; min-width: 0; }
.automation-title { display: flex; align-items: center; flex-wrap: wrap; gap: 5px 14px; }
.automation-title strong { font-size: 12px; font-weight: 600; }
.automation-mode { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; color: var(--color-text-muted); }
.automation-mode i { width: 5px; height: 5px; background: #82c69b; border-radius: 50%; }
.automation-mode.paused i { background: #858b95; }
.automation-summary p { margin-top: 3px; font-size: 11px; }
.automation-banner-error { flex-basis: 100%; }
.automation-review { max-height: calc(100dvh - 160px); overflow-y: auto; padding: 3px; gap: 18px; }
.review-intro { color: var(--color-text-muted); font-size: 12px; line-height: 1.7; max-width: 70ch; }
.automation-settings { border-block: 1px solid var(--color-border); }
.automation-settings summary { cursor: pointer; display: flex; align-items: center; gap: 9px; padding: 13px 2px; list-style: none; font-size: 12px; font-weight: 500; color: var(--color-text-muted); }
.automation-settings summary::-webkit-details-marker { display: none; }
.automation-settings summary span { flex: 1; }
.automation-settings[open] summary { color: var(--color-text); }
.automation-settings[open] summary > svg:last-child { transform: rotate(180deg); }
.automation-settings form { padding: 4px 0 18px; }
.automation-settings fieldset { margin: 0; padding: 12px; border: 1px solid var(--color-border); border-radius: 4px; }
.automation-settings legend { padding: 0 6px; font-size: 11px; }
.automation-settings fieldset p { margin-bottom: 9px; }
.automation-settings .checkbox-label { font-size: 12px; }
.automation-settings fieldset .checkbox-label + .checkbox-label { margin-top: 9px; }
.automation-settings form > .button { justify-self: start; }
.automation-card { border: 1px solid var(--color-border); border-radius: 5px; overflow: hidden; display: grid; grid-template-columns: minmax(180px, .78fr) minmax(0, 1fr); background: var(--color-surface); }
.review-monitor { display: flex; flex-direction: column; background: #0b0d0f; align-self: stretch; min-width: 0; }
.review-monitor-label { color: #9ca3ad; font-size: 9px; letter-spacing: .1em; text-transform: uppercase; padding: 12px; border-bottom: 1px solid #24282d; }
.automation-card video { height: 100%; width: 100%; max-height: 390px; flex: 1; border-radius: 0; object-fit: contain; }
.automation-card.without-preview { grid-template-columns: 1fr; }
.review-content { min-width: 0; padding: 18px; display: grid; gap: 13px; align-content: start; }
.review-destination { display: flex; flex-direction: column; gap: 3px; font-size: 10px; color: var(--color-text-muted); }
.review-destination strong { color: var(--color-text); font-size: 12px; font-weight: 500; }
.review-content h3 { font-size: 17px; line-height: 1.45; letter-spacing: -.2px; }
.review-field-label { display: block; color: var(--color-text-muted); font-size: 10px; margin-bottom: 4px; }
.review-caption p { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.6; font-size: 12px; max-height: 160px; overflow-y: auto; }
.review-schedule { display: flex; align-items: flex-start; gap: 9px; border-top: 1px solid var(--color-border); padding-top: 12px; }
.review-schedule > svg { color: var(--color-accent); margin-top: 2px; }
.review-schedule strong { display: block; font-size: 12px; line-height: 1.6; font-weight: 500; }
.review-schedule small { color: var(--color-text-muted); font-size: 10px; }
.review-options { color: var(--color-text-muted); font-size: 10px; line-height: 1.8; }
.review-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; padding-top: 2px; }
.review-actions .button { font-size: 11px; min-height: 34px; padding: 7px 10px; }
.review-reject { margin-left: auto; color: var(--color-text-muted); font-size: 11px; }
.review-reject:hover { color: var(--color-danger); }
.review-pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 11px; color: var(--color-text-muted); }
.review-empty { padding: 28px 8px 40px; display: flex; flex-direction: column; gap: 12px; align-items: center; text-align: center; }
.review-empty > svg { color: #82c69b; }
.review-empty h3 { font-size: 15px; }
.review-empty p { color: var(--color-text-muted); font-size: 12px; max-width: 42ch; }
@media(max-width: 650px) {
 .automation-banner { padding: 12px; gap: 12px; flex-wrap: wrap; }
 .automation-count { min-width: 30px; font-size: 22px; }
 .automation-summary { min-width: calc(100% - 50px); }
 .automation-banner > .button { margin-left: 42px; }
 .automation-title { align-items: flex-start; flex-direction: column; gap: 4px; }
 .automation-review { max-height: calc(100dvh - 140px); }
 .automation-card { grid-template-columns: 1fr; }
 .automation-card video { max-height: 300px; min-height: 180px; }
 .review-content { padding: 16px; }
 .review-content h3 { font-size: 16px; }
 .review-actions .button { font-size: 12px; min-height: 38px; }
 .review-reject { font-size: 12px; }
}
</style>
