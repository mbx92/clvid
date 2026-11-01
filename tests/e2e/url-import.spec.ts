import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

test('public URL import from the dialog becomes an editable video', async ({ page }) => {
  test.skip(!process.env.CLIPPER_E2E_SOURCE_URL, 'Opt in with a short public video URL')
  test.setTimeout(180_000)
  const screenshots = resolve(import.meta.dirname, '../../.artifacts/ui')
  mkdirSync(screenshots, { recursive: true })
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(process.env.CLIPPER_E2E_EMAIL!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(process.env.CLIPPER_E2E_PASSWORD!)
  await page.getByLabel('Kata sandi', { exact: true }).press('Enter')
  await page.getByRole('button', { name: 'Proyek baru', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Proyek baru' })
  await dialog.getByLabel('Nama proyek').fill(`QA URL browser ${Date.now()}`)
  await dialog.getByRole('button', { name: 'URL video', exact: true }).click()
  await dialog.getByLabel('URL video publik').fill(process.env.CLIPPER_E2E_SOURCE_URL!)
  await expect(dialog.locator('input[type=file]')).toHaveCount(0)
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect(dialog.getByRole('button', { name: 'Impor video', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: resolve(screenshots, `url-dialog-${width}.png`), fullPage: true })
  }
  await dialog.getByRole('button', { name: 'Impor video', exact: true }).press('Enter')
  await expect(page).toHaveURL(/\/projects\//)
  await expect(page.getByRole('button', { name: 'Klip manual', exact: true })).toBeVisible({ timeout: 120_000 })
  await expect.poll(() => page.locator('.source-player video').evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(1)
  await page.screenshot({ path: resolve(screenshots, 'url-import-ready.png'), fullPage: true })
})
