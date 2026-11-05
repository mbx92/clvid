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
    <div class="intro"><span class="production-label">PRODUKSI ASET</span><h2>Kesiapan storyboard</h2><p>Periksa visual, rekaman narasi, dan subtitle sebelum mengekspor video.</p></div>
    <dl class="readiness" aria-label="Kesiapan produksi">
      <div :class="{ complete: missingVisuals === 0 }"><dt>Visual siap</dt><dd>{{ document.scenes.length - missingVisuals }}<small> / {{ document.scenes.length }}</small></dd><progress :value="document.scenes.length - missingVisuals" :max="document.scenes.length || 1" aria-label="Kesiapan visual"/></div>
      <div :class="{ complete: missingSpeech === 0 && narrated.length > 0 }"><dt>Narasi bersuara</dt><dd>{{ narrated.length - missingSpeech }}<small> / {{ narrated.length }}</small></dd><progress :value="narrated.length - missingSpeech" :max="narrated.length || 1" aria-label="Kesiapan narasi"/></div>
      <div :class="{ complete: captionScenes === audioScenes && audioScenes > 0 }"><dt>Subtitle dari audio</dt><dd>{{ captionScenes }}<small> / {{ audioScenes }}</small></dd><progress :value="captionScenes" :max="audioScenes || 1" aria-label="Kesiapan subtitle"/></div>
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
.intro p,.production p {margin:0; line-height:1.65; font-size:12px; color:var(--color-text-muted);}
.readiness {display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:0; padding:16px 0; border-top:1px solid var(--color-border); border-bottom:1px solid var(--color-border);}
.readiness dt {font-size:11px; color:var(--color-text-muted); min-height:32px; line-height:1.45;}
.readiness dd {font-size:20px; font-family:ui-monospace,monospace; margin:5px 0 0; color:var(--color-text);}
.readiness small {font-size:13px; color:var(--color-text-muted);}
.production label {display:grid; gap:8px; font-size:12px; margin:0;}
.production .button {white-space:normal;}
.production .local-mode {display:flex; align-items:center; gap:8px; color:var(--color-positive); font-size:12px;}
.local-mode svg {flex:none;}
.individual {border-top:1px solid var(--color-border); border-bottom:1px solid var(--color-border); padding:14px 0; font-size:12px;}
.individual summary {cursor:pointer; font-weight:600;}
.stages {display:grid; gap:8px; margin-top:14px;}
.scene-readiness {display:grid; gap:2px; min-width:0;}
.scene-readiness h3 {font-size:13px; margin:0 0 10px;}
.scene-readiness button {width:100%; text-align:left; display:flex; align-items:center; gap:12px; padding:13px 0; border:0; border-bottom:1px solid var(--color-border); background:transparent; cursor:pointer;}
.scene-number {font-size:11px; color:var(--color-text-muted);}
.scene-status {display:grid; gap:6px; flex:1; min-width:0;}
.scene-status strong {font-size:12px; overflow-wrap:anywhere;}
.scene-status small {font-size:11px; line-height:1.5; color:var(--color-text-muted);}
.scene-status .duration-warning {color:var(--color-accent);}
@media(max-width:760px) {.production {padding:18px;}}
.production-label {display:block; font:10px ui-monospace,monospace; letter-spacing:1px; color:var(--color-accent); margin-bottom:9px;}
.readiness > div {min-width:0;}
.readiness progress {height:3px; margin-top:12px; border-radius:0;}
.readiness .complete progress {accent-color:var(--color-positive);}
.readiness .complete progress::-webkit-progress-value {background:var(--color-positive);}
.readiness .complete dd {color:var(--color-positive);}
.production select {color:var(--color-text); background:var(--color-canvas); border:1px solid var(--color-border); min-height:36px; padding:8px 10px; border-radius:4px;}
.scene-readiness button {border-radius:0; padding-inline:8px; margin-inline:-8px; width:calc(100% + 16px);}
.scene-readiness button:hover {background:var(--color-surface-muted);}
.scene-number {font-family:ui-monospace,monospace;}
.scene-readiness button > svg {color:var(--color-text-muted);}
.individual summary::marker {color:var(--color-accent);}
</style>
