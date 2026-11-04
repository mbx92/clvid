<script setup lang="ts">
import type { SubtitleStyle } from '~/types/api'
import { applySubtitlePreset, podcastSubtitlePreset, subtitleDefaults, subtitlePresets } from '~/utils/subtitle-style'
const props = defineProps<{ modelValue: SubtitleStyle; effectiveSize: number; oversizedCues: number; missingTiming: number; timingError: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: SubtitleStyle]; repair:[] }>()
const section = ref('presets')
const remotion = computed(() => style.value.renderer === 'remotion')
const presetsOpen = ref(false)
const style = computed(() => ({ ...subtitleDefaults, ...props.modelValue }))
const podcast = computed(() => style.value.renderer === 'remotion' && style.value.remotion_template === 'podcast')
const templateMotion = computed(() => style.value.renderer === 'remotion' && ['gaming', 'cinematic'].includes(style.value.remotion_template))
function update(values: Partial<SubtitleStyle>) { emit('update:modelValue', { ...style.value, ...values }) }
function selectTemplate(template: NonNullable<SubtitleStyle['remotion_template']>) {
  update(template === 'podcast' ? podcastSubtitlePreset.style : { remotion_template: template })
}
function number(event: Event) { return Number((event.target as HTMLInputElement).value) }
function checked(event: Event) { return (event.target as HTMLInputElement).checked }
function value(event: Event) { return (event.target as HTMLInputElement).value }
</script>
<template>
  <div class="subtitle-settings">
    <label class="checkbox-label"><input type="checkbox" :checked="style.enabled" @change="update({ enabled: checked($event) })" />Tampilkan subtitle pada video</label>
    <div class="engine-fields"><label>Mode subtitle<AppSelect :model-value="style.renderer" label="Renderer subtitle" :options="[{ value: 'ffmpeg', label: 'Standar' }, { value: 'remotion', label: 'Remotion' }]" @update:model-value="update({ renderer: $event })" /></label>
    <template v-if="remotion">
      <label>Template animasi<AppSelect :model-value="style.remotion_template" label="Template Remotion" :options="[{ value: 'minimal', label: 'Minimal' }, { value: 'gaming', label: 'Gaming Punch' }, { value: 'cinematic', label: 'Sinematik' }, { value: 'podcast', label: 'Podcast kuning' }]" @update:model-value="selectTemplate($event)" /></label>
    </template></div>
      <p v-if="remotion" class="template-description">{{ style.remotion_template === 'gaming' ? 'Teks masuk dengan hentakan dan pantulan singkat.' : style.remotion_template === 'cinematic' ? 'Teks muncul dengan fade dan gerakan lembut.' : style.remotion_template === 'podcast' ? 'Kotak putih mengikuti kata yang sedang diucapkan.' : 'Gerakan sederhana, dapat diatur pada Warna & efek.' }}</p>
    <label v-if="!podcast">Teks muncul<AppSelect :model-value="style.display_mode || 'sentence'" label="Cara tampil subtitle" :options="[{ value: 'sentence', label: 'Kalimat lengkap' }, { value: 'words', label: 'Kata per kata mengikuti suara' }]" @update:model-value="update({ display_mode: $event as 'sentence' | 'words' })" /></label>
    <div class="tool-tabs" role="group" aria-label="Alat gaya subtitle"><button :aria-pressed="section === 'presets'" @click="section = 'presets'">Preset</button><button :aria-pressed="section === 'custom'" @click="section = 'custom'">Warna & efek</button></div>
    <div v-if="section === 'presets'" class="preset-section">
      <button v-if="remotion" type="button" class="preset-disclosure" :aria-expanded="presetsOpen" aria-controls="subtitle-color-presets" @click="presetsOpen = !presetsOpen"><span><strong>Preset warna &amp; tipografi</strong><small>Ubah tampilan teks pada template ini.</small></span><AppIcon :name="presetsOpen ? 'ChevronUp' : 'ChevronDown'" :size="16" /></button>
      <div v-if="!remotion || presetsOpen" id="subtitle-color-presets" class="subtitle-presets">
      <button v-if="!remotion" type="button" class="podcast-preset" aria-label="Preset Podcast kuning" @click="update(podcastSubtitlePreset.style)"><strong><span>PODCAST</span> KUNING</strong><small>Highlight mengikuti suara</small></button>
      <button v-for="preset in subtitlePresets" :key="preset.name" type="button" :aria-label="`Preset ${preset.name}`" :style="{ color: preset.color, background: preset.background }" @click="update(applySubtitlePreset(style, preset.style)); presetsOpen = false"><strong :style="{ fontWeight: preset.style.bold ? 700 : 400 }">{{ preset.name }}</strong><small>{{ templateMotion ? 'Warna & tipografi' : ({ none: 'Tanpa gerak', fade: 'Fade halus', pop: 'Pop masuk', rise: 'Geser halus' })[preset.style.animation] }}</small></button>
    </div>
    </div>
    <div v-else class="subtitle-custom">
      <label>Warna teks<input type="color" aria-label="Warna teks subtitle" :value="style.text_color" @input="update({ text_color: value($event) })" /></label>
      <label>Warna outline<input type="color" aria-label="Warna outline subtitle" :value="style.outline_color" :disabled="style.background" @input="update({ outline_color: value($event) })" /></label>
      <label>Warna latar<input type="color" aria-label="Warna latar subtitle" :value="style.background_color" @input="update({ background_color: value($event) })" /></label>
      <label>Outline {{ style.outline_width }}<input aria-label="Ketebalan outline" type="range" min="0" max="8" step="0.5" :disabled="style.background" :value="style.outline_width" @input="update({ outline_width: number($event) })" /></label>
      <label>Bayangan {{ style.shadow }}<input aria-label="Bayangan subtitle" type="range" min="0" max="8" step="1" :value="style.shadow" @input="update({ shadow: number($event) })" /></label>
      <div class="subtitle-toggles"><label><input type="checkbox" :checked="style.bold" @change="update({ bold: checked($event) })" />Tebal</label><label><input type="checkbox" :checked="style.italic" @change="update({ italic: checked($event) })" />Miring</label><label><input type="checkbox" :checked="style.uppercase" @change="update({ uppercase: checked($event) })" />KAPITAL</label></div>
      <template v-if="!templateMotion">
        <label class="full-width">Animasi<AppSelect :model-value="style.animation" label="Animasi subtitle" :options="[{ value: 'none', label: 'Tanpa animasi' }, { value: 'fade', label: 'Fade sinematik' }, { value: 'pop', label: 'Pop masuk' }, { value: 'rise', label: 'Geser halus' }]" @update:model-value="update({ animation: $event })" /></label>
        <label>Durasi {{ style.animation_ms }} ms<input aria-label="Durasi animasi subtitle" type="range" min="100" max="500" step="20" :disabled="style.animation === 'none'" :value="style.animation_ms" @input="update({ animation_ms: number($event) })" /></label>
      </template>
      <p v-else class="muted compact-help" style="grid-column: 1 / -1">Gerakan dan durasi animasi mengikuti template {{ style.remotion_template === 'gaming' ? 'Gaming Punch' : 'Sinematik' }}. Pilih Minimal untuk mengaturnya sendiri.</p>
    </div>
    <section class="size-placement"><h3>Ukuran &amp; posisi</h3>
    <label><span class="range-heading">Ukuran teks <span class="muted">{{ style.font_size }} px</span></span><input aria-label="Ukuran teks subtitle" type="range" min="24" max="100" step="2" :value="style.font_size" @input="update({ font_size: number($event), auto_fit: false })" /></label>
    <label class="checkbox-label"><input type="checkbox" :checked="style.auto_fit" @change="update({ auto_fit: checked($event) })" />Kecilkan otomatis agar muat dua baris</label>
    <p v-if="podcast && style.enabled && (missingTiming || timingError)" class="error-text compact-help" role="status">{{ timingError || `${missingTiming} subtitle belum cocok dengan timestamp kata. Highlight belum tersedia. Buat ulang subtitle dari suara, cocokkan teks dengan transkrip, atau pilih template lain.` }}</p>
    <p v-else-if="style.display_mode === 'words' && (missingTiming || timingError)" class="error-text compact-help" role="status">{{ timingError || `${missingTiming} cue belum cocok dengan timestamp kata. Gunakan teks transkrip asli atau pilih Kalimat lengkap.` }}</p>
    <div v-else-if="oversizedCues" class="compact-help" role="status"><p>{{ oversizedCues }} subtitle terlalu panjang pada ukuran ini.</p><button class="button secondary small-button" @click="emit('repair')">Sesuaikan subtitle</button></div>
    <p v-else class="muted compact-help">{{ style.auto_fit ? `Ukuran di preview: ${effectiveSize} px.` : 'Ukuran setara video 1080 px.' }}</p>
    <div class="subtitle-placement"><label>Posisi<AppSelect :model-value="style.position" label="Posisi subtitle" :options="[{ value: 'bottom', label: 'Bawah' }, { value: 'top', label: 'Atas' }]" @update:model-value="update({ position: $event as 'top' | 'bottom' })" /></label><label>Jarak tepi {{ Math.round(style.safe_margin * 100) }}%<input aria-label="Jarak tepi subtitle" type="range" min="0.05" max="0.35" step="0.01" :value="style.safe_margin" @input="update({ safe_margin: number($event) })" /></label></div>
    </section>
    <label class="checkbox-label background-toggle"><input type="checkbox" :checked="style.background" @change="update({ background: checked($event) })" />Latar di belakang teks</label>
  </div>
