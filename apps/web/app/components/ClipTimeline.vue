<script setup lang="ts">
import type { Cue, RemotionEffects, RemotionZoom } from '~/types/api'
import { effectsError, intervalDrag, remotionEffects, zoomAt } from '~/utils/remotion-effects'
import { parseTimecode, timecode } from '~/utils/format'

const props = defineProps<{ cues: Cue[]; effects?: RemotionEffects; remotion: boolean; durationMs: number; startMs: number; endMs: number; sourceDurationMs: number; timeMs: number; maxClipMs: number }>()
const emit = defineEmits<{ 'update:cues': [cues: Cue[]]; 'update:effects': [effects: RemotionEffects]; seek: [time: number]; bounds: [start: number, end: number]; enableRemotion: [] }>()
type Kind = 'video' | 'cue' | 'zoom' | 'intro' | 'outro'
type Edge = 'move' | 'start' | 'end'
const selected = ref<{ kind: Kind; index: number }>({ kind: 'video', index: 0 })
const zoomLevel = ref(1)
const effects = computed(() => remotionEffects(props.effects))
const selectedCue = computed(() => selected.value.kind === 'cue' ? props.cues[selected.value.index] : undefined)
const selectedZoom = computed(() => selected.value.kind === 'zoom' ? effects.value.zooms[selected.value.index] : undefined)
const localTime = computed(() => Math.max(0, Math.min(props.durationMs, props.timeMs)))
const validation = computed(() => effectsError(effects.value, props.durationMs))
const sourceIn = ref('')
const sourceOut = ref('')
const boundError = ref('')
const trimPreview = ref<{ start_ms: number; end_ms: number } | null>(null)
watch(() => [props.startMs, props.endMs], () => { sourceIn.value = timecode(props.startMs, true); sourceOut.value = timecode(props.endMs, true) }, { immediate: true })
const choices = computed(() => [
  { value: 'video:0', label: 'Video' },
  ...props.cues.map((cue, index) => ({ value: `cue:${index}`, label: `Subtitle ${index + 1}: ${cue.text.slice(0, 34)}` })),
  ...(props.remotion ? effects.value.zooms.map((_zoom, index) => ({ value: `zoom:${index}`, label: `Zoom ${index + 1}` })) : []),
  ...(props.remotion && effects.value.intro.enabled ? [{ value: 'intro:0', label: 'Intro' }] : []),
  ...(props.remotion && effects.value.outro.enabled ? [{ value: 'outro:0', label: 'Outro' }] : []),
])
function intervalStyle(value: { start_ms: number; end_ms: number }) {
  return { left: `${value.start_ms / props.durationMs * 100}%`, width: `${Math.max(0, value.end_ms - value.start_ms) / props.durationMs * 100}%` }
}
function select(kind: Kind, index = 0) {
  selected.value = { kind, index }
  const cue = kind === 'cue' ? props.cues[index] : kind === 'zoom' ? effects.value.zooms[index] : null
  if (cue) emit('seek', cue.start_ms)
  if (kind === 'intro') emit('seek', 0)
  if (kind === 'outro') emit('seek', Math.max(0, props.durationMs - effects.value.outro.duration_ms))
}
function choose(value: string) { const [kind, index] = value.split(':'); select(kind as Kind, Number(index)) }
function updateEffects(value: Partial<RemotionEffects>) { emit('update:effects', { ...effects.value, ...value }) }
function setCue(cue: Cue, index = selected.value.index) { emit('update:cues', props.cues.map((value, i) => i === index ? cue : value)) }
function setZoom(zoom: RemotionZoom, index = selected.value.index) { updateEffects({ zooms: effects.value.zooms.map((value, i) => i === index ? zoom : value) }) }
function setCueTime(edge: 'start_ms' | 'end_ms', event: Event) {
  if (!selectedCue.value) return
  const ms = Math.round(Number((event.target as HTMLInputElement).value) * 1000)
  if (Number.isFinite(ms)) setCue({ ...selectedCue.value, [edge]: ms })
}
function addCue() {
  const start = Math.max(0, Math.min(props.durationMs - 100, localTime.value))
  emit('update:cues', [...props.cues, { start_ms: start, end_ms: Math.min(props.durationMs, start + 2000), text: 'Subtitle baru' }])
  selected.value = { kind: 'cue', index: props.cues.length }
}
function addZoom() {
  if (!props.remotion || effects.value.zooms.length >= 20) return
  selected.value = { kind: 'zoom', index: effects.value.zooms.length }
  updateEffects({ zooms: [...effects.value.zooms, zoomAt(localTime.value, props.durationMs)] })
}
function removeSelected() {
  if (selected.value.kind === 'cue') emit('update:cues', props.cues.filter((_value, i) => i !== selected.value.index))
  if (selected.value.kind === 'zoom') updateEffects({ zooms: effects.value.zooms.filter((_value, i) => i !== selected.value.index) })
  selected.value = { kind: 'video', index: 0 }
}
function applyBounds() {
  const start = parseTimecode(sourceIn.value), end = parseTimecode(sourceOut.value)
  if (start === null || end === null || start < 0 || end > props.sourceDurationMs || end - start < 5000 || end - start > props.maxClipMs) {
    boundError.value = 'Gunakan batas dalam video sumber dengan durasi klip minimal 5 detik.'; return
  }
  boundError.value = ''; emit('bounds', start, end)
}
function seekRuler(event: MouseEvent) {
  const box = (event.currentTarget as HTMLElement).getBoundingClientRect()
  emit('seek', Math.round(Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)) * props.durationMs))
}
let drag: { kind: Kind; index: number; edge: Edge; x: number; width: number; duration: number; value: { start_ms: number; end_ms: number }; pointer: number } | null = null
function beginDrag(event: PointerEvent, kind: Kind, index: number, edge: Edge = 'move') {
  if (event.button !== 0) return
  const lane = (event.currentTarget as HTMLElement).closest('.track-lane')
  if (!lane) return
  event.preventDefault(); event.stopPropagation(); select(kind, index)
  const value = kind === 'cue' ? props.cues[index] : kind === 'zoom' ? effects.value.zooms[index] : kind === 'intro' ? { start_ms: 0, end_ms: Math.min(props.durationMs, effects.value.intro.duration_ms) } : kind === 'outro' ? { start_ms: Math.max(0, props.durationMs - effects.value.outro.duration_ms), end_ms: props.durationMs } : { start_ms: 0, end_ms: props.durationMs }
  if (!value) return
  drag = { kind, index, edge, x: event.clientX, width: lane.getBoundingClientRect().width, duration: props.durationMs, value: { ...value }, pointer: event.pointerId }
  document.addEventListener('pointermove', moveDrag)
  document.addEventListener('pointerup', endDrag)
  document.addEventListener('pointercancel', cancelDrag)
}
function moveDrag(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointer) return
  const delta = (event.clientX - drag.x) / drag.width * drag.duration
  const { kind, index, edge, value } = drag
  if (kind === 'video') {
    const minimum = Math.min(5000, drag.duration)
    trimPreview.value = edge === 'start' ? { start_ms: Math.max(-props.startMs, Math.min(drag.duration - minimum, Math.round(delta / 10) * 10)), end_ms: drag.duration } : { start_ms: 0, end_ms: Math.min(props.sourceDurationMs - props.startMs, Math.max(minimum, drag.duration + Math.round(delta / 10) * 10)) }
  } else if (kind === 'intro' || kind === 'outro') {
    const duration = Math.max(300, Math.min(5000, props.durationMs, value.end_ms - value.start_ms + (kind === 'intro' ? delta : -delta)))
    updateEffects({ [kind]: { ...effects.value[kind], duration_ms: Math.round(duration / 10) * 10 } })
  } else {
    const moved = intervalDrag(value, delta, drag.duration, edge)
    if (kind === 'cue' && props.cues[index]) setCue({ ...props.cues[index]!, ...moved }, index)
    if (kind === 'zoom' && effects.value.zooms[index]) setZoom({ ...effects.value.zooms[index]!, ...moved }, index)
  }
}
function releaseDrag() {
  drag = null
  document.removeEventListener('pointermove', moveDrag)
  document.removeEventListener('pointerup', endDrag)
  document.removeEventListener('pointercancel', cancelDrag)
}
function endDrag(event: PointerEvent) {
  if (drag && event.pointerId !== drag.pointer) return
  if (drag?.kind === 'video' && trimPreview.value) emit('bounds', props.startMs + trimPreview.value.start_ms, props.startMs + trimPreview.value.end_ms)
  trimPreview.value = null; releaseDrag()
}
function cancelDrag() { trimPreview.value = null; releaseDrag() }
function nudge(event: KeyboardEvent, kind: 'cue' | 'zoom', index: number, edge: Edge = 'move') {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault(); event.stopPropagation(); selected.value = { kind, index }
  const value = kind === 'cue' ? props.cues[index] : effects.value.zooms[index]
  if (!value) return
  const moved = intervalDrag(value, (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? 1000 : 100), props.durationMs, edge)
  if (kind === 'cue') setCue(moved as Cue, index); else setZoom(moved as RemotionZoom, index)
}
onBeforeUnmount(releaseDrag)
</script>

