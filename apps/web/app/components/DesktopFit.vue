<script setup lang="ts">
// Bounded controls retain their DOM and focus while fitting the available pane.
const props = withDefaults(defineProps<{ fit?: boolean }>(), { fit: true })
const host = ref<HTMLElement | null>(null)
const content = ref<HTMLElement | null>(null)
const scale = ref(1)
let observer: ResizeObserver | undefined
let frame = 0
function measure() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    if (!host.value || !content.value || !host.value.clientHeight) return
    scale.value = props.fit && innerWidth > 900 ? Math.min(1, host.value.clientHeight / Math.max(1, content.value.scrollHeight)) : 1
  })
}
onMounted(() => {
  observer = new ResizeObserver(measure)
  if (host.value) observer.observe(host.value)
  if (content.value) observer.observe(content.value)
  window.addEventListener('resize', measure)
  measure()
})
onBeforeUnmount(() => { observer?.disconnect(); cancelAnimationFrame(frame); window.removeEventListener('resize', measure) })
watch(() => props.fit, measure)
</script>
<template><div ref="host" class="desktop-fit" :class="{ 'desktop-fit-scroll': !fit }"><div ref="content" class="desktop-fit-content" :style="{ zoom: scale }"><slot /></div></div></template>
<style scoped>.desktop-fit-scroll { overflow: auto; overscroll-behavior: contain; }</style>
