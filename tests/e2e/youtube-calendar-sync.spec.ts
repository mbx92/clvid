import { expect, test } from '@playwright/test'

test('YouTube history follows publication time in WITA and cannot be uploaded again from its calendar entry', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  let queued = 0
  const history = { id: 'youtube:history', title: 'Video lama dari YouTube', caption: 'Sudah tayang di channel.', status: 'published',
    platform: 'youtube', account_id: 'channel', account_name: 'Channel terhubung', source: 'youtube', readonly: true,
    scheduled_at: '2025-01-03T16:30:00Z', created_at: '2025-01-03T16:30:00Z', timezone: 'UTC', options: { privacy: 'public' },
    remote_url: 'https://www.youtube.com/watch?v=AAAAAAAAAAA', thumbnail_url: null, preview_url: null }
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { user: { id: 'owner', email: 'qa@example.test' }, csrf_token: 'test' } })
    if (path.endsWith('/auth/csrf')) return route.fulfill({ json: { csrf_token: 'test' } })
    if (path.endsWith('/social/accounts')) return route.fulfill({ json: { items: [{ id: 'channel', platform: 'youtube', name: 'Channel terhubung' }], platforms: [] } })
    if (path.endsWith('/social/automation')) return route.fulfill({ json: { enabled: true, timezone: 'Asia/Makassar', times: ['18:00'], account_ids: [] } })
    if (path.endsWith('/social/automation/scan')) return route.fulfill({ json: { created: 0 } })
    if (path.endsWith('/social/approvals')) return route.fulfill({ json: { items: [], has_more: false } })
    if (path.endsWith('/social/exports')) return route.fulfill({ json: { items: [] } })
    if (path.endsWith('/social/youtube/sync')) {
      if (route.request().method() === 'POST') { queued += 1; return route.fulfill({ status: 202, json: { queued: 1 } }) }
      return route.fulfill({ json: { items: [{ account_id: 'channel', name: 'Channel terhubung', video_count: 1, latest_published_at: history.scheduled_at, last_synced_at: new Date().toISOString().slice(0, 10) + 'T00:00:00Z', pending: false, error_message: null }] } })
    }
    if (path.endsWith('/social/posts')) {
      const at = Date.parse(history.scheduled_at)
      return route.fulfill({ json: { items: at >= Date.parse(url.searchParams.get('start')!) && at < Date.parse(url.searchParams.get('end')!) ? [history] : [] } })
    }
    throw new Error('Unexpected request: ' + path)
  })
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto('/calendar')
  await expect(page.getByRole('region', { name: 'Riwayat YouTube' })).toContainText('1 video sudah tayang')
  await page.getByRole('button', { name: 'Lihat tayangan terbaru' }).click()
  const post = page.locator('.agenda-post').filter({ hasText: history.title })
  await expect(post).toBeVisible()
  await expect(post.locator('.agenda-time')).toHaveText('00:30')
  await expect(page.getByRole('button', { name: '2025-01-04, 1 publikasi', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(post).toContainText('Sudah tayang · YouTube')
  await expect(post.getByRole('button')).toHaveCount(0)
  await expect(post.getByRole('link', { name: /Lihat hasil/ })).toHaveAttribute('href', history.remote_url)
  await page.getByRole('button', { name: 'Sinkronkan YouTube', exact: true }).click()
  await expect.poll(() => queued).toBe(1)
  await expect(page.getByText('Sinkronisasi masuk antrean. Riwayat akan muncul bertahap di kalender.')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('youtube-history-desktop.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('youtube-history-mobile.png'), fullPage: true })
  expect(errors).toEqual([])
})
