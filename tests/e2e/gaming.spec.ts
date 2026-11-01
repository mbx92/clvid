import { test, expect, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Dedicated synthetic source: 960x540, magenta creator at top right, three HUD markers.
const sourceClipId = process.env.CLIPPER_E2E_GAMING_CLIP_ID
const email = process.env.CLIPPER_E2E_EMAIL
const password = process.env.CLIPPER_E2E_PASSWORD
const artifacts = resolve(import.meta.dirname, '../../.artifacts/gaming')
const gaming = { facecam: { x: .75, y: 0, width: .25, height: .25 },
  gameplay: { x: 0, y: 0, width: 1, height: 1 }, facecam_height: .28,
  facecam_fit: 'fill', gameplay_fit: 'fit' }

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(email!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(password!)
  await page.getByLabel('Kata sandi', { exact: true }).press('Enter')
  await expect(page.getByRole('heading', { name: 'Proyek', exact: true })).toBeVisible()
}

async function seek(page: Page, seconds: number) {
  const video = page.locator('.portrait-frame video')
  await video.evaluate((element: HTMLVideoElement, target) => { element.pause(); element.currentTime = target }, seconds)
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => !element.seeking && element.readyState >= 2)).toBe(true)
}

async function pixels(page: Page, facecamHeight: number) {
  return page.getByTestId('gaming-preview').evaluate((element: HTMLCanvasElement, ratio) => {
    const w = element.width, h = element.height
    const top = 2 * Math.floor(h * ratio / 2 + .5)
    const gameHeight = w * 540 / 960
    const gameTop = top + (h - top - gameHeight) / 2
    const points = [
      { name: 'creator', x: .08, y: .06, expected: [217, 70, 239] },
      { name: 'hud-top-left', x: 32 / 960, y: (gameTop + gameHeight * 32 / 540) / h, expected: [250, 204, 21] },
      { name: 'hud-bottom-left', x: 32 / 960, y: (gameTop + gameHeight * 508 / 540) / h, expected: [6, 182, 212] },
      { name: 'hud-bottom-right', x: 928 / 960, y: (gameTop + gameHeight * 508 / 540) / h, expected: [239, 68, 68] },
    ]
    const ctx = element.getContext('2d')!
    return points.map(point => ({ ...point, color: Array.from(ctx.getImageData(Math.floor(point.x * w), Math.floor(point.y * h), 1, 1).data).slice(0, 3) }))
  }, facecamHeight)
}

async function assertPanels(page: Page, ratio: number) {
  await expect.poll(async () => Math.max(...(await pixels(page, ratio)).flatMap(point => point.color.map((channel, i) => Math.abs(channel - point.expected[i]!))))).toBeLessThan(30)
}

