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

let csrfRefresh: Promise<string> | null = null

// Cookies are shared between tabs; Nuxt state is not. Read the current cookie
// immediately before a write so a login in another tab cannot leave a stale header.
export async function prepareCsrfToken(): Promise<string> {
  const { csrf } = useSession()
  if (typeof document === 'undefined') return csrf.value
  const cookie = document.cookie.match(/(?:^|;\s*)clipper_csrf=([^;]*)/)?.[1]
  if (cookie) {
    csrf.value = cookie
    return cookie
  }
  // Recover a missing cookie once, even when several requests start together.
  if (!csrfRefresh) {
    csrfRefresh = $fetch<{ csrf_token: string }>('/api/v1/auth/csrf', {
      credentials: 'include', cache: 'no-store', retry: 0,
    }).then(result => result.csrf_token).finally(() => { csrfRefresh = null })
  }
  csrf.value = await csrfRefresh
  return csrf.value
}

export function useApi() {
  const { user } = useSession()
  return async function api<T = any>(path: string, options: Record<string, any> = {}): Promise<T> {
    const method = (options.method || 'GET').toUpperCase()
    const headers: Record<string, string> = { ...options.headers }
    try {
      if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers['X-CSRF-Token'] = await prepareCsrfToken()
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
