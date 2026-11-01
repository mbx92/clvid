<script setup lang="ts">
import type { GamingLayout, SourceRect } from '~/types/api'
import { cornerRegion, editRegion, moveRegion, resizeRegion, type RegionName, type ResizeCorner } from '~/utils/gaming'
const props = defineProps<{ modelValue: GamingLayout; video: HTMLVideoElement | null }>()
const emit = defineEmits<{ 'update:modelValue': [value: GamingLayout] }>()
const active = ref<RegionName>('facecam')
const tool = ref('area')
const source = ref<HTMLCanvasElement | null>(null)
const surface = ref<HTMLDivElement | null>(null)
const sourceAspect = ref(16 / 9)
const ready = ref(false)
const activeLabel = computed(() => active.value === 'facecam' ? 'Facecam' : 'Gameplay')
const rectangle = computed(() => props.modelValue[active.value])
const coordinates: { key: keyof SourceRect; label: string }[] = [{ key: 'x', label: 'Kiri' }, { key: 'y', label: 'Atas' }, { key: 'width', label: 'Lebar' }, { key: 'height', label: 'Tinggi' }]
const corners: { key: ResizeCorner; label: string }[] = [{ key: 'nw', label: 'kiri atas' }, { key: 'ne', label: 'kanan atas' }, { key: 'sw', label: 'kiri bawah' }, { key: 'se', label: 'kanan bawah' }]
const fits = [{ value: 'fill', label: 'Isi panel (crop)' }, { value: 'fit', label: 'Tampilkan seluruh area' }]
let drag: { pointer: number; kind: 'move' | ResizeCorner; x: number; y: number; region: SourceRect; name: RegionName } | null = null
const draw = () => {
  const video = props.video; const canvas = source.value
  if (!video || !canvas || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return
  const width = Math.min(1280, video.videoWidth); const height = Math.round(width * video.videoHeight / video.videoWidth)
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height }
  sourceAspect.value = video.videoWidth / video.videoHeight
  canvas.getContext('2d')?.drawImage(video, 0, 0, width, height)
  ready.value = true
}
const update = (patch: Partial<GamingLayout>) => emit('update:modelValue', { ...props.modelValue, ...patch })
const setRegion = (region: SourceRect, name: RegionName = active.value) => update({ [name]: region })
const rectStyle = (name: RegionName) => {
  const r = props.modelValue[name]
  return { left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.width * 100}%`, height: `${r.height * 100}%` }
}
const begin = (event: PointerEvent, kind: 'move' | ResizeCorner) => {
  if (event.button !== 0 || !ready.value || !surface.value) return
  event.preventDefault()
  props.video?.pause()
  const bounds = surface.value.getBoundingClientRect()
  drag = { pointer: event.pointerId, kind, x: (event.clientX - bounds.left) / bounds.width, y: (event.clientY - bounds.top) / bounds.height, region: { ...rectangle.value }, name: active.value }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}
const pointerMove = (event: PointerEvent) => {
  if (!drag || drag.pointer !== event.pointerId || !surface.value) return
  const bounds = surface.value.getBoundingClientRect()
  const dx = (event.clientX - bounds.left) / bounds.width - drag.x
  const dy = (event.clientY - bounds.top) / bounds.height - drag.y
  setRegion(drag.kind === 'move' ? moveRegion(drag.region, dx, dy) : resizeRegion(drag.region, drag.kind, dx, dy), drag.name)
}
const finish = (event: PointerEvent) => { if (drag?.pointer === event.pointerId) drag = null }
const adjustKeys = (event: KeyboardEvent, corner?: ResizeCorner) => {
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault(); props.video?.pause()
  const step = event.shiftKey ? .001 : .01
  const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0
  const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0
  setRegion(corner ? resizeRegion(rectangle.value, corner, dx, dy) : moveRegion(rectangle.value, dx, dy))
}
const numeric = (key: keyof SourceRect, event: Event) => {
  const input = event.target as HTMLInputElement
  const value = input.valueAsNumber
  if (Number.isFinite(value)) setRegion(editRegion(rectangle.value, key, value / 100))
  input.value = (rectangle.value[key] * 100).toFixed(1)
}
watch(() => props.video, () => { ready.value = false; void nextTick(draw) })
onMounted(draw)
onBeforeUnmount(() => { drag = null })
defineExpose({ draw })
</script>
<template>
  <div class="gaming-settings">
    <div class="tool-tabs" role="group" aria-label="Alat gaming"><button :aria-pressed="tool === 'area'" @click="tool = 'area'">Area sumber</button><button :aria-pressed="tool === 'layout'" @click="tool = 'layout'">Susunan panel</button></div>
    <div v-show="tool === 'area'" class="gaming-area-tools">
    <div class="gaming-regions" role="group" aria-label="Area sumber yang disunting">
      <button class="button secondary small-button" :class="{ selected: active === 'facecam' }" :aria-pressed="active === 'facecam'" @click="active = 'facecam'">Area facecam</button>
      <button class="button secondary small-button" :class="{ selected: active === 'gameplay' }" :aria-pressed="active === 'gameplay'" @click="active = 'gameplay'">Area gameplay</button>
    </div>
    <div ref="surface" class="source-region-editor" :style="{ aspectRatio: String(sourceAspect), '--source-aspect': sourceAspect }" @pointermove="pointerMove" @pointerup="finish" @pointercancel="finish">
      <canvas ref="source" data-testid="gaming-source" role="img" aria-label="Video sumber utuh untuk memilih area facecam dan gameplay" />
      <span v-if="!ready" class="gaming-loading">Memuat frame sumber…</span>
      <div v-for="name in (['facecam', 'gameplay'] as const)" :key="name" class="source-region-outline" :class="[name, { active: active === name }]" :style="rectStyle(name)" :tabindex="active === name ? 0 : -1" role="group" :aria-label="`Geser area ${name}; tombol panah menggeser 1 persen, Shift untuk 0,1 persen`" @pointerdown="active === name && begin($event, 'move')" @keydown.stop="active === name && adjustKeys($event)">
        <span class="region-tag">{{ name === 'facecam' ? 'Facecam' : 'Gameplay' }}</span>
        <template v-if="active === name"><button v-for="corner in corners" :key="corner.key" type="button" class="region-handle" :class="corner.key" :aria-label="`Ubah ukuran area ${name} dari ${corner.label}`" @pointerdown.stop="begin($event, corner.key)" @keydown.stop="adjustKeys($event, corner.key)" /></template>
      </div>
    </div>
    <p class="muted small compact-help">Geser kotak atau tarik sudutnya. Tombol panah: 1%; Shift: 0,1%.</p>
    <div v-if="active === 'facecam'" class="region-presets" role="group" aria-label="Preset posisi facecam">
      <button v-for="corner in corners" :key="corner.key" class="button secondary small-button" @click="setRegion(cornerRegion(corner.key))">{{ corner.label.charAt(0).toUpperCase() + corner.label.slice(1) }}</button>
    </div>
    <button v-else class="button secondary small-button region-reset" @click="setRegion({ x: 0, y: 0, width: 1, height: 1 })">Gunakan seluruh video untuk gameplay</button>
    <div class="region-numbers">
      <label v-for="field in coordinates" :key="field.key">{{ field.label }} (%)<input type="number" :aria-label="`${field.label} area ${activeLabel} (%)`" :value="(rectangle[field.key] * 100).toFixed(1)" :min="field.key === 'width' || field.key === 'height' ? 2 : 0" max="100" step="0.1" inputmode="decimal" @change="numeric(field.key, $event)" /></label>
    </div>
    </div><div v-show="tool === 'layout'" class="gaming-layout-tools">
    <label>Tinggi panel facecam <span class="muted">{{ Math.round(modelValue.facecam_height * 100) }}%</span><input type="range" aria-label="Tinggi panel facecam" min="0.15" max="0.45" step="0.01" :value="modelValue.facecam_height" @input="update({ facecam_height: Number(($event.target as HTMLInputElement).value) })" /></label>
    <label>Isi panel facecam<AppSelect :model-value="modelValue.facecam_fit" label="Isi panel facecam" :options="fits" @update:model-value="update({ facecam_fit: $event })" /></label>
    <label>Isi panel gameplay<AppSelect :model-value="modelValue.gameplay_fit" label="Isi panel gameplay" :options="fits" @update:model-value="update({ gameplay_fit: $event })" /></label>
    <p class="muted small">Tampilkan seluruh area menjaga HUD gameplay tetap terlihat, dengan ruang kosong bila rasio berbeda. Isi panel memotong tepi area.</p>
    <p class="notice">Jika facecam sudah menyatu dalam video, area gameplay masih dapat memuat facecam asli. Piksel gameplay yang tertutup facecam tidak dapat dipulihkan.</p>
    </div>
  </div>
</template>