test('gaming keeps creator and whole gameplay visible through preview, save and export', async ({ page, context }) => {
  test.skip(!sourceClipId || !email || !password, 'Requires the dedicated synthetic gaming QA fixture')
  test.setTimeout(180_000)
  const browserErrors: string[] = []
  page.on('pageerror', error => browserErrors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1000 })
  await login(page)
  const source = await (await context.request.get(`/api/v1/clips/${sourceClipId}`)).json()
  const csrf = (await context.cookies()).find(cookie => cookie.name === 'clipper_csrf')!.value
  const created = await context.request.post(`/api/v1/projects/${source.project_id}/clips`, {
    headers: { 'X-CSRF-Token': csrf }, data: { title: 'QA gaming facecam dan gameplay', start_ms: 0, end_ms: 6000,
      crop_json: { mode: 'gaming', tracking: 'static', x: .5, y: .5, gaming },
      cues: [{ start_ms: 0, end_ms: 5000, text: 'Momen permainan dan reaksi kreator.' }] },
  })
  expect(created.status()).toBe(201)
  const clip = await created.json()
  await page.goto(`/clips/${clip.id}`)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await expect(page.getByTestId('gaming-preview')).toBeVisible()
  await expect(page.locator('video')).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Analisis preview', exact: true })).toHaveCount(0)
  await seek(page, 2)
  await assertPanels(page, .28)
  await expect(page.locator('.caption-preview')).toContainText('Momen permainan')
  const first = await page.getByTestId('gaming-preview').evaluate((canvas: HTMLCanvasElement) => canvas.toDataURL())
  await page.getByRole('button', { name: 'Putar video', exact: true }).click()
  await expect.poll(() => page.locator('.portrait-frame video').evaluate((video: HTMLVideoElement) => video.currentTime)).toBeGreaterThan(2.6)
  await page.getByRole('button', { name: 'Jeda video', exact: true }).click()
  expect(await page.getByTestId('gaming-preview').evaluate((canvas: HTMLCanvasElement) => canvas.toDataURL())).not.toBe(first)
  await seek(page, 2)
  // Panel proportions redraw while paused; no background render or analysis is required.
  await page.getByRole('button', { name: 'Susunan panel', exact: true }).click()
  await page.getByRole('slider', { name: 'Tinggi panel facecam', exact: true }).press('End')
  await assertPanels(page, .45)
  expect((await (await context.request.get(`/api/v1/clips/${clip.id}`)).json()).revision).toEqual(clip.revision)
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect(page.getByText('Revisi 2', { exact: true })).toBeVisible()
  const saved = await (await context.request.get(`/api/v1/clips/${clip.id}`)).json()
  expect(saved.revision.crop_json.gaming.facecam_height).toBe(.45)
  expect(saved.revision.crop_json.gaming.facecam).toEqual(gaming.facecam)
  await page.reload()
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await seek(page, 2)
  await assertPanels(page, .45)
  mkdirSync(artifacts, { recursive: true })
  await page.screenshot({ path: resolve(artifacts, 'desktop.png'), fullPage: true })
  await page.locator('.portrait-frame').screenshot({ path: resolve(artifacts, 'preview.png') })
  const sampledPixels = await pixels(page, .45)
  await page.setViewportSize({ width: 390, height: 1000 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await assertPanels(page, .45)
  await page.screenshot({ path: resolve(artifacts, 'mobile.png'), fullPage: true })
  const response = await context.request.post(`/api/v1/clips/${clip.id}/exports`, {
    headers: { 'X-CSRF-Token': csrf }, data: { revision: saved.revision.revision, resolution: 720 },
  })
  expect(response.status()).toBe(202)
  const jobId = (await response.json()).id
  let job: any
  await expect.poll(async () => {
    job = await (await context.request.get(`/api/v1/jobs/${jobId}`)).json()
    return ['succeeded', 'failed', 'cancelled'].includes(job.status)
  }, { timeout: 90_000, intervals: [500, 1000] }).toBe(true)
  expect(job.status, job.error_message).toBe('succeeded')
  const outputs = await (await context.request.get(`/api/v1/projects/${source.project_id}/exports`, { params: { clip_id: clip.id } })).json()
  const output = outputs.items.find((item: any) => item.job.id === jobId)
  expect(output.mp4_asset.metadata.framing.layout).toBe('gaming')
  expect(output.mp4_asset.metadata.framing.method).toBe('gaming-layout-1')
  const content = await context.request.get(output.mp4_asset.content_url)
  expect(content.status()).toBe(200)
  writeFileSync(resolve(artifacts, 'gaming-export.mp4'), await content.body())
  writeFileSync(resolve(artifacts, 'report.json'), JSON.stringify({ clip_id: clip.id, revision: saved.revision,
    job_id: jobId, metadata: output.mp4_asset.metadata, sampled_pixels: sampledPixels,
    render_seconds: (Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000 }, null, 2))
  expect(browserErrors).toEqual([])
  expect((await (await context.request.get(`/api/v1/clips/${sourceClipId}`)).json()).revision).toEqual(source.revision)
})

test('gaming source regions can be selected and adjusted without saving or starting jobs', async ({ page, context }) => {
  test.skip(!sourceClipId || !email || !password, 'Requires the dedicated synthetic gaming QA fixture')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await login(page)
  const source = await (await context.request.get(`/api/v1/clips/${sourceClipId}`)).json()
  const csrf = (await context.cookies()).find(cookie => cookie.name === 'clipper_csrf')!.value
  const result = await context.request.post(`/api/v1/projects/${source.project_id}/clips`, {
    headers: { 'X-CSRF-Token': csrf }, data: { title: 'QA pengaturan area gaming', start_ms: 0, end_ms: 6000,
      crop_json: { mode: 'fill', tracking: 'face', x: .5, y: .5 }, cues: [] },
  })
  expect(result.status()).toBe(201)
  const clip = await result.json()
  const before = await (await context.request.get(`/api/v1/projects/${source.project_id}`)).json()
  await page.goto(`/clips/${clip.id}`)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  async function mode(option: string) {
    await page.getByRole('combobox', { name: 'Mode framing', exact: true }).click()
    await page.getByRole('option', { name: option, exact: true }).click()
  }
  await mode('Gaming (facecam + gameplay)')
  await expect(page.getByTestId('gaming-preview')).toBeVisible()
  await page.getByRole('button', { name: 'Kanan atas', exact: true }).click()
  await expect(page.getByLabel('Kiri area Facecam (%)', { exact: true })).toHaveValue('75.0')
  await expect(page.getByLabel('Atas area Facecam (%)', { exact: true })).toHaveValue('0.0')
  await seek(page, 2)
  await assertPanels(page, .28)
  await page.getByLabel('Lebar area Facecam (%)', { exact: true }).fill('20')
  await page.getByLabel('Lebar area Facecam (%)', { exact: true }).press('Tab')
  await expect(page.getByLabel('Lebar area Facecam (%)', { exact: true })).toHaveValue('20.0')
  await page.getByRole('button', { name: 'Kanan atas', exact: true }).click()
  const sourceCanvas = page.getByTestId('gaming-source')
  await sourceCanvas.scrollIntoViewIfNeeded()
  const box = (await sourceCanvas.boundingBox())!
  await page.mouse.move(box.x + box.width * .83, box.y + box.height * .10)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width * .53, box.y + box.height * .40, { steps: 8 })
  await page.mouse.up()
  const moved = Number(await page.getByLabel('Kiri area Facecam (%)', { exact: true }).inputValue())
  expect(moved).toBeLessThan(65)
  expect(moved).toBeGreaterThan(25)
  await page.getByRole('button', { name: 'Ubah ukuran area facecam dari kanan bawah', exact: true }).press('ArrowLeft')
  await expect(page.getByLabel('Lebar area Facecam (%)', { exact: true })).toHaveValue('24.0')
  await page.getByRole('button', { name: 'Area gameplay', exact: true }).click()
  await page.getByRole('button', { name: 'Gunakan seluruh video untuk gameplay', exact: true }).click()
  await expect(page.getByLabel('Lebar area Gameplay (%)', { exact: true })).toHaveValue('100.0')
  await mode('Tampilkan seluruh video')
  await expect(page.getByTestId('gaming-preview')).toHaveCount(0)
  await expect(page.locator('.portrait-frame video')).toBeVisible()
  await expect(page.locator('video')).toHaveCount(1)
  expect((await (await context.request.get(`/api/v1/clips/${clip.id}`)).json()).revision).toEqual(clip.revision)
  const after = await (await context.request.get(`/api/v1/projects/${source.project_id}`)).json()
  expect(after.jobs.map((job: any) => job.id)).toEqual(before.jobs.map((job: any) => job.id))
})
