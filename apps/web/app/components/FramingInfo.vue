<script setup lang="ts">
import type { ExportFramingMetadata } from '~/types/api'
import { framingNotices, speakerSwitchCount, trackingLabel } from '~/utils/framing'
import { GAMING_LABEL } from '~/utils/gaming'
defineProps<{ framing?: ExportFramingMetadata }>()
</script>
<template>
  <div v-if="framing" class="framing-info"><p class="muted small">Framing{{ framing.fallback_reason ? ' yang diminta' : '' }}: {{ framing.layout === 'gaming' ? GAMING_LABEL : trackingLabel(framing.mode) }}</p><p v-if="speakerSwitchCount(framing) !== null" class="muted small">Perpindahan pembicara terdeteksi: {{ speakerSwitchCount(framing) }}.</p><p v-for="message in framingNotices(framing)" :key="message" class="notice">{{ message }}</p></div>
</template>
