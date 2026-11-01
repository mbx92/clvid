import { test, expect, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Opt-in acceptance test using the isolated 43.76-second two-speaker fixture.
const sourceClipId = process.env.CLIPPER_E2E_SPEAKER_CLIP_ID
const email = process.env.CLIPPER_E2E_EMAIL
const password = process.env.CLIPPER_E2E_PASSWORD
const artifacts = resolve(import.meta.dirname, '../../.artifacts/speaker-switching')

async function seek(page: Page, seconds: number) {
  const video = page.locator('.portrait-frame video')
  await video.evaluate((element: HTMLVideoElement, time) => { element.pause(); element.currentTime = time }, seconds)
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => !element.seeking && element.readyState >= 2)).toBe(true)
}

async function horizontalPosition(page: Page) {
  return page.locator('.portrait-frame video').evaluate(element => parseFloat(getComputedStyle(element).objectPosition) / 100)
}

test('two speakers hand off the preview crop and export reuses the same path', async ({ page, context }) => {
  test.skip(!sourceClipId || !email || !password, 'Requires the dedicated two-speaker QA source and credentials')
  test.setTimeout(240_000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(email!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(password!)
  await page.getByLabel('Kata sandi', { exact: true }).press('Enter')
  await expect(page.getByRole('heading', { name: 'Proyek', exact: true })).toBeVisible()
  const source = await (await context.request.get(`/api/v1/clips/${sourceClipId}`)).json()
  const csrf = (await context.cookies()).find(cookie => cookie.name === 'clipper_csrf')!.value
  const createdResponse = await context.request.post(`/api/v1/projects/${source.project_id}/clips`, {
    headers: { 'X-CSRF-Token': csrf }, data: { title: 'QA pergantian dua pembicara', start_ms: 0, end_ms: 43760,
      crop_json: { mode: 'fill', tracking: 'speaker', x: .5, y: .5 }, cues: [] },
  })
  expect(createdResponse.status()).toBe(201)
  const clip = await createdResponse.json()
  await page.goto(`/clips/${clip.id}`)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  const requested = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith(`/clips/${clip.id}/tracking-preview`))
  await page.getByRole('button', { name: 'Analisis preview', exact: true }).click()
  const preview = await (await requested).json()
  async function completed(id: string) {
    let job: any
    await expect.poll(async () => {
      job = await (await context.request.get(`/api/v1/jobs/${id}`)).json()
      return ['succeeded', 'failed', 'cancelled'].includes(job.status)
    }, { timeout: 180_000, intervals: [500, 1000, 2000] }).toBe(true)
    expect(job.status, job.error_message).toBe('succeeded')
    return job
  }
  const job = await completed(preview.id)
  const framing = job.result_json.framing
  expect(framing.method).toBe('yunet-light-asd-v1')
  expect(framing.speaker_model_sha256).toMatch(/^[a-f0-9]{64}$/)
  expect(framing.speaker_switches).toBeGreaterThanOrEqual(2)
  expect(framing.speaker_switches).toBeLessThanOrEqual(5)
  expect(framing.fallback_reason).toBeNull()
  await expect(page.getByText('Preview pelacakan siap', { exact: true })).toBeVisible()
  await expect(page.getByText(`Perpindahan pembicara terdeteksi: ${framing.speaker_switches}.`, { exact: true })).toBeVisible()
  mkdirSync(artifacts, { recursive: true })
  const positions: any[] = []
  for (const [seconds, side] of [[5, 'right'], [23, 'left'], [34, 'right'], [40, 'left']] as const) {
    await seek(page, seconds)
    await expect.poll(async () => (await horizontalPosition(page)) > .5).toBe(side === 'right')
    positions.push({ seconds, side, x: await horizontalPosition(page) })
    await page.locator('.portrait-frame').screenshot({ path: resolve(artifacts, `preview-${seconds}s-${side}.png`) })
  }
  // A reload may restore only an analysis with the current model signature.
  await page.reload()
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  const cachedResponse = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith(`/clips/${clip.id}/tracking-preview`))
  await page.getByRole('button', { name: 'Analisis preview', exact: true }).click()
  expect((await (await cachedResponse).json()).id).toBe(job.id)
  await seek(page, 23)
  await expect.poll(() => horizontalPosition(page)).toBeLessThan(.5)
  const renderResponse = await context.request.post(`/api/v1/clips/${clip.id}/exports`, {
    headers: { 'X-CSRF-Token': csrf }, data: { revision: clip.revision.revision, resolution: 720 },
  })
  expect(renderResponse.status()).toBe(202)
  const render = await completed((await renderResponse.json()).id)
  const exports = await (await context.request.get(`/api/v1/projects/${source.project_id}/exports`, { params: { clip_id: clip.id } })).json()
  const output = exports.items.find((item: any) => item.job.id === render.id)
  expect(output.mp4_asset.metadata.framing.analysis_reused).toBe(true)
  expect(output.mp4_asset.metadata.framing.keyframes).toEqual(framing.keyframes)
  const content = await context.request.get(output.mp4_asset.content_url)
  expect(content.status()).toBe(200)
  writeFileSync(resolve(artifacts, 'speaker-export.mp4'), await content.body())
  writeFileSync(resolve(artifacts, 'report.json'), JSON.stringify({ clip_id: clip.id, preview_job_id: job.id,
    render_job_id: render.id, framing, positions, analysis_reused: true,
    analysis_seconds: (Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000,
    render_seconds: (Date.parse(render.finished_at) - Date.parse(render.started_at)) / 1000 }, null, 2))
  expect((await (await context.request.get(`/api/v1/clips/${sourceClipId}`)).json()).revision).toEqual(source.revision)
  expect(errors).toEqual([])
})
