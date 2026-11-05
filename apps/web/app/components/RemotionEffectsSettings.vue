<script setup lang="ts">
import type { RemotionEffects, RemotionZoom, SubtitleStyle } from '~/types/api'
import { effectsError, remotionEffects, zoomAt } from '~/utils/remotion-effects'
import { timecode } from '~/utils/format'
const props = defineProps<{ modelValue: SubtitleStyle; durationMs: number; timeMs: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: SubtitleStyle]; seek: [timeMs: number]; timeline: [] }>()
const effects = computed(() => remotionEffects(props.modelValue.remotion_effects))
const selectedZoom = ref(0)
const error = computed(() => effectsError(effects.value, props.durationMs))
const options = [{ value: 'none', label: 'Tanpa transisi' }, { value: 'fade', label: 'Fade' }, { value: 'slide', label: 'Geser' }]
function update(values: Partial<RemotionEffects>) { emit('update:modelValue', { ...props.modelValue, renderer: 'remotion', remotion_effects: { ...effects.value, ...values } }) }
function setZoom(zoom: RemotionZoom) { update({ zooms: effects.value.zooms.map((value, index) => index === selectedZoom.value ? zoom : value) }) }
function addZoom() {
  if (effects.value.zooms.length >= 20) return
  selectedZoom.value = effects.value.zooms.length
  update({ zooms: [...effects.value.zooms, zoomAt(props.timeMs, props.durationMs)] })
}
function removeZoom() {
  update({ zooms: effects.value.zooms.filter((_value, index) => index !== selectedZoom.value) })
  selectedZoom.value = Math.max(0, selectedZoom.value - 1)
}
</script>
<template>
  <div class="remotion-effects-settings">
    <template v-if="modelValue.renderer !== 'remotion'">
      <p class="muted small">Tambahkan transisi, judul pembuka dan penutup, serta zoom pada momen pilihan menggunakan Remotion.</p>
      <button class="button secondary" @click="update({})">Aktifkan Remotion untuk efek video</button>
    </template>
    <template v-else>
      <p class="muted small">Efek mengikuti waktu klip dan ikut masuk ke MP4. Subtitle dapat dimatikan secara terpisah.</p>
      <section class="effect-card"><h3>Transisi video</h3>
        <label>Awal klip<AppSelect :model-value="effects.transition_in" label="Transisi awal" :options="options" @update:model-value="update({ transition_in: $event })" /></label>
        <label>Akhir klip<AppSelect :model-value="effects.transition_out" label="Transisi akhir" :options="options" @update:model-value="update({ transition_out: $event })" /></label>
        <label>Durasi {{ effects.transition_ms }} ms<input type="range" aria-label="Durasi transisi" min="100" max="1000" step="50" :value="effects.transition_ms" @input="update({ transition_ms: Number(($event.target as HTMLInputElement).value) })" /></label>
      </section>
      <section class="effect-card"><h3>Intro & outro</h3><p class="muted small">Judul tampil di awal atau akhir klip yang ada; durasi video tidak bertambah. Pada klip pendek, durasinya dibatasi dan outro didahulukan jika judul bertumpuk.</p>
        <RemotionTitleEditor kind="intro" :model-value="effects.intro" @update:model-value="update({ intro: $event })" />
        <RemotionTitleEditor kind="outro" :model-value="effects.outro" @update:model-value="update({ outro: $event })" />
      </section>
      <section class="effect-card"><h3>Zoom momen</h3><p class="muted small">Zoom mendekat lalu kembali halus. Jika rentang bertumpuk, zoom paling kuat yang digunakan.</p>
        <button class="button secondary small-button" :disabled="effects.zooms.length >= 20" @click="addZoom">Tambah zoom di posisi sekarang</button>
        <div v-if="effects.zooms.length" class="zoom-choices" role="group" aria-label="Pilih efek zoom"><button v-for="(zoom, index) in effects.zooms" :key="index" class="button secondary small-button" :aria-pressed="selectedZoom === index" @click="selectedZoom = index; emit('seek', zoom.start_ms)">{{ index + 1 }} · {{ timecode(zoom.start_ms, true) }}</button></div>
        <RemotionZoomEditor v-if="effects.zooms[selectedZoom]" :model-value="effects.zooms[selectedZoom]!" :duration-ms="durationMs" @update:model-value="setZoom" />
        <button v-if="effects.zooms[selectedZoom]" class="text-button" @click="removeZoom">Hapus zoom terpilih</button>
      </section>
      <InlineError :message="error" />
      <button class="button secondary" @click="emit('timeline')">Atur waktu di timeline</button>
    </template>
  </div>
</template>
<style scoped>
.remotion-effects-settings, .effect-card { display: grid; gap: 14px; }
.effect-card { padding: 14px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface-muted); }
.effect-card h3 { font-size: 13px; margin: 0; }
.effect-card p { margin: 0; }
.effect-card > label { display: grid; gap: 5px; font-size: 12px; }
.zoom-choices { display: flex; gap: 6px; flex-wrap: wrap; }
.zoom-choices [aria-pressed=true] { border-color: var(--color-accent); background: var(--color-accent-soft); }
</style>
