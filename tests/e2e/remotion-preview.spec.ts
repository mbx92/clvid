import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'

// API and player bridge are isolated fixtures; no real clip or render job is changed.
const playerBundle = `
window.remotionTest = { mounts: 0, destroyed: 0 };
window.ClipperRemotion = {
  videoStyle() { return { opacity: 1, transform: 'none', transformOrigin: '50% 50%' }; },
  mount(element, props) {
    window.remotionTest.mounts++;
    let frame = 0;
    function draw() {
      element.dataset.frame = String(frame);
      element.dataset.props = JSON.stringify(props);
      element.textContent = props.style.enabled ? props.cues.find(c => frame * 1000 / props.fps >= c.start_ms && frame * 1000 / props.fps < c.end_ms)?.text || '' : '';
    }
    draw();
    return {
      updateProps(next) { props = next; draw(); },
      setFrame(next) { frame = next; draw(); },
      destroy() { window.remotionTest.destroyed++; element.textContent = ''; }
    };
  }
};`

async function clipFixture(page: Page, sourcePath?: string, durationMs = 5000, captionText = 'Awas serangannya', timedWords?: { word: string; start_ms: number; end_ms: number }[]) {
  let clip: any = {
    id: 'remotion-clip', project_id: 'remotion-project', origin: 'ai', created_at: '2026-11-03T00:00:00Z', media_duration_ms: 60000,
    revision: { id: 'revision-1', revision: 1, start_ms: 10000, end_ms: 10000 + durationMs, title: 'Awas serangannya',
      reason: '', crop_json: { mode: 'fit', x: .5, y: .5 },
      cues: [{ start_ms: 0, end_ms: 2500, text: captionText }, { start_ms: 3000, end_ms: 5000, text: 'Menang!' }],
      source_words: timedWords || [{ word: 'Awas', start_ms: 10000, end_ms: 10800 }, { word: 'serangannya', start_ms: 10900, end_ms: 12500 }, { word: 'Menang!', start_ms: 13000, end_ms: 15000 }],
      subtitle_style_json: { enabled: true, display_mode: 'sentence', font_size: 52, position: 'bottom', background: true, safe_margin: .15 } },
  }
  let saved: any
  let exported: any
  let holdSave: Promise<void> | null = null
  const source = sourcePath ? await readFile(sourcePath) : null
  if (source) {
    clip.media_duration_ms = 16000
    clip.source_asset = { id: 'remotion-source', kind: 'source', bytes: source.length, mime: 'video/mp4', state: 'ready', metadata: { width: 320, height: 180 } }
  }
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/me') return route.fulfill({ headers: { 'Set-Cookie': 'clipper_csrf=test-token; Path=/; SameSite=Lax' }, json: { id: 'test-user', email: 'test@example.invalid', csrf_token: 'test-token' } })
    if (source && path === '/api/v1/assets/remotion-source/content') {
      const range = /^bytes=(\d+)-(\d*)$/.exec(route.request().headers().range || '')
      if (range) {
        const start = Number(range[1]), end = range[2] ? Number(range[2]) : source.length - 1
        return route.fulfill({ status: 206, contentType: 'video/mp4', headers: { 'accept-ranges': 'bytes', 'content-range': `bytes ${start}-${end}/${source.length}` }, body: source.subarray(start, end + 1) })
      }
      return route.fulfill({ contentType: 'video/mp4', headers: { 'accept-ranges': 'bytes' }, body: source })
    }
    if (path === `/api/v1/clips/${clip.id}`) {
      if (route.request().method() === 'PATCH') {
        saved = route.request().postDataJSON()
        clip = { ...clip, revision: { ...clip.revision, ...saved, id: `revision-${clip.revision.revision + 1}`, revision: clip.revision.revision + 1 } }
        if (holdSave) { const pending = holdSave; holdSave = null; await pending }
      }
      return route.fulfill({ json: clip })
    }
    if (path === `/api/v1/clips/${clip.id}/exports`) {
      exported = route.request().postDataJSON()
      return route.fulfill({ json: { id: 'export-fixture', status: 'queued' } })
    }
    if (path === `/api/v1/projects/${clip.project_id}/exports`) return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 100 } })
    return route.fulfill({ status: 404, json: { message: 'Unexpected test request' } })
  })
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto(`/clips/${clip.id}`)
  await expect(page.getByLabel('Judul klip', { exact: true })).toHaveValue(clip.revision.title)
  return { saved: () => saved, exported: () => exported, holdNextSave() { let release!: () => void; holdSave = new Promise<void>(resolve => { release = resolve }); return release } }
}
async function subtitleSettings(page: Page) {
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await page.getByRole('button', { name: 'Gaya subtitle', exact: true }).click()
}
async function choose(page: Page, label: string, value: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page.getByRole('option', { name: value, exact: true }).click()
}
async function seek(page: Page, ms: number) {
  await page.getByLabel('Posisi playback video sumber', { exact: true }).evaluate((el: HTMLInputElement, time) => {
    el.value = String(time); el.dispatchEvent(new Event('input', { bubbles: true }))
  }, ms)
}
async function range(page: Page, label: string, value: number) {
  await page.getByLabel(label, { exact: true }).evaluate((el: HTMLInputElement, next) => {
    el.value = String(next); el.dispatchEvent(new Event('input', { bubbles: true }))
  }, value)
}
async function dragAcross(page: Page, label: string | RegExp, fraction: number) {
  const item = page.getByRole('button', { name: label, exact: typeof label === 'string' })
  const box = await item.boundingBox()
  const width = await item.evaluate(el => el.closest('.track-lane')!.getBoundingClientRect().width)
  if (!box) throw new Error('Timeline element is not visible')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + width * fraction, box.y + box.height / 2, { steps: 6 })
  await page.mouse.up()
}

