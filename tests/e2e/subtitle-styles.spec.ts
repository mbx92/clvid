import { test, expect } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
const artifacts = resolve(import.meta.dirname, '../../.artifacts/subtitle-styles')

test('subtitle size changes visibly and styles persist through export', async ({ page, context }) => {
  const sourceId = process.env.CLIPPER_E2E_WORKSPACE_CLIP_ID
  test.skip(!sourceId, 'Requires disposable QA fixture')
  test.setTimeout(120000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setViewportSize({ width: 1366, height: 768 })
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(process.env.CLIPPER_E2E_EMAIL!)
  await page.getByLabel('Kata sandi', { exact: true }).fill(process.env.CLIPPER_E2E_PASSWORD!)
  await page.getByLabel('Kata sandi', { exact: true }).press('Enter')
  await expect(page.getByRole('heading', { name: 'Proyek', exact: true })).toBeVisible()
  const source = await (await context.request.get(`/api/v1/clips/${sourceId}`)).json()
  const csrf = (await context.cookies()).find(c => c.name === 'clipper_csrf')!.value
  const created = await context.request.post(`/api/v1/projects/${source.project_id}/clips`, {
    headers: { 'X-CSRF-Token': csrf }, data: { title: 'QA ukuran dan gaya subtitle', start_ms: 0, end_ms: 6000,
      crop_json: { mode: 'fit', tracking: 'static', x: .5, y: .5 },
      cues: [{ start_ms: 0, end_ms: 6000, text: 'Ukuran teks berubah sesuai pilihan' }] },
  })
  expect(created.status()).toBe(201)
  const clip = await created.json()
  await page.goto(`/clips/${clip.id}`)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await page.getByRole('button', { name: 'Gaya subtitle', exact: true }).click()
  const caption = page.locator('.caption-preview')
  await expect(caption).toBeVisible()
  const size = page.getByRole('slider', { name: 'Ukuran teks subtitle', exact: true })
  await size.press('Home')
  const small = await caption.evaluate(el => parseFloat(getComputedStyle(el).fontSize))
  await size.press('End')
  await expect(page.getByLabel('Kecilkan otomatis agar muat dua baris')).not.toBeChecked()
  const large = await caption.evaluate(el => parseFloat(getComputedStyle(el).fontSize))
  expect(large / small).toBeCloseTo(100 / 24, 1)
  await page.getByRole('button', { name: 'Preset Kuning', exact: true }).click()
  await expect(caption).toHaveCSS('color', 'rgb(255, 230, 0)')
  await expect(caption).toHaveCSS('font-weight', '700')
  await size.press('End')
  mkdirSync(artifacts, { recursive: true })
  await page.screenshot({ path: resolve(artifacts, 'presets-laptop.png') })
  await page.getByRole('button', { name: 'Warna & efek', exact: true }).click()
  await page.getByLabel('Warna teks subtitle', { exact: true }).fill('#ff55aa')
  await page.getByLabel('Miring', { exact: true }).check()
  await expect(caption).toHaveCSS('color', 'rgb(255, 85, 170)')
  await expect(caption).toHaveCSS('font-style', 'italic')
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect(page.getByText('Revisi 2', { exact: true })).toBeVisible()
  await page.reload()
  await expect(caption).toHaveCSS('color', 'rgb(255, 85, 170)')
  await expect(caption).toHaveCSS('font-weight', '700')
  const saved = await (await context.request.get(`/api/v1/clips/${clip.id}`)).json()
  expect(saved.revision.subtitle_style_json.font_size).toBe(100)
  expect(saved.revision.subtitle_style_json.auto_fit).toBe(false)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: resolve(artifacts, 'preview-mobile.png') })
  await page.getByRole('button', { name: 'Alat editor', exact: true }).click()
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await page.getByRole('button', { name: 'Gaya subtitle', exact: true }).click()
  async function fits() {
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 2)).toBe(true)
    const panel = await page.locator('.editor-panel-content').evaluate(el => ({ scroll: el.scrollHeight, height: el.clientHeight }))
    expect(panel.scroll).toBeLessThanOrEqual(panel.height + 2)
  }
  await fits()
  await page.screenshot({ path: resolve(artifacts, 'presets-mobile.png') })
  await page.getByRole('button', { name: 'Warna & efek', exact: true }).click()
  await fits()
  await page.screenshot({ path: resolve(artifacts, 'custom-mobile.png') })
  const exported = await context.request.post(`/api/v1/clips/${clip.id}/exports`, {
    headers: { 'X-CSRF-Token': csrf }, data: { revision: 2, resolution: 720 },
  })
  expect(exported.status()).toBe(202)
  const jobId = (await exported.json()).id
  let job: any
  await expect.poll(async () => {
    job = await (await context.request.get(`/api/v1/jobs/${jobId}`)).json()
    return ['succeeded', 'failed', 'cancelled'].includes(job.status)
  }, { timeout: 90000 }).toBe(true)
  expect(job.status, job.error_message).toBe('succeeded')
  const outputs = await (await context.request.get(`/api/v1/projects/${source.project_id}/exports`, { params: { clip_id: clip.id } })).json()
  const output = outputs.items.find((item: any) => item.job.id === jobId)
  const content = await context.request.get(output.mp4_asset.content_url)
  expect(content.status()).toBe(200)
  writeFileSync(resolve(artifacts, 'styled-export.mp4'), await content.body())
  writeFileSync(resolve(artifacts, 'report.json'), JSON.stringify({ clip_id: clip.id, job_id: jobId, small, large,
    style: saved.revision.subtitle_style_json, errors }, null, 2))
  expect(errors).toEqual([])
})
