import { expect, test, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const video = { id: 'aqz-KE-bpKQ', url: 'https://www.youtube.com/watch?v=aqz-KE-bpKQ', thumbnail_url: 'https://i.ytimg.com/vi/aqz-KE-bpKQ/hqdefault.jpg', title: 'Percakapan tentang kopi', channel: 'Channel contoh uji', description: 'Diskusi proses produksi kopi.', duration_ms: 300000, view_count: 12000 }

async function mockApi(page: Page, options: { ai?: boolean; retry?: boolean; empty?: boolean; failure?: boolean } = {}) {
  const calls = { projects: 0, searches: [] as any[], imports: [] as { key: string | undefined; body: any }[] }
  await page.route('https://i.ytimg.com/**', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#d9ddd7"/></svg>' }))
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body })
    if (path === '/auth/me') return json({ user: { id: 'test-user', email: 'test@example.test' }, csrf_token: 'test-csrf' })
    if (path === '/auth/csrf') return json({ csrf_token: 'test-csrf' })
    if (path === '/settings') return json({ deepseek_configured: options.ai !== false, limits: { max_clip_ms: 60000 }, max_video_seconds: 3600 })
    if (path === '/research/search') {
      calls.searches.push(request.postDataJSON())
      if (options.failure) return json({ message: 'Pencarian video sementara tidak tersedia. Coba lagi.' }, 502)
      return json({ query: request.postDataJSON().query, items: options.empty ? [] : [video], message: null })
    }
    if (path === '/projects' && request.method() === 'POST') { calls.projects++; return json({ id: 'research-project' }, 201) }
    if (path === '/projects/research-project/source-url') {
      calls.imports.push({ key: request.headers()['idempotency-key'], body: request.postDataJSON() })
      if (options.retry && calls.imports.length === 1) return json({ message: 'Antrean sedang sibuk. Coba kembali.' }, 503)
      return json({ id: 'import-job', project_id: 'research-project', kind: 'import_url', status: 'queued' }, 202)
    }
    if (path === '/projects/research-project') return json({ id: 'research-project', name: video.title, status: 'importing', lifecycle_state: 'active', jobs: [], limits: { max_clip_ms: 60000 } })
    if (/\/projects\/research-project\/(clips|exports)$/.test(path)) return json({ items: [], total: 0 })
    return json({ message: 'Unexpected test request: ' + path }, 404)
  })
  return calls
}

test('research selects a source and starts automatic clipping with settings', async ({ page }) => {
  const calls = await mockApi(page)
  await page.goto('/studio/research')
  await expect(page.getByRole('button', { name: 'Buat klip otomatis', exact: true })).toBeDisabled()
  await page.getByLabel('Topik atau kata kunci').fill('kopi Indonesia')
  await page.getByRole('button', { name: 'Cari video', exact: true }).click()
  await page.getByRole('button', { name: `Pilih sumber: ${video.title}` }).click()
  expect(calls.projects).toBe(0)
  await expect(page.getByLabel('Nama proyek')).toHaveValue(video.title)
  await page.getByRole('combobox', { name: 'Jenis konten', exact: true }).click()
  await page.getByRole('option', { name: 'Game / gameplay', exact: true }).click()
  await page.getByLabel('Analisis frame video dengan AI', { exact: true }).check()
  const screenshots = resolve(import.meta.dirname, '../../.artifacts/ui')
  mkdirSync(screenshots, { recursive: true })
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: resolve(screenshots, `video-research-${width}.png`), fullPage: true })
  }
  await page.getByRole('button', { name: 'Buat klip otomatis', exact: true }).click()
  await expect(page).toHaveURL(/\/projects\/research-project$/)
  expect(calls.projects).toBe(1)
  expect(calls.searches).toEqual([{ query: 'kopi Indonesia', count: 6 }])
  expect(calls.imports).toHaveLength(1)
  expect(calls.imports[0].key).toBeTruthy()
  expect(calls.imports[0].body).toEqual({ url: video.url, process: { language: 'auto', content_profile: 'gaming', visual_analysis: true, count: 3, min_duration_ms: 50000, max_duration_ms: 60000, analyze: true, transcribe_again: false } })
})

test('retry reuses the project, immutable settings, and idempotency key', async ({ page }) => {
  const calls = await mockApi(page, { retry: true })
  await page.goto('/studio/research')
  await page.getByLabel('Topik atau kata kunci').fill('kopi')
  await page.getByRole('button', { name: 'Cari video', exact: true }).click()
  await page.getByRole('button', { name: `Pilih sumber: ${video.title}` }).click()
  await page.getByRole('button', { name: 'Buat klip otomatis', exact: true }).click()
  await expect(page.getByText('Antrean sedang sibuk. Coba kembali.')).toBeVisible()
  await expect(page.getByLabel('Jumlah klip', { exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Coba mulai lagi', exact: true }).click()
  await expect(page).toHaveURL(/\/projects\/research-project$/)
  expect(calls.projects).toBe(1)
  expect(calls.imports).toHaveLength(2)
  expect(calls.imports[1]).toEqual(calls.imports[0])
})

test('missing AI configuration blocks imports while allowing source research', async ({ page }) => {
  const calls = await mockApi(page, { ai: false })
  await page.goto('/studio/research')
  await page.getByLabel('Topik atau kata kunci').fill('kopi')
  await page.getByRole('button', { name: 'Cari video', exact: true }).click()
  await page.getByRole('button', { name: `Pilih sumber: ${video.title}` }).click()
  await expect(page.getByText(/AI pemilih klip belum dikonfigurasi/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Buat klip otomatis', exact: true })).toBeDisabled()
  expect(calls.projects).toBe(0)
  expect(calls.imports).toHaveLength(0)
})

test('search failure stays visible and creates no project', async ({ page }) => {
  const calls = await mockApi(page, { failure: true })
  await page.goto('/studio/research')
  await page.getByLabel('Topik atau kata kunci').fill('kopi')
  await page.getByRole('button', { name: 'Cari video', exact: true }).click()
  await expect(page.getByText('Pencarian video sementara tidak tersedia. Coba lagi.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Cari video', exact: true })).toBeEnabled()
  expect(calls.projects).toBe(0)
})

test('no matching sources shows a useful empty result', async ({ page }) => {
  await mockApi(page, { empty: true })
  await page.goto('/studio/research')
  await page.getByLabel('Topik atau kata kunci').fill('kopi')
  await page.getByRole('button', { name: 'Cari video', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Belum ada sumber yang cocok' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Buat klip otomatis', exact: true })).toBeDisabled()
})
