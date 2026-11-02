<script setup lang="ts">
import { drawThumbnail, thumbnailSize, thumbnailStyles, thumbnailPalettes } from '~/utils/thumbnail'
import type { ThumbnailFormat, ThumbnailPosition, ThumbnailStyle, ThumbnailPalette, ThumbnailFont } from '~/utils/thumbnail'
import { timecode } from '~/utils/format'

const props = withDefaults(defineProps<{ open: boolean; src: string; title?: string; initialTime?: number }>(), { title: '', initialTime: 0 })
const emit = defineEmits<{ close: [] }>()
const player = ref<HTMLVideoElement | null>(null)
const output = ref<HTMLCanvasElement | null>(null)
const title = ref('')
const format = ref<ThumbnailFormat>('landscape')
const style = ref<ThumbnailStyle>('pop')
const palette = ref<ThumbnailPalette>('sunset')
const font = ref<ThumbnailFont>('display')
const uppercase = ref(true)
const hasPalette = computed(() => ['pop', 'gradient', 'neon'].includes(style.value))
const position = ref<ThumbnailPosition>('bottom')
const fit = ref(false)
const textSize = ref(14)
const duration = ref(0)
const seconds = ref(0)
const capturedAt = ref(0)
const captured = ref(false)
const ready = ref(false)
const downloading = ref(false)
const error = ref('')
const dimensions = computed(() => thumbnailSize(format.value).join(' × '))
let frame: HTMLCanvasElement | null = null
let initialSeek = 0
let session = 0

