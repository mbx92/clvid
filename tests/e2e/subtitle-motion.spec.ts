import { expect, test } from '@playwright/test'

test('subtitle presets animate against the video clock and preserve editable export settings', async ({ page }, testInfo) => {
  test.skip(!process.env.CLIPPER_E2E_EMAIL || !process.env.CLIPPER_E2E_PROJECT, 'Ready project with a clip required')
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(process.env.CLIPPER_E2E_EMAIL!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(process.env.CLIPPER_E2E_PASSWORD!)
  await page.getByRole('button', { name: 'Masuk', exact: true }).click()
  await expect(page).not.toHaveURL(/\/login/)
  const clips = await (await page.request.get(`/api/v1/projects/${process.env.CLIPPER_E2E_PROJECT}/clips`)).json()
  test.skip(!clips.items?.length, 'A clip is required as the read-only video fixture')
  let fixture = await (await page.request.get(`/api/v1/clips/${clips.items[0].id}`)).json()
  fixture = { ...fixture, revision: { ...fixture.revision, start_ms: 0, end_ms: 5000,
    crop_json: { mode: 'fit', tracking: 'static', x: .5, y: .5 }, source_words: [],
    cues: [{ start_ms: 0, end_ms: 5000, text: 'MOMEN PALING SERU' }],
    subtitle_style_json: { enabled: true, font_size: 52, position: 'bottom', background: false, safe_margin: .15 },
  } }
  let saved: any
  await page.route(`**/api/v1/clips/${fixture.id}`, route => {
    if (route.request().method() === 'PATCH') {
      saved = route.request().postDataJSON()
      fixture = { ...fixture, revision: { ...fixture.revision, ...saved, revision: fixture.revision.revision + 1 } }
    }
    return route.fulfill({ json: fixture })
  })
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto(`/clips/${fixture.id}`)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await page.getByRole('button', { name: 'Gaya subtitle', exact: true }).click()
  const caption = page.locator('.caption-preview')
  const seek = async (ms: number) => {
    await page.getByLabel('Posisi playback video sumber', { exact: true }).evaluate((el: HTMLInputElement, time) => {
      el.value = String(time); el.dispatchEvent(new Event('input', { bubbles: true }))
    }, ms)
  }
  await page.getByRole('button', { name: 'Preset Sinematik', exact: true }).click()
  await seek(150)
  await expect.poll(async () => Number(await caption.evaluate(el => getComputedStyle(el).opacity))).toBeCloseTo(.5, 1)
  await seek(600)
  await expect(caption).toHaveCSS('opacity', '1')
  await seek(150)
  await expect.poll(async () => Number(await caption.evaluate(el => getComputedStyle(el).opacity))).toBeCloseTo(.5, 1)
  await page.getByRole('button', { name: 'Preset Gaming impact', exact: true }).click()
  await seek(80)
  await expect.poll(async () => Number(await caption.evaluate(el => new DOMMatrixReadOnly(getComputedStyle(el).transform).a))).toBeCloseTo(.925, 2)
  await seek(600)
  await expect(caption).toHaveCSS('color', 'rgb(255, 230, 0)')
  await page.screenshot({ path: testInfo.outputPath('subtitle-gaming-impact.png') })
  await page.getByRole('button', { name: 'Warna & efek', exact: true }).click()
  await page.getByRole('combobox', { name: 'Animasi subtitle', exact: true }).click()
  await page.getByRole('option', { name: 'Geser halus', exact: true }).click()
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect.poll(() => saved?.subtitle_style_json.animation).toBe('rise')
  expect(saved.subtitle_style_json.animation_ms).toBe(160)
  await page.reload()
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await page.getByRole('button', { name: 'Gaya subtitle', exact: true }).click()
  await page.getByRole('button', { name: 'Warna & efek', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Animasi subtitle', exact: true })).toContainText('Geser halus')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Alat editor', exact: true }).click()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('subtitle-motion-mobile.png') })
  expect(errors).toEqual([])
})
