<script setup lang="ts">
definePageMeta({ layout: false })
const { user, csrf, initialized } = useSession()
const api = useApi()
const email = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')
const login = async () => {
  busy.value = true; error.value = ''
  try {
    const token = await api<{ csrf_token: string }>('/auth/csrf')
    csrf.value = token.csrf_token
    const response = await api<any>('/auth/login', { method: 'POST', body: { email: email.value, password: password.value } })
    user.value = response.user || response; csrf.value = response.csrf_token || csrf.value; initialized.value = true
    password.value = ''; await navigateTo('/')
  } catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
</script>
<template>
  <main class="login-page production-login">
    <header class="login-masthead"><div class="login-brand brand"><span class="brand-mark"><svg viewBox="0 0 32 32" width="30" height="30" fill="none" aria-hidden="true"><path d="M11 5H5v22h6M21 5h6v22h-6" stroke="currentColor" stroke-width="2.5" /><path d="M19 9 13 23" stroke="currentColor" stroke-width="3" /></svg></span><span>clipper<span class="brand-period">.</span></span><span class="login-edition">VIDEO WORKSPACE</span></div><span class="login-environment">Instalasi lokal</span></header>
    <div class="login-workbench">
      <section class="login-context" aria-label="Ruang produksi video">
        <div class="login-frame" aria-hidden="true"><span class="frame-corner frame-corner-tl" /><span class="frame-corner frame-corner-tr" /><span class="frame-corner frame-corner-bl" /><span class="frame-corner frame-corner-br" /><div class="frame-cut"><span /><span /><span /></div><span class="frame-center-line" /></div>
        <div><p class="eyebrow">Dari sumber ke tayangan</p><h2>Ruang produksi<br />untuk cerita Anda.</h2><p class="login-context-copy">Pilih momen. Rapikan klip.<br />Siapkan konten untuk ditayangkan.</p></div>
        <ol class="login-workflow"><li><span>01</span>Impor</li><li><span>02</span>Edit</li><li><span>03</span>Tayangkan</li></ol>
      </section>
      <section class="login-panel">
        <div class="login-form-heading"><p class="eyebrow">Akses workspace</p><h1>Masuk ke Clipper</h1><p class="muted">Lanjutkan pekerjaan terakhir Anda.</p></div>
        <form class="form-stack" @submit.prevent="login">
          <label>Email<input v-model="email" type="email" autocomplete="username" placeholder="nama@contoh.com" required :disabled="busy" /></label>
          <label>Kata sandi<input v-model="password" type="password" autocomplete="current-password" required :disabled="busy" minlength="1" /></label>
          <InlineError :message="error" />
          <button class="button primary full-width" :disabled="busy" type="submit">{{ busy ? 'Sedang masuk…' : 'Masuk' }}<AppIcon name="ArrowRight" :size="17" /></button>
        </form>
        <p class="login-note">Gunakan akun dari pengelola workspace. Hubungi pengelola jika Anda perlu mengatur ulang kata sandi.</p>
      </section>
    </div>
    <footer class="login-footer"><span><AppIcon name="HardDrive" :size="14" />Video dan transkripsi diproses di instalasi ini.</span><span>CLIPPER / RUANG KERJA VIDEO</span></footer>
  </main>
</template>
