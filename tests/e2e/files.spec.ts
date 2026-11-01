import { expect, test } from '@playwright/test'

test('file manager lists storage and keeps deletion behind confirmation', async ({ page }) => {
  test.skip(!process.env.CLIPPER_E2E_EMAIL, 'QA account required')
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(process.env.CLIPPER_E2E_EMAIL!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(process.env.CLIPPER_E2E_PASSWORD!)
  await page.getByRole('button', { name: 'Masuk' }).click()
  await page.getByRole('link', { name: 'File', exact: true }).click()

  await expect(page).toHaveURL(/\/files$/)
  await expect(page.getByRole('heading', { name: 'File video' })).toBeVisible()
  await expect(page.getByLabel('Ringkasan penyimpanan')).toContainText('Total penyimpanan')
  await expect(page.locator('body')).toHaveCSS('overflow-y', 'clip')
  await expect(page.locator('.media-row, .empty-state.panel').first()).toBeVisible()

  const deleteButtons = page.getByRole('button', { name: /^Hapus video / })
  if (await deleteButtons.count()) {
    await deleteButtons.first().click()
    const dialog = page.getByRole('dialog', { name: 'Hapus video dan proyek?' })
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('Ruang yang akan dibebaskan')
    await dialog.getByRole('button', { name: 'Batal' }).click()
    await expect(dialog).toBeHidden()
  } else {
    await expect(page.getByText('Belum ada video')).toBeVisible()
  }
})
