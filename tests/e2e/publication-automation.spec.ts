import { expect, test } from '@playwright/test'

test('automatic proposals require review and explicit approval; rejected proposals disappear', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  let approvals = 0
  const scheduledAt = new Date(Date.now() + 86400000).toISOString()
  const base = { project_id: 'project', export_id: 'export', account_id: 'channel', account_name: 'Channel tujuan', platform: 'youtube',
    caption: 'Caption hasil ekspor', status: 'draft', scheduled_at: scheduledAt, timezone: 'Asia/Makassar', version: 1,
    options: { privacy: 'public', audience: 'general' }, automatic: true, preview_url: null, created_at: new Date().toISOString() }
  let posts = [{ ...base, id: 'one', title: 'Video pertama' }, { ...base, id: 'two', title: 'Video kedua' }]
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { user: { id: 'owner', email: 'qa@example.test' }, csrf_token: 'test' } })
    if (path.endsWith('/auth/csrf')) return route.fulfill({ json: { csrf_token: 'test' } })
    if (path.endsWith('/social/accounts')) return route.fulfill({ json: { items: [{ id: 'channel', platform: 'youtube', name: 'Channel tujuan', connected: true }], platforms: [{ id: 'youtube', configured: true, publishing_ready: true }] } })
    if (path.endsWith('/social/automation')) return route.fulfill({ json: { enabled: true, timezone: 'Asia/Makassar', times: ['18:00'], account_ids: [] } })
    if (path.endsWith('/social/automation/scan')) return route.fulfill({ json: { created: 0 } })
    if (path.endsWith('/social/youtube/sync')) return route.fulfill({ json: { items: [] } })
    if (path.endsWith('/social/approvals')) return route.fulfill({ json: { items: posts.filter(post => post.status === 'draft'), has_more: false } })
    if (path.endsWith('/social/posts')) return route.fulfill({ json: { items: posts } })
    if (path.endsWith('/social/exports')) return route.fulfill({ json: { items: [{ id: 'export', title: 'Video pertama', revision: 1 }] } })
    if (path.endsWith('/one/approve')) {
      expect(route.request().postDataJSON()).toEqual({ expected_version: 1, consent: true })
      approvals += 1; posts[0]!.status = 'scheduled'
      return route.fulfill({ json: posts[0] })
    }
    if (path.endsWith('/two/cancel')) { posts[1]!.status = 'cancelled'; return route.fulfill({ json: posts[1] }) }
    return route.fulfill({ status: 404, json: { message: 'Unexpected test request' } })
  })
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto('/calendar')
  await page.getByRole('button', { name: 'Tinjau & approve' }).click()
  const dialog = page.getByRole('dialog', { name: 'Persetujuan publikasi otomatis' })
  await expect(dialog).toContainText('Channel tujuan')
  await expect(dialog).toContainText('Visibilitas: Publik')
  await expect(dialog.locator('.automation-card')).toHaveCount(2)
  expect(approvals).toBe(0)
  await dialog.locator('.automation-card').filter({ hasText: 'Video pertama' }).getByRole('button', { name: 'Edit', exact: true }).click()
  const editor = page.getByRole('dialog', { name: 'Edit jadwal publikasi' })
  await expect(editor.getByLabel('Judul publikasi', { exact: true })).toHaveValue('Video pertama')
  await expect(editor.getByLabel('Saya menyetujui pengiriman video dan metadata ini ke akun tujuan pada waktu yang dipilih.')).not.toBeChecked()
  await editor.getByRole('button', { name: 'Tutup dialog' }).click()
  await page.getByRole('button', { name: 'Tinjau & approve' }).click()
  await page.screenshot({ path: testInfo.outputPath('approval-desktop.png') })
  await dialog.locator('.automation-card').filter({ hasText: 'Video pertama' }).getByRole('button', { name: 'Setujui & jadwalkan' }).click()
  await expect(dialog.locator('.automation-card')).toHaveCount(1)
  expect(approvals).toBe(1)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(dialog.getByRole('button', { name: 'Tolak', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('approval-mobile.png') })
  await dialog.getByRole('button', { name: 'Tolak', exact: true }).click()
  await expect(dialog.locator('.automation-card')).toHaveCount(0)
  expect(approvals).toBe(1)
  expect(errors).toEqual([])
})
