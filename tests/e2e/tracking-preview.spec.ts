import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Real detector, jobs, browser video and export. Use a disposable QA account.
const sourceClipId = process.env.CLIPPER_E2E_PREVIEW_CLIP_ID
const email = process.env.CLIPPER_E2E_EMAIL
const password = process.env.CLIPPER_E2E_PASSWORD
const artifacts = resolve(import.meta.dirname, '../../.artifacts/tracking-preview')
const manual = { x: 0.23, y: 0.67 }

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(email!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(password!)
  await page.getByLabel('Kata sandi', { exact: true }).press('Enter')
  await expect(page.getByRole('heading', { name: 'Proyek', exact: true })).toBeVisible()
}

async function getClip(request: APIRequestContext, id: string) {
  const response = await request.get(`/api/v1/clips/${id}`)
  expect(response.status()).toBe(200)
  return response.json()
}

async function choose(page: Page, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page.getByRole('option', { name: option, exact: true }).click()
}

async function waitJob(request: APIRequestContext, id: string) {
  let job: any
  await expect.poll(async () => {
    const response = await request.get(`/api/v1/jobs/${id}`)
    expect(response.status()).toBe(200)
    job = await response.json()
    return ['succeeded', 'failed', 'cancelled'].includes(job.status)
  }, { timeout: 180_000, intervals: [500, 1000, 2000] }).toBe(true)
  expect(job.status, job.error_message || 'Real analysis must succeed').toBe('succeeded')
  return job
}

function expectedPosition(frames: any[], localMs: number) {
  let current = frames[0]
  for (let i = 1; i < frames.length; i++) {
    const next = frames[i]
    if (localMs < next.t_ms) {
      const alpha = next.cut ? 0 : Math.max(0, Math.min(1, (localMs - current.t_ms) / (next.t_ms - current.t_ms)))
      return { x: current.x + (next.x - current.x) * alpha, y: current.y + (next.y - current.y) * alpha }
    }
    current = next
  }
  return { x: current.x, y: current.y }
}

async function atTime(page: Page, seconds: number) {
  const player = page.locator('.portrait-frame video')
  await player.evaluate((element: HTMLVideoElement, target) => { element.pause(); element.currentTime = target }, seconds)
  await expect.poll(() => player.evaluate((element: HTMLVideoElement) => !element.seeking && element.readyState >= 2)).toBe(true)
}

async function position(page: Page) {
  return page.locator('.portrait-frame video').evaluate((element: HTMLVideoElement) => {
    const parts = getComputedStyle(element).objectPosition.split(' ').map(parseFloat)
    return { x: parts[0]! / 100, y: parts[1]! / 100, timeMs: element.currentTime * 1000 }
  })
}

async function assertPosition(page: Page, framing: any, startMs = 0) {
  await expect.poll(async () => {
    const actual = await position(page)
    const expected = expectedPosition(framing.keyframes, actual.timeMs - startMs)
    return Math.max(Math.abs(actual.x - expected.x), Math.abs(actual.y - expected.y))
  }, { message: 'Browser crop must match the analyzed path at the seek position' }).toBeLessThan(0.003)
}

