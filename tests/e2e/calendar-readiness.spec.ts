import { expect, test } from '@playwright/test'

test('calendar recognizes a connected YouTube account and distinguishes an unselected destination', async ({ page }, testInfo) => {
  test.skip(!process.env.CLIPPER_E2E_EMAIL, 'Local account required')
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(process.env.CLIPPER_E2E_EMAIL!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(process.env.CLIPPER_E2E_PASSWORD!)
  await page.getByRole('button', { name: 'Masuk', exact: true }).click()
  await expect(page).not.toHaveURL(/\/login/)
  const response = await page.request.get('/api/v1/social/accounts')
  expect(response.ok()).toBe(true)
  const connected = await response.json()
  const accounts = connected.items.filter((a: any) => a.platform === 'youtube')
  test.skip(accounts.length !== 1, 'Requires exactly one connected YouTube channel')
  expect(connected.platforms.find((p: any) => p.id === 'youtube').publishing_ready).toBe(true)
  await page.goto('/calendar')
  await page.getByRole('button', { name: 'Tambah jadwal', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Jadwal publikasi baru' })
  const target = dialog.getByRole('combobox', { name: 'Akun tujuan', exact: true })
  await expect(target).toContainText(accounts[0].name)
  await expect(dialog.getByText('Kelola koneksi akun di Pengaturan.')).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: 'Jadwalkan publikasi', exact: true })).toBeDisabled() // No consent; never post during QA.
  await page.screenshot({ path: testInfo.outputPath('connected-destination.png') })
  await target.click()
  await page.getByRole('option', { name: 'Belum dipilih (draft)', exact: true }).click()
  await expect(dialog).toContainText('sudah terhubung. Pilih Akun tujuan')
  await expect(dialog.getByText('Kelola koneksi akun di Pengaturan.')).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Opsi publikasi', exact: true }).click()
  await dialog.getByRole('button', { name: 'Pilih akun tujuan', exact: true }).click()
  await expect(target).toBeVisible()
  await dialog.getByRole('button', { name: 'Tutup dialog' }).click()
  // A second channel is simulated only in this browser; force an explicit choice.
  let fail = false
  await page.route('**/api/v1/social/accounts', route => fail ? route.fulfill({ status: 503, json: { message: 'QA unavailable' } }) : route.fulfill({ json: {
    ...connected, items: [...connected.items, { ...accounts[0], id: 'qa-second-channel', name: 'QA second channel' }],
  } }))
  await page.getByRole('button', { name: 'Tambah jadwal', exact: true }).click()
  await expect(target).toBeEnabled()
  await expect(target).toContainText('Belum dipilih (draft)')
  await expect(dialog).toContainText('sudah terhubung. Pilih Akun tujuan')
  await dialog.getByRole('button', { name: 'Tutup dialog' }).click()
  fail = true
  await page.getByRole('button', { name: 'Tambah jadwal', exact: true }).click()
  await expect(dialog).toContainText('Status koneksi akun gagal dimuat')
  await expect(dialog.getByText('Kelola koneksi akun di Pengaturan.')).toHaveCount(0)
  fail = false
  await dialog.getByRole('button', { name: 'Periksa lagi', exact: true }).click()
  await expect(dialog).not.toContainText('Status koneksi akun gagal dimuat')
  expect(errors).toEqual([])
})
