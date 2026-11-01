<script setup lang="ts">
import { statusLabels } from '~/utils/format'
defineProps<{ status: string }>()
</script>
<template><span class="status" :class="`status-${status}`"><span class="status-dot" aria-hidden="true" />{{ statusLabels[status] || status }}</span></template>
