import { test, expect } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
const artifacts = resolve(import.meta.dirname, '../../.artifacts/word-subtitles')
test('words follow recorded timing in preview, seeks, silence and export', async ({ page, context }) => {
  const sourceId = process.env.CLIPPER_E2E_WORKSPACE_CLIP_ID
  test.skip(!sourceId, 'Requires QA transcript fixture')
  test.setTimeout(120000)
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.setViewportSize({ width:1366,height:768 })
  await page.goto('/login')
  await page.getByLabel('Email', {exact:true}).fill(process.env.CLIPPER_E2E_EMAIL!)
  await page.getByLabel('Kata sandi', {exact:true}).fill(process.env.CLIPPER_E2E_PASSWORD!)
  await page.getByLabel('Kata sandi', {exact:true}).press('Enter')
  await expect(page.getByRole('heading', {name:'Proyek',exact:true})).toBeVisible()
  const csrf = (await context.cookies()).find(c => c.name === 'clipper_csrf')!.value
  const source = await (await context.request.get(`/api/v1/clips/${sourceId}`)).json()
  const result = await context.request.post(`/api/v1/projects/${source.project_id}/clips`, {
    headers:{'X-CSRF-Token':csrf}, data:{title:'QA subtitle mengikuti suara',start_ms:0,end_ms:6000,
      crop_json:{mode:'fit',tracking:'static',x:.5,y:.5}}})
  expect(result.status()).toBe(201)
  const clip = await result.json()
  expect(clip.revision.source_words).toHaveLength(3)
  await page.goto(`/clips/${clip.id}`)
  await page.getByRole('tab',{name:'Tampilan',exact:true}).click()
  await page.getByRole('button',{name:'Gaya subtitle',exact:true}).click()
  await page.getByRole('combobox',{name:'Cara tampil subtitle',exact:true}).click()
  await page.getByRole('option',{name:'Kata per kata mengikuti suara',exact:true}).click()
  const caption = page.locator('.caption-preview')
  async function seek(seconds:number) {
    await expect.poll(() => page.locator('.portrait-frame video').evaluate((v:HTMLVideoElement) => v.readyState >= 2)).toBe(true)
    await page.locator('.portrait-frame video').evaluate((v:HTMLVideoElement,t) => {v.pause();v.currentTime=t},seconds)
    await expect.poll(() => page.locator('.portrait-frame video').evaluate((v:HTMLVideoElement) => !v.seeking && v.readyState >= 2)).toBe(true)
  }
  await seek(.6); await expect(caption).toHaveText('Ini')
  await seek(1.1); await expect(caption).toHaveCount(0)
  await seek(1.6); await expect(caption).toHaveText('momen')
  await seek(3); await expect(caption).toHaveText('seru.')
  await seek(.6); await expect(caption).toHaveText('Ini')
  await page.getByRole('button',{name:'Putar video',exact:true}).click()
  await expect(caption).toHaveText('momen')
  await page.getByRole('button',{name:'Jeda video',exact:true}).click()
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  await expect(page.getByText('Revisi 2',{exact:true})).toBeVisible()
  await page.reload()
  await seek(3); await expect(caption).toHaveText('seru.')
  mkdirSync(artifacts,{recursive:true})
  await page.screenshot({path:resolve(artifacts,'preview-laptop.png')})
  await page.setViewportSize({width:390,height:844})
  await page.getByRole('button',{name:'Alat editor',exact:true}).click()
  await page.getByRole('tab',{name:'Tampilan',exact:true}).click()
  await page.getByRole('button',{name:'Gaya subtitle',exact:true}).click()
  expect(await page.locator('.editor-panel-content').evaluate(e => e.scrollHeight <= e.clientHeight+2)).toBe(true)
  await page.screenshot({path:resolve(artifacts,'settings-mobile.png')})
  const exported = await context.request.post(`/api/v1/clips/${clip.id}/exports`, {headers:{'X-CSRF-Token':csrf},data:{revision:2,resolution:720}})
  expect(exported.status()).toBe(202)
  const id = (await exported.json()).id
  let job:any
  await expect.poll(async () => {job=await (await context.request.get(`/api/v1/jobs/${id}`)).json();return ['succeeded','failed','cancelled'].includes(job.status)}, {timeout:90000}).toBe(true)
  expect(job.status,job.error_message).toBe('succeeded')
  const list=await (await context.request.get(`/api/v1/projects/${source.project_id}/exports`,{params:{clip_id:clip.id}})).json()
  const output=list.items.find((e:any) => e.job.id === id)
  writeFileSync(resolve(artifacts,'word-export.mp4'),await (await context.request.get(output.mp4_asset.content_url)).body())
  const srt=await (await context.request.get(output.srt_asset.content_url)).text()
  expect(srt).toContain('Ini momen seru.')
  writeFileSync(resolve(artifacts,'report.json'),JSON.stringify({clip_id:clip.id,job_id:id,timing:clip.revision.source_words,errors},null,2))
  expect(errors).toEqual([])
})
