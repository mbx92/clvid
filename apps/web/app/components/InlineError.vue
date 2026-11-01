<script setup lang="ts">defineProps<{ message: string }>()</script>
<template><div v-if="message" class="inline-error" role="alert"><AppIcon name="CircleAlert" /><span>{{ message }}</span><slot /></div></template>
