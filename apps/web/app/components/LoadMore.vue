<script setup lang="ts">
defineProps<{ loaded: number; total: number; loading: boolean; hasMore: boolean; label: string; buttonLabel: string }>()
const emit = defineEmits<{ more: [] }>()
</script>
<template>
  <div v-if="total > 0" class="load-more-footer"><span class="muted small">{{ loaded }} dari {{ total }} {{ label }}</span><button v-if="hasMore" class="button secondary small-button" :disabled="loading" @click="emit('more')">{{ loading ? 'Memuat…' : buttonLabel }}</button></div>
</template>