<template>
  <div class="clip-timeline">
    <div class="timeline-heading"><h2>Timeline klip</h2><span class="timecode">{{ timecode(localTime, true) }} / {{ timecode(durationMs, true) }}</span></div>
    <p class="muted small">Waktu dihitung dari awal klip. Geser blok untuk memindahkan; tarik tepinya untuk mengubah durasi. Tombol ←/→ menggeser 0,1 detik, Shift 1 detik. Nilai presisi tersedia di bawah.</p>
    <label class="timeline-zoom">Perbesar timeline<input type="range" aria-label="Perbesaran timeline" min="1" max="6" step="1" v-model.number="zoomLevel" /></label>
    <div class="tracks-scroll" tabindex="0" aria-label="Trek timeline klip">
      <div class="tracks" :style="{ width: `${zoomLevel * 100}%` }">
        <button class="timeline-ruler" aria-label="Pindah posisi timeline" @click="seekRuler"><span v-for="step in 5" :key="step" :style="{ left: `${(step - 1) * 25}%` }">{{ timecode(durationMs * (step - 1) / 4) }}</span></button>
        <div class="track"><span class="track-label">Video</span><div class="track-lane video-lane"><button class="timeline-block video-block" :class="{ selected: selected.kind === 'video' }" :style="intervalStyle(trimPreview || { start_ms: 0, end_ms: durationMs })" @click="select('video')">Video · {{ timecode(durationMs, true) }}</button><button class="trim-handle start" aria-label="Tarik batas masuk video" @pointerdown="beginDrag($event, 'video', 0, 'start')" /><button class="trim-handle end" aria-label="Tarik batas keluar video" @pointerdown="beginDrag($event, 'video', 0, 'end')" /></div></div>
        <div class="track"><span class="track-label">Subtitle</span><div class="track-lane">
          <div v-for="(cue, index) in cues" :key="index" class="timeline-item" :style="intervalStyle(cue)"><button class="timeline-block cue-block" :class="{ selected: selected.kind === 'cue' && selected.index === index }" :aria-label="`Subtitle timeline ${index + 1}: ${cue.text}`" @click="select('cue', index)" @pointerdown="beginDrag($event, 'cue', index)" @keydown="nudge($event, 'cue', index)">{{ cue.text }}</button><button class="trim-handle start" :aria-label="`Ubah awal subtitle ${index + 1}`" @pointerdown="beginDrag($event, 'cue', index, 'start')" @keydown="nudge($event, 'cue', index, 'start')" /><button class="trim-handle end" :aria-label="`Ubah akhir subtitle ${index + 1}`" @pointerdown="beginDrag($event, 'cue', index, 'end')" @keydown="nudge($event, 'cue', index, 'end')" /></div>
          <span v-if="!cues.length" class="track-empty">Belum ada subtitle</span>
        </div></div>
        <template v-if="remotion">
          <div class="track"><span class="track-label">Zoom</span><div class="track-lane">
            <div v-for="(zoom, index) in effects.zooms" :key="index" class="timeline-item" :style="intervalStyle(zoom)"><button class="timeline-block zoom-block" :class="{ selected: selected.kind === 'zoom' && selected.index === index }" :aria-label="`Zoom timeline ${index + 1}`" @click="select('zoom', index)" @pointerdown="beginDrag($event, 'zoom', index)" @keydown="nudge($event, 'zoom', index)">{{ zoom.scale.toFixed(2) }}×</button><button class="trim-handle start" :aria-label="`Ubah awal zoom ${index + 1}`" @pointerdown="beginDrag($event, 'zoom', index, 'start')" @keydown="nudge($event, 'zoom', index, 'start')" /><button class="trim-handle end" :aria-label="`Ubah akhir zoom ${index + 1}`" @pointerdown="beginDrag($event, 'zoom', index, 'end')" @keydown="nudge($event, 'zoom', index, 'end')" /></div>
            <span v-if="!effects.zooms.length" class="track-empty">Tambahkan zoom pada momen pilihan</span>
          </div></div>
          <div class="track"><span class="track-label">Intro / outro</span><div class="track-lane">
            <div v-if="effects.intro.enabled" class="timeline-item" :style="intervalStyle({ start_ms: 0, end_ms: Math.min(durationMs, effects.intro.duration_ms) })"><button class="timeline-block title-block" :class="{ selected: selected.kind === 'intro' }" aria-label="Intro timeline" @click="select('intro')">Intro</button><button class="trim-handle end" aria-label="Ubah durasi intro" @pointerdown="beginDrag($event, 'intro', 0, 'end')" /></div>
            <div v-if="effects.outro.enabled" class="timeline-item" :style="intervalStyle({ start_ms: Math.max(0, durationMs - effects.outro.duration_ms), end_ms: durationMs })"><button class="timeline-block title-block" :class="{ selected: selected.kind === 'outro' }" aria-label="Outro timeline" @click="select('outro')">Outro</button><button class="trim-handle start" aria-label="Ubah durasi outro" @pointerdown="beginDrag($event, 'outro', 0, 'start')" /></div>
            <span v-if="!effects.intro.enabled && !effects.outro.enabled" class="track-empty">Judul pembuka / penutup belum aktif</span>
          </div></div>
        </template>
        <div class="clip-playhead" :style="{ left: `${localTime / durationMs * 100}%` }" />
      </div>
    </div>
    <label class="sr-only" for="clip-local-playhead">Posisi timeline klip</label><input id="clip-local-playhead" type="range" min="0" :max="durationMs" step="10" :value="localTime" @input="emit('seek', Number(($event.target as HTMLInputElement).value))" />
    <div class="timeline-actions"><button class="button secondary small-button" @click="addCue">Tambah subtitle di sini</button><button v-if="remotion" class="button secondary small-button" :disabled="effects.zooms.length >= 20" @click="addZoom">Tambah zoom di sini</button><button v-else class="button secondary small-button" @click="emit('enableRemotion')">Aktifkan efek Remotion</button></div>
    <label>Pilih elemen<AppSelect :model-value="`${selected.kind}:${selected.index}`" label="Elemen timeline" :options="choices" @update:model-value="choose" /></label>
    <section class="timeline-inspector" aria-label="Properti elemen timeline">
      <template v-if="selected.kind === 'video'"><h3>Batas video sumber</h3><div class="time-fields"><label>Masuk<input v-model="sourceIn" aria-label="Masuk video timeline" class="timecode" /></label><label>Keluar<input v-model="sourceOut" aria-label="Keluar video timeline" class="timecode" /></label></div><button class="button secondary small-button" @click="applyBounds">Terapkan batas timeline</button><InlineError :message="boundError" /></template>
      <template v-else-if="selectedCue"><h3>Subtitle {{ selected.index + 1 }}</h3><div class="time-fields"><label>Mulai (detik)<input type="number" aria-label="Mulai subtitle timeline (detik)" min="0" :max="durationMs / 1000" step="0.01" :value="selectedCue.start_ms / 1000" @change="setCueTime('start_ms', $event)" /></label><label>Akhir (detik)<input type="number" aria-label="Akhir subtitle timeline (detik)" min="0" :max="durationMs / 1000" step="0.01" :value="selectedCue.end_ms / 1000" @change="setCueTime('end_ms', $event)" /></label></div><label>Teks subtitle<textarea aria-label="Teks subtitle timeline" rows="3" maxlength="2000" :value="selectedCue.text" @input="setCue({ ...selectedCue, text: ($event.target as HTMLTextAreaElement).value })" /></label><button class="text-button" @click="removeSelected">Hapus subtitle terpilih</button></template>
      <template v-else-if="selectedZoom"><h3>Zoom {{ selected.index + 1 }}</h3><RemotionZoomEditor :model-value="selectedZoom" :duration-ms="durationMs" @update:model-value="setZoom($event)" /><button class="text-button" @click="removeSelected">Hapus zoom terpilih</button></template>
      <RemotionTitleEditor v-else-if="selected.kind === 'intro' || selected.kind === 'outro'" :kind="selected.kind" :model-value="effects[selected.kind]" @update:model-value="updateEffects({ [selected.kind]: $event })" />
    </section>
    <InlineError :message="validation" />
  </div>
