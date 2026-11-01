import { test, expect, type Page } from '@playwright/test'
import { readFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '../..')
const artifacts = resolve(root, '.artifacts/ui')
mkdirSync(artifacts, { recursive: true })
const email = process.env.CLIPPER_E2E_EMAIL!
const password = process.env.CLIPPER_E2E_PASSWORD!
const report = JSON.parse(readFileSync(resolve(root, '.artifacts/smoke-report.json'), 'utf8'))

async function login(page: Page, account = email, secret = password) {
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(account)
  await page.getByLabel('Kata sandi', { exact: true }).fill(secret)
  await page.getByLabel('Kata sandi', { exact: true }).press('Enter')
  await expect(page.getByRole('heading', { name: 'Proyek', exact: true })).toBeVisible()
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
}

test('real upload, keyboard edit, crop, save, render and download', async ({ page }) => {
  test.setTimeout(180_000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1000 })
  await login(page)
  await page.getByRole('button', { name: 'Proyek baru', exact: true }).click()
  const upload = page.getByRole('dialog', { name: 'Proyek baru' })
  await upload.getByLabel('Nama proyek').fill(`E2E editorial ${Date.now()}`)
  await upload.locator('input[type=file]').setInputFiles(resolve(root, '.artifacts/fixture-source.mp4'))
  await upload.getByRole('button', { name: 'Unggah video', exact: true }).click()
  await expect(page).toHaveURL(/\/projects\//)
  await expect(page.getByRole('button', { name: 'Klip manual', exact: true })).toBeVisible({ timeout: 60_000 })
  await page.getByRole('button', { name: 'Klip manual', exact: true }).focus()
  await page.keyboard.press('Enter')
  const manual = page.getByRole('dialog', { name: 'Buat klip manual' })
  await manual.getByLabel('Judul klip').fill('Klip dari pengujian browser')
  await manual.getByLabel('Mulai', { exact: true }).fill('00:01.000')
  await manual.getByLabel('Selesai', { exact: true }).fill('00:08.000')
  await manual.getByRole('button', { name: 'Buat klip', exact: true }).press('Enter')
  await expect(page).toHaveURL(/\/clips\//)
  await page.getByRole('button', { name: 'Tambah subtitle' }).press('Enter')
  await page.getByLabel('Teks subtitle 1').fill('Koreksi subtitle dari browser.')
  await page.getByLabel('Masuk', { exact: true }).fill('00:01.200')
  await page.getByLabel('Keluar', { exact: true }).fill('00:07.700')
  await page.getByRole('button', { name: 'Terapkan batas', exact: true }).press('Enter')
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await page.getByRole('slider', { name: /Posisi horizontal/ }).focus()
  await page.keyboard.press('End')
  await page.getByRole('button', { name: 'Simpan', exact: true }).press('Enter')
  await expect(page.getByText('Revisi 2', { exact: true })).toBeVisible()
  await expect(page.getByText('Tersimpan', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Ekspor', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Ekspor klip' })
  await dialog.getByRole('combobox', { name: 'Resolusi ekspor' }).press('ArrowDown')
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  await dialog.getByRole('button', { name: 'Mulai ekspor' }).press('Enter')
  await expect(page.getByRole('link', { name: 'Unduh MP4' })).toBeVisible({ timeout: 90_000 })
  await page.getByRole('button', { name: 'Lihat hasil' }).click()
  await expect(page.getByRole('dialog', { name: 'Hasil revisi 2' })).toBeVisible()
  await expect.poll(() => page.locator('.final-video').evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(1)
  await page.keyboard.press('Escape')
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Unduh SRT' }).click()
  const download = await downloadEvent
  const srtPath = resolve(root, '.artifacts/e2e.srt')
  await download.saveAs(srtPath)
  expect(readFileSync(srtPath, 'utf8')).toContain('Koreksi subtitle dari browser.')
  await noOverflow(page)
  expect(errors).toEqual([])
})

test('stale editor keeps draft and resolves revision conflict through a custom dialog', async ({ page, context }) => {
  await login(page)
  const csrf = (await context.cookies()).find(c => c.name === 'clipper_csrf')!.value
  const created = await context.request.post(`/api/v1/projects/${report.project_id}/clips`, {
    headers: { 'X-CSRF-Token': csrf },
    data: { title: 'Uji konflik revisi', start_ms: 0, end_ms: 6000 },
  })
  expect(created.ok()).toBeTruthy()
  const clip = await created.json()
  await page.goto(`/clips/${clip.id}`)
  await expect(page.getByLabel('Judul klip', { exact: true })).toHaveValue('Uji konflik revisi')
  const other = await context.newPage()
  await other.goto(`/clips/${clip.id}`)
  await expect(other.getByLabel('Judul klip', { exact: true })).toHaveValue('Uji konflik revisi')
  await page.getByLabel('Judul klip', { exact: true }).fill('Tersimpan dari tab pertama')
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect(page.getByText('Revisi 2', { exact: true })).toBeVisible()
  await other.getByLabel('Judul klip', { exact: true }).fill('Koreksi tab kedua masih ada')
  await other.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect(other.getByRole('dialog', { name: 'Revisi sudah berubah' })).toBeVisible()
  await other.getByRole('button', { name: 'Kembali ke perubahan saya' }).click()
  await expect(other.getByLabel('Judul klip', { exact: true })).toHaveValue('Koreksi tab kedua masih ada')
  await other.getByRole('button', { name: 'Simpan', exact: true }).click()
  await other.getByRole('button', { name: 'Muat revisi terbaru' }).click()
  await expect(other.getByLabel('Judul klip', { exact: true })).toHaveValue('Tersimpan dari tab pertama')
  await other.close()
})

for (const width of [1440, 1024, 768, 390]) {
  test(`workspace visual states and keyboard dialogs at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    await login(page)
    await page.screenshot({ path: resolve(artifacts, `projects-${width}.png`), fullPage: true })
    await noOverflow(page)
    await page.getByRole('button', { name: /Hapus proyek Uji pipeline nyata/ }).first().click()
    await expect(page.getByRole('dialog', { name: 'Hapus proyek?' })).toBeVisible()
    await page.screenshot({ path: resolve(artifacts, `delete-${width}.png`), fullPage: true })
    const dialog = page.getByRole('dialog', { name: 'Hapus proyek?' })
    await dialog.getByRole('button', { name: 'Hapus proyek', exact: true }).focus()
    await page.keyboard.press('Tab')
    await expect(dialog.getByRole('button', { name: 'Tutup dialog' })).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible()
    await page.goto(`/projects/${report.project_id}`)
    await expect(page.getByRole('button', { name: 'Klip manual', exact: true })).toBeVisible()
    await page.screenshot({ path: resolve(artifacts, `detail-${width}.png`), fullPage: true })
    await noOverflow(page)
    await page.goto(`/clips/${report.clip_id}`)
    await expect(page.getByLabel('Judul klip', { exact: true })).toBeVisible()
    await expect.poll(() => page.locator('.portrait-frame video').evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(1)
    await page.screenshot({ path: resolve(artifacts, `editor-${width}.png`), fullPage: true })
    await noOverflow(page)
    await page.getByLabel('Judul klip', { exact: true }).fill('Perubahan belum disimpan untuk uji dialog')
    await page.getByRole('link', { name: 'Kembali ke proyek', exact: true }).click()
    await expect(page.getByRole('dialog', { name: 'Perubahan belum tersimpan' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByLabel('Judul klip', { exact: true })).toHaveValue('Perubahan belum disimpan untuk uji dialog')
    await page.getByRole('link', { name: 'Kembali ke proyek', exact: true }).click()
    await page.getByRole('button', { name: 'Tinggalkan perubahan' }).click()
    await page.goto('/projects/not-a-project')
    await expect(page.getByRole('alert')).toBeVisible()
    await page.screenshot({ path: resolve(artifacts, `error-${width}.png`), fullPage: true })
    await noOverflow(page)
  })
}

for (const width of [1440, 390]) {
  test(`true empty account at ${width}px`, async ({ page }) => {
    test.skip(!process.env.CLIPPER_E2E_EMPTY_PASSWORD, 'Requires a dedicated empty test account')
    await page.setViewportSize({ width, height: 1000 })
    await login(page, process.env.CLIPPER_E2E_EMPTY_EMAIL!, process.env.CLIPPER_E2E_EMPTY_PASSWORD!)
    await expect(page.getByRole('heading', { name: 'Belum ada proyek' })).toBeVisible()
    await page.screenshot({ path: resolve(artifacts, `empty-${width}.png`), fullPage: true })
    await noOverflow(page)
  })
}
