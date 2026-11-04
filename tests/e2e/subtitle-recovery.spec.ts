import { expect, test, type Page } from '@playwright/test'

// All API responses are mocked: these checks never queue a real transcription
// or modify an existing clip, and work without local login credentials.
async function emptyClip(page: Page, existing = false) {
  let clip: any = {
    id: 'recovery-clip', project_id: 'recovery-project', origin: 'ai', created_at: '2026-11-03T00:00:00Z',
    media_duration_ms: 60000,
    revision: { id: 'revision-1', revision: 1, start_ms: 10000, end_ms: 55000, title: 'Pertarungan bos',
      reason: '', crop_json: { mode: 'fit', x: .5, y: .5 }, cues: [], source_words: [],
      subtitle_style_json: { enabled: true, display_mode: 'words', font_size: 52, position: 'bottom', background: true, safe_margin: .15 } },
  }
  if (existing) {
    clip.origin = 'manual'
    clip.revision.cues = [{ start_ms: 0, end_ms: 1200, text: 'Koreksi saya' }]
  }
  const job: any = { id: 'recovery-job', project_id: clip.project_id, kind: 'subtitle_generate', stage: 'subtitle_generate', status: 'queued', progress: null }
  let submitted: any
  let polls = 0
  let heldPoll: { started: () => void; pending: Promise<void> } | null = null
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/me') return route.fulfill({ headers: { 'Set-Cookie': 'clipper_csrf=test-token; Path=/; SameSite=Lax' }, json: { id: 'test-user', email: 'test@example.invalid', csrf_token: 'test-token' } })
    if (path === `/api/v1/clips/${clip.id}`) {
      if (route.request().method() === 'PATCH') {
        const body = route.request().postDataJSON()
        clip = { ...clip, revision: { ...clip.revision, ...body, id: `revision-${clip.revision.revision + 1}`, revision: clip.revision.revision + 1 } }
      }
      return route.fulfill({ json: clip })
    }
    if (path === `/api/v1/clips/${clip.id}/subtitles/generate`) {
      submitted = route.request().postDataJSON()
      return route.fulfill({ json: job })
    }
    if (path === `/api/v1/jobs/${job.id}`) {
      polls++
      const snapshot = structuredClone(job)
      if (heldPoll) { const hold = heldPoll; heldPoll = null; hold.started(); await hold.pending }
      return route.fulfill({ json: snapshot })
    }
    if (path === `/api/v1/jobs/${job.id}/cancel`) {
      if (job.status === 'queued') job.status = 'cancelled'
      return route.fulfill({ json: job })
    }
    if (path === `/api/v1/jobs/${job.id}/retry`) { job.status = 'queued'; return route.fulfill({ json: job }) }
    if (path === `/api/v1/projects/${clip.project_id}/exports`) return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 100 } })
    return route.fulfill({ status: 404, json: { message: 'Unexpected test request' } })
  })
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto(`/clips/${clip.id}`)
  if (!existing) await expect(page.getByRole('heading', { name: 'Belum ada subtitle', exact: true })).toBeVisible()
  return {
    submitted: () => submitted,
    polls: () => polls,
    fail() { job.status = 'failed' },
    holdNextPoll() {
      let release!: () => void
      let started!: () => void
      const seen = new Promise<void>(resolve => { started = resolve })
      const pending = new Promise<void>(resolve => { release = resolve })
      heldPoll = { started, pending }
      return { started: seen, release }
    },
    finish(speech: boolean) {
      job.status = 'succeeded'
      job.progress = 1
      job.result_json = { cues: speech ? 1 : 0, message: speech ? '1 subtitle berhasil dibuat dari audio klip.' : 'Tidak ada ucapan yang terdeteksi pada audio klip ini.' }
      if (speech) clip = { ...clip, revision: { ...clip.revision, id: `revision-${clip.revision.revision + 1}`, revision: clip.revision.revision + 1,
        cues: [{ start_ms: 0, end_ms: 1200, text: 'Tahan!' }],
        source_words: [{ word: 'Tahan!', start_ms: 10000, end_ms: 11200 }] } }
    },
  }
}

