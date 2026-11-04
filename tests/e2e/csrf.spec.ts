import { expect, test } from '@playwright/test'

// Isolated browser cookies and intercepted API calls; no user session is changed.
for (const scenario of ['rotated', 'missing'] as const) {
  test(`writes recover from a ${scenario} CSRF cookie without reloading`, async ({ page, context, baseURL }) => {
    let sentToken = ''
    let refreshes = 0
    await context.addCookies([{ name: 'clipper_csrf', value: 'page-token', url: baseURL! }])
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'csrf-test-user', email: 'csrf@example.invalid', csrf_token: 'page-token' } })
      if (path.endsWith('/auth/csrf')) {
        refreshes++
        return route.fulfill({ headers: { 'Set-Cookie': 'clipper_csrf=current-token; Path=/; SameSite=Lax' }, json: { csrf_token: 'current-token' } })
      }
      if (path.endsWith('/auth/logout')) {
        sentToken = route.request().headers()['x-csrf-token'] || ''
        return route.fulfill({ status: 204 })
      }
      if (path.endsWith('/projects')) return route.fulfill({ json: { items: [], total: 0 } })
      return route.fulfill({ status: 404, json: { message: 'Unexpected test request' } })
    })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Proyek', exact: true })).toBeVisible()
    if (scenario === 'rotated') {
      await context.addCookies([{ name: 'clipper_csrf', value: 'current-token', url: baseURL! }])
    } else {
      await context.clearCookies({ name: 'clipper_csrf' })
    }
    await page.getByRole('button', { name: 'Keluar dari akun', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Masuk ke Clipper', exact: true })).toBeVisible()
    expect(sentToken).toBe('current-token')
    expect(refreshes).toBe(scenario === 'missing' ? 1 : 0)
  })
}
