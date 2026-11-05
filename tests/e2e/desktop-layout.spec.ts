import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

test('desktop shell stays fixed while readable content panels scroll', async ({ page, context }) => {
  test.skip(!process.env.CLIPPER_E2E_WORKSPACE_CLIP_ID, 'Disposable QA account required')
  test.setTimeout(120000)
  const artifacts = resolve(import.meta.dirname, '../../.artifacts/desktop-layout')
  mkdirSync(artifacts, { recursive: true })
  const errors:string[]=[]
  page.on('pageerror', e => errors.push(e.message))
  await page.setViewportSize({width:1366,height:768})
  await page.goto('/login')
  async function fits(name:string) {
    await expect.poll(async () => page.evaluate(() => ({
      body:document.documentElement.scrollHeight<=innerHeight+2 && document.documentElement.scrollWidth<=innerWidth+2 ? true : {height:document.documentElement.scrollHeight,width:document.documentElement.scrollWidth,viewport:[innerWidth,innerHeight]},
      clippedControls:Array.from(document.querySelectorAll<HTMLElement>('.main-content button,.main-content input,.main-content textarea,.main-content select,.dialog button,.dialog input,.dialog textarea,.dialog select')).filter(e => {
        const r=e.getBoundingClientRect()
        // Long inspectors and dialogs scroll at their native font size. A control
        // may be outside the viewport only if a bounded ancestor can reveal it.
        let ancestor=e.parentElement
        while(ancestor && ancestor!==document.body) {
          const style=getComputedStyle(ancestor), bounds=ancestor.getBoundingClientRect()
          if(/(auto|scroll)/.test(style.overflowY) && ancestor.scrollHeight>ancestor.clientHeight+2 && bounds.top>=-1 && bounds.bottom<=innerHeight+1) return false
          ancestor=ancestor.parentElement
        }
        return r.width>2 && r.height>2 && (r.top < -1 || r.bottom > innerHeight+1 || r.left < -1 || r.right > innerWidth+1)
      }).map(e=>e.getAttribute('aria-label') || e.textContent?.slice(0,40) || e.tagName),
      scrollers:Array.from(document.querySelectorAll<HTMLElement>('body *')).filter(e => {
        const r=e.getBoundingClientRect(),s=getComputedStyle(e)
        return r.width>0 && r.height>0 && !['TEXTAREA','SELECT'].includes(e.tagName) && /(auto|scroll)/.test(s.overflowY) && e.scrollHeight>e.clientHeight+2 && (r.top < -1 || r.bottom > innerHeight+1)
      }).map(e=>e.className)
    })),{message:name}).toEqual({body:true,scrollers:[],clippedControls:[]})
    await page.screenshot({path:resolve(artifacts,name+'.png')})
  }
  await fits('login')
  await page.getByLabel('Email',{exact:true}).fill(process.env.CLIPPER_E2E_EMAIL!)
  await page.getByLabel('Kata sandi',{exact:true}).fill(process.env.CLIPPER_E2E_PASSWORD!)
  await page.getByLabel('Kata sandi',{exact:true}).press('Enter')
  await expect(page.getByRole('heading',{name:'Proyek',exact:true})).toBeVisible()
  const csrf=(await context.cookies()).find(c=>c.name==='clipper_csrf')!.value
  const headers={'X-CSRF-Token':csrf}
  const clipId=process.env.CLIPPER_E2E_WORKSPACE_CLIP_ID!
  const clip=await (await context.request.get(`/api/v1/clips/${clipId}`)).json()
  for(let i=0;i<25;i++) {
    expect((await context.request.post('/api/v1/projects',{headers,data:{name:`Desktop QA ${i}`}})).ok()).toBe(true)
    expect((await context.request.post(`/api/v1/projects/${clip.project_id}/clips`,{headers,data:{title:`Desktop kandidat ${i}`,start_ms:0,end_ms:6000}})).ok()).toBe(true)
  }
  await page.reload()
  await expect.poll(() => page.locator('.project-row').count()).toBeGreaterThan(5)
  const library=page.getByRole('region',{name:'Daftar proyek',exact:true})
  await library.hover(); await page.mouse.wheel(0,600)
  await expect.poll(()=>library.evaluate(e=>e.scrollTop)).toBeGreaterThan(0)
  await expect(page.getByRole('button',{name:'Proyek baru',exact:true})).toBeInViewport()
  await fits('projects')
  await page.getByRole('button',{name:'Berikutnya',exact:true}).click()
  await expect(page.locator('.pagination')).toContainText('Halaman 2')
  await fits('projects-next')
  await page.getByRole('button',{name:'Proyek baru',exact:true}).click()
  await fits('upload-dialog')
  await page.getByRole('button',{name:'Tutup dialog',exact:true}).click()
  await page.goto('/settings')
  await expect(page.getByRole('button',{name:'Simpan batas',exact:true})).toBeVisible()
  for(const section of ['Batas pemrosesan','Koneksi akun','Video','AI & layanan','Pemakaian']) {
    await page.getByRole('group',{name:'Bagian pengaturan'}).getByRole('button',{name:section,exact:true}).click()
    if(section==='Koneksi akun') for(const details of await page.locator('.connection-grid summary').all()) await details.click()
    if(section==='AI & layanan') await page.getByText('Status layanan',{exact:true}).click()
    await fits('settings-'+section.replace(/[^a-z]/gi,''))
  }
  await page.goto(`/projects/${clip.project_id}`)
  await expect.poll(() => page.locator('.clip-row').count()).toBeGreaterThan(3)
  const candidates=page.getByRole('region',{name:'Daftar kandidat',exact:true})
  const sourcePosition=await page.locator('.source-player').boundingBox()
  await candidates.hover(); await page.mouse.wheel(0,700)
  await expect.poll(()=>candidates.evaluate(e=>e.scrollTop)).toBeGreaterThan(0)
  expect((await page.locator('.source-player').boundingBox())!.y).toBe(sourcePosition!.y)
  await fits('project-detail')
  await page.goto(`/clips/${clipId}`)
  await expect(page.getByRole('button',{name:'Tambah subtitle',exact:true})).toBeVisible()
  for(let i=0;i<20;i++) await page.getByRole('button',{name:'Tambah subtitle',exact:true}).click()
  await expect(page.locator('.cue-row')).toHaveCount(20)
  const subtitles=page.getByRole('region',{name:'Daftar subtitle',exact:true})
  const header=await page.locator('.editor-header').boundingBox()
  const player=await page.locator('.player-matte').boundingBox()
  await subtitles.hover(); await page.mouse.wheel(0,850)
  await expect.poll(()=>subtitles.evaluate(e=>e.scrollTop)).toBeGreaterThan(0)
  expect((await page.locator('.editor-header').boundingBox())!.y).toBe(header!.y)
  expect((await page.locator('.player-matte').boundingBox())!.y).toBe(player!.y)
  await expect(page.getByRole('button',{name:'Tambah subtitle',exact:true})).toBeInViewport()
  await subtitles.focus(); await page.keyboard.press('End')
  await expect(page.getByLabel('Teks subtitle 20',{exact:true})).toBeInViewport()
  await page.getByLabel('Teks subtitle 20',{exact:true}).fill('Subtitle terakhir tetap dapat diedit')
  await fits('editor-subtitles')
  await page.setViewportSize({width:1366,height:1080})
  await expect(page.locator('.cue-row')).toHaveCount(20)
  await fits('editor-subtitles-tall')
  await page.setViewportSize({width:1366,height:768})
  await page.getByRole('tab',{name:'Tampilan',exact:true}).click()
  await page.getByRole('button',{name:'Gaya subtitle',exact:true}).click()
  await fits('editor-style')
  await page.getByRole('button',{name:'Warna & efek',exact:true}).click()
  await fits('editor-effects')
  // A full navigation discards QA-only, unsaved subtitle edits.
  await page.goto('/calendar')
  await expect(page.getByRole('heading',{name:'Kalender',exact:true})).toBeVisible()
  await fits('calendar')
  await page.getByRole('button',{name:'Tambah jadwal',exact:true}).click()
  await fits('schedule-details')
  await page.getByRole('button',{name:'Opsi publikasi',exact:true}).click()
  await fits('schedule-options')
  await page.getByRole('button',{name:'Tutup dialog',exact:true}).click()
  for(const size of [{width:1280,height:720},{width:1920,height:1080}]) {
    await page.setViewportSize(size)
    for(const [name,url] of [['library','/'],['settings','/settings'],['project',`/projects/${clip.project_id}`],['editor',`/clips/${clipId}`],['calendar','/calendar']]) {
      await page.goto(url!)
      await expect(page.locator('.page,.editor-page').first()).toBeVisible()
      await expect(page.locator('.loading-text')).toHaveCount(0)
      if(name==='editor') await expect(page.getByRole('button',{name:'Tambah subtitle',exact:true})).toBeVisible()
      await fits(name+'-'+size.width)
    }
  }
  await page.setViewportSize({width:390,height:844})
  await page.goto('/calendar')
  await expect(page.getByRole('button',{name:'Tambah jadwal',exact:true})).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2)).toBe(true)
  expect(errors).toEqual([])
})
