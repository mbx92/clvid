<script setup lang="ts">
import type { GamingLayout } from '~/types/api'
import { drawGaming } from '~/utils/gaming'
const props = defineProps<{ video: HTMLVideoElement | null; layout: GamingLayout; sourceWidth: number; sourceHeight: number; outputWidth: number }>()
const canvas = ref<HTMLCanvasElement | null>(null)
const ready = ref(false)
const draw = () => {
  if (canvas.value && props.video) ready.value = drawGaming(canvas.value, props.video, props.layout, props.sourceWidth, props.sourceHeight, props.outputWidth)
}
watch(() => [props.video, props.layout, props.sourceWidth, props.sourceHeight, props.outputWidth], () => { void nextTick(draw) }, { deep: true })
onMounted(draw)
defineExpose({ draw })
</script>
<template>
  <canvas ref="canvas" class="gaming-output" data-testid="gaming-preview" :width="outputWidth" :height="outputWidth * 16 / 9" role="img" aria-label="Preview Gaming: facecam di atas dan gameplay di bawah" />
  <span v-if="!ready" class="gaming-loading" role="status">Memuat frame video…</span>
</template>
