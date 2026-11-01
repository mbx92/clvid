export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return
  const { user, csrf, initialized } = useSession()
  if (!initialized.value) {
    try {
      const result = await $fetch<any>('/api/v1/auth/me', { credentials: 'include' })
      user.value = result.user || result
      csrf.value = result.csrf_token || ''
    } catch { user.value = null }
    initialized.value = true
  }
  if (!user.value && to.path !== '/login') return navigateTo('/login')
  if (user.value && to.path === '/login') return navigateTo('/')
})
