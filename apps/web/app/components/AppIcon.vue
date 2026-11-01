<script setup lang="ts">
import { CalendarDays, ChevronLeft, ArrowLeft, ArrowRight, Check, ChevronDown, ChevronRight, CircleAlert, Clock3, Download, FileText, Film, FolderOpen, LogOut, Menu, MoreHorizontal, Pause, Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Trash2, Upload, X } from '@lucide/vue'
const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })
const icons: Record<string, any> = { CalendarDays, ChevronLeft, ArrowLeft, ArrowRight, Check, ChevronDown, ChevronRight, CircleAlert, Clock3, Download, FileText, Film, FolderOpen, LogOut, Menu, MoreHorizontal, Pause, Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Trash2, Upload, X }
</script>
<template><component :is="icons[props.name] || CircleAlert" :size="size" :stroke-width="1.7" aria-hidden="true" /></template>
