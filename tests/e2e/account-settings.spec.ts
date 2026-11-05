import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const artifacts = resolve(import.meta.dirname, '../../.artifacts/account-settings')

test('social connections live in settings and calendar only schedules', async ({ page }) => {
  test.skip(!process.env.CLIPPER_E2E_EMAIL, 'QA account required')
  await page.route('**/api/v1/social/accounts', route => route.fulfill({ json: {
    items: [
      { id: 'channel-one', platform: 'youtube', name: 'Channel Utama', connected: true },
      { id: 'channel-two', platform: 'youtube', name: 'Channel Kedua', connected: true },
    ],
    platforms: ['youtube', 'instagram', 'tiktok'].map(id => ({
      id, configured: true, publishing_ready: id !== 'tiktok',
      callback_url: `http://localhost:8080/api/v1/social/oauth/${id}/callback`,
    })),
  } }))
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(process.env.CLIPPER_E2E_EMAIL!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(process.env.CLIPPER_E2E_PASSWORD!)
  await page.getByLabel('Kata sandi', { exact: true }).press('Enter')
  await expect(page.getByRole('heading', { name: 'Proyek', exact: true })).toBeVisible()

  await page.goto('/settings?section=accounts&connection=connected')
  await expect(page.getByRole('button', { name: 'Koneksi akun', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByRole('heading', { name: 'Koneksi akun publikasi', exact: true })).toBeVisible()
  await expect(page.getByText('Akun berhasil dihubungkan.', { exact: true })).toBeVisible()
  await expect(page.getByText('Channel Utama', { exact: true })).toBeVisible()
  await expect(page.getByText('Channel Kedua', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Tambah channel YouTube', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /Hubungkan/ })).toHaveCount(2)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)
  mkdirSync(artifacts, { recursive: true })
  await page.screenshot({ path: resolve(artifacts, 'connections-settings.png') })

  await page.goto('/calendar')
  await expect(page.getByRole('heading', { name: 'Kalender', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Koneksi akun', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Tambah jadwal', exact: true })).toBeVisible()
})
