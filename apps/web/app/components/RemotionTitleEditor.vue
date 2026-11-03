<script setup lang="ts">
import type { RemotionTitle } from '~/types/api'
const props = defineProps<{ modelValue: RemotionTitle; kind: 'intro' | 'outro' }>()
const emit = defineEmits<{ 'update:modelValue': [value: RemotionTitle] }>()
function update(values: Partial<RemotionTitle>) { emit('update:modelValue', { ...props.modelValue, ...values }) }
</script>
<template>
  <div class="title-effect-editor">
    <label class="checkbox-label"><input type="checkbox" :aria-label="`Aktifkan ${kind}`" :checked="modelValue.enabled" @change="update({ enabled: ($event.target as HTMLInputElement).checked })" />{{ kind === 'intro' ? 'Judul pembuka' : 'Judul penutup' }}</label>
    <template v-if="modelValue.enabled">
      <label>Teks {{ kind }}<input type="text" :aria-label="`Teks ${kind}`" maxlength="80" :value="modelValue.text" :placeholder="kind === 'intro' ? 'Momen yang tidak disangka' : 'Ikuti untuk momen berikutnya'" @input="update({ text: ($event.target as HTMLInputElement).value })" /></label>
      <label>Durasi (detik)<input type="number" :aria-label="`Durasi ${kind} (detik)`" min="0.3" max="5" step="0.1" :value="modelValue.duration_ms / 1000" @change="update({ duration_ms: Math.round(Number(($event.target as HTMLInputElement).value) * 1000) })" /></label>
    </template>
  </div>
</template>
<style scoped>
.title-effect-editor { display: grid; gap: 12px; }
label:not(.checkbox-label) { display: grid; gap: 5px; font-size: 12px; }
input:not([type=checkbox]) { width: 100%; min-width: 0; }
</style>
