<script setup lang="ts">
import type { SubtitleStyle } from '~/types/api'
import { subtitleDefaults, subtitlePresets } from '~/utils/subtitle-style'
const props = defineProps<{ modelValue: SubtitleStyle; effectiveSize: number; oversizedCues: number; missingTiming: number; timingError: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: SubtitleStyle] }>()
const section = ref('presets')
const style = computed(() => ({ ...subtitleDefaults, ...props.modelValue }))
function update(values: Partial<SubtitleStyle>) { emit('update:modelValue', { ...style.value, ...values }) }
function number(event: Event) { return Number((event.target as HTMLInputElement).value) }
function checked(event: Event) { return (event.target as HTMLInputElement).checked }
function value(event: Event) { return (event.target as HTMLInputElement).value }
</script>
<template>
  <div class="subtitle-settings">
    <label class="checkbox-label"><input type="checkbox" :checked="style.enabled" @change="update({ enabled: checked($event) })" />Tampilkan subtitle pada video</label>
    <label>Teks muncul<AppSelect :model-value="style.display_mode || 'sentence'" label="Cara tampil subtitle" :options="[{ value: 'sentence', label: 'Kalimat lengkap' }, { value: 'words', label: 'Kata per kata mengikuti suara' }]" @update:model-value="update({ display_mode: $event as 'sentence' | 'words' })" /></label>
    <div class="tool-tabs" role="group" aria-label="Alat gaya subtitle"><button :aria-pressed="section === 'presets'" @click="section = 'presets'">Preset</button><button :aria-pressed="section === 'custom'" @click="section = 'custom'">Warna & efek</button></div>
    <div v-if="section === 'presets'" class="subtitle-presets">
      <button v-for="preset in subtitlePresets" :key="preset.name" type="button" :aria-label="`Preset ${preset.name}`" :style="{ color: preset.color, background: preset.background }" @click="update({ ...preset.style, enabled: true })"><strong :style="{ fontWeight: preset.style.bold ? 700 : 400 }">{{ preset.name }}</strong><small>Aa • Subtitle</small></button>
    </div>
    <div v-else class="subtitle-custom">
      <label>Warna teks<input type="color" aria-label="Warna teks subtitle" :value="style.text_color" @input="update({ text_color: value($event) })" /></label>
      <label>Warna outline<input type="color" aria-label="Warna outline subtitle" :value="style.outline_color" :disabled="style.background" @input="update({ outline_color: value($event) })" /></label>
      <label>Warna latar<input type="color" aria-label="Warna latar subtitle" :value="style.background_color" @input="update({ background_color: value($event) })" /></label>
      <label>Outline {{ style.outline_width }}<input aria-label="Ketebalan outline" type="range" min="0" max="8" step="0.5" :disabled="style.background" :value="style.outline_width" @input="update({ outline_width: number($event) })" /></label>
      <label>Bayangan {{ style.shadow }}<input aria-label="Bayangan subtitle" type="range" min="0" max="8" step="1" :value="style.shadow" @input="update({ shadow: number($event) })" /></label>
      <div class="subtitle-toggles"><label><input type="checkbox" :checked="style.bold" @change="update({ bold: checked($event) })" />Tebal</label><label><input type="checkbox" :checked="style.italic" @change="update({ italic: checked($event) })" />Miring</label><label><input type="checkbox" :checked="style.uppercase" @change="update({ uppercase: checked($event) })" />KAPITAL</label></div>
    </div>
    <label>Ukuran teks <span class="muted">{{ style.font_size }} px</span><input aria-label="Ukuran teks subtitle" type="range" min="24" max="100" step="2" :value="style.font_size" @input="update({ font_size: number($event), auto_fit: false })" /></label>
    <label class="checkbox-label"><input type="checkbox" :checked="style.auto_fit" @change="update({ auto_fit: checked($event) })" />Kecilkan otomatis agar muat dua baris</label>
    <p v-if="style.display_mode === 'words' && (missingTiming || timingError)" class="error-text compact-help" role="status">{{ timingError || `${missingTiming} cue belum cocok dengan timestamp kata. Gunakan teks transkrip asli atau pilih Kalimat lengkap.` }}</p>
    <p v-else-if="oversizedCues" class="error-text compact-help" role="status">{{ oversizedCues }} cue terlalu panjang. Kecilkan ukuran, aktifkan ukuran otomatis, atau pecah teks di tab Subtitle.</p>
    <p v-else class="muted compact-help">{{ style.auto_fit ? `Ukuran cue di preview: ${effectiveSize} px.` : 'Ukuran mengikuti slider; teks membungkus hingga empat baris.' }} Ukuran setara video 1080 px.</p>
    <div class="subtitle-placement"><label>Posisi<AppSelect :model-value="style.position" label="Posisi subtitle" :options="[{ value: 'bottom', label: 'Bawah' }, { value: 'top', label: 'Atas' }]" @update:model-value="update({ position: $event as 'top' | 'bottom' })" /></label><label>Jarak tepi {{ Math.round(style.safe_margin * 100) }}%<input aria-label="Jarak tepi subtitle" type="range" min="0.05" max="0.35" step="0.01" :value="style.safe_margin" @input="update({ safe_margin: number($event) })" /></label></div>
    <label class="checkbox-label"><input type="checkbox" :checked="style.background" @change="update({ background: checked($event) })" />Latar di belakang teks</label>
  </div>
</template>