async function chooseTypographyPreset(page: Page, name: string) {
  const disclosure = page.getByRole('button', {name: 'Preset warna & tipografi', exact: false})
  if (await disclosure.count() && await disclosure.getAttribute('aria-expanded') === 'false') await disclosure.click()
  await page.getByRole('button', {name: `Preset ${name}`, exact: true}).click()
}

test('Podcast kuning follows spoken words, clears pauses and survives save/reload', async ({ page }, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const fixture = await clipFixture(page, undefined, 5000, 'Buat rokok gitu depan gedung', [
    { word: 'Buat', start_ms: 10000, end_ms: 10300 }, { word: 'rokok', start_ms: 10400, end_ms: 10800 },
    { word: 'gitu', start_ms: 10900, end_ms: 11200 }, { word: 'depan', start_ms: 11300, end_ms: 11700 },
    { word: 'gedung', start_ms: 11800, end_ms: 12200 }, { word: 'Menang!', start_ms: 13000, end_ms: 15000 },
  ])
  await subtitleSettings(page)
  await page.getByRole('button', { name: 'Preset Podcast kuning', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Renderer subtitle', exact: true })).toContainText('Remotion')
  await expect(page.getByRole('combobox', { name: 'Template Remotion', exact: true })).toContainText('Podcast kuning')
  const caption = page.locator('[data-caption-template="podcast"]')
  await seek(page, 10500)
  await expect(caption).toBeVisible()
  await expect(caption).toHaveText('BUAT ROKOK GITU DEPAN\nGEDUNG')
  await expect(caption).toHaveCSS('font-style', 'italic')
  await expect(caption).toHaveCSS('color', 'rgb(255, 230, 0)')
  await expect(caption.locator('[data-podcast-highlight]')).toHaveCSS('background-color', 'rgb(255, 255, 255)')
  await expect(caption.locator('[data-podcast-highlight]')).toHaveCount(1)
  await expect(caption.locator('[data-active="true"]')).toHaveText('ROKOK')
  const layoutBefore = await caption.boundingBox()
  await seek(page, 10050)
  await expect(caption.locator('[data-active="true"]')).toHaveText('BUAT')
  await seek(page, 10850)
  await expect(caption.locator('[data-podcast-highlight]')).toHaveCount(0)
  await expect(caption).toHaveText('BUAT ROKOK GITU DEPAN\nGEDUNG')
  await seek(page, 11900)
  await expect(caption.locator('[data-active="true"]')).toHaveText('GEDUNG')
  expect(await caption.boundingBox()).toEqual(layoutBefore)
  await seek(page, 10500)
  await expect(caption.locator('[data-active="true"]')).toHaveText('ROKOK')
  await page.locator('.portrait-frame').screenshot({ path: testInfo.outputPath('podcast-preview.png') })
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect.poll(() => fixture.saved()?.subtitle_style_json).toMatchObject({ renderer: 'remotion', remotion_template: 'podcast', italic: true, bold: true, uppercase: true, safe_margin: .16 })
  await page.reload()
  await expect(page.getByLabel('Judul klip', { exact: true })).toHaveValue('Awas serangannya')
  await seek(page, 10500)
  await expect(caption).toBeVisible()
  await expect(caption.locator('[data-active="true"]')).toHaveText('ROKOK')
  await page.setViewportSize({ width: 390, height: 844 })
  await caption.scrollIntoViewIfNeeded()
  await expect(caption).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)
  await page.locator('.portrait-frame').screenshot({ path: testInfo.outputPath('podcast-preview-mobile.png') })
  await page.getByRole('button', { name: 'Ekspor', exact: true }).click()
  await page.getByRole('button', { name: 'Mulai ekspor', exact: true }).click()
  await expect.poll(fixture.exported).toEqual({ revision: 2, resolution: 1080 })
  expect(errors).toEqual([])
})

test('Podcast kuning explains missing timing and does not invent a highlight or allow an unsynchronized export', async ({ page }) => {
  await clipFixture(page, undefined, 5000, 'Teks telah diubah')
  await subtitleSettings(page)
  await page.getByRole('button', { name: 'Preset Podcast kuning', exact: true }).click()
  await seek(page, 10500)
  await expect(page.locator('[data-caption-template="podcast"]')).toBeVisible()
  await expect(page.locator('[data-podcast-highlight]')).toHaveCount(0)
  await expect(page.getByText(/Highlight belum tersedia\./)).toBeVisible()
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect(page.getByText('Tersimpan', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Ekspor', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Mulai ekspor', exact: true })).toBeDisabled()
  await expect(page.getByText(/Highlight kata belum memiliki timestamp/)).toBeVisible()
})

