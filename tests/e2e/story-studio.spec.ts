import {expect, test, type Page} from '@playwright/test'
import {readFileSync} from 'node:fs'

async function fixture(page: Page) {
  const theme = {background:'#132923',foreground:'#FFFFFF',accent:'#D9F279',font:'sans',motion:'rise',align:'left',font_size:72,uppercase:false}
  const scene = {id:'intro',layout:'title',title:'Cerita dimulai dari secangkir kopi.',text:'Tiga kebiasaan kecil untuk seduhan yang lebih baik.',narration:'Mulai dengan biji yang segar.',visual_note:'',duration_ms:5000,asset_id:null,audio_id:null,media_start_ms:0,show_caption:true}
  let data: any = {id:'story-test',version:1,document:{title:'Ritual kopi pagi',script:'Mulai dengan biji yang segar.',style_prompt:'',preserve_script:true,aspect:'portrait',theme,scenes:[scene]},assets:[],jobs:[],ai_available:true,capabilities:{images:true,speech:true,alignment:true,voices:['coral','alloy'],default_voice:'coral'}}
  const templates: any[] = [{id:'editorial',name:'Editorial',theme},{id:'paper',name:'Paper',theme:{...theme,background:'#F5F0E6',foreground:'#292522',accent:'#B7462F',font:'serif',motion:'fade'}}]
  let submitted: any
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname
    if(path === '/api/v1/auth/me') return route.fulfill({headers:{'Set-Cookie':'clipper_csrf=test-token; Path=/; SameSite=Lax'},json:{id:'test-user',email:'test@example.invalid',csrf_token:'test-token'}})
    if(path === '/api/v1/studio/templates') {
      if(req.method() === 'POST') templates.push({id:'personal',...req.postDataJSON(),custom:true})
      return route.fulfill({json:req.method() === 'POST' ? templates.at(-1) : {items:templates}})
    }
    if(path === '/api/v1/studio/story-test') {
      if(req.method() === 'PUT') {const body = req.postDataJSON(); data.document = body.document; data.version++}
      return route.fulfill({json:data})
    }
    if(path === '/api/v1/assets/generated-image/content') return route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')})
    if(path === '/api/v1/assets/generated-audio/content') {
      const wav = Buffer.alloc(44 + 8000 * 2 * 7)
      wav.write('RIFF'); wav.writeUInt32LE(wav.length-8,4); wav.write('WAVEfmt ',8); wav.writeUInt32LE(16,16); wav.writeUInt16LE(1,20); wav.writeUInt16LE(1,22); wav.writeUInt32LE(8000,24); wav.writeUInt32LE(16000,28); wav.writeUInt16LE(2,32); wav.writeUInt16LE(16,34); wav.write('data',36); wav.writeUInt32LE(wav.length-44,40)
      return route.fulfill({contentType:'audio/wav',body:wav})
    }
    if(path.endsWith('/produce')) {
      submitted = req.postDataJSON()
      const document = structuredClone(data.document), target = document.scenes.find((s:any) => !submitted.scene_id || submitted.scene_id === s.id)
      const addAsset = (id:string,kind:string,mime:string) => {if (!data.assets.some((a:any) => a.id === id)) data.assets.push({id,kind:'story_media',bytes:100,mime,state:'ready',metadata:{story_kind:kind,filename:`${kind} adegan`,duration_ms:kind === 'audio' ? 7000 : 0,generated:true},content_url:`/api/v1/assets/${id}/content`})}
      if(submitted.mode === 'images' || submitted.mode === 'complete' && !target.asset_id && (!target.visual || target.visual.kind === 'none')) {target.asset_id = 'generated-image'; addAsset('generated-image','image','image/png')}
      if(['speech','complete'].includes(submitted.mode)) {target.audio_id = 'generated-audio'; addAsset('generated-audio','audio','audio/wav')}
      if(['speech','captions','complete'].includes(submitted.mode)) {target.duration_ms = 7000; target.captions = [{start_ms:350,end_ms:6350,text:target.narration}]; target.caption_audio_id = target.audio_id; target.caption_narration = target.narration}
      const job = {id:'produce-job',kind:'story_produce',stage:'story_captions',project_id:data.id,status:'succeeded',progress:1,result_json:{document,mode:submitted.mode,base_version:data.version,warnings:['Durasi adegan disesuaikan agar audio selesai.']}}
      data.jobs = [job]
      return route.fulfill({json:job})
    }
    if(path.endsWith('/generate')) {
      submitted = req.postDataJSON()
      const document = structuredClone(data.document)
      if(submitted.mode === 'style') document.theme.accent = '#FFAA44'
      else if(submitted.mode === 'visuals') document.scenes[0].visual = {kind:'coffee_pair',items:[],motion:'gentle',reveal_ms:2000}
      else document.scenes[0].title = 'Usulan cerita baru'
      const job = {id:'ai-job',kind:'story_generate',stage:'story_generate',project_id:data.id,status:'succeeded',progress:1,result_json:{document,mode:submitted.mode,base_version:data.version}}
      data.jobs = [job]
      return route.fulfill({json:job})
    }
    if(path.endsWith('/visuals')) {
      submitted = req.postDataJSON()
      const document = structuredClone(data.document)
      document.scenes[0].visual = {kind:'coffee_compare',items:[],motion:'gentle',reveal_ms:2000}
      return route.fulfill({json:{document,base_version:data.version,mode:'visuals'}})
    }
    if(path.endsWith('/import-table')) {
      const document = structuredClone(data.document)
      document.title = 'Mana Biji Kopi yang Tumbuh Sendirian?'
      document.scenes = [7,11,11,11,15,13].map((duration,i) => ({...scene,id:`scene-${i+1}`,title:`Adegan ${i+1}`,duration_ms:duration*1000,narration:i ? 'Narasi berikutnya.' : 'Salah satu biji kopi ini tumbuh sendirian di dalam buahnya. Coba tebak, yang A atau yang B?'}))
      return route.fulfill({json:{document,base_version:data.version,mode:'storyboard'}})
    }
    if(path.endsWith('/render')) {
      submitted = req.postDataJSON()
      const job = {id:'render-job',kind:'story_render',stage:'story_render',project_id:data.id,status:'queued',progress:0}
      data.jobs.unshift(job)
      return route.fulfill({json:job})
    }
    return route.fulfill({status:404,json:{message:'Unexpected request'}})
  })
  await page.setViewportSize({width:1440,height:1000})
  await page.goto('/studio/story-test')
  await expect(page.getByLabel('Judul video',{exact:true})).toHaveValue('Ritual kopi pagi')
  return {data:()=>data,submitted:()=>submitted}
}

