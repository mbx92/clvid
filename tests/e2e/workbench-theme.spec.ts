import { expect, test, type Locator, type Page } from '@playwright/test'

async function mockReviewQueue(page: Page) {
  const unexpectedRequests: string[] = []
  const scheduledAt = new Date(Date.now() + 86400000).toISOString()
  const posts = Array.from({ length: 18 }, (_, index) => ({
    id: `review-${index + 1}`, project_id: 'project', export_id: 'export', account_id: 'channel',
    account_name: 'Channel dokumenter', platform: 'youtube', title: `Episode ${index + 1}: Catatan produksi dari lapangan`,
    caption: 'Catatan hasil ekspor untuk ditinjau sebelum tayang. Periksa judul, deskripsi, dan waktu pengiriman kepada penonton.',
    status: 'draft', scheduled_at: scheduledAt, timezone: 'Asia/Makassar', version: 1,
    options: { privacy: 'public', audience: 'general' }, automatic: true, preview_url: null, created_at: new Date().toISOString(),
  }))
  // Intercept every API request, including the automatic scan, so this test cannot publish or modify live data.
  await page.route('**/api/v1/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    const fixtures: Record<string, unknown> = {
      '/auth/me': { user: { id: 'owner', email: 'qa@example.test' }, csrf_token: 'test' },
      '/auth/csrf': { csrf_token: 'test' },
      '/social/accounts': {
        items: [{ id: 'channel', platform: 'youtube', name: 'Channel dokumenter', connected: true }],
        platforms: [{ id: 'youtube', configured: true, publishing_ready: true }],
      },
      '/social/automation': { enabled: true, timezone: 'Asia/Makassar', times: ['18:00'], account_ids: [] },
      '/social/youtube/sync': { items: [] },
      '/social/approvals': { items: posts, has_more: false },
      '/social/posts': { items: posts },
      '/social/exports': { items: [{ id: 'export', title: 'Catatan produksi', revision: 1 }] },
    }
    if (request.method() === 'POST' && path === '/social/automation/scan') return route.fulfill({ json: { created: 0 } })
    if (request.method() === 'GET' && path in fixtures) return route.fulfill({ json: fixtures[path] })
    unexpectedRequests.push(`${request.method()} ${path}`)
    return route.fulfill({ status: 404, json: { message: 'Unexpected mocked request' } })
  })
  return unexpectedRequests
}

async function textContrast(control: Locator) {
  return control.evaluate(element => {
    const rgba = (value: string) => {
      const channels = value.match(/[\d.]+/g)!.map(Number)
      return [channels[0]!, channels[1]!, channels[2]!, channels[3] ?? 1]
    }
    const over = (front: number[], back: number[]) => front.slice(0, 3).map((value, i) => value * front[3]! + back[i]! * (1 - front[3]!))
    const ancestors: Element[] = []
    for (let current: Element | null = element; current; current = current.parentElement) ancestors.unshift(current)
    const background = ancestors.reduce((result, ancestor) => over(rgba(getComputedStyle(ancestor).backgroundColor), result), [255, 255, 255])
    const foreground = over(rgba(getComputedStyle(element).color), background)
    const luminance = (color: number[]) => color.map(value => {
      const channel = value / 255
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    }).reduce((result, channel, index) => result + channel * [0.2126, 0.7152, 0.0722][index]!, 0)
    const [lighter, darker] = [luminance(background), luminance(foreground)].sort((a, b) => b - a)
    return (lighter! + 0.05) / (darker! + 0.05)
  })
}

for (const viewport of [{ name: 'desktop', width: 1366, height: 768 }, { name: 'mobile', width: 390, height: 844 }]) {
  test(`${viewport.name}: a long review queue remains readable, scrollable, and keyboard accessible`, async ({ page }, testInfo) => {
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    const unexpectedRequests = await mockReviewQueue(page)
    await page.setViewportSize(viewport)
    await page.goto('/calendar')
    await expect(page.getByText('18 usulan pada halaman ini menunggu persetujuan')).toBeVisible()
    const navigation = page.getByRole('navigation', { name: 'Navigasi utama' })
    for (const name of ['Proyek', 'Studio', 'File', 'Kalender', 'Pengaturan']) {
      await expect(navigation.getByRole('link', { name, exact: true })).toBeInViewport()
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)

    const trigger = page.getByRole('button', { name: 'Tinjau & approve' })
    await trigger.click()
    const dialog = page.getByRole('dialog', { name: 'Persetujuan publikasi otomatis' })
    const close = dialog.getByRole('button', { name: 'Tutup dialog' })
    await expect(close).toBeFocused()
    await expect(dialog.getByRole('button', { name: 'Tolak', exact: true })).toHaveCount(18)
    const bounds = (await dialog.boundingBox())!
    expect(bounds.x).toBeGreaterThanOrEqual(0)
    expect(bounds.y).toBeGreaterThanOrEqual(0)
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width)
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(viewport.height)

    const settings = dialog.locator('summary').filter({ hasText: 'Pengaturan jadwal otomatis' })
    await settings.focus()
    await settings.press('Enter')
    const timeInput = dialog.getByRole('textbox', { name: 'Jam tayang otomatis' })
    const timezone = dialog.getByRole('combobox', { name: 'Zona waktu otomatis' })
    for (const control of [timeInput, timezone]) {
      await control.scrollIntoViewIfNeeded()
      await expect(control).toBeInViewport()
      // Measure rendered controls, rather than CSS zoom, to catch any shrinking mechanism.
      expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(36)
      expect(await textContrast(control)).toBeGreaterThanOrEqual(4.5)
    }
    await timezone.focus()
    await timezone.press('ArrowDown')
    await expect(page.getByRole('listbox', { name: 'Zona waktu otomatis' })).toBeVisible()
    await timezone.press('Escape')
    await expect(page.getByRole('listbox', { name: 'Zona waktu otomatis' })).toBeHidden()
    await expect(dialog).toBeVisible()
    await expect(timezone).toBeFocused()

    const lastReject = dialog.getByRole('button', { name: 'Tolak', exact: true }).last()
    await expect(lastReject).not.toBeInViewport()
    await lastReject.scrollIntoViewIfNeeded()
    await expect(lastReject).toBeInViewport({ ratio: 1 })
    const lastTitle = dialog.getByRole('heading', { name: 'Episode 18: Catatan produksi dari lapangan' })
    expect(await lastTitle.evaluate(element => {
      const range = document.createRange()
      range.selectNodeContents(element)
      return range.getBoundingClientRect().height
    })).toBeGreaterThanOrEqual(16)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`review-scrolled-${viewport.name}.png`) })

    await lastReject.focus()
    await page.keyboard.press('Tab')
    await expect(close).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(lastReject).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
    expect(unexpectedRequests).toEqual([])
    expect(errors).toEqual([])
  })
}
