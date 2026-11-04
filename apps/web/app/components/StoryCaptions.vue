<script setup lang="ts">
import { hasTimedCaptions, type StoryScene } from '~/utils/story'
const props = defineProps<{ scene: StoryScene; disabled?: boolean; alignmentAvailable?: boolean }>()
const emit = defineEmits<{ align: [] }>()
const timed = computed(() => hasTimedCaptions(props.scene))
function clear() {props.scene.captions = []; props.scene.caption_audio_id = null; props.scene.caption_narration = ''}
function add() {
  if (!props.scene.audio_id) return
  const start = props.scene.captions.at(-1)?.end_ms || 0
  if (start >= props.scene.duration_ms) return
  props.scene.captions.push({start_ms:start,end_ms:Math.min(start+2000,props.scene.duration_ms),text:''})
  props.scene.caption_audio_id = props.scene.audio_id; props.scene.caption_narration = props.scene.narration
}
</script>
<template>
  <section class="caption-editor">
    <div class="caption-heading"><h3>Subtitle & waktu</h3><span :class="{timed}">{{ timed ? 'Mengikuti audio' : 'Timing perkiraan' }}</span></div>
    <p v-if="!scene.audio_id" class="muted small">Pilih rekaman atau buat suara narator untuk menyusun subtitle dari audio. Tanpa rekaman, teks narasi dibagi sepanjang adegan.</p>
    <p v-else-if="scene.captions.length && !timed" class="notice">Audio atau narasi sudah berubah. Susun ulang subtitle agar waktunya mengikuti rekaman yang dipilih.</p>
    <p v-else-if="!timed" class="muted small">Subtitle masih dibagi rata sepanjang adegan. Susun dari audio untuk mengikuti ucapan dan jeda.</p>
    <button class="button secondary" :disabled="disabled || !scene.audio_id || !alignmentAvailable" @click="emit('align')">Susun subtitle dari audio</button>
    <details v-if="scene.audio_id" class="cue-details"><summary>Edit teks & waktu{{ scene.captions.length ? ` (${scene.captions.length})` : '' }}</summary>
      <p class="muted small">Waktu dihitung dari awal adegan. Cue harus berurutan, tidak bertumpuk, dan berada di dalam durasi adegan.</p>
      <div v-for="(cue,i) in scene.captions" :key="i" class="caption-cue">
        <div class="cue-top"><strong>{{ i+1 }}</strong><label>Mulai {{ i+1 }} (detik)<input :value="cue.start_ms/1000" type="number" min="0" :max="scene.duration_ms/1000" step="0.01" :disabled="disabled" @input="cue.start_ms = Math.round(Number(($event.target as HTMLInputElement).value)*1000)"/></label><label>Selesai {{ i+1 }} (detik)<input :value="cue.end_ms/1000" type="number" min="0" :max="scene.duration_ms/1000" step="0.01" :disabled="disabled" @input="cue.end_ms = Math.round(Number(($event.target as HTMLInputElement).value)*1000)"/></label><button class="icon-button" :aria-label="`Hapus subtitle ${i+1}`" :disabled="disabled" @click="scene.captions.splice(i,1)"><AppIcon name="X" :size="14"/></button></div>
        <label class="sr-only" :for="`story-cue-${scene.id}-${i}`">Teks subtitle {{ i+1 }}</label><textarea :id="`story-cue-${scene.id}-${i}`" v-model="cue.text" rows="2" maxlength="200" :disabled="disabled"/>
      </div>
      <div class="cue-actions"><button class="button secondary" :disabled="disabled || scene.captions.length >= 200 || (scene.captions.at(-1)?.end_ms || 0) >= scene.duration_ms || (!!scene.captions.length && !timed)" @click="add">Tambah subtitle</button><button v-if="scene.captions.length" class="text-button" :disabled="disabled" @click="clear">Hapus timing subtitle</button></div>
    </details>
    <button v-if="!scene.audio_id && scene.captions.length" class="text-button" :disabled="disabled" @click="clear">Hapus timing subtitle lama</button>
  </section>
</template>
<style scoped>
.caption-editor {display:grid; gap:14px; border-top:1px solid #e3e8e0; padding-top:20px; min-width:0;}
.caption-heading {display:flex; align-items:center; justify-content:space-between; gap:8px;}
.caption-heading h3 {font-size:13px; margin:0;}
.caption-heading span {font-size:10px; color:#866321;}
.caption-heading .timed {color:#2b694b;}
.caption-editor p {margin:0; font-size:12px; line-height:1.6;}
.cue-details summary {font-size:12px; cursor:pointer;}
.cue-details > p {margin:12px 0;}
.caption-cue {margin:12px 0; display:grid; gap:8px;}
.cue-top {display:grid; grid-template-columns:18px minmax(0,1fr) minmax(0,1fr) 28px; align-items:end; gap:8px;}
.cue-top strong {font-size:11px; align-self:center; color:#77847a;}
.cue-top label {display:grid; gap:6px; font-size:10px; margin:0;}
.cue-top input,.caption-cue textarea {width:100%; min-width:0; font-size:12px;}
.cue-actions {display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-top:12px;}
</style>
