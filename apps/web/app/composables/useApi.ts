import type { User } from '~/types/api'

export function useSession() {
  const user = useState<User | null>('user', () => null)
  const csrf = useState<string>('csrf', () => '')
  const initialized = useState<boolean>('auth-initialized', () => false)
  return { user, csrf, initialized }
}

export function errorMessage(error: any): string {
  return error?.data?.message || error?.data?.detail?.message || (typeof error?.data?.detail === 'string' ? error.data.detail : '') || error?.message || 'Permintaan gagal. Periksa koneksi lalu coba lagi.'
}

export function useApi() {
  const { csrf, user } = useSession()
  return async function api<T = any>(path: string, options: Record<string, any> = {}): Promise<T> {
    const method = (options.method || 'GET').toUpperCase()
    const headers: Record<string, string> = { ...options.headers }
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrf.value) headers['X-CSRF-Token'] = csrf.value
    try {
      return await $fetch<T>(`/api/v1${path}`, { ...options, headers, credentials: 'include' }) as T
    } catch (error: any) {
      if (error?.status === 401 && path !== '/auth/login') {
        user.value = null
        if (import.meta.client && window.location.pathname !== '/login') await navigateTo('/login')
      }
      throw error
    }
  }
}

export function idempotencyKey(): string { return crypto.randomUUID() }
