import { expect, test, type Page } from '@playwright/test'

async function connections(page: Page) {
  const channels = [{ id: 'channel-one', platform: 'youtube', name: 'Channel Utama', connected: true }]
  let starts = 0
  const deletes: string[] = []
  await page.route('https://accounts.google.com/**', route => route.fulfill({ contentType: 'text/html', body: '<p>Google authorization fixture</p>' }))
  await page.route('**/api/v1/**', route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (request.method() === 'DELETE') deletes.push(path)
    if (path === '/api/v1/auth/me') return route.fulfill({ headers: { 'Set-Cookie': 'clipper_csrf=test-csrf; Path=/; SameSite=Lax' }, json: { user: { id: 'test-user', email: 'test@example.invalid' }, csrf_token: 'test-csrf' } })
    if (path === '/api/v1/settings') return route.fulfill({ json: { max_video_seconds: 3600, max_upload_bytes: 2147483648, max_clip_ms: 180000 } })
    if (path === '/api/v1/usage') return route.fulfill({ json: { items: [], storage_bytes: 0 } })
    if (path === '/api/v1/social/accounts') return route.fulfill({ json: {
      items: channels,
      platforms: ['youtube', 'instagram', 'tiktok'].map(id => ({ id, configured: true, publishing_ready: true, callback_url: `http://localhost/api/v1/social/oauth/${id}/callback` })),
    } })
    if (path === '/api/v1/social/oauth/youtube/start' && request.method() === 'POST') {
      starts++
      return route.fulfill({ json: { url: 'https://accounts.google.com/o/oauth2/v2/auth?prompt=consent%20select_account' } })
    }
    if (path === '/api/v1/social/exports' || path === '/api/v1/social/posts') return route.fulfill({ json: { items: [] } })
    return route.fulfill({ status: 404, json: { message: 'Unexpected test request' } })
  })
  return { channels, deletes, starts: () => starts }
}

test('adding a second YouTube channel starts authorization and retains both calendar destinations', async ({ page }) => {
  const fixture = await connections(page)
  await page.goto('/settings?section=accounts')
  await expect(page.getByText('Channel Utama', { exact: true })).toBeVisible()
  await expect(page.getByText(/Hubungkan setiap channel secara terpisah/)).toBeVisible()
  await page.getByRole('button', { name: 'Tambah channel YouTube', exact: true }).click()
  await expect(page).toHaveURL(/accounts\.google\.com\/o\/oauth2\/v2\/auth/)
  expect(fixture.starts()).toBe(1)
  expect(fixture.deletes).toEqual([])

  // Simulate Google's callback after the user authorizes a distinct identity.
  fixture.channels.push({ id: 'channel-two', platform: 'youtube', name: 'Channel Kedua', connected: true })
  await page.goto('/settings?section=accounts&connection=connected')
  await expect(page.getByText('Akun berhasil dihubungkan.', { exact: true })).toBeVisible()
  await expect(page.getByText('Channel Utama', { exact: true })).toBeVisible()
  await expect(page.getByText('Channel Kedua', { exact: true })).toBeVisible()
  for (const width of [1366, 390]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)
  }
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.screenshot({ path: test.info().outputPath('youtube-connections.png'), fullPage: true })

  await page.goto('/calendar')
  await page.getByRole('button', { name: 'Tambah jadwal', exact: true }).click()
  const destination = page.getByRole('combobox', { name: 'Akun tujuan', exact: true })
  await expect(destination).toBeEnabled()
  await expect(destination).toContainText('Belum dipilih (draft)')
  await destination.click()
  await expect(page.getByRole('option', { name: 'Channel Utama', exact: true })).toBeVisible()
  await page.getByRole('option', { name: 'Channel Kedua', exact: true }).click()
  await expect(destination).toContainText('Channel Kedua')
  expect(fixture.deletes).toEqual([])
})

test('reconnecting the same YouTube identity does not claim another channel was added', async ({ page }) => {
  const fixture = await connections(page)
  await page.goto('/settings?section=accounts&connection=reconnected')
  await expect(page.getByText('Koneksi akun yang sudah ada diperbarui. Tidak ada akun baru yang ditambahkan.', { exact: true })).toBeVisible()
  await expect(page.getByText('Akun berhasil dihubungkan.', { exact: true })).toHaveCount(0)
  await expect(page.locator('.connected-account')).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Tambah channel YouTube', exact: true })).toBeEnabled()
  expect(fixture.starts()).toBe(0)
  expect(fixture.deletes).toEqual([])
})
