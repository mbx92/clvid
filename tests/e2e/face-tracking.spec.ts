import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * Opt-in acceptance against the real, updated QA stack. No provider/media mocks.
 * Required: CLIPPER_E2E_EMAIL, CLIPPER_E2E_PASSWORD,
 * CLIPPER_E2E_TRACKING_CLIP_ID (a dedicated QA clip with an accessible source).
 * The render test creates its own clip; it never edits the supplied source clip.
 * Optional: CLIPPER_E2E_TRACKING_EXPECT_DETECTION=1 for a known face fixture;
 * CLIPPER_E2E_LEGACY_CLIP_ID for a real, read-only revision lacking tracking.
 * CLIPPER_E2E_URL is supplied through playwright.config.ts.
 */
const sourceClipId = process.env.CLIPPER_E2E_TRACKING_CLIP_ID
const legacyClipId = process.env.CLIPPER_E2E_LEGACY_CLIP_ID
const email = process.env.CLIPPER_E2E_EMAIL
const password = process.env.CLIPPER_E2E_PASSWORD
const artifacts = resolve(import.meta.dirname, '../../.artifacts/ui')
const manualPosition = { x: 0.23, y: 0.67 }

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(email!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(password!)
  await page.getByLabel('Kata sandi', { exact: true }).press('Enter')
  await expect(page.getByRole('heading', { name: 'Proyek', exact: true })).toBeVisible()
}

async function readClip(request: APIRequestContext, id: string) {
  const response = await request.get(`/api/v1/clips/${id}`)
  expect(response.status(), 'The dedicated QA clip must be accessible to the QA account').toBe(200)
  return response.json()
}

async function chooseTracking(page: Page, option: string) {
  const control = page.getByRole('combobox', { name: 'Pelacakan frame', exact: true })
  await control.click()
  await page.getByRole('option', { name: option, exact: true }).click()
  await expect(control).toHaveText(option)
}

async function captureEditor(page: Page, path: string) {
  await expect.poll(() => page.locator('.portrait-frame video').evaluate((video: HTMLVideoElement) => video.readyState)).toBeGreaterThanOrEqual(2)
  // Full-page captures must start at the document top so sticky navigation is not duplicated mid-page.
  await page.evaluate(() => { (document.activeElement as HTMLElement | null)?.blur(); window.scrollTo(0, 0) })
  await page.screenshot({ path, fullPage: true })
}

test('legacy tracking default opens without modifying the stored clip', async ({ page, context }) => {
  test.skip(!email || !password || !legacyClipId, 'Opt in with a dedicated legacy QA clip and QA credentials')
  await login(page)
  const before = await readClip(context.request, legacyClipId!)
  expect(Object.hasOwn(before.revision.crop_json, 'tracking'), 'This check requires an actual pre-tracking revision').toBe(false)
  await page.goto(`/clips/${legacyClipId}`)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  if (before.revision.crop_json.mode === 'fill') {
    await expect(page.getByRole('combobox', { name: 'Pelacakan frame', exact: true })).toHaveText('Manual (tetap)')
  } else {
    await expect(page.getByRole('combobox', { name: 'Pelacakan frame', exact: true })).toHaveCount(0)
  }
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeDisabled()
  await expect(page.getByText('Tersimpan', { exact: true })).toBeVisible()
  const after = await readClip(context.request, legacyClipId!)
  expect(after.revision).toEqual(before.revision)
})

