<script setup lang="ts">
import type { Cue, SubtitleStyle } from '~/types/api'
import { subtitleDefaults } from '~/utils/subtitle-style'
import { remotionEffects } from '~/utils/remotion-effects'
import { loadRemotionPreview, remotionFrame, type RemotionBridge, type RemotionController, type RemotionPreviewProps, type RemotionVideoStyle } from '~/utils/remotion-preview'

const props = defineProps<{ cues: Cue[]; subtitleStyle: SubtitleStyle; durationMs: number; timeMs: number }>()
const emit = defineEmits<{ 'video-style': [style: RemotionVideoStyle | {}] }>()
const host = ref<HTMLElement | null>(null)
const error = ref('')
const ready = ref(false)
let controller: RemotionController | null = null
let bridge: RemotionBridge | null = null
let disposed = false
const composition = computed<RemotionPreviewProps>(() => ({
  cues: props.cues.map(({ start_ms, end_ms, text }) => ({ start_ms, end_ms, text })),
  style: { ...subtitleDefaults, ...props.subtitleStyle, remotion_effects: remotionEffects(props.subtitleStyle.remotion_effects) },
  durationMs: props.durationMs, width: 1080, height: 1920, fps: 30,
  fontUrl: '/fonts/NotoSans-Regular.ttf',
}))
const frame = computed(() => remotionFrame(props.timeMs, props.durationMs))
const withinClip = computed(() => props.timeMs >= 0 && props.timeMs < props.durationMs)
function failed() {
  error.value = 'Preview Remotion gagal dimuat. Muat ulang halaman atau pilih renderer Standar.'
  ready.value = false
  const failedController = controller
  controller = null
  emit('video-style', {})
  try { failedController?.destroy() } catch { /* Preserve the visible preview error. */ }
}
watch(composition, value => {
  try {
    if (controller) { controller.updateProps(value); syncFrame() }
    else if (bridge) mountPreview()
  } catch { failed() }
})
function mountPreview() {
  if (disposed || !host.value || !bridge) return
  error.value = ''
  controller = bridge.mount(host.value, composition.value)
  syncFrame()
  ready.value = true
}
function syncFrame() {
  if (!controller || !bridge) return
  controller.setFrame(frame.value)
  emit('video-style', withinClip.value ? bridge.videoStyle(composition.value, frame.value) : {})
}
watch([frame, withinClip], () => { try { syncFrame() } catch { failed() } })
onMounted(async () => {
  host.value?.addEventListener('clipper-remotion-error', failed)
  try {
    bridge = await loadRemotionPreview()
    mountPreview()
  } catch { if (!disposed) failed() }
})
onBeforeUnmount(() => {
  disposed = true
  host.value?.removeEventListener('clipper-remotion-error', failed)
  try { controller?.destroy() } catch { /* A failed player must not prevent leaving the editor. */ }
  controller = null
  bridge = null
  emit('video-style', {})
})
</script>

<template>
  <div class="remotion-caption" :aria-busy="!ready && !error" aria-label="Preview Remotion">
    <div ref="host" class="remotion-caption-host" :style="{ visibility: withinClip ? 'visible' : 'hidden' }" />
    <p v-if="error" class="remotion-preview-status remotion-preview-error" role="alert">{{ error }}</p>
    <p v-else-if="!ready" class="remotion-preview-status" role="status">Memuat preview Remotion…</p>
  </div>
</template>

<style scoped>
.remotion-caption { position: absolute; inset: 0; z-index: 2; pointer-events: none; }
.remotion-caption-host { width: 100%; height: 100%; }
.remotion-preview-status { position: absolute; left: 6%; right: 6%; top: 40%; margin: 0; padding: .8rem; border-radius: .5rem; background: #171a20ed; color: #fff; font-size: .8rem; line-height: 1.5; text-align: center; }
.remotion-preview-error { border: 1px solid #e38a8a; }
</style>
