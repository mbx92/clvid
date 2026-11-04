<script setup lang="ts">
import { newStory } from '~/utils/story'
const api = useApi()
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const busy = ref(false)
const error = ref('')
async function load(more = false) {
  try {const r = await api<{items: any[]; total: number}>('/studio', {query: {page: page.value}}); items.value = more ? [...items.value, ...r.items] : r.items; total.value = r.total} catch(e) {error.value = errorMessage(e)}
}
async function create() {
  busy.value = true
  try {const r = await api<{id: string}>('/studio', {method: 'POST', body: newStory()}); await navigateTo(`/studio/${r.id}`)} catch(e) {error.value = errorMessage(e)} finally {busy.value = false}
}
onMounted(() => load())
</script>
<template>
  <div class="page studio-library"><header class="page-header"><div><p class="eyebrow">STORY STUDIO</p><h1>Dari ide menjadi video</h1><p class="muted">Susun naskah, bangun adegan, dan temukan gaya Anda.</p></div><button class="button primary" :disabled="busy" @click="create"><AppIcon name="Plus"/>Buat video</button></header>
    <InlineError :message="error"/>
    <div v-if="!items.length" class="studio-welcome"><AppIcon name="Film" :size="40"/><h2>Cerita Anda, dalam gerak.</h2><p>Mulai dari naskah atau storyboard sendiri. Gunakan bantuan DeepSeek, pilih template, lalu tambahkan gambar dan rekaman suara.</p><button class="button primary" :disabled="busy" @click="create">Mulai storyboard pertama</button><span class="muted small">Bisa digunakan secara manual tanpa AI.</span></div>
    <div v-else class="story-cards"><NuxtLink v-for="item in items" :key="item.id" :to="`/studio/${item.id}`" class="story-card"><div class="story-cover" :style="{background: item.theme.background, color: item.theme.foreground}"><span :style="{color: item.theme.accent}">STORY / {{ String(item.scene_count).padStart(2, '0') }}</span><strong>{{ item.title }}</strong><i :style="{background: item.theme.accent}"/></div><div class="story-card-label"><strong>{{ item.title }}</strong><span>{{ item.scene_count }} adegan · Versi {{ item.version }}</span></div></NuxtLink></div>
    <button v-if="items.length < total" class="button secondary" @click="page++; load(true)">Muat lainnya</button>
  </div>
</template>
<style scoped>
.studio-library { overflow-y: auto; }
.studio-library .page-header { align-items: center; }
.studio-library .page-header p { margin-top: 8px; }
.studio-welcome { margin: auto; padding: 50px 20px; max-width: 540px; text-align: center; display: grid; justify-items: center; gap: 18px; }
.studio-welcome > svg { color: #567367; }
.studio-welcome p { line-height: 1.8; color: #6b756e; }
.story-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 22px; }
.story-card { border: 1px solid #dfe5df; border-radius: 12px; overflow: hidden; color: inherit; text-decoration: none; background: white; }
.story-cover { height: 230px; padding: 28px; display: flex; flex-direction: column; justify-content: space-between; }
.story-cover span { font-size: 10px; letter-spacing: 2px; }
.story-cover strong { font-size: 26px; line-height: 1.25; overflow-wrap: anywhere; }
.story-cover i { width: 48px; height: 4px; }
.story-card-label { display: grid; gap: 6px; padding: 18px; }
.story-card-label span { font-size: 11px; color: #6b756e; }
</style>
