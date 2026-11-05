<script setup lang="ts">
const { user, csrf } = useSession()
const api = useApi()
const route = useRoute()
const error = ref('')
const workspaceLinks = [
  { to: '/', label: 'Proyek', hint: 'Bahan & klip', icon: 'FolderOpen', number: '01' },
  { to: '/studio', label: 'Studio', hint: 'Naskah & adegan', icon: 'Film', number: '02' },
  { to: '/files', label: 'File', hint: 'Media & penyimpanan', icon: 'HardDrive', number: '03' },
  { to: '/calendar', label: 'Kalender', hint: 'Review & publikasi', icon: 'CalendarDays', number: '04' },
]
const selectedLink = (to: string) => to === '/' ? route.path === '/' || route.path.startsWith('/projects/') || route.path.startsWith('/clips/') : route.path.startsWith(to)
const logout = async () => { try { await api('/auth/logout', { method: 'POST' }); user.value = null; csrf.value = ''; await navigateTo('/login') } catch (e) { error.value = errorMessage(e) } }
</script>
<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">Lewati ke konten</a>
    <aside class="sidebar">
      <NuxtLink to="/" class="brand" aria-label="Clipper, halaman proyek"><span class="brand-mark"><svg viewBox="0 0 32 32" width="30" height="30" fill="none" aria-hidden="true"><path d="M11 5H5v22h6M21 5h6v22h-6" stroke="currentColor" stroke-width="2.5"/><path d="M19 9 13 23" stroke="currentColor" stroke-width="3"/></svg></span><span>clipper<span class="brand-period">.</span></span></NuxtLink>
      <span class="sidebar-caption">Ruang produksi video</span>
      <span class="nav-section-label">Ruang kerja</span>
      <nav class="main-nav" aria-label="Navigasi utama">
        <NuxtLink v-for="link in workspaceLinks" :key="link.to" :to="link.to" :class="{ selected: selectedLink(link.to) }" :aria-label="link.label"><AppIcon :name="link.icon" /><span class="nav-copy"><span>{{ link.label }}</span><small>{{ link.hint }}</small></span><span class="nav-number" aria-hidden="true">{{ link.number }}</span></NuxtLink>
        <NuxtLink to="/settings" class="settings-nav-link" :class="{ selected: route.path === '/settings' }" aria-label="Pengaturan"><AppIcon name="Settings2" /><span class="nav-copy"><span>Pengaturan</span><small>Akun & preferensi</small></span></NuxtLink>
      </nav>
      <div class="sidebar-footer"><span class="sidebar-workspace-label">WORKSPACE LOKAL</span><div class="account"><span class="account-avatar" aria-hidden="true">{{ user?.email?.[0]?.toUpperCase() || 'C' }}</span><div class="account-info"><span>{{ user?.email }}</span><small>Akun pengguna</small></div><button class="icon-button" aria-label="Keluar dari akun" @click="logout"><AppIcon name="LogOut" :size="17" /></button></div></div>
    </aside>
    <main id="main-content" class="main-content" tabindex="-1"><InlineError :message="error" /><slot /></main>
  </div>
</template>
