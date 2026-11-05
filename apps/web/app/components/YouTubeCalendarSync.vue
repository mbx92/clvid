<script setup lang="ts">
const emit = defineEmits<{ changed: []; jump: [date: string] }>()
const api = useApi()
const items = ref<any[]>([])
const error = ref('')
const busy = ref(false)
const notice = ref('')
const expanded = ref(false)
let previous = ''
const total = computed(() => items.value.reduce((sum, item) => sum + item.video_count, 0))
const pending = computed(() => items.value.some(item => item.pending && !item.error_message))
const latest = computed(() => items.value.map(item => item.latest_published_at).filter(Boolean).sort().at(-1))
async function refresh() {
  try {
    const result = await api<any>('/social/youtube/sync')
    const key = JSON.stringify(result.items.map((item: any) => [item.video_count, item.last_synced_at, item.pending]))
    items.value = result.items; error.value = ''
    if (previous !== key) emit('changed')
    previous = key
  } catch (e) { error.value = errorMessage(e) }
}
onMounted(refresh)
usePolling(refresh, () => !busy.value)
async function synchronize() {
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await api('/social/youtube/sync', { method: 'POST' })
    notice.value = 'Sinkronisasi masuk antrean. Riwayat akan muncul bertahap di kalender.'
    await refresh()
  } catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
</script>

<template>
  <section v-if="items.length || error" class="youtube-sync" aria-label="Riwayat YouTube">
    <div class="youtube-sync-row">
      <div class="youtube-sync-summary"><AppIcon name="Film" :size="15" /><strong>Riwayat YouTube</strong><span>{{ total }} video sudah tayang</span><span v-if="pending" class="sync-progress" role="status"><AppIcon name="RefreshCw" :size="12" />Menyinkronkan...</span></div>
      <div class="youtube-sync-actions"><button v-if="latest" class="text-button" @click="emit('jump', latest)">Lihat tayangan terbaru</button><button class="text-button sync-detail-toggle" :aria-expanded="expanded" @click="expanded = !expanded">Detail<AppIcon name="ChevronDown" :size="12" /></button><button class="button secondary small-button" :disabled="busy || pending" @click="synchronize"><AppIcon name="RefreshCw" :size="13" />Sinkronkan YouTube</button></div>
    </div>
    <InlineError :message="error" />
    <p v-if="notice" class="sync-notice" role="status">{{ notice }}</p>
    <div v-if="expanded || items.some(item => item.error_message)" class="youtube-sync-details">
      <p class="muted small">Mengambil video publik dari akun terhubung setiap 6 jam. Riwayat mengikuti tanggal tayang YouTube dan tidak memerlukan persetujuan upload.</p>
      <div v-for="item in items" :key="item.account_id" class="sync-account"><div><strong>{{ item.name }}</strong><span>{{ item.video_count }} video</span></div><p>{{ item.last_synced_at ? `Sinkronisasi terakhir ${new Date(item.last_synced_at).toLocaleString('id-ID', { timeZone: 'Asia/Makassar' })} WITA` : 'Belum selesai disinkronkan' }}</p><p v-if="item.error_message" class="error-text" role="alert">{{ item.error_message }} <NuxtLink to="/settings?section=accounts">Pengaturan akun</NuxtLink></p></div>
    </div>
  </section>
</template>

<style scoped>
.youtube-sync { flex: none; padding: 0 1px 14px; }
.youtube-sync-row { display: flex; gap: 8px 16px; justify-content: space-between; align-items: center; flex-wrap: wrap; font-size: 10px; }
.youtube-sync-summary { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; color: var(--color-text-muted); }
.youtube-sync-summary > svg { opacity: .8; }
.youtube-sync-summary strong { font-size: 11px; font-weight: 500; color: var(--color-text); }
.youtube-sync-summary > span:not(.sync-progress) { padding-left: 9px; border-left: 1px solid var(--color-border); }
.youtube-sync-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.youtube-sync-actions > .text-button { font-size: 10px; color: var(--color-text-muted); }
.youtube-sync-actions > .text-button:hover { color: var(--color-accent); }
.youtube-sync-actions > .button { font-size: 10px; min-height: 30px; padding: 5px 8px; gap: 6px; }
.sync-detail-toggle[aria-expanded='true'] > svg { transform: rotate(180deg); }
.sync-progress { display: inline-flex; gap: 5px; align-items: center; color: var(--color-accent); }
.sync-progress svg { animation: sync-turn 1.8s linear infinite; }
.sync-notice { font-size: 10px; color: var(--color-text-muted); margin-top: 7px; }
.youtube-sync-details { max-height: 160px; overflow: auto; margin-top: 12px; padding: 13px 15px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); }
.youtube-sync-details > p { font-size: 11px; line-height: 1.7; margin-bottom: 12px; }
.sync-account { font-size: 10px; padding: 10px 0; border-top: 1px solid var(--color-border); }
.sync-account > div { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }
.sync-account strong { font-weight: 500; font-size: 11px; }
.sync-account span, .sync-account > p:not(.error-text) { color: var(--color-text-muted); }
.sync-account > p { margin-top: 4px; }
.sync-account a { text-decoration: underline; text-underline-offset: 3px; }
@keyframes sync-turn { to { transform: rotate(360deg); } }
@media(prefers-reduced-motion: reduce) { .sync-progress svg { animation: none; } }
@media(max-width: 650px) {
 .youtube-sync { padding-bottom: 15px; }
 .youtube-sync-row { gap: 10px; }
 .youtube-sync-summary strong { font-size: 11px; }
 .youtube-sync-actions { gap: 13px; }
 .youtube-sync-actions > .button { min-height: 34px; font-size: 11px; }
 .youtube-sync-actions > .text-button { font-size: 11px; }
}
</style>
