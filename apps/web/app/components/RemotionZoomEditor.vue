<script setup lang="ts">
import type { RemotionZoom } from '~/types/api'
const props = defineProps<{ modelValue: RemotionZoom; durationMs: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: RemotionZoom] }>()
function update(key: keyof RemotionZoom, event: Event, milliseconds = false) {
  const value = Number((event.target as HTMLInputElement).value)
  if (Number.isFinite(value)) emit('update:modelValue', { ...props.modelValue, [key]: milliseconds ? Math.round(value * 1000) : value })
}
</script>
<template>
  <div class="zoom-editor">
    <div class="effect-fields"><label>Mulai (detik)<input type="number" aria-label="Mulai zoom (detik)" min="0" :max="durationMs / 1000" step="0.01" :value="modelValue.start_ms / 1000" @change="update('start_ms', $event, true)" /></label><label>Akhir (detik)<input type="number" aria-label="Akhir zoom (detik)" min="0" :max="durationMs / 1000" step="0.01" :value="modelValue.end_ms / 1000" @change="update('end_ms', $event, true)" /></label></div>
    <label>Pembesaran {{ modelValue.scale.toFixed(2) }}×<input type="range" aria-label="Pembesaran zoom" min="1" max="2" step="0.05" :value="modelValue.scale" @input="update('scale', $event)" /></label>
    <label>Pusat horizontal {{ Math.round(modelValue.x * 100) }}%<input type="range" aria-label="Pusat horizontal zoom" min="0" max="1" step="0.01" :value="modelValue.x" @input="update('x', $event)" /></label>
    <label>Pusat vertikal {{ Math.round(modelValue.y * 100) }}%<input type="range" aria-label="Pusat vertikal zoom" min="0" max="1" step="0.01" :value="modelValue.y" @input="update('y', $event)" /></label>
  </div>
</template>
<style scoped>
.zoom-editor { display: grid; gap: 12px; }
.effect-fields { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
label { display: grid; gap: 5px; font-size: 12px; }
input { width: 100%; min-width: 0; }
</style>
