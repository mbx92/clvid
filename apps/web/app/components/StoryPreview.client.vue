<script setup lang="ts">
import { storySize, storyError, type StoryDocument } from '~/utils/story'
import type { Asset } from '~/types/api'
const props = defineProps<{ document: StoryDocument; assets: Asset[]; selectedScene?: number }>()
const host = ref<HTMLElement | null>(null)
const container = ref<HTMLElement | null>(null)
const size = ref({width: 1, height: 1})
let observer: ResizeObserver | undefined
const error = ref('')
let controller: {updateProps: (props: any) => void; setFrame: (frame: number) => void; destroy: () => void} | undefined
let disposed = false
const input = computed(() => {
  const [width, height] = storySize(props.document.aspect)
  return {document: props.document, width, height, fps: 30, fontUrl: '/fonts/NotoSans-Regular.ttf', assets: Object.fromEntries(props.assets.map(a => [a.id, {url: a.content_url, kind: a.metadata.story_kind}]))}
})
const fit = computed(() => {
  const [w,h] = storySize(props.document.aspect)
  const scale = Math.min(size.value.width / w!, size.value.height / h!)
  return {width: `${w! * scale}px`, height: `${h! * scale}px`}
})
function seekScene() {controller?.setFrame(props.document.scenes.slice(0, props.selectedScene || 0).reduce((n,s) => n + s.duration_ms * .03, 12))}
watch(() => props.selectedScene, seekScene)
watch(input, value => { if (!storyError(props.document)) controller?.updateProps(value) }, {deep: true})
onMounted(async () => {
  observer = new ResizeObserver(entries => {const r = entries[0]?.contentRect; if (r) size.value = {width:r.width,height:r.height}})
  if (container.value) observer.observe(container.value)
  try {
    const win = window as any
    if (!win.ClipperStory) await new Promise<void>((resolve, reject) => {
      const script = document.createElement('script')
      const timer = setTimeout(() => reject(new Error('timeout')), 15000)
      script.src = '/remotion/story-player.js'
      script.onload = () => {clearTimeout(timer); resolve()}
      script.onerror = () => {clearTimeout(timer); script.remove(); reject(new Error('load'))}
      document.head.appendChild(script)
    })
    if (!disposed && host.value) {controller = win.ClipperStory.mount(host.value, input.value); seekScene()}
  } catch {error.value = 'Preview gagal dimuat. Muat ulang halaman.'}
})
onBeforeUnmount(() => {disposed = true; observer?.disconnect(); controller?.destroy()})
</script>
<template><div ref="container" class="story-preview"><div ref="host" class="story-preview-host" :style="fit"/><p v-if="error" role="alert">{{ error }}</p></div></template>
<style scoped>
.story-preview { display: flex; align-items: center; justify-content: center; min-height: 0; height: 100%; width: 100%; }
.story-preview-host { flex: none; }
</style>
