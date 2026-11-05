<script setup lang="ts">
// Keep control sizes readable. Content scrolls inside the available workspace.
withDefaults(defineProps<{ fit?: boolean }>(), { fit: true })
</script>
<template><div class="desktop-fit" :class="{ 'desktop-fit-scroll': !fit }"><div class="desktop-fit-content"><slot /></div></div></template>
<style scoped>.desktop-fit { overflow: auto; overscroll-behavior: contain; } .desktop-fit-content { min-height: 0; }</style>
