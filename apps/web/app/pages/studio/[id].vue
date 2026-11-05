<script setup lang="ts">
import { newScene, storyError, normalizeStory, visualOptions, visualIcons, hasTimedCaptions, storyModeLabel, type StoryDetail, type StoryDocument, type StoryJob, type StoryTemplate, type StoryProduceMode } from '~/utils/story'
import { isActive, timecode } from '~/utils/format'
import type { Asset, Job } from '~/types/api'
const api = useApi(), route = useRoute()
const data = ref<StoryDetail | null>(null), draft = ref<StoryDocument | null>(null)
const saved = ref(''), busy = ref(false), uploading = ref(false), error = ref(''), message = ref('')
const tab = ref('script'), selected = ref(0), mobilePane = ref('edit')
const templates = ref<StoryTemplate[]>([]), templateOpen = ref(false), templateName = ref('')
const proposal = ref<StoryDocument | null>(null), proposalVersion = ref(0), proposalMode = ref('storyboard')
const proposalWarnings = ref<string[]>([]), voice = ref('')
const latestVersion = ref(0)
const leaving = ref(false), leaveOpen = ref(false), leaveTo = ref('')
const dirty = computed(() => !!draft.value && JSON.stringify(draft.value) !== saved.value)
const proposalStale = computed(() => dirty.value || proposalVersion.value !== data.value?.version || proposalVersion.value !== latestVersion.value)
const validation = computed(() => draft.value ? storyError(draft.value) : '')
const hasStoryboardTable = computed(() => /^(?:\|\s*)?(waktu|time|timestamp)\s*[|\t]/im.test(draft.value?.script || ''))
const scene = computed(() => draft.value?.scenes[selected.value])
const duration = computed(() => draft.value?.scenes.reduce((n,s) => n + s.duration_ms, 0) || 0)
const activeJobs = computed(() => data.value?.jobs.filter(j => isActive(j.status)) || [])
const visualAssets = computed(() => data.value?.assets.filter(a => a.metadata.story_kind !== 'audio') || [])
const audioAssets = computed(() => data.value?.assets.filter(a => a.metadata.story_kind === 'audio') || [])
const producing = computed(() => activeJobs.value.some(j => j.kind === 'story_produce'))
const sceneAudio = computed(() => audioAssets.value.find(a => a.id === scene.value?.audio_id))
const sceneMedia = computed(() => visualAssets.value.find(a => a.id === scene.value?.asset_id))
const captionsReady = computed(() => draft.value?.scenes.filter(hasTimedCaptions).length || 0)
watch(() => data.value?.capabilities, value => {if (value && !value.voices.includes(voice.value)) voice.value = value.default_voice})
function adopt(value: StoryDetail) {data.value = value; latestVersion.value = value.version; draft.value = normalizeStory(structuredClone(value.document)); saved.value = JSON.stringify(draft.value); selected.value = Math.min(selected.value, value.document.scenes.length - 1)}
async function loadTemplates() {templates.value = (await api<{items: StoryTemplate[]}>('/studio/templates')).items}
async function load() {try {adopt(await api<StoryDetail>(`/studio/${route.params.id}`)); await loadTemplates()} catch(e) {error.value = errorMessage(e)}}
onMounted(load)
async function refresh() {
  try {const value = await api<StoryDetail>(`/studio/${route.params.id}`); if (data.value) {latestVersion.value = value.version; data.value.assets = value.assets; data.value.jobs = value.jobs; data.value.capabilities = value.capabilities}; return true} catch(e) {error.value = errorMessage(e); return false}
}
usePolling(refresh, () => activeJobs.value.length > 0)
async function save() {
  if (!draft.value || !data.value || busy.value) return false
  if (validation.value) {error.value = validation.value; return false}
  if (!dirty.value) return true
  busy.value = true; error.value = ''
  try {adopt(await api<StoryDetail>(`/studio/${data.value.id}`, {method: 'PUT', body: {expected_version: data.value.version, document: draft.value}})); message.value = 'Storyboard tersimpan.'; return true} catch(e) {error.value = errorMessage(e); return false} finally {busy.value = false}
}
async function run(kind: 'generate'|'render', mode = 'storyboard', sceneId?: string) {
  if (!await save() || !data.value) return
  busy.value = true; error.value = ''; message.value = ''
  try {const job = await api<StoryJob>(`/studio/${data.value.id}/${kind}`, {method: 'POST', headers: {'Idempotency-Key': idempotencyKey()}, body: {expected_version: data.value.version, mode, ...(sceneId ? {scene_id:sceneId} : {})}}); data.value.jobs = [job, ...data.value.jobs.filter(j => j.id !== job.id)]; tab.value = 'results'} catch(e) {error.value = errorMessage(e)} finally {busy.value = false}
}
async function produce(mode: StoryProduceMode, selectedVoice = voice.value, sceneId?: string, replaceExisting = false) {
  if (producing.value || !await save() || !data.value) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    const job = await api<StoryJob>(`/studio/${data.value.id}/produce`, {method:'POST', headers:{'Idempotency-Key':idempotencyKey()}, body:{expected_version:data.value.version,mode,...(selectedVoice ? {voice:selectedVoice} : {}),...(sceneId ? {scene_id:sceneId} : {}),replace_existing:replaceExisting}})
    data.value.jobs = [job,...data.value.jobs.filter(j => j.id !== job.id)]; tab.value = 'results'
    if (job.status === 'succeeded') await refresh()
  } catch(e) {error.value = errorMessage(e)} finally {busy.value = false}
}
function clearSceneCaptions() {if (scene.value) {scene.value.captions = []; scene.value.caption_audio_id = null; scene.value.caption_narration = ''}}
function selectScene(index: number) {selected.value = index; tab.value = 'scenes'}
async function review(job: StoryJob) {if (job.result_json?.document && await refresh()) {proposal.value = normalizeStory(structuredClone(toRaw(job.result_json.document))); proposalVersion.value = job.result_json.base_version || 0; proposalMode.value = job.result_json.mode || 'storyboard'; proposalWarnings.value = job.result_json.warnings || []}}
function applyProposal() {
  if (!proposal.value || !data.value || proposalStale.value) return
  draft.value = normalizeStory(structuredClone(toRaw(proposal.value))); proposal.value = null; selected.value = 0; tab.value = proposalMode.value === 'style' ? 'style' : 'scenes'; message.value = 'Usulan diterapkan ke draft. Simpan untuk menyimpan perubahan.'
}
async function splitScript() {
  if (!await save() || !draft.value || !data.value) return
  const blocks = draft.value.script.trim().split(/\n\s*\n/).filter(Boolean)
  if (!blocks.length || blocks.length > 20 || blocks.some(b => b.length > 600)) {error.value = 'Pisahkan naskah dengan baris kosong. Maksimal 20 paragraf, masing-masing 600 karakter.'; return}
  const doc = structuredClone(toRaw(draft.value))
  doc.scenes = blocks.map((block, i) => ({...newScene(), title: `Adegan ${i+1}`, narration: block, duration_ms: Math.min(30000, Math.max(3000, block.split(/\s+/).length * 400))}))
  if (storyError(doc)) {error.value = storyError(doc); return}
  proposal.value = doc; proposalVersion.value = data.value.version; proposalMode.value = 'storyboard'; proposalWarnings.value = []
}
async function importTable() {
  if (!await save() || !data.value) return
  busy.value = true; error.value = ''
  try {
    const result = await api<{document: StoryDocument; base_version: number}>(`/studio/${data.value.id}/import-table`, {method: 'POST', body: {expected_version: data.value.version}})
    proposal.value = result.document; proposalVersion.value = result.base_version; proposalMode.value = 'storyboard'; proposalWarnings.value = []
  } catch(e) {error.value = errorMessage(e)} finally {busy.value = false}
}
async function suggestVisuals(sceneId?: string) {
  if (!await save() || !data.value) return
  busy.value = true; error.value = ''
  try {
    const result = await api<{document: StoryDocument; base_version:number}>(`/studio/${data.value.id}/visuals`, {method:'POST', body:{expected_version:data.value.version, ...(sceneId ? {scene_id:sceneId} : {})}})
    proposal.value = result.document; proposalVersion.value = result.base_version; proposalMode.value = 'visuals'; proposalWarnings.value = []
  } catch(e) {error.value = errorMessage(e)} finally {busy.value = false}
}
function moveScene(delta: number) {if (!draft.value) return; const index = selected.value + delta; if (index < 0 || index >= draft.value.scenes.length) return; const [s] = draft.value.scenes.splice(selected.value,1); draft.value.scenes.splice(index,0,s!); selected.value = index}
function addScene() {if (!draft.value || draft.value.scenes.length >= 20) return; draft.value.scenes.push(newScene()); selected.value = draft.value.scenes.length - 1}
function removeScene() {if (!draft.value || draft.value.scenes.length <= 1) return; draft.value.scenes.splice(selected.value,1); selected.value = Math.max(0,selected.value-1)}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file || !data.value) return
  if (file.size > 60*1024*1024) {error.value = 'Maksimal 60 MB per aset.'; input.value = ''; return}
  uploading.value = true; error.value = ''
  try {const a = await api<Asset>(`/studio/${data.value.id}/assets`, {method: 'POST', query: {filename: file.name}, body: file, headers: {'Content-Type': 'application/octet-stream'}}); data.value.assets.push(a); message.value = 'Aset siap dipilih pada adegan.'} catch(e) {error.value = errorMessage(e)} finally {uploading.value = false; input.value = ''}
}
async function saveTemplate() {
  if (!draft.value || !templateName.value.trim()) return
  busy.value = true
  try {await api('/studio/templates', {method: 'POST', body: {name: templateName.value, theme: draft.value.theme}}); await loadTemplates(); templateOpen.value = false; templateName.value = ''; message.value = 'Template pribadi tersimpan.'} catch(e) {error.value = errorMessage(e)} finally {busy.value = false}
}
async function deleteTemplate(id: string) {try {await api(`/studio/templates/${id}`, {method: 'DELETE'}); await loadTemplates()} catch(e) {error.value = errorMessage(e)}}
function applyTheme(t: StoryTemplate) {if (draft.value) draft.value.theme = structuredClone(toRaw(t.theme))}
const beforeUnload = (event: BeforeUnloadEvent) => {if(dirty.value) {event.preventDefault(); event.returnValue = ''}}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
onBeforeRouteLeave(to => {if(dirty.value && !leaving.value) {leaveTo.value = to.fullPath; leaveOpen.value = true; return false}})
</script>
<template>
  <div class="story-editor-page">
    <header class="story-header"><NuxtLink to="/studio" class="icon-button" aria-label="Kembali ke Story Studio"><AppIcon name="ArrowLeft"/></NuxtLink><div class="story-heading"><label class="sr-only" for="story-title">Judul video</label><input v-if="draft" id="story-title" v-model="draft.title" maxlength="200" :disabled="busy"/><small :class="{ 'has-changes': dirty }"><span class="save-indicator"/>{{ dirty ? 'Perubahan belum tersimpan' : `Versi ${data?.version || 1} tersimpan` }}<span class="header-duration">{{ timecode(duration) }}</span></small></div><div class="row gap-2"><button class="button secondary" :disabled="busy || !dirty || !!validation" @click="save"><AppIcon name="Save"/>Simpan</button><button class="button primary" :disabled="busy || !draft || !!validation" @click="run('render')"><AppIcon name="Download"/>Ekspor MP4</button></div></header>
    <InlineError :message="error || validation"/>
    <p v-if="message" class="story-message" role="status">{{ message }}<button class="icon-button" aria-label="Tutup pemberitahuan" @click="message = ''"><AppIcon name="X" :size="14"/></button></p>
    <div class="story-mobile-switch"><button :aria-pressed="mobilePane === 'edit'" @click="mobilePane = 'edit'">Editor</button><button :aria-pressed="mobilePane === 'preview'" @click="mobilePane = 'preview'">Preview</button></div>
    <div v-if="draft && data" class="story-workspace" :class="`show-${mobilePane}`">
      <section class="story-player-panel" aria-label="Preview dan urutan adegan">
        <div class="story-monitor-heading"><span>MONITOR PROGRAM</span><span>{{ draft.aspect === 'portrait' ? '720 × 1280' : draft.aspect === 'landscape' ? '1280 × 720' : '1080 × 1080' }} <b>30 FPS</b></span></div>
        <div class="story-preview-stage"><StoryPreview v-if="!validation" :document="draft" :assets="data.assets" :selected-scene="selected"/><p v-else class="notice">Perbaiki durasi adegan untuk menampilkan preview.</p></div>
        <div class="story-preview-footer"><span>ADEGAN {{ String(selected + 1).padStart(2, '0') }} / {{ String(draft.scenes.length).padStart(2, '0') }}</span><label>Format<select v-model="draft.aspect" :disabled="busy"><option value="portrait">9:16 Vertikal</option><option value="landscape">16:9 Horizontal</option><option value="square">1:1 Persegi</option></select></label></div>
        <div class="story-sequence"><div class="sequence-heading"><h2>Urutan adegan</h2><span>{{ timecode(duration) }}</span></div><div class="sequence-tracks" role="group" aria-label="Urutan adegan"><button v-for="(s, i) in draft.scenes" :key="s.id" :style="{ flexGrow: s.duration_ms }" :aria-pressed="selected === i" :aria-label="`Pilih adegan ${i + 1}: ${s.title || 'Tanpa judul'}`" @click="selectScene(i)"><span>{{ String(i + 1).padStart(2, '0') }}</span><strong>{{ s.title || 'Tanpa judul' }}</strong><small>{{ timecode(s.duration_ms) }}</small></button></div></div>
        <p class="story-caption-note">{{ captionsReady }} dari {{ draft.scenes.length }} adegan memakai subtitle dari audio. Sisanya mengikuti perkiraan teks narasi.</p>
      </section>
      <section class="story-tools"><div class="story-tabs" role="tablist" aria-label="Editor storyboard"><button v-for="t in [{id:'script',label:'Naskah'},{id:'scenes',label:'Adegan'},{id:'production',label:'Produksi'},{id:'style',label:'Gaya'},{id:'results',label:'Hasil'}]" :key="t.id" role="tab" :aria-selected="tab === t.id" :aria-controls="`story-panel-${t.id}`" :id="`story-tab-${t.id}`" @click="tab = t.id">{{ t.label }}<span v-if="t.id === 'scenes'">{{ draft.scenes.length }}</span><span v-if="t.id === 'results' && activeJobs.length">{{ activeJobs.length }}</span></button></div>
        <div class="story-tool-content" role="tabpanel" :id="`story-panel-${tab}`" :aria-labelledby="`story-tab-${tab}`" :inert="busy || undefined">
          <div v-if="tab === 'script'" class="story-form"><div class="section-heading"><span class="eyebrow">NASKAH &amp; STRUKTUR</span><h2>Susun isi video.</h2><p>Tulis naskah, storyboard per paragraf, atau tempel tabel Waktu, Visual, dan Narasi.</p></div><label>Naskah atau storyboard<textarea v-model="draft.script" rows="10" maxlength="12000" placeholder="Pembuka: Kenapa kopi terasa pahit?&#10;&#10;Adegan berikutnya: Tiga hal yang perlu diperhatikan..."/></label><label class="checkbox-label"><input v-model="draft.preserve_script" type="checkbox"/>Pertahankan naskah persis saat memakai AI</label><p class="muted small">Untuk tabel, yang dipertahankan adalah kolom narasi. Waktu dan visual dibaca terpisah; tautan sumber tetap tersimpan di naskah.</p><div class="story-actions"><button class="button primary" :disabled="!draft.script.trim() || !data.ai_available || activeJobs.some(j => j.kind === 'story_generate')" @click="run('generate')"><AppIcon name="Film"/>Susun dengan DeepSeek</button><button v-if="hasStoryboardTable" class="button secondary" @click="importTable">Impor tabel storyboard</button><button v-else class="button secondary" :disabled="!draft.script.trim()" @click="splitScript">Satu paragraf per adegan</button></div><p class="muted small">Naskah dan arahan gaya dikirim ke DeepSeek saat Anda menggunakan AI. Aset unggahan tidak dikirim.</p><p v-if="!data.ai_available" class="notice">DeepSeek belum dikonfigurasi. Anda tetap dapat menulis adegan dan memilih template secara manual.</p><button class="text-button" @click="tab = 'scenes'">Atau susun adegan sendiri <AppIcon name="ArrowRight" :size="14"/></button></div>
          <div v-if="tab === 'scenes'" class="story-form"><div class="visual-tools"><div><h3>Ilustrasi storyboard</h3><p>Isi adegan dengan gambar animasi dari catatan visual.</p></div><div class="story-actions"><button class="button secondary" @click="suggestVisuals()">Isi visual kosong</button><button class="button primary" :disabled="!data.ai_available || activeJobs.some(j => j.kind === 'story_generate')" @click="run('generate', 'visuals')">Buat visual dengan DeepSeek</button></div><p class="muted small">Ilustrasi animasi, bukan foto. Unggahan Anda tetap dipakai.</p></div><div class="scene-strip" role="group" aria-label="Pilih adegan"><button v-for="(s,i) in draft.scenes" :key="s.id" :aria-pressed="selected === i" @click="selected = i"><span>{{ String(i+1).padStart(2,'0') }}</span><strong>{{ s.title || 'Tanpa judul' }}</strong><small>{{ s.duration_ms / 1000 }} dtk</small></button><button class="scene-add" :disabled="draft.scenes.length >= 20" aria-label="Tambah adegan" @click="addScene"><AppIcon name="Plus"/></button></div>
            <template v-if="scene"><div class="scene-controls"><strong>Adegan {{ selected+1 }}</strong><div class="row gap-2"><button class="icon-button" aria-label="Geser adegan ke kiri" :disabled="selected === 0" @click="moveScene(-1)"><AppIcon name="ChevronLeft"/></button><button class="icon-button" aria-label="Geser adegan ke kanan" :disabled="selected === draft.scenes.length-1" @click="moveScene(1)"><AppIcon name="ChevronRight"/></button><button class="icon-button" aria-label="Hapus adegan" :disabled="draft.scenes.length === 1" @click="removeScene"><AppIcon name="Trash2"/></button></div></div><div class="story-two-col"><label>Tata letak<select v-model="scene.layout"><option value="title">Judul & teks</option><option value="split">Gambar & teks</option><option value="quote">Kutipan</option><option value="stat">Angka utama</option></select></label><label>Durasi (detik)<input :value="scene.duration_ms / 1000" type="number" min="1" max="30" step="0.1" @input="scene.duration_ms = Math.round(Number(($event.target as HTMLInputElement).value)*1000)"/></label></div><label>Judul adegan<input v-model="scene.title" maxlength="120"/></label><label>Teks layar<textarea v-model="scene.text" rows="3" maxlength="360"/></label><label>Narasi / subtitle<textarea v-model="scene.narration" rows="3" maxlength="600" @input="clearSceneCaptions"/></label><label class="checkbox-label"><input v-model="scene.show_caption" type="checkbox"/>Tampilkan narasi sebagai subtitle</label><label>Catatan visual<textarea v-model="scene.visual_note" rows="2" maxlength="500" placeholder="Contoh: penampang buah kopi dengan dua biji, lalu pisahkan perlahan"/></label>
              <div class="illustration-controls"><h3>Ilustrasi adegan</h3><p v-if="scene.asset_id" class="notice">Unggahan gambar/video sedang dipakai. Pilih Ilustrasi / latar template pada Media adegan untuk menampilkan ilustrasi.</p><label>Jenis ilustrasi<select v-model="scene.visual.kind" :disabled="!!scene.asset_id"><option v-for="option in visualOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label><template v-if="scene.visual.kind !== 'none'"><label>Gerakan ilustrasi<select v-model="scene.visual.motion"><option value="gentle">Animasi lembut</option><option value="still">Diam</option></select></label><label v-if="scene.visual.kind === 'coffee_reveal'">Ungkap jawaban setelah (detik)<input :value="scene.visual.reveal_ms / 1000" type="number" min="0" max="10" step="0.1" @input="scene.visual.reveal_ms = Math.round(Number(($event.target as HTMLInputElement).value)*1000)"/></label><template v-if="['diagram','comparison','steps'].includes(scene.visual.kind)"><div v-for="(item,i) in scene.visual.items" :key="i" class="visual-item-editor"><label>Objek {{ i+1 }}<select v-model="item.icon"><option v-for="icon in visualIcons" :key="icon.value" :value="icon.value">{{ icon.label }}</option></select></label><label>Label {{ i+1 }}<input v-model="item.label" maxlength="32"/></label><button class="icon-button" :aria-label="`Hapus objek ${i+1}`" @click="scene.visual.items.splice(i,1)"><AppIcon name="X" :size="15"/></button></div><button class="button secondary" :disabled="scene.visual.items.length >= 4" @click="scene.visual.items.push({icon:'box',label:''})">Tambah objek</button></template></template><div class="story-actions"><button class="button secondary" :disabled="!!scene.asset_id" @click="suggestVisuals(scene.id)">Ilustrasikan adegan ini</button><button class="text-button" :disabled="!!scene.asset_id || !data.ai_available || activeJobs.some(j => j.kind === 'story_generate')" @click="run('generate','visuals',scene.id)">Gunakan DeepSeek untuk adegan ini</button></div></div>
              <StorySceneGeneration :scene="scene" :capabilities="data.capabilities" :disabled="busy || producing || !!validation" @produce="(mode, selectedVoice, replace) => produce(mode, selectedVoice, scene?.id, replace)"/>
              <div class="asset-section"><h3>Media adegan</h3><img v-if="sceneMedia?.metadata.story_kind === 'image'" :src="`/api/v1/assets/${sceneMedia.id}/content`" alt="Gambar adegan terpilih" class="scene-image"/><label>Gambar atau video<select v-model="scene.asset_id"><option :value="null">Ilustrasi / latar template</option><option v-for="a in visualAssets" :key="a.id" :value="a.id">{{ a.metadata.filename }}</option></select></label><label v-if="scene.asset_id && visualAssets.find(a => a.id === scene?.asset_id)?.metadata.story_kind === 'video'">Mulai video (detik)<input :value="scene.media_start_ms/1000" type="number" min="0" step="0.1" @input="scene.media_start_ms = Math.round(Number(($event.target as HTMLInputElement).value)*1000)"/></label><label>Rekaman suara<select v-model="scene.audio_id" @change="clearSceneCaptions"><option :value="null">Tanpa suara</option><option v-for="a in audioAssets" :key="a.id" :value="a.id">{{ a.metadata.filename }} ({{ timecode(a.metadata.duration_ms) }})</option></select></label><audio v-if="sceneAudio" :src="`/api/v1/assets/${sceneAudio.id}/content`" controls preload="metadata" class="scene-audio"/><p v-if="sceneAudio?.metadata.generated" class="muted small">Suara narator ini dibuat oleh AI.</p><p v-if="sceneAudio && sceneAudio.metadata.duration_ms > scene.duration_ms + 100" class="notice">Audio lebih panjang dari adegan dan akan terpotong saat ekspor. Susun subtitle dari audio untuk menyesuaikan durasinya.</p><p class="muted small">Rekaman dimulai dari awal adegan. Suara asli video tidak dipakai.</p><label class="story-upload"><AppIcon name="Upload" :size="16"/><span>{{ uploading ? 'Mengunggah dan menyiapkan aset...' : 'Unggah gambar, video, atau audio' }}</span><input type="file" accept=".png,.jpg,.jpeg,.mp4,.mp3,.wav,.m4a" :disabled="uploading" @change="upload"/></label><span class="muted small">PNG, JPG, MP4, MP3, WAV, M4A · Maks. 60 MB / 3 menit</span></div>
              <StoryCaptions :scene="scene" :disabled="busy || producing" :alignment-available="data.capabilities?.alignment" @align="produce('captions',voice,scene?.id)"/>
            </template>
          </div>
          <StoryProduction v-if="tab === 'production'" :document="draft" :assets="data.assets" :capabilities="data.capabilities" :busy="busy || producing || !!validation" @produce="produce" @select-scene="selectScene"/>
          <div v-if="tab === 'style'" class="story-form"><div class="section-heading"><span class="eyebrow">02 / IDENTITAS</span><h2>Satu gaya untuk seluruh cerita.</h2><p>Pilih template, sesuaikan sendiri, atau jelaskan gaya yang Anda inginkan.</p></div><div class="theme-grid"><div v-for="t in templates" :key="t.id" class="theme-item"><button :style="{background: t.theme.background, color: t.theme.foreground}" @click="applyTheme(t)"><span :style="{color: t.theme.accent}">Aa</span><strong>{{ t.name }}</strong></button><button v-if="t.custom" class="text-button small" :aria-label="`Hapus template ${t.name}`" @click="deleteTemplate(t.id)">Hapus</button></div></div><div class="story-colors"><label>Latar<input v-model="draft.theme.background" type="color"/></label><label>Teks<input v-model="draft.theme.foreground" type="color"/></label><label>Aksen<input v-model="draft.theme.accent" type="color"/></label></div><div class="story-two-col"><label>Tipografi<select v-model="draft.theme.font"><option value="sans">Sans</option><option value="serif">Serif</option><option value="mono">Mono</option></select></label><label>Gerak<select v-model="draft.theme.motion"><option value="rise">Naik perlahan</option><option value="fade">Fade</option><option value="zoom">Zoom</option><option value="none">Tanpa animasi</option></select></label><label>Perataan<select v-model="draft.theme.align"><option value="left">Kiri</option><option value="center">Tengah</option></select></label><label>Ukuran judul<input v-model.number="draft.theme.font_size" type="number" min="40" max="100"/></label></div><label class="checkbox-label"><input v-model="draft.theme.uppercase" type="checkbox"/>Judul huruf kapital</label><button class="button secondary" @click="templateOpen = true"><AppIcon name="Save"/>Simpan sebagai template</button><div class="prompt-section"><label>Arahan gaya<textarea v-model="draft.style_prompt" rows="3" maxlength="2000" placeholder="Contoh: editorial hangat, latar krem, aksen merah bata, huruf serif dan animasi lembut."/></label><button class="button primary" :disabled="!draft.style_prompt.trim() || !data.ai_available || activeJobs.some(j => j.kind === 'story_generate')" @click="run('generate','style')">Buat variasi gaya dengan AI</button><p class="muted small">Prompt mengubah warna, tipografi, perataan, dan gerak. Isi adegan tetap dipertahankan.</p></div></div>
          <div v-if="tab === 'results'" class="story-form"><div class="section-heading"><span class="eyebrow">03 / HASIL</span><h2>Tinjau, terapkan, ekspor.</h2><p>Hasil AI tidak mengganti draft sebelum Anda menerapkannya.</p></div><p v-if="!data.jobs.length" class="muted">Belum ada proses. Susun dengan AI atau ekspor storyboard Anda.</p><article v-for="job in data.jobs" :key="job.id" class="story-job"><JobStatus :job="job as Job" @refresh="refresh"/><template v-if="job.status === 'succeeded' && job.result_json?.document"><p class="muted small">Usulan {{ storyModeLabel(job.result_json.mode) }} dari versi {{ job.result_json.base_version }}.</p><button class="button secondary" @click="review(job)">Tinjau usulan</button></template><div v-if="job.status === 'succeeded' && job.result_json?.mp4_asset_id" class="story-downloads"><p>Video versi {{ job.result_json.version }} siap.</p><video :src="`/api/v1/assets/${job.result_json.mp4_asset_id}/content`" controls preload="metadata"/><div class="row gap-2"><a class="button primary" :href="`/api/v1/assets/${job.result_json.mp4_asset_id}/content?download=true`" download>Unduh MP4</a><a class="button secondary" :href="`/api/v1/assets/${job.result_json.srt_asset_id}/content?download=true`" download>Unduh SRT</a></div></div></article></div>
        </div>
      </section>
    </div>
    <AppDialog :open="!!proposal" title="Tinjau usulan" wide @close="proposal = null"><template v-if="proposal"><p class="muted">{{ proposal.scenes.length }} adegan · {{ timecode(proposal.scenes.reduce((n,s) => n+s.duration_ms,0)) }}. Menerapkan usulan akan mengganti {{ storyModeLabel(proposalMode) }} pada draft.</p><ul v-if="proposalWarnings.length" class="proposal-warnings"><li v-for="warning in proposalWarnings" :key="warning">{{ warning }}</li></ul><div class="proposal-preview"><StoryPreview :document="proposal" :assets="data?.assets || []"/></div><div class="proposal-scenes"><p v-for="(s,i) in proposal.scenes" :key="s.id"><strong>{{ i+1 }}. {{ s.title }}</strong> — {{ s.narration || s.text }}</p></div><p v-if="proposalStale" class="notice">Draft sudah berubah sejak usulan dibuat. Simpan perubahan dan minta usulan baru agar perubahan Anda tetap aman.</p><div class="dialog-actions"><button class="button secondary" @click="proposal = null">Kembali</button><button class="button primary" :disabled="proposalStale" @click="applyProposal">Terapkan ke draft</button></div></template></AppDialog>
    <AppDialog :open="templateOpen" title="Simpan template pribadi" :busy="busy" @close="templateOpen = false"><label>Nama template<input v-model="templateName" maxlength="80" placeholder="Contoh: Brand kopi saya"/></label><p class="muted small">Menyimpan warna, tipografi, dan animasi untuk video berikutnya.</p><div class="dialog-actions"><button class="button secondary" @click="templateOpen = false">Batal</button><button class="button primary" :disabled="busy || !templateName.trim()" @click="saveTemplate">Simpan template</button></div></AppDialog>
    <AppDialog :open="leaveOpen" title="Perubahan belum tersimpan" @close="leaveOpen = false"><p>Simpan storyboard sebelum meninggalkan halaman.</p><div class="dialog-actions"><button class="button secondary" @click="leaving = true; navigateTo(leaveTo)">Tinggalkan perubahan</button><button class="button primary" :disabled="busy" @click="save().then(ok => { if(ok) {leaving = true; navigateTo(leaveTo)} })">Simpan dan lanjutkan</button></div></AppDialog>
  </div>
