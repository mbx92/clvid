<script setup lang="ts">
import type { Export } from '~/types/api'
import { dateTime, fileSize } from '~/utils/format'
defineProps<{ exports: Export[]; currentRevision?: number }>()
const emit = defineEmits<{ refresh: [] }>()
const preview = ref<Export | null>(null)
const thumbnail = ref<Export | null>(null)
</script>
<template>
  <section v-if="!exports.length" class="empty-state"><AppIcon name="Download" :size="25" /><h2>Belum ada ekspor</h2><p>Buka klip, simpan perubahan, lalu pilih Ekspor.</p></section>
  <ScrollList v-else :items="exports" label="ekspor" v-slot="{ items }"><div class="export-list">
    <article v-for="item in items" :key="item.id" class="export-row"><div class="export-heading"><div><h3>{{ item.clip_title || 'Klip video' }}</h3><p class="muted small">Hasil revisi {{ item.revision }}<span v-if="currentRevision && item.revision !== currentRevision"> · Revisi saat ini {{ currentRevision }}</span> · {{ item.config?.resolution || item.config?.width || 1080 }}p<span v-if="item.mp4_asset"> · {{ fileSize(item.mp4_asset.bytes) }}</span></p><small class="muted">{{ dateTime(item.created_at) }}</small></div><StatusBadge :status="item.status" /></div>
      <FramingInfo :framing="item.mp4_asset?.metadata.framing" />
      <div v-if="item.mp4_asset && ['succeeded', 'ready', 'completed'].includes(item.status)" class="export-actions"><button class="button secondary small-button" @click="preview = item"><AppIcon name="Play" :size="15" />Lihat hasil</button><a class="button secondary small-button" :href="`/api/v1/assets/${item.mp4_asset.id}/content?download=true`" download><AppIcon name="Download" :size="15" />Unduh MP4</a><button class="button secondary small-button" @click="thumbnail = item"><AppIcon name="Image" :size="15" />Thumbnail</button><NuxtLink class="button secondary small-button" :to="`/calendar?export=${item.id}`"><AppIcon name="CalendarDays" :size="15" />Jadwalkan</NuxtLink><a v-if="item.srt_asset" class="text-button" :href="`/api/v1/assets/${item.srt_asset.id}/content?download=true`" download>Unduh SRT</a></div>
      <JobStatus v-else-if="item.job" :job="item.job" @refresh="emit('refresh')" />
    </article>
  </div>
  </ScrollList>
  <AppDialog :open="!!preview" :title="`Hasil revisi ${preview?.revision}`" description="File render final adalah acuan untuk crop, tampilan subtitle, dan timing." wide @close="preview = null"><FramingInfo :framing="preview?.mp4_asset?.metadata.framing" /><video v-if="preview?.mp4_asset" class="final-video" controls playsinline :src="`/api/v1/assets/${preview.mp4_asset.id}/content`" /></AppDialog>
  <ThumbnailGenerator :open="!!thumbnail" :src="thumbnail?.mp4_asset ? `/api/v1/assets/${thumbnail.mp4_asset.id}/content` : ''" :title="thumbnail?.clip_title || ''" @close="thumbnail = null" />
</template>