test('Remotion selection, typography and template survive save/reload and export the saved revision', async ({ page }) => {
  let loads = 0
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/remotion/player.js', route => { loads++; return route.fulfill({ contentType: 'application/javascript', body: playerBundle }) })
  const fixture = await clipFixture(page)
  await subtitleSettings(page)
  await expect(page.getByRole('combobox', { name: 'Renderer subtitle', exact: true })).toContainText('Standar')
  expect(loads).toBe(0)
  await choose(page, 'Renderer subtitle', 'Remotion')
  await expect(page.locator('.remotion-caption-host')).toHaveAttribute('data-frame', '0')
  await expect(page.locator('.caption-preview')).toHaveCount(0)
  await choose(page, 'Template Remotion', 'Sinematik')
  await chooseTypographyPreset(page, 'Gaming impact')
  await expect(page.getByRole('combobox', { name: 'Renderer subtitle', exact: true })).toContainText('Remotion')
  await expect(page.getByRole('combobox', { name: 'Template Remotion', exact: true })).toContainText('Sinematik')
  await page.getByRole('button', { name: 'Warna & efek', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Animasi subtitle', exact: true })).toHaveCount(0)
  await choose(page, 'Template Remotion', 'Minimal')
  await expect(page.getByRole('combobox', { name: 'Animasi subtitle', exact: true })).toBeVisible()
  await choose(page, 'Animasi subtitle', 'Geser halus')
  await choose(page, 'Template Remotion', 'Sinematik')
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect.poll(() => fixture.saved()?.subtitle_style_json).toMatchObject({ renderer: 'remotion', remotion_template: 'cinematic', animation: 'rise', text_color: '#FFE600' })
  await page.reload()
  await subtitleSettings(page)
  await expect(page.getByRole('combobox', { name: 'Renderer subtitle', exact: true })).toContainText('Remotion')
  await expect(page.getByRole('combobox', { name: 'Template Remotion', exact: true })).toContainText('Sinematik')
  await page.getByRole('button', { name: 'Ekspor', exact: true }).click()
  await page.getByRole('button', { name: 'Mulai ekspor', exact: true }).click()
  await expect.poll(fixture.exported).toEqual({ revision: 2, resolution: 1080 })
  expect(errors).toEqual([])
})

test('Remotion follows clip-relative frames and word cues, and releases its root when the renderer changes', async ({ page }) => {
  let loads = 0
  await page.route('**/remotion/player.js', route => { loads++; return route.fulfill({ contentType: 'application/javascript', body: playerBundle }) })
  await clipFixture(page)
  await subtitleSettings(page)
  await choose(page, 'Renderer subtitle', 'Remotion')
  const host = page.locator('.remotion-caption-host')
  await expect(host).toHaveAttribute('data-frame', '0')
  await seek(page, 11250)
  await expect(host).toHaveAttribute('data-frame', '37')
  await choose(page, 'Cara tampil subtitle', 'Kata per kata mengikuti suara')
  await expect(host).toHaveText('serangannya')
  await seek(page, 10400)
  await expect(host).toHaveAttribute('data-frame', '12')
  await expect(host).toHaveText('Awas')
  await seek(page, 5000)
  await expect(host).toHaveAttribute('data-frame', '0')
  await seek(page, 50000)
  await expect(host).toHaveAttribute('data-frame', '149')
  const enabled = page.getByLabel('Tampilkan subtitle pada video', { exact: true })
  await enabled.uncheck()
  await expect(host).toHaveText('')
  await expect.poll(() => page.evaluate(() => (window as any).remotionTest.destroyed)).toBe(0)
  await enabled.check()
  await expect(host).toHaveAttribute('data-frame', '149')
  expect(loads).toBe(1)
  await choose(page, 'Renderer subtitle', 'Standar')
  await expect.poll(() => page.evaluate(() => (window as any).remotionTest.destroyed)).toBe(1)
})

test('a failed bundle shows a visible error and can retry without silently changing renderer', async ({ page }) => {
  let loads = 0
  await page.route('**/remotion/player.js', route => ++loads === 1 ? route.fulfill({ status: 503, body: 'Unavailable' }) : route.fulfill({ contentType: 'application/javascript', body: playerBundle }))
  await clipFixture(page)
  await subtitleSettings(page)
  await choose(page, 'Renderer subtitle', 'Remotion')
  await expect(page.getByRole('alert')).toContainText('Preview Remotion gagal dimuat')
  await expect(page.locator('.caption-preview')).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: 'Renderer subtitle', exact: true })).toContainText('Remotion')
  await choose(page, 'Renderer subtitle', 'Standar')
  // This fixture has no media asset, so explicitly position its source clock.
  await seek(page, 10000)
  await expect(page.locator('.caption-preview')).toHaveText('Awas serangannya')
  await choose(page, 'Renderer subtitle', 'Remotion')
  await expect(page.locator('.remotion-caption-host')).toHaveAttribute('data-frame', '0')
  await expect(page.getByRole('alert')).toHaveCount(0)
  expect(loads).toBe(2)
})