test('manual clip with existing subtitles exposes audio generation from timeline and confirms replacement', async ({ page }) => {
  const fixture = await emptyClip(page, true)
  await page.getByRole('tab', { name: 'Timeline', exact: true }).click()
  await page.getByRole('button', { name: 'Buat subtitle dari audio', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Buat ulang subtitle dari audio?' })
  await expect(dialog).toBeVisible()
  expect(fixture.submitted()).toBeUndefined()
  await dialog.getByRole('button', { name: 'Batal', exact: true }).click()
  await page.getByRole('tab', { name: 'Subtitle 1', exact: true }).click()
  await expect(page.getByLabel('Teks subtitle 1', { exact: true })).toHaveValue('Koreksi saya')
  await page.screenshot({ path: test.info().outputPath('audio-toolbar-desktop.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: 'Alat editor', exact: true }).click()
  await page.getByRole('button', { name: 'Buat subtitle dari audio', exact: true }).click()
  await page.screenshot({ path: test.info().outputPath('audio-dialog-mobile.png') })
  await dialog.getByRole('button', { name: 'Ganti subtitle dari audio', exact: true }).click()
  await expect.poll(fixture.submitted).toEqual({ expected_revision: 1, language: 'auto', replace_existing: true })
  fixture.finish(true)
  await expect(page.getByLabel('Teks subtitle 1', { exact: true })).toHaveValue('Tahan!')
  await expect(page.getByRole('button', { name: 'Buat subtitle dari audio', exact: true })).toBeVisible()
})

test('recover subtitles from clip audio after saving and refresh word timing at unchanged bounds', async ({ page }) => {
  const fixture = await emptyClip(page)
  const generate = page.getByRole('button', { name: 'Buat subtitle dari audio', exact: true })
  await page.getByLabel('Judul klip', { exact: true }).fill('Pertarungan terakhir')
  await expect(generate).toBeDisabled()
  await expect(page.getByText('Simpan perubahan terlebih dahulu', { exact: false })).toBeVisible()
  await page.getByRole('button', { name: 'Simpan', exact: true }).click()
  await expect(generate).toBeEnabled()
  await generate.click()
  await page.getByRole('combobox', { name: 'Bahasa subtitle dari audio', exact: true }).click()
  await page.getByRole('option', { name: 'Bahasa Indonesia', exact: true }).click()
  await page.screenshot({ path: test.info().outputPath('audio-dialog-desktop.png') })
  await page.getByRole('button', { name: 'Mulai buat subtitle', exact: true }).click()
  await expect.poll(fixture.submitted).toEqual({ expected_revision: 2, language: 'id' })
  await expect(generate).toBeDisabled()
  fixture.finish(true)
  await expect(page.getByLabel('Teks subtitle 1', { exact: true })).toHaveValue('Tahan!')
  await page.getByRole('button', { name: 'Putar subtitle 1', exact: true }).click()
  await expect(page.locator('.caption-preview')).toHaveText('Tahan!')
  await expect(page.getByLabel('Judul klip', { exact: true })).toHaveValue('Pertarungan terakhir')
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeDisabled()
})

test('no speech keeps subtitles empty and explains the result', async ({ page }) => {
  const fixture = await emptyClip(page)
  await page.getByRole('button', { name: 'Buat subtitle dari audio', exact: true }).click()
  await page.getByRole('button', { name: 'Mulai buat subtitle', exact: true }).click()
  await expect.poll(fixture.submitted).toEqual({ expected_revision: 1, language: 'auto' })
  fixture.finish(false)
  await expect(page.getByText('Tidak ada ucapan yang terdeteksi pada audio klip ini.', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Belum ada subtitle', exact: true })).toBeVisible()
  await expect(page.getByLabel('Teks subtitle 1', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Revisi 1', { exact: true })).toBeVisible()
})

test('a subtitle job finishing during editing preserves the unsaved draft', async ({ page }) => {
  const fixture = await emptyClip(page)
  await page.getByRole('button', { name: 'Buat subtitle dari audio', exact: true }).click()
  await page.getByRole('button', { name: 'Mulai buat subtitle', exact: true }).click()
  await expect.poll(fixture.submitted).toEqual({ expected_revision: 1, language: 'auto' })
  await page.getByLabel('Judul klip', { exact: true }).fill('Judul yang sedang saya edit')
  await page.getByRole('button', { name: 'Tambah subtitle', exact: true }).click()
  await page.getByLabel('Teks subtitle 1', { exact: true }).fill('Teks manual saya')
  fixture.finish(true)
  await expect(page.getByRole('button', { name: 'Tinjau revisi terbaru', exact: true })).toBeVisible()
  await expect(page.getByLabel('Judul klip', { exact: true })).toHaveValue('Judul yang sedang saya edit')
  await expect(page.getByLabel('Teks subtitle 1', { exact: true })).toHaveValue('Teks manual saya')
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeEnabled()
})

test('a delayed failed poll cannot stop polling after the same subtitle job is retried', async ({ page }) => {
  const fixture = await emptyClip(page)
  await page.getByRole('button', { name: 'Buat subtitle dari audio', exact: true }).click()
  await page.getByRole('button', { name: 'Mulai buat subtitle', exact: true }).click()
  await expect.poll(fixture.submitted).toEqual({ expected_revision: 1, language: 'auto' })
  fixture.fail()
  const held = fixture.holdNextPoll()
  await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
  await held.started
  // The job failed on the server while this tab still displayed queued. Cancel
  // returns that terminal state, making retry available before the old GET.
  await page.getByRole('button', { name: 'Batalkan', exact: true }).click()
  await page.getByRole('button', { name: 'Coba lagi', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Batalkan', exact: true })).toBeVisible()
  held.release()
  fixture.finish(true)
  await expect(page.getByLabel('Teks subtitle 1', { exact: true })).toHaveValue('Tahan!')
})