</template>
<style scoped>
.story-editor-page { height: var(--workspace-height, 100dvh); display: flex; flex-direction: column; min-height: 0; background: var(--color-canvas); }
.story-header { display: flex; align-items: center; gap: 12px; padding: 16px 22px; background: var(--color-surface); border-bottom: 1px solid var(--color-border); flex: none; }
.story-heading { flex: 1; min-width: 0; }
.story-heading input { border: 0; background: transparent; padding: 0; min-height: 28px; font-weight: 600; font-size: 17px; width: 100%; }
.story-heading small { color: var(--color-text-muted); font-size: 10px; }
.story-message { display: flex; align-items: center; justify-content: space-between; padding: 5px 22px; background: #203129; color: var(--color-positive); font-size: 12px; flex: none; margin: 0; }
.story-workspace { display: grid; grid-template-columns: minmax(280px,1fr) minmax(390px,450px); flex: 1; min-height: 0; }
.story-player-panel { padding: 18px 22px; display: flex; flex-direction: column; gap: 10px; min-width: 0; min-height: 0; }
.story-preview-stage { display: flex; align-items: center; justify-content: center; flex: 1; min-height: 100px; padding: 16px; border: 1px solid #2b3036; background: #0e1012; border-radius: 6px; overflow: hidden; }
.story-preview-footer { display: flex; gap: 12px; align-items: center; justify-content: space-between; }
.story-preview-footer > span { font-size: 9px; letter-spacing: 1.4px; color: var(--color-text-muted); }
.story-preview-footer label { margin: 0; display: flex; align-items: center; gap: 10px; font-size: 11px; }
.story-preview-footer select { min-height: 34px; padding: 5px; }
.story-tools { display: flex; flex-direction: column; min-height: 0; border-left: 1px solid var(--color-border); background: var(--color-surface); }
.story-tabs { display: flex; gap: 16px; overflow-x: auto; padding: 0 20px; border-bottom: 1px solid var(--color-border); flex: none; }
.story-tabs button { flex-shrink:0; border: 0; border-bottom: 2px solid transparent; background: none; padding: 16px 0; font-size: 12px; cursor: pointer; color: var(--color-text-muted); }
.story-tabs button[aria-selected=true] { color: var(--color-accent); border-color: var(--color-accent); font-weight: 600; }
.story-tabs span { margin-left: 5px; padding: 2px 4px; background: var(--color-surface-muted); border-radius: 3px; font-size: 9px; }
.story-tool-content { overflow-y: auto; flex: 1; min-height: 0; }
.story-form { padding: 22px; display: flex; flex-direction: column; gap: 18px; }
.story-form label { margin: 0; display: flex; flex-direction: column; gap: 8px; font-size: 12px; }
.story-form .checkbox-label { flex-direction: row; align-items: center; gap: 8px; }
.story-form textarea { line-height: 1.65; resize: vertical; }
.story-form p { margin: 0; }
.section-heading h2 { font-size: 20px; line-height: 1.4; margin: 10px 0; }
.section-heading p { color: var(--color-text-muted); font-size: 12px; line-height: 1.7; }
.visual-tools { padding: 16px; border: 1px solid var(--color-border); background: var(--color-surface-muted); border-radius: 6px; display: grid; gap: 12px; }
.visual-tools p { font-size: 12px; line-height: 1.6; margin-top: 6px; color: var(--color-text-muted); }
.visual-item-editor { display: grid; grid-template-columns: 1fr 1fr auto; gap: 8px; align-items: end; }
.story-actions { display: flex; flex-direction: column; gap: 8px; }
.story-two-col { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; }
.story-two-col input, .story-form select { width: 100%; min-width: 0; }
.scene-strip { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; }
.scene-strip button { flex: 0 0 110px; padding: 12px; border: 1px solid var(--color-border); border-radius: 5px; background: var(--color-surface); display: grid; gap: 8px; text-align: left; cursor: pointer; }
.scene-strip button[aria-pressed=true] { border-color: var(--color-accent); background: #302a21; }
.scene-strip span { font-size: 10px; color: var(--color-text-muted); }
.scene-strip strong { font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 85px; }
.scene-strip small { color: var(--color-text-muted); font-size: 10px; }
.scene-strip .scene-add { flex-basis: 40px; align-items: center; justify-content: center; }
.scene-controls { display: flex; justify-content: space-between; align-items: center; }
.scene-controls strong { font-size: 14px; }
.asset-section, .prompt-section, .illustration-controls { border-top: 1px solid var(--color-border); padding-top: 20px; display: flex; flex-direction: column; gap: 14px; }
.asset-section h3, .illustration-controls h3, .visual-tools h3 { font-size: 13px; margin: 0; }
.story-upload { padding: 16px; border: 1px dashed #545a63; border-radius: 5px; background: var(--color-canvas); }
.story-upload input { font-size: 11px; border: 0; padding: 0; min-height: 24px; }
.theme-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }
.theme-item > button:first-child { width: 100%; min-height: 100px; border-radius: 5px; border: 0; display: flex; flex-direction: column; justify-content: space-between; align-items: flex-start; padding: 12px; cursor: pointer; }
.theme-item span { font-size: 28px; }
.theme-item strong { font-size: 10px; overflow-wrap: anywhere; text-align: left; }
.story-colors { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; }
.story-colors input { width: 100%; height: 38px; padding: 3px; }
.story-job { border: 1px solid var(--color-border); border-radius: 5px; padding: 12px; display: grid; gap: 12px; }
.story-job :deep(.job-row) { padding: 0; flex-wrap: wrap; }
.scene-image {width:100%; max-height:180px; object-fit:contain; background:#0e1012; border-radius:6px;}
.scene-audio {width:100%;}
.proposal-warnings {margin:14px 0; padding-left:20px; font-size:12px; line-height:1.6; color:var(--color-accent);}
.story-downloads { display: grid; gap: 12px; }
.story-downloads video { max-height: 220px; width: 100%; background: #0e1012; border-radius: 6px; }
.proposal-preview { height: 300px; padding: 12px; background: #0e1012; border-radius: 5px; margin-top: 16px; }
.proposal-scenes { max-height: 130px; overflow-y: auto; margin-top: 12px; font-size: 12px; }
.proposal-scenes p { padding: 8px 0; border-bottom: 1px solid var(--color-border); }
.story-mobile-switch { display: none; }
@media(max-width: 1050px) {.story-workspace {grid-template-columns: minmax(200px,1fr) 390px;} .story-player-panel {padding: 14px;} .story-header {padding: 12px;} .story-header .button {font-size: 11px; padding: 8px;}}
@media(max-width: 900px) {
  .story-editor-page { height: var(--workspace-height, calc(100dvh - 104px)); }
  .story-header {flex-wrap: wrap; gap: 8px;}
  .story-header > .row { width: 100%; justify-content: flex-end; }
  .story-header .button {min-height: 36px;}
  .story-mobile-switch {display: flex; gap: 6px; padding: 8px 14px;}
  .story-mobile-switch button {flex: 1; border: 0; padding: 8px; border-radius: 6px; background: var(--color-surface-muted); color: var(--color-text-muted);}
  .story-mobile-switch button[aria-pressed=true] {background: var(--color-accent); color: #191712;}
  .story-workspace {display: flex; flex-direction: column;}
  .story-tools, .story-player-panel {flex: 1;}
  .show-edit .story-player-panel, .show-preview .story-tools {display: none;}
  .story-form {padding: 18px;}
  .story-tabs {gap: 20px;}
  .story-preview-footer > span {display: none;}
  .proposal-preview {height: 220px;}
}
.story-heading small { display: flex; align-items: center; gap: 7px; margin-top: 4px; }
.save-indicator { width: 5px; height: 5px; border-radius: 50%; background: var(--color-positive); }
.has-changes .save-indicator { background: var(--color-accent); }
.header-duration { padding-left: 10px; margin-left: 4px; border-left: 1px solid var(--color-border); font-family: ui-monospace, monospace; }
.story-monitor-heading { display: flex; justify-content: space-between; gap: 12px; color: var(--color-text-muted); font: 10px ui-monospace, monospace; letter-spacing: .6px; flex: none; }
.story-monitor-heading b { font-weight: 400; margin-left: 12px; color: #c2c7ce; }
.story-preview-footer { flex: none; }
.story-preview-footer > span { font: 10px ui-monospace, monospace; letter-spacing: .5px; }
.story-preview-footer select { border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text); }
.story-sequence { flex: none; border-top: 1px solid var(--color-border); padding-top: 13px; margin-top: 2px; min-width: 0; }
.sequence-heading { display: flex; justify-content: space-between; align-items: center; margin-bottom: 9px; }
.sequence-heading h2 { color: var(--color-text-muted); font-size: 11px; font-weight: 500; }
.sequence-heading > span { font: 11px ui-monospace, monospace; color: var(--color-text); }
.sequence-tracks { display: flex; gap: 4px; padding-bottom: 3px; overflow-x: auto; }
.sequence-tracks button { flex-basis: 96px; flex-shrink: 0; min-width: 96px; max-width: 220px; min-height: 70px; padding: 8px 10px; border: 1px solid #454d56; border-top: 3px solid #66707d; border-radius: 3px; background: #262c33; color: var(--color-text); text-align: left; display: grid; grid-template-columns: 1fr auto; gap: 7px; }
.sequence-tracks button[aria-pressed=true] { border-color: var(--color-accent); background: #312a21; }
.sequence-tracks button span, .sequence-tracks button small { font: 10px ui-monospace, monospace; color: var(--color-text-muted); }
.sequence-tracks button strong { grid-column: 1 / -1; grid-row: 2; font-size: 11px; line-height: 1.35; font-weight: 500; max-width: 100%; text-overflow: ellipsis; white-space: nowrap; overflow: hidden; }
.sequence-tracks button[aria-pressed=true] span { color: var(--color-accent); }
.story-caption-note { flex: none; font-size: 10px; line-height: 1.5; color: var(--color-text-muted); }
.story-form select, .story-form input[type=color] { color: var(--color-text); background: var(--color-canvas); border: 1px solid var(--color-border); border-radius: 4px; padding: 8px 10px; min-height: 36px; }
.story-form .section-heading .eyebrow { font: 10px ui-monospace, monospace; letter-spacing: 1px; color: var(--color-accent); }
.story-form .section-heading h2 { font-size: 20px; margin-block: 8px; letter-spacing: -.3px; }
.story-form .visual-tools { border-left: 2px solid #666f7a; padding: 14px; }
.scene-strip button { min-height: 83px; }
.scene-strip button[aria-pressed=true] span { color: var(--color-accent); }
.scene-strip button:hover:not(:disabled) { border-color: #737d8a; }
.scene-controls { padding-bottom: 12px; border-bottom: 1px solid var(--color-border); }
.theme-item > button:first-child { outline: 1px solid #ffffff20; outline-offset: -1px; }
.story-job { background: var(--color-canvas); }
.proposal-scenes { max-height: 180px; color: var(--color-text-muted); line-height: 1.65; }
.proposal-scenes strong { color: var(--color-text); }
.story-tabs button:focus-visible { outline-offset: -4px; }
@media (max-width: 900px) {
  .story-player-panel { padding: 12px; }
  .story-monitor-heading { font-size: 9px; }
  .story-preview-stage { padding: 10px; }
  .story-tools { border-left: 0; border-top: 1px solid var(--color-border); }
  .story-header > .row { padding-left: 44px; }
  .story-header > .row .button { flex: 1; }
  .story-header .button { min-height: 38px; font-size: 12px; }
  .story-tabs { gap: 0; justify-content: space-between; padding-inline: 16px; }
  .story-tabs button { min-height: 46px; padding-inline: 3px; }
  .story-monitor-heading b { margin-left: 7px; }
  .sequence-tracks button { min-height: 62px; }
  .story-caption-note { font-size: 10px; }
}
@media (max-height: 720px) and (min-width: 901px) {
  .story-player-panel { gap: 8px; padding: 12px 16px; }
  .sequence-tracks button { min-height: 58px; }
  .story-caption-note { display: none; }
}
</style>