test('a delayed player bundle does not mount an overlay that has already been removed', async ({ page }) => {
  let release!: () => void
  let requested!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  const started = new Promise<void>(resolve => { requested = resolve })
  let loads = 0
  await page.route('**/remotion/player.js', async route => {
    loads++; requested(); await pending
    return route.fulfill({ contentType: 'application/javascript', body: playerBundle })
  })
  await clipFixture(page)
  await subtitleSettings(page)
  await choose(page, 'Renderer subtitle', 'Remotion')
  await started
  await choose(page, 'Renderer subtitle', 'Standar')
  release()
  await expect.poll(() => page.evaluate(() => (window as any).remotionTest?.mounts)).toBe(0)
  await choose(page, 'Renderer subtitle', 'Remotion')
  await expect(page.locator('.remotion-caption-host')).toHaveAttribute('data-frame', '0')
  expect(loads).toBe(1)
})

test('real Remotion bundle uses the local font, animation and native video frame clock', async ({ page }, testInfo) => {
  test.skip(!process.env.CLIPPER_E2E_REMOTION_VIDEO, 'Build the Remotion player and provide a 16 second synthetic MP4 fixture')
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  await clipFixture(page, process.env.CLIPPER_E2E_REMOTION_VIDEO)
  const video = page.locator('.framing-preview > video')
  await expect.poll(() => video.evaluate((el: HTMLVideoElement) => el.readyState)).toBeGreaterThanOrEqual(2)
  await subtitleSettings(page)
  await choose(page, 'Renderer subtitle', 'Remotion')
  const host = page.locator('.remotion-caption-host')
  const caption = host.getByText('Awas serangannya', { exact: true })
  await seek(page, 10500)
  await expect(caption).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.fonts.check('52px "Clipper Noto Sans"'))).toBe(true)
  await expect(caption).toHaveCSS('font-family', '"Clipper Noto Sans", sans-serif')
  await expect(caption).toHaveCSS('opacity', '1')
  await seek(page, 10040)
  await expect.poll(() => caption.evaluate(el => Number(getComputedStyle(el).opacity))).toBeLessThan(1)
  await seek(page, 10500)
  await expect(caption).toHaveCSS('opacity', '1')
  await chooseTypographyPreset(page, 'Gaming impact')
  await expect(host.getByText('AWAS SERANGANNYA', { exact: true })).toHaveCSS('color', 'rgb(255, 230, 0)')
  await page.screenshot({ path: testInfo.outputPath('remotion-gaming-desktop.png') })
  await choose(page, 'Template Remotion', 'Sinematik')
  await choose(page, 'Cara tampil subtitle', 'Kata per kata mengikuti suara')
  await seek(page, 10400)
  await expect(host).toHaveText('AWAS')
  // The 100 ms gap between these spoken words must remain empty.
  await seek(page, 10850)
  await expect(host).toHaveText('')
  await seek(page, 11100)
  await expect(host).toHaveText('SERANGANNYA')
  await seek(page, 12600)
  await expect(host).toHaveText('')
  // Real playback advances the native requestVideoFrameCallback clock into cue 2.
  await page.getByRole('button', { name: 'Putar video', exact: true }).click()
  await expect(host).toHaveText('MENANG!')
  await page.getByRole('button', { name: 'Jeda video', exact: true }).click()
  await expect.poll(() => video.evaluate((el: HTMLVideoElement) => el.paused)).toBe(true)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: testInfo.outputPath('remotion-cinematic-mobile.png') })
  await page.getByRole('button', { name: 'Alat editor', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Template Remotion', exact: true })).toContainText('Sinematik')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('remotion-settings-mobile.png') })
  expect(errors).toEqual([])
})

