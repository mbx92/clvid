<script setup lang="ts">
type Option = { value: string | number; label: string; disabled?: boolean }
const props = withDefaults(defineProps<{ modelValue: string | number; options: Option[]; label: string; placeholder?: string; disabled?: boolean; required?: boolean }>(), { disabled: false, required: false })
const emit = defineEmits<{ 'update:modelValue': [value: any] }>()
const root = ref<HTMLElement | null>(null)
const button = ref<HTMLButtonElement | null>(null)
const popup = ref<HTMLElement | null>(null)
const open = ref(false)
const query = ref('')
const active = ref(-1)
const page = ref(0)
const size = ref(6)
const placement = ref<Record<string, string>>({})
const uid = useId()
const selected = computed(() => props.options.find(x => x.value === props.modelValue))
const filtered = computed(() => props.options.filter(x => x.label.toLocaleLowerCase().includes(query.value.toLocaleLowerCase().trim())))
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / size.value)))
const visible = computed(() => filtered.value.slice(page.value * size.value, (page.value + 1) * size.value))
const enabled = computed(() => filtered.value.flatMap((x, i) => x.disabled ? [] : [i]))
function place() {
  if (!open.value || !button.value) return
  const r = button.value.getBoundingClientRect()
  size.value = Math.max(1, Math.min(6, Math.floor((innerHeight - 160) / 44)))
  const height = Math.min(size.value, Math.max(1, filtered.value.length)) * 44 + 16 + (props.options.length > 6 ? 50 : 0) + (pages.value > 1 ? 44 : 0)
  const width = Math.min(Math.max(r.width, 200), innerWidth - 24)
  const top = r.bottom + height + 8 <= innerHeight ? r.bottom + 4 : Math.max(8, r.top - height - 4)
  placement.value = { top: `${top}px`, left: `${Math.max(12, Math.min(r.left, innerWidth - width - 12))}px`, width: `${width}px` }
}
function activate(index: number) { active.value = index; if (index >= 0) page.value = Math.floor(index / size.value) }
function show() {
  if (props.disabled) return
  query.value = ''; open.value = true; place()
  const index = filtered.value.findIndex(x => x.value === props.modelValue && !x.disabled)
  activate(index >= 0 ? index : (enabled.value[0] ?? -1))
}
function choose(index: number) {
  const option = filtered.value[index]
  if (!option || option.disabled) return
  emit('update:modelValue', option.value); open.value = false
  button.value?.focus({ preventScroll: true })
}
function changePage(delta: number) {
  page.value = Math.max(0, Math.min(pages.value - 1, page.value + delta))
  active.value = enabled.value.find(i => Math.floor(i / size.value) === page.value) ?? -1
}
function key(event: KeyboardEvent) {
  const searching = event.target instanceof HTMLInputElement
  if (event.key === 'Escape' && open.value) { event.preventDefault(); event.stopPropagation(); open.value = false; button.value?.focus({ preventScroll: true }); return }
  if (event.key === 'Tab' && !searching) { open.value = false; return }
  if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter'].includes(event.key) || (event.key === ' ' && !searching)) {
    if (searching && ['Home', 'End'].includes(event.key)) return
    event.preventDefault(); event.stopPropagation()
    if (!open.value) { show(); return }
    if (event.key === 'Enter' || event.key === ' ') { choose(active.value); return }
    if (!enabled.value.length) return
    if (event.key === 'Home') activate(enabled.value[0]!)
    else if (event.key === 'End') activate(enabled.value.at(-1)!)
    else { const current = enabled.value.indexOf(active.value); activate(enabled.value[(current + (event.key === 'ArrowDown' ? 1 : -1) + enabled.value.length) % enabled.value.length]!) }
  } else if (!searching && event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
    if (!open.value) show()
    const found = filtered.value.findIndex(x => !x.disabled && x.label.toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase()))
    if (found >= 0) activate(found)
  }
}
watch(query, () => { page.value = 0; active.value = enabled.value[0] ?? -1; nextTick(place) }, { flush: 'sync' })
watch(() => props.options, () => { page.value = Math.min(page.value, pages.value - 1); if (!enabled.value.includes(active.value)) active.value = enabled.value[0] ?? -1; nextTick(place) })
watch(() => props.disabled, disabled => { if (disabled) open.value = false })
const outside = (event: Event) => { if (!root.value?.contains(event.target as Node) && !popup.value?.contains(event.target as Node)) open.value = false }
onMounted(() => { document.addEventListener('pointerdown', outside); document.addEventListener('focusin', outside); window.addEventListener('resize', place); document.addEventListener('scroll', place, true) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', outside); document.removeEventListener('focusin', outside); window.removeEventListener('resize', place); document.removeEventListener('scroll', place, true) })
</script>
<template>
  <div ref="root" class="custom-select">
    <button ref="button" type="button" class="select-button" :class="{ 'select-open': open, 'select-placeholder': !selected }" role="combobox" :aria-label="label" :aria-expanded="open" :aria-required="required || undefined" aria-haspopup="listbox" :aria-controls="`${uid}-options`" :aria-activedescendant="open && active >= 0 ? `${uid}-option-${active}` : undefined" :disabled="disabled" @click="open ? open = false : show()" @keydown="key"><span>{{ selected?.label || placeholder || label }}</span><AppIcon name="ChevronDown" :size="16" /></button>
    <Teleport to="body"><div v-if="open" ref="popup" class="select-popover" :style="placement" @keydown.esc="key">
      <label v-if="options.length > 6" class="select-search"><AppIcon name="Search" :size="15" /><input v-model="query" type="search" :aria-label="`Cari ${label}`" placeholder="Cari pilihan..." :aria-controls="`${uid}-options`" :aria-activedescendant="active >= 0 ? `${uid}-option-${active}` : undefined" @keydown="key" /></label>
      <ul :id="`${uid}-options`" class="select-options" role="listbox" :aria-label="label">
        <li v-for="(option, offset) in visible" :id="`${uid}-option-${page * size + offset}`" :key="option.value" role="option" :aria-selected="option.value === modelValue" :aria-disabled="option.disabled || undefined" :aria-posinset="page * size + offset + 1" :aria-setsize="filtered.length" :class="{ active: page * size + offset === active, disabled: option.disabled }" :title="option.label" @pointerdown.prevent @click="choose(page * size + offset)" @mousemove="!option.disabled && (active = page * size + offset)"><span>{{ option.label }}</span><AppIcon v-if="option.value === modelValue" name="Check" :size="15" /></li>
      </ul>
      <p v-if="!filtered.length" class="select-empty" role="status">{{ query ? 'Tidak ada pilihan yang cocok.' : 'Belum ada pilihan tersedia.' }}</p>
      <nav v-if="pages > 1" class="select-pagination" :aria-label="`Halaman pilihan ${label}`"><button type="button" class="icon-button" :disabled="page === 0" aria-label="Pilihan sebelumnya" @click="changePage(-1)"><AppIcon name="ChevronLeft" :size="16" /></button><span>{{ page + 1 }} / {{ pages }}</span><button type="button" class="icon-button" :disabled="page >= pages - 1" aria-label="Pilihan berikutnya" @click="changePage(1)"><AppIcon name="ChevronRight" :size="16" /></button></nav>
    </div></Teleport>
  </div>
</template>
