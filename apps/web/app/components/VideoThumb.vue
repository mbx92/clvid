<script setup lang="ts">
import type { Asset } from '~/types/api'
const props = defineProps<{ asset?: Asset | null; timeMs?: number }>()
const failed = ref(false)
const ready = ref(false)
watch(() => props.asset?.id, () => { failed.value = false; ready.value = false })
const thumbnailReady = (event: Event) => {
  const video = event.target as HTMLVideoElement
  video.currentTime = Math.min(Number.isFinite(video.duration) ? video.duration : 1, Math.max(0.1, (props.timeMs || 0) / 1000))
}
</script>
<template>
  <span class="video-thumb" aria-hidden="true"><AppIcon v-if="!ready || failed" name="Film" :size="23" /><video v-if="asset?.state === 'ready' && !failed" :src="`/api/v1/assets/${asset.id}/content`" preload="metadata" muted playsinline :class="{ visible: ready }" tabindex="-1" @loadedmetadata="thumbnailReady" @seeked="ready = true" @error="failed = true" /></span>
</template>