test('unsaved tracking draft previews real motion, invalidates stale paths and reuses analysis at export', async ({ page, context }) => {
  test.skip(!sourceClipId || !email || !password, 'Requires a dedicated QA source clip and credentials')
  test.setTimeout(240_000)
  const browserErrors: string[] = []
  page.on('pageerror', error => browserErrors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1000 })
  await login(page)
  const source = await getClip(context.request, sourceClipId!)
  const csrf = (await context.cookies()).find(cookie => cookie.name === 'clipper_csrf')!.value
  const response = await context.request.post(`/api/v1/projects/${source.project_id}/clips`, {
    headers: { 'X-CSRF-Token': csrf },
    data: { title: `QA preview ${Date.now()}`, start_ms: 0, end_ms: 6000,
      crop_json: { mode: 'fill', tracking: 'static', ...manual },
      cues: [{ start_ms: 0, end_ms: 5000, text: 'Uji preview dan subtitle.' }] },
  })
  expect(response.status()).toBe(201)
  const created = await response.json()
  const exportCount = async () => {
    const result = await context.request.get(`/api/v1/projects/${source.project_id}/exports`, { params: { clip_id: created.id } })
    expect(result.status()).toBe(200)
    return (await result.json()).total
  }
  await page.goto(`/clips/${created.id}`)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await choose(page, 'Pelacakan frame', 'Ikuti wajah')
  expect(await exportCount()).toBe(0)
  expect((await getClip(context.request, created.id)).revision).toEqual(created.revision)
  const analyze = page.getByRole('button', { name: 'Analisis preview', exact: true })
  const requested = page.waitForResponse(result => result.request().method() === 'POST' && result.url().endsWith(`/clips/${created.id}/tracking-preview`))
  await analyze.click()
  const analysisResponse = await requested
  expect(analysisResponse.status()).toBe(202)
  const requestedJob = await analysisResponse.json()
  const job = await waitJob(context.request, requestedJob.id)
  const framing = job.result_json.framing
  expect(framing.detected_frames).toBeGreaterThan(0)
  expect(framing.fallback_reason).toBeNull()
  await atTime(page, 0)
  await assertPosition(page, framing)
  const first = await position(page)
  await atTime(page, 3)
  await assertPosition(page, framing)
  const later = await position(page)
  expect(Math.abs(later.x - first.x)).toBeGreaterThan(0.002)
  await expect(page.locator('.caption-preview')).toContainText('Uji preview dan subtitle.')
  expect(await exportCount()).toBe(0)
  expect((await getClip(context.request, created.id)).revision).toEqual(created.revision)

  // Playback must follow frames continuously, and stop at the selected clip end.
  await atTime(page, 0.5)
  await page.locator('.portrait-frame video').evaluate((video: HTMLVideoElement) => video.play())
  await expect.poll(async () => (await position(page)).timeMs).toBeGreaterThan(1500)
  await page.locator('.portrait-frame video').evaluate((video: HTMLVideoElement) => video.pause())
  await assertPosition(page, framing)
  await atTime(page, 5.7)
  await page.locator('.portrait-frame video').evaluate((video: HTMLVideoElement) => video.play())
  await expect.poll(() => page.locator('.portrait-frame video').evaluate((video: HTMLVideoElement) => video.paused)).toBe(true)
  expect((await position(page)).timeMs).toBeLessThanOrEqual(6100)

  // Outside the selected clip, the source player returns to the manual crop.
  await atTime(page, 12)
  await expect.poll(async () => (await position(page)).x).toBeCloseTo(manual.x, 4)
  await atTime(page, 2)
  await assertPosition(page, framing)
  await page.getByLabel('Judul klip', { exact: true }).fill('QA preview tersimpan')
  await assertPosition(page, framing)
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect(page.getByText('Revisi 2', { exact: true })).toBeVisible()
  await assertPosition(page, framing)
  const saved = await getClip(context.request, created.id)
  expect(saved.revision.crop_json.tracking).toBe('face')

  // Changing tracking invalidates the prior path; returning can fetch the same cached job.
  await choose(page, 'Pelacakan frame', 'Ikuti pembicara (perkiraan)')
  await expect.poll(async () => (await position(page)).x).toBeCloseTo(manual.x, 4)
  await choose(page, 'Pelacakan frame', 'Ikuti wajah')
  await page.reload()
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  const cached = page.waitForResponse(result => result.request().method() === 'POST' && result.url().endsWith(`/clips/${created.id}/tracking-preview`))
  await analyze.click()
  const cachedJob = await (await cached).json()
  expect(cachedJob.id).toBe(job.id)
  expect(cachedJob.status).toBe('succeeded')
  expect(cachedJob.attempt).toBe(1)
  await atTime(page, 2)
  await assertPosition(page, framing)

  mkdirSync(artifacts, { recursive: true })
  await page.screenshot({ path: resolve(artifacts, 'preview-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 1000 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: resolve(artifacts, 'preview-mobile.png'), fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1000 })

  // A saved equivalent draft reuses exactly the path already previewed.
  const render = await context.request.post(`/api/v1/clips/${created.id}/exports`, {
    headers: { 'X-CSRF-Token': csrf }, data: { revision: saved.revision.revision, resolution: 720 },
  })
  expect(render.status()).toBe(202)
  const rendered = await waitJob(context.request, (await render.json()).id)
  const list = await context.request.get(`/api/v1/projects/${source.project_id}/exports`, { params: { clip_id: created.id } })
  const output = (await list.json()).items.find((item: any) => item.job.id === rendered.id)
  expect(output.mp4_asset.metadata.framing.analysis_reused).toBe(true)
  expect(output.mp4_asset.metadata.framing.keyframes).toEqual(framing.keyframes)
  const video = await context.request.get(output.mp4_asset.content_url)
  expect(video.status()).toBe(200)
  writeFileSync(resolve(artifacts, 'preview-matched-export.mp4'), await video.body())
  writeFileSync(resolve(artifacts, 'report.json'), JSON.stringify({ project_id: source.project_id, clip_id: created.id,
    preview_job_id: job.id, render_job_id: rendered.id, analysis_reused: true, first_position: first, later_position: later,
    analysis_seconds: (Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000,
    render_seconds: (Date.parse(rendered.finished_at) - Date.parse(rendered.started_at)) / 1000,
    framing, export_framing: output.mp4_asset.metadata.framing }, null, 2))
  expect((await getClip(context.request, sourceClipId!)).revision).toEqual(source.revision)
  expect(browserErrors).toEqual([])
})

test('late real analysis response cannot replace a changed draft', async ({ page, context }) => {
  test.skip(!sourceClipId || !email || !password, 'Requires a dedicated QA source clip and credentials')
  test.setTimeout(180_000)
  await login(page)
  const source = await getClip(context.request, sourceClipId!)
  const csrf = (await context.cookies()).find(cookie => cookie.name === 'clipper_csrf')!.value
  const response = await context.request.post(`/api/v1/projects/${source.project_id}/clips`, {
    headers: { 'X-CSRF-Token': csrf },
    data: { title: 'QA respons preview terlambat', start_ms: 0, end_ms: 6000,
      crop_json: { mode: 'fill', tracking: 'static', ...manual }, cues: [] },
  })
  expect(response.status()).toBe(201)
  const created = await response.json()
  await page.goto(`/clips/${created.id}`)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await choose(page, 'Pelacakan frame', 'Ikuti wajah')
  let release!: () => void
  let fetched!: () => void
  const releaseResponse = new Promise<void>(resolve => { release = resolve })
  const responseFetched = new Promise<void>(resolve => { fetched = resolve })
  const endpoint = `**/clips/${created.id}/tracking-preview`
  // Delay an actual authenticated backend response, without replacing media or detector output.
  await page.route(endpoint, async route => {
    const realResponse = await route.fetch()
    fetched()
    await releaseResponse
    await route.fulfill({ response: realResponse })
  }, { times: 1 })
  const oldResponse = page.waitForResponse(result => result.request().method() === 'POST' && result.url().endsWith(`/clips/${created.id}/tracking-preview`))
  await page.getByRole('button', { name: 'Analisis preview', exact: true }).click()
  await responseFetched
  await choose(page, 'Pelacakan frame', 'Ikuti pembicara (perkiraan)')
  release()
  const oldJob = await (await oldResponse).json()
  await waitJob(context.request, oldJob.id)
  await atTime(page, 2)
  await expect.poll(async () => (await position(page)).x).toBeCloseTo(manual.x, 4)
  await expect(page.getByText('Preview pelacakan siap', { exact: true })).toHaveCount(0)
  expect((await getClip(context.request, created.id)).revision).toEqual(created.revision)

  const newResponse = page.waitForResponse(result => result.request().method() === 'POST' && result.url().endsWith(`/clips/${created.id}/tracking-preview`))
  await page.getByRole('button', { name: 'Analisis preview', exact: true }).click()
  const speakerJob = await waitJob(context.request, (await (await newResponse).json()).id)
  expect(speakerJob.id).not.toBe(oldJob.id)
  expect(speakerJob.result_json.framing.mode).toBe('speaker')
  await assertPosition(page, speakerJob.result_json.framing)

  // Bounds and manual fallback also belong to the analysis identity.
  await page.getByLabel('Keluar', { exact: true }).fill('00:08.000')
  await page.getByRole('button', { name: 'Terapkan batas', exact: true }).click()
  await expect.poll(async () => (await position(page)).x).toBeCloseTo(manual.x, 4)
  await expect(page.getByText('Preview pelacakan siap', { exact: true })).toHaveCount(0)
  await page.getByRole('slider', { name: /Posisi cadangan horizontal/ }).press('Home')
  await expect.poll(async () => (await position(page)).x).toBeCloseTo(0, 4)
  expect((await getClip(context.request, created.id)).revision).toEqual(created.revision)
})
