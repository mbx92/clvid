<script setup lang="ts">
import type { SubtitleStyle } from '~/types/api'
import { applySubtitlePreset, subtitleDefaults, subtitlePresets } from '~/utils/subtitle-style'
const props = defineProps<{ modelValue: SubtitleStyle; effectiveSize: number; oversizedCues: number; missingTiming: number; timingError: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: SubtitleStyle] }>()
const section = ref('presets')
const style = computed(() => ({ ...subtitleDefaults, ...props.modelValue }))
const templateMotion = computed(() => style.value.renderer === 'remotion' && style.value.remotion_template !== 'minimal')
function update(values: Partial<SubtitleStyle>) { emit('update:modelValue', { ...style.value, ...values }) }
function number(event: Event) { return Number((event.target as HTMLInputElement).value) }
function checked(event: Event) { return (event.target as HTMLInputElement).checked }
function value(event: Event) { return (event.target as HTMLInputElement).value }
</script>
<template>
  <div class="subtitle-settings">
    <label class="checkbox-label"><input type="checkbox" :checked="style.enabled" @change="update({ enabled: checked($event) })" />Tampilkan subtitle pada video</label>
    <label>Renderer<AppSelect :model-value="style.renderer" label="Renderer subtitle" :options="[{ value: 'ffmpeg', label: 'Standar' }, { value: 'remotion', label: 'Remotion' }]" @update:model-value="update({ renderer: $event })" /></label>
    <template v-if="style.renderer === 'remotion'">
      <label>Template animasi<AppSelect :model-value="style.remotion_template" label="Template Remotion" :options="[{ value: 'minimal', label: 'Minimal' }, { value: 'gaming', label: 'Gaming Punch' }, { value: 'cinematic', label: 'Sinematik' }]" @update:model-value="update({ remotion_template: $event })" /></label>
      <p class="muted compact-help">{{ style.remotion_template === 'gaming' ? 'Teks masuk dengan hentakan dan pantulan singkat.' : style.remotion_template === 'cinematic' ? 'Teks muncul dengan fade dan gerakan lembut.' : 'Gunakan pilihan animasi pada Warna & efek.' }} Warna, ukuran, dan posisi tetap dapat diatur. Template yang disimpan digunakan saat ekspor.</p>
    </template>
    <label>Teks muncul<AppSelect :model-value="style.display_mode || 'sentence'" label="Cara tampil subtitle" :options="[{ value: 'sentence', label: 'Kalimat lengkap' }, { value: 'words', label: 'Kata per kata mengikuti suara' }]" @update:model-value="update({ display_mode: $event as 'sentence' | 'words' })" /></label>
    <div class="tool-tabs" role="group" aria-label="Alat gaya subtitle"><button :aria-pressed="section === 'presets'" @click="section = 'presets'">Preset</button><button :aria-pressed="section === 'custom'" @click="section = 'custom'">Warna & efek</button></div>
    <div v-if="section === 'presets'" class="subtitle-presets">
      <button v-for="preset in subtitlePresets" :key="preset.name" type="button" :aria-label="`Preset ${preset.name}`" :style="{ color: preset.color, background: preset.background }" @click="update(applySubtitlePreset(style, preset.style))"><strong :style="{ fontWeight: preset.style.bold ? 700 : 400 }">{{ preset.name }}</strong><small>{{ templateMotion ? 'Warna & tipografi' : ({ none: 'Tanpa gerak', fade: 'Fade halus', pop: 'Pop masuk', rise: 'Geser halus' })[preset.style.animation] }}</small></button>
    </div>
    <div v-else class="subtitle-custom">
      <label>Warna teks<input type="color" aria-label="Warna teks subtitle" :value="style.text_color" @input="update({ text_color: value($event) })" /></label>
      <label>Warna outline<input type="color" aria-label="Warna outline subtitle" :value="style.outline_color" :disabled="style.background" @input="update({ outline_color: value($event) })" /></label>
      <label>Warna latar<input type="color" aria-label="Warna latar subtitle" :value="style.background_color" @input="update({ background_color: value($event) })" /></label>
      <label>Outline {{ style.outline_width }}<input aria-label="Ketebalan outline" type="range" min="0" max="8" step="0.5" :disabled="style.background" :value="style.outline_width" @input="update({ outline_width: number($event) })" /></label>
      <label>Bayangan {{ style.shadow }}<input aria-label="Bayangan subtitle" type="range" min="0" max="8" step="1" :value="style.shadow" @input="update({ shadow: number($event) })" /></label>
      <div class="subtitle-toggles"><label><input type="checkbox" :checked="style.bold" @change="update({ bold: checked($event) })" />Tebal</label><label><input type="checkbox" :checked="style.italic" @change="update({ italic: checked($event) })" />Miring</label><label><input type="checkbox" :checked="style.uppercase" @change="update({ uppercase: checked($event) })" />KAPITAL</label></div>
      <template v-if="!templateMotion">
        <label style="grid-column: span 2">Animasi<AppSelect :model-value="style.animation" label="Animasi subtitle" :options="[{ value: 'none', label: 'Tanpa animasi' }, { value: 'fade', label: 'Fade sinematik' }, { value: 'pop', label: 'Pop masuk' }, { value: 'rise', label: 'Geser halus' }]" @update:model-value="update({ animation: $event })" /></label>
        <label>Durasi {{ style.animation_ms }} ms<input aria-label="Durasi animasi subtitle" type="range" min="100" max="500" step="20" :disabled="style.animation === 'none'" :value="style.animation_ms" @input="update({ animation_ms: number($event) })" /></label>
      </template>
      <p v-else class="muted compact-help" style="grid-column: 1 / -1">Gerakan dan durasi animasi mengikuti template {{ style.remotion_template === 'gaming' ? 'Gaming Punch' : 'Sinematik' }}. Pilih Minimal untuk mengaturnya sendiri.</p>
    </div>
    <label>Ukuran teks <span class="muted">{{ style.font_size }} px</span><input aria-label="Ukuran teks subtitle" type="range" min="24" max="100" step="2" :value="style.font_size" @input="update({ font_size: number($event), auto_fit: false })" /></label>
    <label class="checkbox-label"><input type="checkbox" :checked="style.auto_fit" @change="update({ auto_fit: checked($event) })" />Kecilkan otomatis agar muat dua baris</label>
    <p v-if="style.display_mode === 'words' && (missingTiming || timingError)" class="error-text compact-help" role="status">{{ timingError || `${missingTiming} cue belum cocok dengan timestamp kata. Gunakan teks transkrip asli atau pilih Kalimat lengkap.` }}</p>
    <p v-else-if="oversizedCues" class="error-text compact-help" role="status">{{ oversizedCues }} cue terlalu panjang. Kecilkan ukuran, aktifkan ukuran otomatis, atau pecah teks di tab Subtitle.</p>
    <p v-else class="muted compact-help">{{ style.auto_fit ? `Ukuran cue di preview: ${effectiveSize} px.` : 'Ukuran mengikuti slider; teks membungkus hingga empat baris.' }} Ukuran setara video 1080 px.<span v-if="templateMotion || style.animation !== 'none'"> Putar video untuk melihat animasi; efek ikut masuk ke MP4.</span></p>
    <div class="subtitle-placement"><label>Posisi<AppSelect :model-value="style.position" label="Posisi subtitle" :options="[{ value: 'bottom', label: 'Bawah' }, { value: 'top', label: 'Atas' }]" @update:model-value="update({ position: $event as 'top' | 'bottom' })" /></label><label>Jarak tepi {{ Math.round(style.safe_margin * 100) }}%<input aria-label="Jarak tepi subtitle" type="range" min="0.05" max="0.35" step="0.01" :value="style.safe_margin" @input="update({ safe_margin: number($event) })" /></label></div>
    <label class="checkbox-label"><input type="checkbox" :checked="style.background" @change="update({ background: checked($event) })" />Latar di belakang teks</label>
  </div>
</template>