</template>

<style scoped>
.clip-timeline { flex: 1; min-height: 0; overflow: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; overscroll-behavior: contain; }
.clip-timeline > * { flex-shrink: 0; }
.timeline-heading { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
h2, h3, p { margin: 0; }
h2 { font-size: 14px; } h3 { font-size: 13px; }
.timeline-heading span { font-size: 10px; }
.timeline-zoom { display: grid; grid-template-columns: auto 1fr; gap: 14px; align-items: center; }
label { font-size: 12px; display: grid; gap: 6px; }
input, textarea { width: 100%; min-width: 0; }
.tracks-scroll { overflow-x: auto; overflow-y: hidden; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-field); padding: 8px; }
.tracks { position: relative; min-width: 100%; padding-top: 8px; }
.timeline-ruler { position: relative; display: block; width: 100%; height: 28px; border: none; background: transparent; margin-bottom: 8px; }
.timeline-ruler span { position: absolute; top: 0; font-family: ui-monospace, Consolas, monospace; font-size: 10px; color: var(--color-text-muted); transform: translateX(-50%); }
.timeline-ruler span:first-child { transform: none; }.timeline-ruler span:last-child { transform: translateX(-100%); }
.track { margin-bottom: 10px; }
.track-label { display: block; margin-bottom: 4px; font-size: 10px; color: var(--color-text-muted); }
.track-lane { position: relative; height: 34px; border-radius: 4px; background: #22272d; }
.timeline-item { position: absolute; top: 0; height: 34px; min-width: 3px; }
.timeline-block { position: absolute; inset: 0; width: 100%; border: 1px solid transparent; border-radius: 4px; padding: 0 12px; font-size: 10px; text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: grab; touch-action: none; }
.video-block { background: #284652; color: #c0e2ee; }.cue-block { background: #2a4439; color: #b4dfc5; }.zoom-block { background: #42394d; color: #d6c3ed; }.title-block { background: #54432b; color: #f1d5a7; }
.timeline-block.selected { border: 2px solid var(--color-accent); }
.trim-handle { position: absolute; top: 2px; bottom: 2px; width: 9px; border: 0; border-radius: 3px; background: #ffffff28; cursor: ew-resize; touch-action: none; z-index: 2; padding: 0; }
.trim-handle.start { left: 1px; }.trim-handle.end { right: 1px; }.trim-handle:focus-visible { outline: 2px solid var(--color-accent); }
.track-empty { font-size: 10px; line-height: 34px; padding: 0 8px; color: var(--color-text-muted); }
.clip-playhead { position: absolute; top: 22px; bottom: 0; width: 1px; background: var(--color-accent); pointer-events: none; z-index: 3; }
.clip-playhead::before { content: ''; position: absolute; top: -5px; left: -4px; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 7px solid var(--color-accent); }
.timeline-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.timeline-inspector { display: grid; gap: 12px; padding: 14px; border: 1px solid var(--color-border); border-radius: 5px; background: var(--color-surface-muted); }
.time-fields { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 10px; }
</style>