test('story editor previews, saves edits, adds scenes and reuses personal style templates', async ({page}) => {
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message))
  const f = await fixture(page)
  await expect(page.locator('[data-story-scene="intro"]')).toBeVisible()
  await page.getByRole('tab',{name:'Adegan'}).click()
  await page.screenshot({path:test.info().outputPath('story-editor-desktop.png')})
  await page.getByLabel('Judul adegan',{exact:true}).fill('Kopi yang lebih baik')
  await page.getByRole('button',{name:'Tambah adegan',exact:true}).click()
  await page.getByLabel('Judul adegan',{exact:true}).fill('Nikmati perlahan')
  await page.getByRole('button',{name:'Geser adegan ke kiri'}).click()
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  expect(f.data().document.scenes[0].title).toBe('Nikmati perlahan')
  await page.getByRole('tab',{name:'Gaya',exact:true}).click()
  await page.getByRole('button',{name:'Aa Paper',exact:true}).click()
  await page.getByRole('button',{name:'Simpan sebagai template'}).click()
  await page.getByLabel('Nama template').fill('Kopi hangat')
  await page.getByRole('button',{name:'Simpan template',exact:true}).click()
  await expect(page.getByRole('button',{name:'Aa Kopi hangat',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  await page.reload()
  await page.getByRole('tab',{name:'Adegan'}).click()
  await expect(page.getByLabel('Judul adegan',{exact:true})).toHaveValue('Nikmati perlahan')
  await page.setViewportSize({width:390,height:844})
  await page.screenshot({path:test.info().outputPath('story-editor-mobile.png')})
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.getByRole('button',{name:'Preview',exact:true}).click()
  await expect(page.locator('.story-preview-stage')).toBeVisible()
  await page.screenshot({path:test.info().outputPath('story-preview-mobile.png')})
  expect(errors).toEqual([])
})

test('illustrations are reviewed, editable, persisted and previewed with all coffee recipes', async ({page}) => {
  const errors: string[] = []; page.on('pageerror',e=>errors.push(e.message))
  const f = await fixture(page)
  await page.getByRole('tab',{name:'Adegan'}).click()
  await page.getByRole('button',{name:'Isi visual kosong',exact:true}).click()
  await expect(page.getByRole('dialog',{name:'Tinjau usulan'})).toBeVisible()
  expect(f.data().document.scenes[0].visual).toBeUndefined()
  await page.getByRole('button',{name:'Terapkan ke draft'}).click()
  await expect(page.locator('[data-story-visual="coffee_compare"]')).toBeVisible()
  for(const kind of ['coffee_compare','coffee_flat','coffee_pair','coffee_separate','coffee_peaberry','coffee_reveal','steps']) {
    await page.getByLabel('Jenis ilustrasi').selectOption(kind)
    await page.getByLabel('Gerakan ilustrasi').selectOption('still')
    await expect(page.locator(`[data-story-visual="${kind}"]`)).toBeVisible()
    await page.locator('.story-preview-stage').screenshot({path:test.info().outputPath(`${kind}.png`)})
  }
  for(let i=1;i<=4;i++) {
    await page.getByRole('button',{name:'Tambah objek',exact:true}).click()
    await page.getByRole('combobox',{name:new RegExp(`^Objek ${i}`)}).selectOption(['bean','water','cup','check'][i-1]!)
    await page.getByLabel(`Label ${i}`,{exact:true}).fill(['Biji kopi pilihan','Air bersih','Seduh perlahan','Nikmati kopi'][i-1]!)
  }
  for(const aspect of ['portrait','landscape','square']) {
    await page.getByLabel('Format').selectOption(aspect)
    await page.locator('.story-preview-stage').screenshot({path:test.info().outputPath(`steps-${aspect}.png`)})
  }
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  await page.reload()
  await page.getByRole('tab',{name:'Adegan'}).click()
  await expect(page.getByLabel('Jenis ilustrasi')).toHaveValue('steps')
  await page.getByRole('button',{name:'Gunakan DeepSeek untuk adegan ini',exact:true}).click()
  await expect.poll(()=>f.submitted()?.scene_id).toBe('intro')
  await page.getByRole('button',{name:'Tinjau usulan',exact:true}).click()
  await page.getByRole('button',{name:'Terapkan ke draft'}).click()
  await expect(page.locator('[data-story-visual="coffee_pair"]')).toBeVisible()
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  expect(f.data().document.scenes[0].narration).toBe('Mulai dengan biji yang segar.')
  expect(f.data().document.scenes[0].duration_ms).toBe(5000)
  expect(errors).toEqual([])
})

test('AI style changes are reviewed before application and export uses the saved version', async ({page}) => {
  const f = await fixture(page)
  await page.getByRole('tab',{name:'Gaya',exact:true}).click()
  await page.getByLabel('Arahan gaya').fill('Aksen jingga hangat, latar hijau gelap')
  await page.getByRole('button',{name:'Buat variasi gaya dengan AI'}).click()
  await expect.poll(f.submitted).toEqual({expected_version:2,mode:'style'})
  expect(f.data().document.theme.accent).toBe('#D9F279')
  await page.getByRole('button',{name:'Tinjau usulan'}).click()
  await expect(page.getByRole('dialog',{name:'Tinjau usulan'})).toBeVisible()
  await page.getByRole('button',{name:'Terapkan ke draft'}).click()
  await expect(page.getByLabel('Aksen',{exact:true})).toHaveValue('#ffaa44')
  await page.getByRole('button',{name:'Ekspor MP4'}).click()
  await expect.poll(f.submitted).toEqual({expected_version:3,mode:'storyboard'})
  expect(f.data().document.scenes[0].title).toBe('Cerita dimulai dari secangkir kopi.')
})

test('manual paragraph storyboard remains editable and refuses stale AI replacement', async ({page}) => {
  const f = await fixture(page)
  await page.getByLabel('Naskah atau storyboard').fill('Pembuka cerita.\n\nPenutup cerita.')
  await page.getByRole('button',{name:'Satu paragraf per adegan'}).click()
  await page.getByRole('button',{name:'Terapkan ke draft'}).click()
  await expect(page.getByLabel('Narasi / subtitle')).toHaveValue('Pembuka cerita.')
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  await page.getByRole('tab',{name:'Naskah',exact:true}).click()
  await page.getByRole('button',{name:'Susun dengan DeepSeek'}).click()
  await page.getByLabel('Judul video',{exact:true}).fill('Edit setelah AI')
  await page.getByRole('button',{name:'Tinjau usulan'}).click()
  await expect(page.getByRole('button',{name:'Terapkan ke draft'})).toBeDisabled()
  expect(f.data().document.scenes[0].title).toBe('Adegan 1')
})

for (const format of ['Markdown', 'clipboard']) test(`timed ${format} table imports into a reviewed 68 second storyboard without AI`, async ({page}) => {
  const f = await fixture(page)
  let script = readFileSync(new URL('../fixtures/story-coffee.md', import.meta.url), 'utf8')
  if (format === 'clipboard') script = script.split('\n').filter(line => !line.startsWith('| ---')).map(line => line.startsWith('|') ? line.trim().slice(1,-1).split('|').map(s=>s.trim()).join('\t') : line.replace(/^#+\s*/, '')).join('\n')
  await page.getByLabel('Naskah atau storyboard').fill(script)
  await page.getByRole('button',{name:'Impor tabel storyboard',exact:true}).click()
  const dialog = page.getByRole('dialog',{name:'Tinjau usulan'})
  await expect(dialog).toContainText('6 adegan')
  await expect(dialog).toContainText('01:08')
  await dialog.getByRole('button',{name:'Terapkan ke draft'}).click()
  await expect(page.getByLabel('Durasi (detik)',{exact:true})).toHaveValue('7')
  await expect(page.getByLabel('Narasi / subtitle')).toHaveValue('Salah satu biji kopi ini tumbuh sendirian di dalam buahnya. Coba tebak, yang A atau yang B?')
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  expect(f.data().document.scenes).toHaveLength(6)
  expect(f.data().document.script).toContain('ctahr.hawaii.edu')
  expect(f.submitted()).toBeUndefined()
})

test('production reviews generated media, voice and aligned captions before applying to the saved story', async ({page}) => {
  const errors:string[] = []; page.on('pageerror', e=>errors.push(e.message))
  const f = await fixture(page)
  await page.getByRole('tab',{name:'Adegan'}).click()
  await page.getByLabel('Catatan visual').fill('Dua biji kopi di piring putih.')
  await page.getByRole('tab',{name:'Produksi',exact:true}).click()
  await expect(page.getByRole('definition')).toHaveCount(3)
  await page.getByRole('combobox',{name:'Suara narator',exact:true}).selectOption('alloy')
  await page.screenshot({path:test.info().outputPath('story-production-desktop.png')})
  await page.getByRole('button',{name:'Lengkapi semua adegan',exact:true}).click()
  await expect.poll(f.submitted).toEqual({expected_version:2,mode:'complete',voice:'alloy',replace_existing:false})
  expect(f.data().document.scenes[0].audio_id).toBeNull()
  await page.getByRole('button',{name:'Tinjau usulan',exact:true}).click()
  const dialog = page.getByRole('dialog',{name:'Tinjau usulan'})
  await expect(dialog).toContainText('Durasi adegan disesuaikan agar audio selesai.')
  await dialog.getByRole('button',{name:'Terapkan ke draft'}).click()
  await expect(page.getByRole('combobox',{name:'Rekaman suara',exact:true})).toHaveValue('generated-audio')
  await expect(page.getByRole('combobox',{name:'Gambar atau video',exact:true})).toHaveValue('generated-image')
  await expect(page.getByLabel('Durasi (detik)',{exact:true})).toHaveValue('7')
  await expect(page.getByText('Mengikuti audio',{exact:true})).toBeVisible()
  await expect(page.getByAltText('Gambar adegan terpilih')).toBeVisible()
  await expect(page.locator('audio.scene-audio')).toHaveAttribute('src','/api/v1/assets/generated-audio/content')
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  expect(f.data().document.scenes[0].captions).toEqual([{start_ms:350,end_ms:6350,text:'Mulai dengan biji yang segar.'}])
  await page.getByRole('tab',{name:'Produksi',exact:true}).click()
  await page.setViewportSize({width:390,height:844})
  await page.screenshot({path:test.info().outputPath('story-production-mobile.png')})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  expect(errors).toEqual([])
})

test('scene generation requires replacement choice and caption times remain editable with bounds validation', async ({page}) => {
  const f = await fixture(page)
  await page.getByRole('tab',{name:'Produksi',exact:true}).click()
  await page.getByRole('button',{name:'Lengkapi semua adegan',exact:true}).click()
  await page.getByRole('button',{name:'Tinjau usulan',exact:true}).click()
  await page.getByRole('button',{name:'Terapkan ke draft'}).click()
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  await expect(page.getByRole('button',{name:'Buat gambar pengganti',exact:true})).toBeDisabled()
  await expect(page.getByRole('button',{name:'Buat suara pengganti',exact:true})).toBeDisabled()
  await page.getByLabel('Buat pengganti gambar/video yang dipilih').check()
  await page.getByRole('button',{name:'Buat gambar pengganti',exact:true}).click()
  await expect.poll(f.submitted).toEqual({expected_version:2,mode:'images',voice:'coral',scene_id:'intro',replace_existing:true})
  await page.getByRole('tab',{name:'Adegan'}).click()
  await page.getByText('Edit teks & waktu (1)',{exact:true}).click()
  await page.getByLabel('Teks subtitle 1',{exact:true}).fill('Mulailah dengan biji yang segar.')
  await page.getByLabel('Selesai 1 (detik)',{exact:true}).fill('6.8')
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  expect(f.data().document.scenes[0].captions[0].end_ms).toBe(6800)
  await page.getByLabel('Durasi (detik)',{exact:true}).fill('4')
  await expect(page.getByRole('button',{name:'Simpan',exact:true})).toBeDisabled()
  await expect(page.getByText(/Periksa subtitle adegan 1:/)).toBeVisible()
  await page.getByRole('button',{name:'Hapus timing subtitle',exact:true}).click()
  await expect(page.getByRole('button',{name:'Simpan',exact:true})).toBeEnabled()
  await page.getByLabel('Durasi (detik)',{exact:true}).fill('7')
  await page.getByRole('button',{name:'Susun subtitle dari audio',exact:true}).click()
  await expect.poll(()=>f.submitted().mode).toBe('captions')
  await page.getByRole('button',{name:'Tinjau usulan',exact:true}).click()
  await page.getByRole('button',{name:'Terapkan ke draft'}).click()
  await page.getByLabel('Narasi / subtitle').fill('Narasi yang sudah diperbarui.')
  await expect(page.getByText('Timing perkiraan',{exact:true})).toBeVisible()
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  expect(f.data().document.scenes[0].captions).toEqual([])
})

test('unconfigured providers leave manual assets and audio caption generation available', async ({page}) => {
  const f = await fixture(page)
  f.data().capabilities = {images:false,speech:false,alignment:true,voices:[],default_voice:''}
  f.data().document.scenes[0].audio_id = 'generated-audio'
  f.data().assets = [{id:'generated-audio',kind:'story_media',bytes:100,mime:'audio/wav',state:'ready',content_url:'/api/v1/assets/generated-audio/content',metadata:{story_kind:'audio',filename:'Rekaman saya',duration_ms:7000}}]
  await page.reload()
  await page.getByRole('tab',{name:'Produksi',exact:true}).click()
  await expect(page.getByRole('button',{name:'Lengkapi semua adegan',exact:true})).toBeDisabled()
  await expect(page.getByText(/Layanan gambar AI dan suara narator belum aktif/)).toBeVisible()
  await page.getByRole('tab',{name:'Adegan'}).click()
  await expect(page.getByRole('button',{name:'Buat gambar AI adegan ini',exact:true})).toBeDisabled()
  await expect(page.getByRole('button',{name:'Susun subtitle dari audio',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Susun subtitle dari audio',exact:true}).click()
  await expect.poll(()=>f.submitted()?.mode).toBe('captions')
  await page.getByLabel('Judul video',{exact:true}).fill('Perubahan setelah proses')
  await page.getByRole('button',{name:'Tinjau usulan',exact:true}).click()
  await expect(page.getByRole('button',{name:'Terapkan ke draft'})).toBeDisabled()
  await page.getByRole('button',{name:'Kembali',exact:true}).click()
  await page.getByLabel('Judul video',{exact:true}).fill('Ritual kopi pagi')
  f.data().version++
  await page.getByRole('button',{name:'Tinjau usulan',exact:true}).click()
  await expect(page.getByRole('button',{name:'Terapkan ke draft'})).toBeDisabled()
})

test('local production uses installed voices and explains missing model setup without cloud credentials', async ({page}) => {
  const f = await fixture(page)
  f.data().capabilities = {provider:'local',images:true,speech:true,alignment:true,voices:['pocket-id-1','pocket-id-2','espeak-en'],default_voice:'pocket-id-1',voice_labels:{'pocket-id-1':'Indonesia · Suara 1 (lokal)','pocket-id-2':'Indonesia · Suara 2 (lokal)','espeak-en':'English · Suara dasar (lokal)'}}
  await page.reload()
  await page.getByRole('tab',{name:'Produksi',exact:true}).click()
  await expect(page.getByText('Model lokal · Tanpa biaya API gambar dan suara',{exact:true})).toBeVisible()
  await expect(page.getByRole('combobox',{name:'Suara narator',exact:true})).toHaveValue('pocket-id-1')
  await expect(page.getByRole('option',{name:'Indonesia · Suara 1 (lokal)'})).toBeAttached()
  await expect(page.getByText(/Narasi dan arahan visual dikirim ke layanan pembuat aset/)).toHaveCount(0)
  await page.screenshot({path:test.info().outputPath('story-local-production-desktop.png')})
  await page.getByRole('button',{name:'Lengkapi semua adegan',exact:true}).click()
  await expect.poll(()=>f.submitted()?.voice).toBe('pocket-id-1')
  f.data().capabilities.images = false
  await page.reload()
  await page.getByRole('tab',{name:'Produksi',exact:true}).click()
  await expect(page.getByRole('button',{name:'Lengkapi semua adegan',exact:true})).toBeDisabled()
  await expect(page.getByText(/Model gambar lokal belum siap/)).toBeVisible()
  await expect(page.getByText(/OPENAI_API_KEY|kunci API/)).toHaveCount(0)
  await page.getByText('Jalankan satu tahap',{exact:true}).click()
  await expect(page.getByRole('button',{name:'Buat 1 narasi yang belum bersuara',exact:true})).toBeEnabled()
  await page.setViewportSize({width:390,height:844})
  await expect(page.getByText(/Model gambar lokal belum siap/)).toBeVisible()
  await page.screenshot({path:test.info().outputPath('story-local-production-mobile.png')})
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
})

test('complete production retains selected illustrations without requiring an image model', async ({page}) => {
  const f = await fixture(page)
  f.data().capabilities = {provider:'local',images:false,speech:true,alignment:true,voices:['pocket-id-1'],default_voice:'pocket-id-1',voice_labels:{'pocket-id-1':'Indonesia · Suara 1 (lokal)'}}
  f.data().document.scenes[0].visual = {kind:'coffee_compare',items:[],motion:'gentle',reveal_ms:2000}
  await page.reload()
  await page.getByRole('tab',{name:'Produksi',exact:true}).click()
  const visuals = page.getByLabel('Kesiapan produksi').locator('div').filter({has:page.getByText('Visual siap',{exact:true})})
  await expect(visuals.locator('dd')).toHaveText('1 / 1')
  await expect(page.getByText(/Gambar, ilustrasi, dan rekaman yang sudah dipilih tetap dipakai/)).toBeVisible()
  await expect(page.getByRole('button',{name:'Lengkapi semua adegan',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Lengkapi semua adegan',exact:true}).click()
  await expect.poll(()=>f.submitted()?.mode).toBe('complete')
  await page.getByRole('button',{name:'Tinjau usulan',exact:true}).click()
  await page.getByRole('button',{name:'Terapkan ke draft'}).click()
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  expect(f.data().document.scenes[0].visual.kind).toBe('coffee_compare')
  expect(f.data().document.scenes[0].asset_id).toBeNull()
  expect(f.data().document.scenes[0].audio_id).toBe('generated-audio')
})
