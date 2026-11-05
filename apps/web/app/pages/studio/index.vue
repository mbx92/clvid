<script setup lang="ts">
import { newStory } from '~/utils/story'
const api = useApi()
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const busy = ref(false)
const loading = ref(true)
const error = ref('')
async function load(more = false) {
  try {const r = await api<{items: any[]; total: number}>('/studio', {query: {page: page.value}}); items.value = more ? [...items.value, ...r.items] : r.items; total.value = r.total} catch(e) {error.value = errorMessage(e)} finally {loading.value = false}
}
async function create() {
  busy.value = true
  try {const r = await api<{id: string}>('/studio', {method: 'POST', body: newStory()}); await navigateTo(`/studio/${r.id}`)} catch(e) {error.value = errorMessage(e)} finally {busy.value = false}
}
onMounted(() => load())
</script>
<template>
  <div class="page studio-library"><header class="page-header"><div><p class="eyebrow">PRODUKSI VIDEO</p><h1>Story Studio</h1><p class="muted">Naskah, adegan, suara, dan hasil produksi dalam satu ruang kerja.</p></div><div class="row gap-3 wrap"><NuxtLink to="/studio/research" class="button secondary"><AppIcon name="Search"/>Riset &amp; klip otomatis</NuxtLink><button class="button primary" :disabled="busy" @click="create"><AppIcon name="Plus"/>Buat video</button></div></header>
    <InlineError :message="error"/>
    <div class="studio-library-bar"><span class="studio-view-name"><AppIcon name="Film" :size="15"/>Storyboard</span><span class="muted">{{ loading ? 'Memuat…' : `${total} video` }}</span></div>
    <div v-if="loading" class="studio-loading" role="status">Memuat storyboard…</div>
    <div v-else-if="!items.length" class="studio-welcome"><span class="studio-empty-frame"><AppIcon name="Film" :size="32"/></span><div><p class="eyebrow">BELUM ADA STORYBOARD</p><h2>Siapkan video pertama.</h2><p>Mulai dari naskah atau susun adegan secara manual. Tambahkan visual dan suara, lalu tinjau hasil sebelum ekspor.</p></div><button class="button primary" :disabled="busy" @click="create">Mulai storyboard pertama</button><ol class="studio-flow" aria-label="Alur produksi"><li><span>01</span>Naskah</li><li><span>02</span>Adegan &amp; suara</li><li><span>03</span>Ekspor MP4</li></ol></div>
    <div v-else class="story-cards"><NuxtLink v-for="item in items" :key="item.id" :to="`/studio/${item.id}`" class="story-card"><div class="story-cover" :style="{background: item.theme.background, color: item.theme.foreground}"><span :style="{color: item.theme.accent}">STORY / {{ String(item.scene_count).padStart(2, '0') }}</span><strong>{{ item.title }}</strong><i :style="{background: item.theme.accent}"/></div><div class="story-card-label"><strong>{{ item.title }}</strong><div class="story-card-meta"><span>{{ item.scene_count }} adegan</span><span class="story-version">V{{ String(item.version).padStart(2, '0') }}</span><AppIcon name="ArrowRight" :size="15"/></div></div></NuxtLink></div>
    <button v-if="items.length < total" class="button secondary" @click="page++; load(true)">Muat lainnya</button>
  </div>
</template>
<style scoped>
.studio-library { overflow-y: auto; }
.studio-library .page-header { align-items: center; }
.studio-library .page-header p { margin-top: 8px; }
.studio-library-bar { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; margin-bottom: 18px; border-block: 1px solid var(--color-border); font-size: 12px; flex: none; }
.studio-view-name { display: flex; align-items: center; gap: 9px; font-weight: 600; }
.studio-view-name svg { color: var(--color-accent); }
.studio-loading { padding: 40px 0; color: var(--color-text-muted); }
.studio-welcome { margin: auto; padding: 42px 20px; width: 100%; max-width: 560px; text-align: center; display: grid; justify-items: center; gap: 22px; }
.studio-empty-frame { width: 88px; aspect-ratio: 16 / 10; display: grid; place-items: center; border: 1px solid var(--color-border); border-radius: 4px; color: var(--color-accent); background: var(--color-surface); }
.studio-welcome h2 { margin-bottom: 10px; font-size: 24px; letter-spacing: -.5px; }
.studio-welcome p { line-height: 1.75; color: var(--color-text-muted); font-size: 13px; }
.studio-welcome .eyebrow { font-size: 10px; letter-spacing: 1.6px; margin-bottom: 8px; }
.studio-flow { list-style: none; margin: 4px 0 0; padding: 18px 0 0; display: flex; gap: 24px; border-top: 1px solid var(--color-border); font-size: 11px; color: var(--color-text-muted); }
.studio-flow li { display: grid; gap: 5px; }
.studio-flow span { font: 10px ui-monospace, monospace; color: var(--color-accent); }
.story-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 18px; padding-bottom: 20px; }
.story-card { border: 1px solid var(--color-border); border-radius: 6px; overflow: hidden; color: inherit; text-decoration: none; background: var(--color-surface); transition: border-color 140ms ease; }
.story-card:hover { border-color: var(--color-accent); }
.story-cover { aspect-ratio: 16 / 10; min-height: 160px; padding: 24px; display: flex; flex-direction: column; justify-content: space-between; }
.story-cover span { font: 10px ui-monospace, monospace; letter-spacing: 1.6px; }
.story-cover strong { font-size: 24px; line-height: 1.25; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; }
.story-cover i { width: 36px; height: 3px; }
.story-card-label { display: grid; gap: 12px; padding: 16px; }
.story-card-label > strong { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.story-card-meta { display: flex; align-items: center; gap: 12px; color: var(--color-text-muted); font-size: 11px; }
.story-card-meta .story-version { margin-left: auto; font: 10px ui-monospace, monospace; }
.story-card-meta svg { color: var(--color-accent); }
@media (max-width: 550px) { .studio-library .page-header { align-items: stretch; } .studio-library .page-header > .row { width: 100%; } .studio-library .page-header .button { flex: 1; } .studio-welcome { padding-inline: 0; } .story-cards { grid-template-columns: 1fr; } }
</style>
