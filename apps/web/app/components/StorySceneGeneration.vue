<script setup lang="ts">
import { storyVoiceLabel, storyProviderNotice, type StoryScene, type StoryCapabilities, type StoryProduceMode } from '~/utils/story'
const props = defineProps<{scene: StoryScene; capabilities?: StoryCapabilities; disabled: boolean}>()
const emit = defineEmits<{produce: [mode: StoryProduceMode, voice: string, replace: boolean]}>()
const replaceImage = ref(false), replaceVoice = ref(false), voice = ref('')
watch(() => props.scene.id, () => {replaceImage.value = false; replaceVoice.value = false})
watch(() => props.capabilities, value => {if (value && !value.voices.includes(voice.value)) voice.value = value.default_voice}, {immediate:true})
</script>
<template>
  <section class="scene-generation">
    <h3>Buat aset adegan</h3>
    <p class="muted small">Gambar mengikuti catatan visual dan gaya cerita. Suara narator membaca teks narasi adegan ini.</p>
    <p v-if="capabilities?.provider === 'local'" class="muted small">Gambar dan suara dibuat dengan model lokal, tanpa biaya API.</p>
    <label v-if="scene.asset_id" class="checkbox-label"><input v-model="replaceImage" type="checkbox" :disabled="disabled"/>Buat pengganti gambar/video yang dipilih</label>
    <button class="button secondary" :disabled="disabled || !capabilities?.images || (!!scene.asset_id && !replaceImage)" @click="emit('produce','images',voice,replaceImage)">{{ scene.asset_id ? 'Buat gambar pengganti' : 'Buat gambar AI adegan ini' }}</button>
    <label v-if="capabilities?.voices.length">Suara narator<select v-model="voice" :disabled="disabled || !capabilities?.speech"><option v-for="v in capabilities.voices" :key="v" :value="v">{{ storyVoiceLabel(v, capabilities) }}</option></select></label>
    <label v-if="scene.audio_id" class="checkbox-label"><input v-model="replaceVoice" type="checkbox" :disabled="disabled"/>Buat pengganti rekaman yang dipilih</label>
    <button class="button secondary" :disabled="disabled || !capabilities?.speech || !scene.narration.trim() || (!!scene.audio_id && !replaceVoice)" @click="emit('produce','speech',voice,replaceVoice)">{{ scene.audio_id ? 'Buat suara pengganti' : 'Buat suara narator adegan ini' }}</button>
    <p v-if="storyProviderNotice(capabilities)" class="muted small">{{ storyProviderNotice(capabilities) }}</p>
    <p v-else class="muted small">Narator menggunakan suara AI. Aset baru ditampilkan sebagai usulan sebelum mengganti pilihan Anda.</p>
  </section>
</template>
<style scoped>
.scene-generation {display:grid; gap:14px; border-top:1px solid var(--color-border); padding-top:20px; min-width:0;}
.scene-generation h3 {font-size:13px; margin:0;}
.scene-generation p {font-size:12px; line-height:1.6; margin:0;}
.scene-generation label {display:grid; gap:8px; font-size:12px; margin:0;}
.scene-generation .checkbox-label {display:flex; align-items:center; gap:8px;}
.scene-generation select {width:100%; min-width:0;}
.scene-generation button {white-space:normal;}
.scene-generation select {color:var(--color-text); background:var(--color-canvas); border:1px solid var(--color-border); min-height:36px; padding:8px 10px; border-radius:4px;}
.scene-generation h3 {padding-left:10px; border-left:2px solid var(--color-accent);}
</style>