</template>
<style scoped>
.subtitle-settings { gap:16px; padding:4px 0 18px; }
.subtitle-settings label { display:flex; flex-direction:column; gap:7px; font-size:12px; font-weight:500; min-width:0; }
.subtitle-settings .checkbox-label { flex-direction:row; align-items:center; font-weight:400; line-height:1.5; }
.subtitle-settings > .checkbox-label:first-child { padding-bottom:14px; border-bottom:1px solid #e4e8e1; font-weight:600; }
.engine-fields { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.engine-fields > label:only-child { grid-column:1 / -1; }
.template-description { font-size:12px; line-height:1.6; color:#657169; margin:-6px 0 0; }
.range-heading { display:flex; justify-content:space-between; align-items:center; }
.subtitle-settings .tool-tabs { background:transparent; padding:0; border-bottom:1px solid #dfe5dc; border-radius:0; gap:18px; }
.subtitle-settings .tool-tabs button { flex:none; padding:9px 0; border-radius:0; border-bottom:2px solid transparent; font-size:12px; }
.subtitle-settings .tool-tabs button[aria-pressed=true] { box-shadow:none; background:transparent; border-bottom-color:#355d78; font-weight:600; }
.preset-disclosure { display:flex; width:100%; align-items:center; justify-content:space-between; gap:12px; text-align:left; padding:12px; border:1px solid #dce3d7; border-radius:6px; background:#f8faf5; color:inherit; cursor:pointer; }
.preset-disclosure strong { display:block; font-size:12px; font-weight:600; }
.preset-disclosure small { display:block; font-size:11px; color:#6b766e; margin-top:4px; }
.subtitle-settings .subtitle-presets { grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
.preset-disclosure + .subtitle-presets { margin-top:10px; }
.subtitle-settings .subtitle-presets button { min-height:70px; padding:12px 8px; text-align:left; border-radius:5px; }
.subtitle-settings .subtitle-presets strong { font-size:14px; line-height:1.4; }
.subtitle-settings .subtitle-presets small { display:block; font-size:11px; margin-top:4px; }
.subtitle-settings .subtitle-custom { grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px 12px; }
.subtitle-settings .subtitle-custom label, .subtitle-settings .subtitle-placement label { font-size:12px; }
.subtitle-settings .subtitle-custom input[type=color] { height:36px; padding:3px; }
.subtitle-settings .subtitle-toggles { justify-content:flex-start; flex-wrap:wrap; gap:16px; padding:10px 0; }
.subtitle-settings .subtitle-toggles label { flex-direction:row; align-items:center; }
.full-width { grid-column:1 / -1; }
.size-placement { display:flex; flex-direction:column; gap:14px; padding-top:16px; border-top:1px solid #e4e8e1; }
.size-placement h3 { margin:0; font-size:12px; font-weight:600; }
.subtitle-settings .compact-help { font-size:11px; line-height:1.6; margin:0; }
.subtitle-settings .subtitle-placement { align-items:start; }
.background-toggle { margin-top:0; }
.subtitle-settings :deep(.select-button) { min-height:40px; font-size:12px; }
.subtitle-settings input[type=range] { width:100%; min-height:24px; }
.subtitle-settings input[type=checkbox] { width:15px; height:15px; }
.subtitle-settings button:focus-visible { outline:2px solid #355d78; outline-offset:3px; }
.podcast-preset { background: #29282d; color: #ffe600; }
.podcast-preset strong { font-weight: 900; font-style: italic; -webkit-text-stroke: 1.5px #111; paint-order: stroke fill; }
.podcast-preset strong span { background: #fff; border-radius: 2px; padding: 1px 3px; }
.podcast-preset small { color: #f2f2f2; }
</style>
