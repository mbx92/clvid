<script setup lang="ts">
const props = withDefaults(defineProps<{ open: boolean; title: string; description?: string; busy?: boolean; wide?: boolean }>(), { busy: false })
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
const uid = useId()
let priorFocus: HTMLElement | null = null
let previousOverflow = ''
const focusable = () => Array.from(panel.value?.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex="0"]') || []).filter(el => el.offsetParent !== null)
const onKey = (event: KeyboardEvent) => {
  if (!props.open) return
  if (event.key === 'Escape' && !props.busy) { event.preventDefault(); emit('close') }
  if (event.key === 'Tab') {
    const items = focusable()
    const first = items[0]; const last = items[items.length - 1]
    if (!first) { event.preventDefault(); panel.value?.focus(); return }
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.value)) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
}
watch(() => props.open, async (open) => {
  if (!import.meta.client) return
  if (open) {
    priorFocus = document.activeElement as HTMLElement
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    await nextTick()
    focusable()[0]?.focus()
    document.addEventListener('keydown', onKey)
  } else {
    document.body.style.overflow = previousOverflow
    document.removeEventListener('keydown', onKey)
    priorFocus?.focus()
  }
})
onBeforeUnmount(() => { if (import.meta.client && props.open) { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', onKey); priorFocus?.focus() } })
</script>
<template>
  <Teleport to="body">
    <div v-if="open" class="dialog-backdrop" @mousedown.self="!busy && emit('close')">
      <section ref="panel" class="dialog" :class="{ 'dialog-wide': wide }" role="dialog" aria-modal="true" :aria-labelledby="`${uid}-title`" :aria-describedby="description ? `${uid}-description` : undefined" tabindex="-1">
        <header class="dialog-header"><h2 :id="`${uid}-title`">{{ title }}</h2><button class="icon-button" aria-label="Tutup dialog" :disabled="busy" @click="emit('close')"><AppIcon name="X" /></button></header>
        <p v-if="description" :id="`${uid}-description`" class="muted dialog-description">{{ description }}</p>
        <slot />
      </section>
    </div>
  </Teleport>
</template>
