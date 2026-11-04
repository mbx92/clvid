<script setup lang="ts">
import { hasTimedCaptions, storyVoiceLabel, storyProviderNotice, type StoryDocument, type StoryCapabilities, type StoryProduceMode } from '~/utils/story'
import type { Asset } from '~/types/api'
const props = defineProps<{ document: StoryDocument; assets: Asset[]; capabilities?: StoryCapabilities; busy: boolean }>()
const emit = defineEmits<{ produce: [mode: StoryProduceMode, voice?: string]; selectScene: [index: number] }>()
const voice = ref('')
watch(() => props.capabilities, value => {if (value && !value.voices.includes(voice.value)) voice.value = value.default_voice}, {immediate:true})
const narrated = computed(() => props.document.scenes.filter(s => s.narration.trim()))
const missingImages = computed(() => props.document.scenes.filter(s => !s.asset_id).length)
const missingVisuals = computed(() => props.document.scenes.filter(s => !s.asset_id && (!s.visual || s.visual.kind === 'none')).length)
const missingSpeech = computed(() => narrated.value.filter(s => !s.audio_id).length)
const audioScenes = computed(() => props.document.scenes.filter(s => s.audio_id).length)
const captionScenes = computed(() => props.document.scenes.filter(hasTimedCaptions).length)
const canComplete = computed(() => (missingVisuals.value > 0 || missingSpeech.value > 0 || audioScenes.value > 0) && (!missingVisuals.value || props.capabilities?.images) && (!missingSpeech.value || props.capabilities?.speech) && props.capabilities?.alignment)
function clippedAudio(id: string|null, duration: number) {return props.assets.some(a => a.id === id && (a.metadata.duration_ms || 0) > duration + 100)}
</script>
<template>
  <div class="production">
    <div class="intro"><h2>Dari adegan menjadi video.</h2><p>Lengkapi gambar, buat suara narator, lalu susun subtitle dari audionya. Tinjau hasil sebelum diterapkan.</p></div>
    <dl class="readiness" aria-label="Kesiapan produksi">
      <div><dt>Visual siap</dt><dd>{{ document.scenes.length - missingVisuals }}<small> / {{ document.scenes.length }}</small></dd></div>
      <div><dt>Narasi bersuara</dt><dd>{{ narrated.length - missingSpeech }}<small> / {{ narrated.length }}</small></dd></div>
      <div><dt>Subtitle dari audio</dt><dd>{{ captionScenes }}<small> / {{ audioScenes }}</small></dd></div>
    </dl>
    <p v-if="capabilities?.provider === 'local'" class="local-mode"><AppIcon name="HardDrive" :size="15"/><span>Model lokal · Tanpa biaya API gambar dan suara</span></p>
    <label v-if="capabilities?.voices.length">Suara narator<select v-model="voice" :disabled="busy || !capabilities?.speech"><option v-for="v in capabilities.voices" :key="v" :value="v">{{ storyVoiceLabel(v, capabilities) }}</option></select></label>
    <button class="button primary" :disabled="busy || !canComplete" @click="emit('produce','complete',voice)">Lengkapi semua adegan</button>
    <p class="muted small">Gambar, ilustrasi, dan rekaman yang sudah dipilih tetap dipakai. Durasi disesuaikan agar narasi selesai; hasilnya dapat mengubah durasi total video.</p>
    <p v-if="storyProviderNotice(capabilities)" class="notice">{{ storyProviderNotice(capabilities) }}</p>
    <details class="individual"><summary>Jalankan satu tahap</summary><div class="stages">
      <button class="button secondary" :disabled="busy || !capabilities?.images || !missingImages" @click="emit('produce','images',voice)">Buat {{ missingImages }} gambar AI untuk adegan tanpa unggahan</button>
      <p class="muted small">Tahap gambar AI dapat mengganti ilustrasi template pada adegan tanpa unggahan. Hasil tetap ditinjau sebelum diterapkan.</p>
      <button class="button secondary" :disabled="busy || !capabilities?.speech || !missingSpeech" @click="emit('produce','speech',voice)">Buat {{ missingSpeech }} narasi yang belum bersuara</button>
      <button class="button secondary" :disabled="busy || !capabilities?.alignment || !audioScenes" @click="emit('produce','captions',voice)">Susun subtitle semua rekaman</button>
    </div></details>
    <p class="muted small">Suara narator dibuat oleh AI. {{ capabilities?.provider === 'local' ? 'Pembuatan gambar dan suara dijalankan di server lokal. Waktu proses bergantung pada kemampuan perangkat.' : 'Narasi dan arahan visual dikirim ke layanan pembuat aset ketika Anda menjalankan tahap tersebut.' }}</p>
    <div class="scene-readiness"><h3>Periksa tiap adegan</h3><button v-for="(s,i) in document.scenes" :key="s.id" @click="emit('selectScene',i)"><span class="scene-number">{{ String(i+1).padStart(2,'0') }}</span><span class="scene-status"><strong>{{ s.title || `Adegan ${i+1}` }}</strong><small>{{ s.asset_id ? 'Media siap' : s.visual.kind !== 'none' ? 'Ilustrasi template' : 'Tanpa gambar' }} · {{ s.audio_id ? 'Audio siap' : s.narration.trim() ? 'Belum bersuara' : 'Tanpa narasi' }} · {{ hasTimedCaptions(s) ? 'Subtitle mengikuti audio' : s.show_caption && s.narration ? 'Timing perkiraan' : 'Tanpa subtitle' }}</small><small v-if="clippedAudio(s.audio_id,s.duration_ms)" class="duration-warning">Audio melewati akhir adegan. Sesuaikan durasi atau susun ulang subtitle.</small></span><AppIcon name="ChevronRight" :size="16"/></button></div>
  </div>
</template>
<style scoped>
.production {display:grid; gap:18px; padding:22px; min-width:0;}
.intro h2 {font-size:20px; line-height:1.4; margin:0 0 10px;}
.intro p,.production p {margin:0; line-height:1.65; font-size:12px; color:#617167;}
.readiness {display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:0; padding:16px 0; border-top:1px solid #e3e8e0; border-bottom:1px solid #e3e8e0;}
.readiness dt {font-size:11px; color:#63746a; min-height:32px; line-height:1.45;}
.readiness dd {font-size:25px; margin:5px 0 0; color:#244d3b;}
.readiness small {font-size:13px; color:#7c887f;}
.production label {display:grid; gap:8px; font-size:12px; margin:0;}
.production .button {white-space:normal;}
.production .local-mode {display:flex; align-items:center; gap:8px; color:#355d49; font-size:12px;}
.local-mode svg {flex:none;}
.individual {border-top:1px solid #e3e8e0; border-bottom:1px solid #e3e8e0; padding:14px 0; font-size:12px;}
.individual summary {cursor:pointer; font-weight:600;}
.stages {display:grid; gap:8px; margin-top:14px;}
.scene-readiness {display:grid; gap:2px; min-width:0;}
.scene-readiness h3 {font-size:13px; margin:0 0 10px;}
.scene-readiness button {width:100%; text-align:left; display:flex; align-items:center; gap:12px; padding:13px 0; border:0; border-bottom:1px solid #e3e8e0; background:transparent; cursor:pointer;}
.scene-number {font-size:11px; color:#718375;}
.scene-status {display:grid; gap:6px; flex:1; min-width:0;}
.scene-status strong {font-size:12px; overflow-wrap:anywhere;}
.scene-status small {font-size:11px; line-height:1.5; color:#63746a;}
.scene-status .duration-warning {color:#9a5a16;}
@media(max-width:760px) {.production {padding:18px;}}
</style>