test('real Remotion font failure reaches a clear Vue preview error without an internal stack', async ({ page }) => {
  test.skip(!process.env.CLIPPER_E2E_REMOTION_VIDEO, 'Build the Remotion player and provide a synthetic MP4 fixture')
  await page.route('**/fonts/NotoSans-Regular.ttf', route => route.fulfill({ status: 503, body: 'Unavailable' }))
  await clipFixture(page, process.env.CLIPPER_E2E_REMOTION_VIDEO)
  await subtitleSettings(page)
  await choose(page, 'Renderer subtitle', 'Remotion')
  await expect(page.locator('.remotion-preview-error')).toHaveText('Preview Remotion gagal dimuat. Muat ulang halaman atau pilih renderer Standar.')
  await expect(page.locator('.remotion-caption-host')).toBeEmpty()
  await expect(page.locator('.caption-preview')).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: 'Renderer subtitle', exact: true })).toContainText('Remotion')
  await expect(page.getByText('Subtitle font unavailable', { exact: false })).toHaveCount(0)
})

test('timeline edits, draggable ranges, titles and zooms persist after trim and reload', async ({ page }, testInfo) => {
  await page.route('**/remotion/player.js', route => route.fulfill({ contentType: 'application/javascript', body: playerBundle }))
  const fixture = await clipFixture(page, undefined, 10000)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await page.getByRole('button', { name: 'Efek video', exact: true }).click()
  await page.getByRole('button', { name: 'Aktifkan Remotion untuk efek video', exact: true }).click()
  await choose(page, 'Transisi awal', 'Fade')
  await choose(page, 'Transisi akhir', 'Geser')
  await page.getByLabel('Aktifkan intro', { exact: true }).check()
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeDisabled()
  await expect(page.getByRole('alert').first()).toContainText('Isi teks intro terlebih dahulu')
  await page.getByLabel('Teks intro', { exact: true }).fill('Pertarungan terakhir')
  await page.getByLabel('Aktifkan outro', { exact: true }).check()
  await page.getByLabel('Teks outro', { exact: true }).fill('Sampai jumpa!')
  await seek(page, 12000)
  await page.getByRole('button', { name: 'Tambah zoom di posisi sekarang', exact: true }).click()
  await range(page, 'Pembesaran zoom', 1.5)
  await range(page, 'Pusat horizontal zoom', .7)
  await range(page, 'Pusat vertikal zoom', .3)
  await page.getByRole('button', { name: 'Atur waktu di timeline', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Timeline klip', exact: true })).toBeVisible()
  await dragAcross(page, /^Subtitle timeline 2:/, .1)
  await expect(page.getByLabel('Mulai subtitle timeline (detik)', { exact: true })).toHaveValue('4')
  await dragAcross(page, 'Ubah akhir subtitle 2', -.05)
  await expect(page.getByLabel('Akhir subtitle timeline (detik)', { exact: true })).toHaveValue('5.5')
  await page.getByRole('button', { name: /^Subtitle timeline 2:/ }).press('ArrowRight')
  await expect(page.getByLabel('Mulai subtitle timeline (detik)', { exact: true })).toHaveValue('4.1')
  await page.getByLabel('Teks subtitle timeline', { exact: true }).fill('Akhirnya menang!')
  await page.getByRole('button', { name: 'Zoom timeline 1', exact: true }).click()
  await expect(page.getByLabel('Mulai zoom (detik)', { exact: true })).toHaveValue('2')
  await page.screenshot({ path: testInfo.outputPath('remotion-timeline-desktop.png') })
  await choose(page, 'Elemen timeline', 'Video')
  await page.getByLabel('Masuk video timeline', { exact: true }).fill('00:11.000')
  await page.getByLabel('Keluar video timeline', { exact: true }).fill('00:19.000')
  await page.getByRole('button', { name: 'Terapkan batas timeline', exact: true }).click()
  await expect(page.getByLabel('Masuk', { exact: true })).toHaveValue('00:11.000')
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect.poll(() => fixture.saved()?.start_ms).toBe(11000)
  expect(fixture.saved().end_ms).toBe(19000)
  expect(fixture.saved().cues[1]).toEqual({ start_ms: 3100, end_ms: 4600, text: 'Akhirnya menang!' })
  expect(fixture.saved().subtitle_style_json.remotion_effects).toMatchObject({ transition_in: 'fade', transition_out: 'slide', intro: { enabled: true, text: 'Pertarungan terakhir' }, outro: { enabled: true, text: 'Sampai jumpa!' }, zooms: [{ start_ms: 1000, end_ms: 2500, scale: 1.5, x: .7, y: .3 }] })
  await page.reload()
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click()
  await page.getByRole('button', { name: 'Zoom timeline 1', exact: true }).click()
  await expect(page.getByLabel('Mulai zoom (detik)', { exact: true })).toHaveValue('1')
  await expect(page.getByLabel('Pembesaran zoom', { exact: true })).toHaveValue('1.5')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Alat editor', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'Timeline', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('remotion-timeline-mobile.png') })
  await page.getByRole('button', { name: 'Hapus zoom terpilih', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Zoom timeline 1', exact: true })).toHaveCount(0)
})

test('timeline can add and resize zooms and subtitle blocks without leaving clip bounds', async ({ page }) => {
  await page.route('**/remotion/player.js', route => route.fulfill({ contentType: 'application/javascript', body: playerBundle }))
  await clipFixture(page, undefined, 10000)
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click()
  await page.getByRole('button', { name: 'Aktifkan efek Remotion', exact: true }).click()
  await range(page, 'Posisi timeline klip', 7000)
  await page.getByRole('button', { name: 'Tambah zoom di sini', exact: true }).click()
  await expect(page.getByLabel('Mulai zoom (detik)', { exact: true })).toHaveValue('7')
  await dragAcross(page, 'Zoom timeline 1', .5)
  await expect(page.getByLabel('Akhir zoom (detik)', { exact: true })).toHaveValue('10')
  await dragAcross(page, 'Ubah awal zoom 1', -.05)
  await expect(page.getByLabel('Mulai zoom (detik)', { exact: true })).toHaveValue('8')
  await range(page, 'Posisi timeline klip', 6000)
  await page.getByRole('button', { name: 'Tambah subtitle di sini', exact: true }).click()
  await expect(page.getByLabel('Mulai subtitle timeline (detik)', { exact: true })).toHaveValue('6')
  await page.getByLabel('Teks subtitle timeline', { exact: true }).fill('Tahan dulu')
  await page.getByRole('button', { name: 'Hapus subtitle terpilih', exact: true }).click()
  await expect(page.getByRole('button', { name: /^Subtitle timeline 3:/ })).toHaveCount(0)
})

test('real Remotion applies zoom and transitions to video and keeps titles when subtitles are off', async ({ page }, testInfo) => {
  test.skip(!process.env.CLIPPER_E2E_REMOTION_VIDEO, 'Build the Remotion player and provide a synthetic MP4 fixture')
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  await clipFixture(page, process.env.CLIPPER_E2E_REMOTION_VIDEO)
  await subtitleSettings(page)
  await choose(page, 'Renderer subtitle', 'Remotion')
  await page.getByLabel('Tampilkan subtitle pada video', { exact: true }).uncheck()
  await page.getByRole('button', { name: 'Efek video', exact: true }).click()
  await choose(page, 'Transisi awal', 'Fade')
  await choose(page, 'Transisi akhir', 'Geser')
  await page.getByLabel('Aktifkan intro', { exact: true }).check()
  await page.getByLabel('Teks intro', { exact: true }).fill('PERTARUNGAN TERAKHIR')
  await page.getByLabel('Aktifkan outro', { exact: true }).check()
  await page.getByLabel('Teks outro', { exact: true }).fill('SAMPAI JUMPA!')
  await seek(page, 11000)
  await page.getByRole('button', { name: 'Tambah zoom di posisi sekarang', exact: true }).click()
  await range(page, 'Pembesaran zoom', 1.5)
  await seek(page, 10050)
  const layer = page.locator('.framing-preview')
  await expect.poll(() => layer.evaluate(el => Number(getComputedStyle(el).opacity))).toBeLessThan(.5)
  await seek(page, 10500)
  await expect(layer).toHaveCSS('opacity', '1')
  await expect(page.locator('.remotion-caption-host').getByText('PERTARUNGAN TERAKHIR', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('remotion-intro-desktop.png') })
  await seek(page, 11750)
  await expect.poll(() => layer.evaluate(el => new DOMMatrixReadOnly(getComputedStyle(el).transform).a)).toBeCloseTo(1.5, 2)
  await expect(page.locator('.remotion-caption-host')).toHaveText('')
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click()
  await page.screenshot({ path: testInfo.outputPath('remotion-zoom-timeline-desktop.png') })
  await seek(page, 14500)
  await expect(page.locator('.remotion-caption-host').getByText('SAMPAI JUMPA!', { exact: true })).toBeVisible()
  await seek(page, 14950)
  await expect.poll(() => layer.evaluate(el => Number(getComputedStyle(el).opacity))).toBeLessThan(.5)
  await expect.poll(() => layer.evaluate(el => new DOMMatrixReadOnly(getComputedStyle(el).transform).e)).toBeLessThan(0)
  await seek(page, 15500)
  await expect(layer).toHaveCSS('opacity', '1')
  await expect(layer).toHaveCSS('transform', 'none')
  await expect(page.locator('.remotion-caption-host')).toHaveCSS('visibility', 'hidden')
  await seek(page, 5000)
  await expect(layer).toHaveCSS('opacity', '1')
  await expect(page.locator('.remotion-caption-host')).toHaveCSS('visibility', 'hidden')
  expect(await page.locator('.remotion-caption-host video, .remotion-caption-host audio').count()).toBe(0)
  expect(errors).toEqual([])
})

test('saving freezes draft controls until the persisted revision has been adopted', async ({ page }) => {
  await page.route('**/remotion/player.js', route => route.fulfill({ contentType: 'application/javascript', body: playerBundle }))
  const fixture = await clipFixture(page)
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click()
  await page.getByRole('button', { name: /^Subtitle timeline 1:/ }).click()
  await page.getByLabel('Teks subtitle timeline', { exact: true }).fill('Teks tersimpan')
  const release = fixture.holdNextSave()
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect.poll(() => fixture.saved()?.cues[0].text).toBe('Teks tersimpan')
  await expect(page.getByLabel('Judul klip', { exact: true })).toBeDisabled()
  await expect(page.locator('.editor-grid')).toHaveAttribute('inert', '')
  const position = await page.getByRole('button', { name: /^Subtitle timeline 1:/ }).boundingBox()
  if (!position) throw new Error('Timeline cue missing')
  await page.mouse.click(position.x + position.width / 2, position.y + position.height / 2)
  await page.keyboard.press('ArrowRight')
  await expect(page.getByLabel('Mulai subtitle timeline (detik)', { exact: true })).toHaveValue('0')
  release()
  await expect(page.getByText('Revisi 2', { exact: true })).toBeVisible()
  await expect(page.locator('.editor-grid')).not.toHaveAttribute('inert')
  await expect(page.getByLabel('Teks subtitle timeline', { exact: true })).toHaveValue('Teks tersimpan')
})

test('new overlapping cues use export ordering without moving timeline editor indices', async ({ page }) => {
  await page.route('**/remotion/player.js', route => route.fulfill({ contentType: 'application/javascript', body: playerBundle }))
  await clipFixture(page)
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click()
  await page.getByRole('button', { name: 'Aktifkan efek Remotion', exact: true }).click()
  await page.getByRole('button', { name: /^Subtitle timeline 1:/ }).click()
  await page.getByLabel('Akhir subtitle timeline (detik)', { exact: true }).fill('4')
  await page.getByLabel('Akhir subtitle timeline (detik)', { exact: true }).press('Tab')
  await page.getByLabel('Mulai subtitle timeline (detik)', { exact: true }).fill('2')
  await page.getByLabel('Mulai subtitle timeline (detik)', { exact: true }).press('Tab')
  await range(page, 'Posisi timeline klip', 0)
  await page.getByRole('button', { name: 'Tambah subtitle di sini', exact: true }).click()
  await page.getByLabel('Teks subtitle timeline', { exact: true }).fill('Lebih awal')
  await page.getByLabel('Akhir subtitle timeline (detik)', { exact: true }).fill('3.5')
  await page.getByLabel('Akhir subtitle timeline (detik)', { exact: true }).press('Tab')
  await seek(page, 12500)
  await expect(page.locator('.remotion-caption-host')).toHaveText('Lebih awal')
  await expect(page.getByRole('button', { name: 'Subtitle timeline 3: Lebih awal', exact: true })).toBeVisible()
  await subtitleSettings(page)
  await choose(page, 'Renderer subtitle', 'Standar')
  await expect(page.locator('.caption-preview')).toHaveText('Lebih awal')
})

test('an invalid stored title has a visible correction path even after choosing standard renderer', async ({ page }) => {
  await page.route('**/remotion/player.js', route => route.fulfill({ contentType: 'application/javascript', body: playerBundle }))
  await clipFixture(page)
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await page.getByRole('button', { name: 'Efek video', exact: true }).click()
  await page.getByRole('button', { name: 'Aktifkan Remotion untuk efek video', exact: true }).click()
  await page.getByLabel('Aktifkan intro', { exact: true }).check()
  await page.getByRole('button', { name: 'Gaya subtitle', exact: true }).click()
  await choose(page, 'Renderer subtitle', 'Standar')
  await expect(page.getByRole('alert')).toContainText('Isi teks intro terlebih dahulu')
  await page.getByRole('button', { name: 'Periksa efek video', exact: true }).click()
  await page.getByRole('button', { name: 'Aktifkan Remotion untuk efek video', exact: true }).click()
  await page.getByLabel('Teks intro', { exact: true }).fill('Sudah diperbaiki')
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeEnabled()
})

test('real Remotion preview recovers after an oversized draft subtitle is corrected', async ({ page }) => {
  test.skip(!process.env.CLIPPER_E2E_REMOTION_VIDEO, 'Build the Remotion player and provide a synthetic MP4 fixture')
  await clipFixture(page, process.env.CLIPPER_E2E_REMOTION_VIDEO)
  await subtitleSettings(page)
  await choose(page, 'Renderer subtitle', 'Remotion')
  await seek(page, 10500)
  await page.getByRole('tab', { name: /^Subtitle/ }).click()
  await page.getByLabel('Teks subtitle 1', { exact: true }).fill('Kata yang terlalu panjang '.repeat(30))
  await expect(page.locator('.remotion-preview-error')).toBeVisible()
  await page.getByLabel('Teks subtitle 1', { exact: true }).fill('Preview pulih')
  await expect(page.locator('.remotion-preview-error')).toHaveCount(0)
  await expect(page.locator('.remotion-caption-host').getByText('Preview pulih', { exact: true })).toBeVisible()
})


test('Remotion style controls remain readable without shrinking at desktop and mobile sizes', async ({page}) => {
  await page.route('**/remotion/player.js',route=>route.fulfill({contentType:'application/javascript',body:playerBundle}))
  await clipFixture(page)
  await subtitleSettings(page)
  await choose(page,'Renderer subtitle','Remotion')
  for(const [width,height] of [[1366,768],[1920,1080],[390,844]]) {
    await page.setViewportSize({width,height})
    if(width<760) await page.getByRole('button',{name:'Alat editor',exact:true}).click()
    await choose(page,'Template Remotion','Podcast kuning')
    await expect(page.getByRole('button',{name:'Preset Podcast kuning',exact:true})).toHaveCount(0)
    await expect(page.locator('.subtitle-presets')).toHaveCount(0)
    const control=page.getByRole('combobox',{name:'Template Remotion',exact:true})
    expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(36)
    expect(await page.locator('.desktop-fit-content').evaluate(el=>getComputedStyle(el).zoom)).toBe('1')
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy()
    await page.screenshot({path:test.info().outputPath(`remotion-settings-${width}.png`)})
    await page.getByRole('button',{name:'Warna & efek',exact:true}).click()
    await page.getByRole('slider',{name:'Ketebalan outline',exact:true}).focus()
    await page.screenshot({path:test.info().outputPath(`remotion-colors-${width}.png`)})
    await page.getByRole('button',{name:'Preset',exact:true}).click()
  }
})


test('long subtitles can be repaired in a reviewed draft and saved for export', async ({page}) => {
  await page.route('**/remotion/player.js',route=>route.fulfill({contentType:'application/javascript',body:playerBundle}))
  const text='Kopi tumbuh dalam buah merah dan setiap biji memiliki bentuk yang menarik untuk diperhatikan. '.repeat(4).trim()
  const fixture=await clipFixture(page,undefined,5000,text)
  await page.getByRole('button',{name:'Sesuaikan subtitle',exact:true}).click()
  const dialog=page.getByRole('dialog',{name:'Sesuaikan subtitle',exact:true})
  await expect(dialog).toContainText('diperkirakan secara proporsional')
  expect(fixture.saved()).toBeUndefined()
  await expect(page.getByLabel('Teks subtitle 1',{exact:true})).toHaveValue(text)
  await page.screenshot({path:test.info().outputPath('subtitle-repair-review.png')})
  await dialog.getByRole('button',{name:'Batal',exact:true}).click()
  await expect(page.getByLabel('Teks subtitle 1',{exact:true})).toHaveValue(text)
  await page.getByRole('button',{name:'Sesuaikan subtitle',exact:true}).click()
  await page.getByRole('button',{name:'Terapkan penyesuaian',exact:true}).click()
  await expect(page.getByRole('button',{name:'Sesuaikan subtitle',exact:true})).toHaveCount(0)
  await page.getByRole('button',{name:'Simpan',exact:true}).click()
  const cues=fixture.saved().cues
  expect(cues.slice(0,-1).map((c:any)=>c.text).join(' ')).toBe(text)
  expect(cues[0].start_ms).toBe(0)
  expect(cues.at(-2).end_ms).toBe(2500)
  expect(fixture.saved().subtitle_style_json.auto_fit).toBe(true)
  await page.getByRole('button',{name:'Ekspor',exact:true}).click()
  await expect(page.getByRole('button',{name:'Mulai ekspor',exact:true})).toBeEnabled()
  await page.getByRole('button',{name:'Mulai ekspor',exact:true}).click()
  await expect.poll(fixture.exported).toEqual({revision:2,resolution:1080})
})
