<script setup lang="ts">
const { user, csrf } = useSession()
const api = useApi()
const route = useRoute()
const error = ref('')
const logout = async () => { try { await api('/auth/logout', { method: 'POST' }); user.value = null; csrf.value = ''; await navigateTo('/login') } catch (e) { error.value = errorMessage(e) } }
</script>
<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">Lewati ke konten</a>
    <aside class="sidebar">
      <NuxtLink to="/" class="brand" aria-label="Clipper, halaman proyek"><span class="brand-mark"><AppIcon name="Scissors" :size="22" /></span><span>Clipper</span></NuxtLink>
      <span class="sidebar-caption">Ruang kerja video</span>
      <nav class="main-nav" aria-label="Navigasi utama"><NuxtLink to="/" :class="{ selected: !['/settings', '/calendar'].includes(route.path) }"><AppIcon name="FolderOpen" />Proyek</NuxtLink><NuxtLink to="/calendar" :class="{ selected: route.path === '/calendar' }"><AppIcon name="CalendarDays" /><span>Kalender</span></NuxtLink><NuxtLink to="/settings" :class="{ selected: route.path === '/settings' }"><AppIcon name="Settings2" />Pengaturan</NuxtLink></nav>
      <div class="account"><span class="account-avatar" aria-hidden="true">{{ user?.email?.[0]?.toUpperCase() || 'C' }}</span><div class="account-info"><span>{{ user?.email }}</span><small>Instalasi lokal</small></div><button class="icon-button" aria-label="Keluar dari akun" @click="logout"><AppIcon name="LogOut" :size="17" /></button></div>
    </aside>
    <main id="main-content" class="main-content" tabindex="-1"><InlineError :message="error" /><slot /></main>
  </div>
</template>

<style scoped>
@media (max-width: 550px) {
  .sidebar { height: auto; min-height: 96px; flex-wrap: wrap; padding: 6px 12px; gap: 4px 8px; }
  .brand { flex: none; }
  .account { margin-left: auto; flex: none; }
  .main-nav { order: 3; flex: 0 0 100%; justify-content: space-between; gap: 3px; }
  .main-nav a { padding: 7px 5px; gap: 4px; font-size: 11px; }
}
</style>
