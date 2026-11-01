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
  <main class="login-page">
    <div class="login-brand brand"><span class="brand-mark"><AppIcon name="Scissors" :size="22" /></span>Clipper</div>
    <section class="login-panel"><span class="eyebrow">Ruang kerja video</span><h1>Masuk ke Clipper</h1><p class="muted">Lanjutkan memilih dan menyunting klip Anda.</p>
      <form class="form-stack" @submit.prevent="login"><label>Email<input v-model="email" type="email" autocomplete="username" placeholder="nama@contoh.com" required :disabled="busy" /></label><label>Kata sandi<input v-model="password" type="password" autocomplete="current-password" required :disabled="busy" minlength="1" /></label><InlineError :message="error" /><button class="button primary full-width" :disabled="busy" type="submit">{{ busy ? 'Sedang masuk…' : 'Masuk' }}<AppIcon name="ArrowRight" :size="17" /></button></form>
      <p class="login-note">Akun dibuat oleh pengelola melalui CLI lokal.<br />Hubungi pengelola untuk mengatur ulang kata sandi.</p>
    </section><p class="login-footer">Video dan transkripsi diproses di server instalasi ini.</p>
  </main>
</template>