function render() {
  if (!output.value || !frame) return
  try { drawThumbnail(output.value, frame, { title: title.value, format: format.value, fit: fit.value, style: style.value, position: position.value, textSize: textSize.value, palette: palette.value, font: font.value, uppercase: uppercase.value }); error.value = '' }
  catch { captured.value = false; error.value = 'Thumbnail gagal dibuat. Pilih frame lain atau muat ulang video.' }
}
function capture() {
  const video = player.value
  if (!video || video.seeking || video.readyState < 2 || !video.videoWidth) return
  video.pause()
  try {
    frame ||= document.createElement('canvas')
    // Limit memory for 4K/8K sources while retaining enough pixels for the output.
    const scale = Math.min(1, 1920 / Math.max(video.videoWidth, video.videoHeight))
    frame.width = Math.round(video.videoWidth * scale); frame.height = Math.round(video.videoHeight * scale)
    const ctx = frame.getContext('2d')
    if (!ctx) throw new Error('canvas')
    ctx.drawImage(video, 0, 0, frame.width, frame.height)
    capturedAt.value = video.currentTime; captured.value = true; render()
  } catch { captured.value = false; error.value = 'Frame tidak dapat diambil. Coba waktu lain atau gunakan video yang kompatibel.' }
}
function metadata() {
  const video = player.value
  if (!video || !Number.isFinite(video.duration)) return
  duration.value = video.duration
  initialSeek = Math.min(Math.max(0, props.initialTime), Math.max(0, video.duration - .1))
  if (initialSeek > 0) { seconds.value = initialSeek; video.currentTime = initialSeek }
}
function loaded() {
  ready.value = true
  if (!captured.value && initialSeek === 0) capture()
}
function seek() {
  const video = player.value
  if (!video || !Number.isFinite(Number(seconds.value))) return
  video.pause()
  seconds.value = Math.min(Math.max(0, Number(seconds.value)), Math.max(0, duration.value - .05))
  video.currentTime = seconds.value
}
function seeked() { ready.value = true; capture() }
function mediaError() { ready.value = false; error.value = 'Video tidak dapat dimuat. Periksa koneksi dan akses video, lalu tutup dan buka kembali generator.' }
async function download() {
  if (!captured.value || !output.value || downloading.value) return
  const currentSession = session
  const filename = `thumbnail-${format.value}-${capturedAt.value.toFixed(1)}s.jpg`
  downloading.value = true
  try {
    const blob = await new Promise<Blob | null>(resolve => output.value!.toBlob(resolve, 'image/jpeg', .9))
    if (currentSession !== session) return
    if (!blob) throw new Error('encode')
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url; link.download = filename
    document.body.append(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch { if (currentSession === session) error.value = 'Unduhan JPG gagal. Coba lagi atau pilih frame lain.' }
  finally { if (currentSession === session) downloading.value = false }
}
watch([title, format, style, position, fit, textSize, palette, font, uppercase], render)
watch(() => [props.open, props.src] as const, () => {
  session++
  player.value?.pause(); frame = null; captured.value = false; ready.value = false; error.value = ''; downloading.value = false
  duration.value = 0; seconds.value = 0; initialSeek = 0
  if (props.open) { title.value = props.title.slice(0, 180); format.value = 'landscape'; style.value = 'pop'; palette.value = 'sunset'; font.value = 'display'; uppercase.value = true; position.value = 'bottom'; fit.value = false; textSize.value = 14 }
}, { immediate: true })
onBeforeUnmount(() => { session++; player.value?.pause(); frame = null })
</script>

<template>
  <AppDialog :open="open" title="Buat thumbnail" description="Pilih frame video, tulis judul, lalu unduh sebagai JPG. Hasil diunduh ke perangkat Anda." wide @close="emit('close')">
    <div class="thumbnail-layout">
      <div class="thumbnail-preview">
        <div class="thumbnail-canvas-wrap"><canvas v-show="captured" ref="output" role="img" :aria-label="`Preview thumbnail: ${title || 'Tanpa teks'}`" /><p v-if="!captured" class="muted" role="status">Pilih frame dari video untuk memulai.</p></div>
        <p v-if="captured" class="muted small" aria-live="polite">{{ dimensions }} px · Frame {{ timecode(capturedAt * 1000, true) }}</p>
        <video v-if="open && src" ref="player" :key="src" :src="src" controls muted playsinline preload="auto" aria-label="Pilih frame thumbnail" @loadedmetadata="metadata" @loadeddata="loaded" @seeking="ready = false" @seeked="seeked" @canplay="ready = true" @error="mediaError" @timeupdate="seconds = player?.currentTime || 0" />
        <div class="thumbnail-seek"><label>Waktu (detik)<input v-model.number="seconds" type="number" min="0" :max="duration" step="0.1" :disabled="!duration" @change="seek" /></label><button class="button secondary" :disabled="!ready" @click="capture">Ambil frame ini</button></div>
      </div>
      <div class="form-stack thumbnail-controls">
        <label>Judul thumbnail<textarea v-model="title" rows="3" maxlength="180" placeholder="Tulis judul yang menarik" /><span class="muted small">Kosongkan untuk frame tanpa teks.</span></label>
        <label>Format<AppSelect v-model="format" label="Format thumbnail" :options="[{ value: 'landscape', label: 'YouTube · 16:9' }, { value: 'portrait', label: 'Vertikal · 9:16' }, { value: 'square', label: 'Persegi · 1:1' }]" /></label>
        <fieldset class="thumbnail-presets"><legend>Gaya teks</legend><div class="thumbnail-style-grid"><button v-for="preset in thumbnailStyles" :key="preset.value" type="button" :aria-pressed="style === preset.value" :aria-label="preset.label" :title="preset.description" @click="style = preset.value"><span class="style-sample" :class="`sample-${preset.value}`" aria-hidden="true">Aa</span><span>{{ preset.value === 'panel' ? 'Latar gelap' : preset.label }}</span></button></div></fieldset>
        <fieldset v-if="hasPalette" class="thumbnail-presets"><legend>Warna efek</legend><div class="thumbnail-palettes"><button v-for="item in thumbnailPalettes" :key="item.value" type="button" :aria-label="item.label" :title="item.label" :aria-pressed="palette === item.value" :style="{ background: `linear-gradient(135deg, ${item.colors[0]}, ${item.colors[1]})` }" @click="palette = item.value"><AppIcon v-if="palette === item.value" name="Check" :size="18" /></button></div></fieldset>
        <div class="form-grid">
        <label>Font<AppSelect v-model="font" label="Font thumbnail" :options="[{ value: 'display', label: 'Display tebal' }, { value: 'modern', label: 'Modern' }]" /></label>
        <label>Posisi teks<AppSelect v-model="position" label="Posisi teks thumbnail" :options="[{ value: 'top', label: 'Atas' }, { value: 'middle', label: 'Tengah' }, { value: 'bottom', label: 'Bawah' }]" /></label>
        </div>
        <label>Ukuran teks<input v-model.number="textSize" type="range" min="5" max="16" step="1" /></label>
        <label class="checkbox-label"><input v-model="uppercase" type="checkbox" />Huruf kapital</label>
        <label class="checkbox-label"><input v-model="fit" type="checkbox" />Tampilkan seluruh frame</label>
        <p class="muted small">{{ fit ? 'Ruang kosong diisi latar gelap.' : 'Frame dipotong dari tengah agar memenuhi format.' }} Judul panjang otomatis diperkecil.</p>
      </div>
    </div>
    <InlineError :message="error" />
    <div class="dialog-actions"><button class="button secondary" @click="emit('close')">Tutup</button><button class="button primary" :disabled="!captured || downloading" @click="download"><AppIcon name="Download" />{{ downloading ? 'Menyiapkan…' : 'Unduh JPG' }}</button></div>
  </AppDialog>
</template>

<style scoped>
.thumbnail-layout { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr); gap: 22px; }
.thumbnail-preview { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.thumbnail-canvas-wrap { display: flex; align-items: center; justify-content: center; min-height: 180px; background: #ecede9; border: 1px solid #d9ddd7; border-radius: 6px; overflow: hidden; padding: 6px; }
.thumbnail-canvas-wrap canvas { display: block; max-width: 100%; max-height: 300px; object-fit: contain; }
.thumbnail-canvas-wrap p { padding: 20px; text-align: center; }
.thumbnail-preview video { display: block; width: 100%; height: 160px; background: #111827; border-radius: 6px; }
.thumbnail-seek { display: flex; align-items: end; gap: 10px; }
.thumbnail-seek label { flex: 1; min-width: 0; font-size: 12px; }
.thumbnail-controls { gap: 12px; align-content: start; }
.thumbnail-presets { border: 0; padding: 0; margin: 0; min-width: 0; }
.thumbnail-presets legend { font-size: 12px; font-weight: 550; margin-bottom: 7px; }
.thumbnail-style-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }
.thumbnail-style-grid button { min-width: 0; display: flex; flex-direction: column; align-items: center; gap: 4px; background: #f4f5f3; border: 1px solid #bdc3bb; border-radius: 6px; padding: 6px 3px; font-size: 10px; }
.thumbnail-style-grid button[aria-pressed='true'] { border-color: #355d78; box-shadow: 0 0 0 1px #355d78; background: #e8f0f5; }
.style-sample { display: block; font: 900 25px/1.2 Impact, 'Arial Black', sans-serif; color: white; -webkit-text-stroke: 1px #171725; }
.sample-pop { color: #ffcf45; -webkit-text-stroke: .5px #fff; text-shadow: 1px 1px #171725, 2px 2px #171725, 3px 3px #171725; }
.sample-gradient { background: linear-gradient(#fff36b, #ff831e); background-clip: text; color: transparent; -webkit-text-stroke: .7px #171725; }
.sample-neon { background: #151527; border-radius: 4px; padding: 0 7px; -webkit-text-stroke: 0; text-shadow: 0 0 4px #e544ff, 0 0 8px #e544ff; }
.sample-yellow { color: #ffe03b; }
.sample-panel { background: #171725; padding: 0 7px; border-radius: 3px; }
.thumbnail-palettes { display: flex; gap: 10px; }
.thumbnail-palettes button { display: grid; place-items: center; width: 36px; height: 32px; border: 2px solid #fff; border-radius: 6px; box-shadow: 0 0 0 1px #bdc3bb; color: #171725; }
.thumbnail-palettes button[aria-pressed='true'] { box-shadow: 0 0 0 2px #355d78; }
@media (max-width: 600px) { .thumbnail-layout { grid-template-columns: 1fr; } }
</style>
