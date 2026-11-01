<script setup lang="ts" generic="T">
withDefaults(defineProps<{ items: T[]; label?: string }>(), { label: 'item' })
</script>
<template>
  <div class="scroll-list" role="region" :aria-label="`Daftar ${label}`" tabindex="0">
    <slot :items="items" :start="0" />
  </div>
</template>