test('tracking selection saves explicitly, preserves manual fallback and exposes real render metadata', async ({ page, context }, testInfo) => {
  test.skip(!email || !password || !sourceClipId, 'Opt in with a dedicated QA source clip and QA credentials')
  test.setTimeout(240_000)
  const browserErrors: string[] = []
  page.on('pageerror', error => browserErrors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1000 })
  await login(page)
  const source = await readClip(context.request, sourceClipId!)
  const csrf = (await context.cookies()).find(cookie => cookie.name === 'clipper_csrf')?.value
  expect(csrf).toBeTruthy()
  const title = `QA pelacakan browser ${Date.now()}`
  const response = await context.request.post(`/api/v1/projects/${source.project_id}/clips`, {
    headers: { 'X-CSRF-Token': csrf! },
    data: {
      title,
      start_ms: source.revision.start_ms,
      end_ms: Math.min(source.revision.end_ms, source.revision.start_ms + 6000),
      crop_json: { mode: 'fill', ...manualPosition },
      subtitle_style_json: { enabled: false, font_size: 52, position: 'bottom', background: true, safe_margin: 0.15 },
      cues: [],
    },
  })
  expect(response.status()).toBe(201)
  const created = await response.json()
  await page.goto(`/clips/${created.id}`)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  const trackingControl = page.getByRole('combobox', { name: 'Pelacakan frame', exact: true })
  await expect(trackingControl).toHaveText('Manual (tetap)')
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeDisabled()
  expect((await readClip(context.request, created.id)).revision).toEqual(created.revision)
  const player = page.locator('.portrait-frame video')
  const fallbackPosition = await player.evaluate(video => getComputedStyle(video).objectPosition)

  // Exercise the custom selector by keyboard, while retaining an unchanged saved revision.
  await trackingControl.press('ArrowDown')
  await trackingControl.press('ArrowDown')
  await trackingControl.press('Enter')
  await expect(trackingControl).toHaveText('Ikuti wajah')
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeEnabled()
  await expect(page.getByText('Belum tersimpan', { exact: true })).toBeVisible()
  const unchanged = await readClip(context.request, created.id)
  expect(unchanged.revision).toEqual(created.revision)
  expect(await player.evaluate(video => getComputedStyle(video).objectPosition)).toBe(fallbackPosition)
  await expect(page.getByText('Belum ada analisis untuk pengaturan ini. Preview menggunakan posisi manual sebagai cadangan.', { exact: true })).toBeVisible()

  // The multi-speaker option must communicate its estimate and keep preview static.
  await chooseTracking(page, 'Ikuti pembicara (perkiraan)')
  await expect(page.getByText(/Model audio-visual memperkirakan wajah/)).toBeVisible()
  await expect(page.getByText('Preview memakai posisi manual. Jalankan analisis untuk melihat framing bergerak.', { exact: true })).toBeVisible()
  expect(await player.evaluate(video => getComputedStyle(video).objectPosition)).toBe(fallbackPosition)
  await chooseTracking(page, 'Ikuti wajah')

  // Mobile controls remain accessible, with no fake moving crop in the source player.
  await page.setViewportSize({ width: 390, height: 1000 })
  await trackingControl.scrollIntoViewIfNeeded()
  await expect(trackingControl).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  mkdirSync(artifacts, { recursive: true })
  await captureEditor(page, resolve(artifacts, 'tracking-editor-390.png'))
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect(page.getByText('Revisi 2', { exact: true })).toBeVisible()
  const saved = await readClip(context.request, created.id)
  expect(saved.revision.crop_json).toEqual({ mode: 'fill', tracking: 'face', ...manualPosition })
  expect((await readClip(context.request, sourceClipId!)).revision).toEqual(source.revision)
  await page.reload()
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await expect(trackingControl).toHaveText('Ikuti wajah')
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeDisabled()
  expect(await player.evaluate(video => getComputedStyle(video).objectPosition)).toBe(fallbackPosition)
  await captureEditor(page, resolve(artifacts, 'tracking-editor-1440.png'))

  await page.getByRole('button', { name: 'Ekspor', exact: true }).click()
  const exportDialog = page.getByRole('dialog', { name: 'Ekspor klip', exact: true })
  await expect(exportDialog.getByText(/Framing: Ikuti wajah/)).toBeVisible()
  await exportDialog.getByRole('combobox', { name: 'Resolusi ekspor', exact: true }).click()
  await page.getByRole('option', { name: '720 × 1280 · 30 fps', exact: true }).click()
  const renderResponse = page.waitForResponse(result => result.request().method() === 'POST' && result.url().endsWith(`/clips/${created.id}/exports`))
  await exportDialog.getByRole('button', { name: 'Mulai ekspor', exact: true }).click()
  const started = await renderResponse
  expect(started.status()).toBe(202)
  const job = await started.json()

  // Short clips may finish before the next browser poll; record elapsed UI when observable.
  let elapsedVisible = false
  let terminalJob: any
  await expect.poll(async () => {
    elapsedVisible ||= await page.locator('.job-row').getByText(/Berjalan \d+ (dtk|mnt|jam)/).count() > 0
    const result = await context.request.get(`/api/v1/jobs/${job.id}`)
    expect(result.status()).toBe(200)
    terminalJob = await result.json()
    return ['succeeded', 'failed', 'cancelled'].includes(terminalJob.status)
  }, { timeout: 180_000, intervals: [1000, 2000, 3000], message: 'Real face analysis and FFmpeg render must finish' }).toBe(true)
  expect(terminalJob.status, terminalJob.error_message || 'Tracking export must succeed').toBe('succeeded')
  console.log(`Tracking render finished: ${job.id} (${terminalJob.status})`)
  await expect(page.getByRole('link', { name: 'Unduh MP4', exact: true })).toBeVisible({ timeout: 15_000 })
  const historyResponse = await context.request.get(`/api/v1/projects/${source.project_id}/exports`, { params: { clip_id: created.id } })
  expect(historyResponse.status()).toBe(200)
  const history = await historyResponse.json()
  const output = history.items.find((item: any) => item.job.id === job.id)
  expect(output?.mp4_asset?.metadata?.framing, 'Final MP4 must expose actual tracking metadata').toBeTruthy()
  const framing = output.mp4_asset.metadata.framing
  expect(framing.mode).toBe('face')
  expect(Array.isArray(framing.keyframes)).toBe(true)
  expect(framing.keyframes.length).toBeGreaterThan(0)
  for (const keyframe of framing.keyframes) {
    expect(keyframe.t_ms).toBeGreaterThanOrEqual(0)
    expect(keyframe.t_ms).toBeLessThanOrEqual(saved.revision.end_ms - saved.revision.start_ms)
    expect(keyframe.x).toBeGreaterThanOrEqual(0)
    expect(keyframe.x).toBeLessThanOrEqual(1)
    expect(keyframe.y).toBeGreaterThanOrEqual(0)
    expect(keyframe.y).toBeLessThanOrEqual(1)
  }
  expect(Array.isArray(framing.warnings)).toBe(true)
  expect(framing.coverage).toBeGreaterThanOrEqual(0)
  expect(framing.coverage).toBeLessThanOrEqual(1)
  if (process.env.CLIPPER_E2E_TRACKING_EXPECT_DETECTION === '1') {
    expect(framing.detected_frames, 'Known face fixture must exercise real detection, not only fallback').toBeGreaterThan(0)
    expect(framing.total_frames).toBeGreaterThan(0)
    expect(framing.fallback_reason).toBeNull()
  } else if (framing.detected_frames === 0) {
    expect(framing.fallback_reason, 'No-face or unavailable-model output must disclose the fallback').toBeTruthy()
  }
  const exportRow = page.locator('.export-row').filter({ has: page.getByRole('heading', { name: title, exact: true }) })
  await expect(exportRow.locator('.framing-info')).toBeVisible()
  const messages = [...new Set([framing.fallback_reason, ...framing.warnings].filter(Boolean))] as string[]
  for (const message of messages) await expect(exportRow.getByText(message, { exact: true })).toBeVisible()
  await exportRow.getByRole('button', { name: 'Lihat hasil', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Hasil revisi 2', exact: true })).toBeVisible()
  await expect.poll(() => page.locator('.final-video').evaluate((video: HTMLVideoElement) => video.readyState)).toBeGreaterThanOrEqual(1)
  await page.screenshot({ path: resolve(artifacts, 'tracking-result-1440.png'), fullPage: true })
  await testInfo.attach('tracking-result', { contentType: 'application/json', body: JSON.stringify({ clip_id: created.id, job_id: job.id, elapsed_ui_observed: elapsedVisible, framing }, null, 2) })
  expect(browserErrors).toEqual([])
})
