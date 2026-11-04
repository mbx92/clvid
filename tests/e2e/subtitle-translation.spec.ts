import {expect,test,type Page} from '@playwright/test'

async function fixture(page:Page, empty=false) {
  let clip:any = {id:'translation-clip',project_id:'translation-project',origin:'manual',media_duration_ms:60000,translation_available:true,
    revision:{id:'rev-1',revision:1,start_ms:0,end_ms:10000,title:'Coffee beans',reason:'',crop_json:{mode:'fit',x:.5,y:.5},source_words:[],
      cues:empty?[]:[{start_ms:500,end_ms:2500,text:'Coffee grows inside a fruit.'},{start_ms:3000,end_ms:5000,text:'Look at these two beans.'}],
      subtitle_style_json:{enabled:true,renderer:'remotion',remotion_template:'podcast',display_mode:'words',font_size:52,position:'bottom',background:true,safe_margin:.15}}}
  const job:any = {id:'translation-job',project_id:clip.project_id,kind:'subtitle_translate',stage:'subtitle_translate',status:'queued',progress:null}
  let submitted:any, saved:any, exportRequest:any
  await page.route('**/api/v1/**',async route=>{
    const request=route.request(), path=new URL(request.url()).pathname
    if(path==='/api/v1/auth/me') return route.fulfill({headers:{'Set-Cookie':'clipper_csrf=test-token; Path=/; SameSite=Lax'},json:{id:'user',email:'test@example.invalid',csrf_token:'test-token'}})
    if(path===`/api/v1/clips/${clip.id}`) {
      if(request.method()==='PATCH') {saved=request.postDataJSON();clip={...clip,revision:{...clip.revision,...saved,revision:clip.revision.revision+1}}}
      return route.fulfill({json:clip})
    }
    if(path.endsWith('/subtitles/translate')) {submitted=request.postDataJSON();return route.fulfill({json:job})}
    if(path===`/api/v1/jobs/${job.id}`) return route.fulfill({json:job})
    if(path===`/api/v1/clips/${clip.id}/exports`) {exportRequest=request.postDataJSON();return route.fulfill({json:{id:'export',status:'queued'}})}
    if(path===`/api/v1/projects/${clip.project_id}/exports`) return route.fulfill({json:{items:[],total:0}})
    return route.fulfill({status:404,json:{message:'Unexpected request'}})
  })
  await page.setViewportSize({width:1366,height:900})
  await page.goto('/clips/translation-clip')
  await expect(page.getByLabel('Judul klip',{exact:true})).toHaveValue('Coffee beans')
  return {submitted:()=>submitted,saved:()=>saved,exportRequest:()=>exportRequest,finish(){job.status='succeeded';job.progress=1;job.result_json={base_revision:1,target_language:'id',translated_cues:[{start_ms:500,end_ms:2500,text:'Kopi tumbuh di dalam buah.'},{start_ms:3000,end_ms:5000,text:'Lihat dua biji ini.'}]}}}
}

test('review English translation, preserve timing, save and export Indonesian subtitles',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
  const f=await fixture(page)
  await page.getByRole('button',{name:'Terjemahkan',exact:true}).click()
  await page.getByRole('button',{name:'Mulai terjemahkan',exact:true}).click()
  await expect.poll(f.submitted).toEqual({expected_revision:1,target_language:'id'})
  f.finish()
  await expect(page.getByText('2 subtitle siap ditinjau.',{exact:true})).toBeVisible()
  expect(f.saved()).toBeUndefined()
  await expect(page.getByLabel('Teks subtitle 1',{exact:true})).toHaveValue('Coffee grows inside a fruit.')
  await page.screenshot({path:test.info().outputPath('translation-review-desktop.png')})
  await page.setViewportSize({width:390,height:844})
  await page.screenshot({path:test.info().outputPath('translation-review-mobile.png')})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
  await page.getByRole('button',{name:'Terapkan terjemahan ke draft',exact:true}).click()
  await page.setViewportSize({width:1366,height:900})
  await expect(page.getByLabel('Teks subtitle 1',{exact:true})).toHaveValue('Kopi tumbuh di dalam buah.')
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  expect(f.saved().subtitle_style_json.display_mode).toBe('sentence')
  expect(f.saved().subtitle_style_json.remotion_template).toBe('minimal')
  expect(f.saved().cues[0]).toEqual({start_ms:500,end_ms:2500,text:'Kopi tumbuh di dalam buah.'})
  await page.reload()
  await expect(page.getByLabel('Teks subtitle 1',{exact:true})).toHaveValue('Kopi tumbuh di dalam buah.')
  await page.getByRole('button',{name:'Ekspor',exact:true}).click()
  await page.getByRole('button',{name:'Mulai ekspor',exact:true}).click()
  await expect.poll(f.exportRequest).toBeTruthy()
  expect(errors).toEqual([])
})

test('translation completion cannot replace edits or a newer saved revision',async({page})=>{
  const f=await fixture(page)
  await page.getByRole('button',{name:'Terjemahkan',exact:true}).click()
  await page.getByRole('button',{name:'Mulai terjemahkan',exact:true}).click()
  await expect.poll(f.submitted).toBeTruthy()
  await page.getByRole('button',{name:'Tutup',exact:true}).click()
  await page.getByLabel('Teks subtitle 1',{exact:true}).fill('My correction')
  f.finish()
  await page.getByRole('button',{name:'Tinjau terjemahan',exact:true}).click()
  await expect(page.getByRole('button',{name:'Terapkan terjemahan ke draft'})).toBeDisabled()
  await page.getByRole('button',{name:'Tutup',exact:true}).click()
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  await page.getByRole('button',{name:'Tinjau terjemahan',exact:true}).click()
  await expect(page.getByRole('button',{name:'Terapkan terjemahan ke draft'})).toBeDisabled()
  expect(f.saved().cues[0].text).toBe('My correction')
})

test('empty clip explains transcription before translation',async({page})=>{
  await fixture(page,true)
  await expect(page.getByRole('button',{name:'Terjemahkan',exact:true})).toBeDisabled()
  await expect(page.getByText('Buat subtitle lewat Dari audio, pilih English, lalu terjemahkan di sini.')).toBeVisible()
  await page.getByRole('tab',{name:'Timeline',exact:true}).click()
  await expect(page.getByRole('button',{name:'Terjemahkan',exact:true})).toBeVisible()
})
