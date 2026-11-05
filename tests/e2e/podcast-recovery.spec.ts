import { expect, test, type Page } from '@playwright/test'

// Mocked audio recovery keeps these checks independent of ASR and real clips.
async function recoveryFixture(page: Page, savedPodcast = true, conflict = false) {
  const text = 'dan berhenti dan berbicara'
  let clip: any = {
    id: 'podcast-recovery', project_id: 'podcast-project', origin: 'ai', media_duration_ms: 60000,
    revision: { id: 'revision-2', revision: 2, start_ms: 10000, end_ms: 15000, title: 'Percakapan',
      reason: '', crop_json: { mode: 'fit', x: .5, y: .5 },
      cues: [{ start_ms: 0, end_ms: 1200, text }],
      source_words: [
        { word: ' dan', start_ms: 10000, end_ms: 10300 },
        { word: ' berhenti', start_ms: 10300, end_ms: 10300 },
        { word: ' dan', start_ms: 10300, end_ms: 10300 },
        { word: ' berbicara', start_ms: 10300, end_ms: 11200 },
      ],
      subtitle_style_json: { enabled: true, display_mode: 'sentence', font_size: 52, position: 'bottom',
        background: true, safe_margin: .15, ...(savedPodcast ? { renderer: 'remotion', remotion_template: 'podcast' } : {}) },
    },
  }
  const job: any = { id: 'podcast-recovery-job', project_id: clip.project_id, kind: 'subtitle_generate',
    stage: 'subtitle_generate', status: 'queued', progress: null }
  const saves: any[] = []
  const generations: any[] = []
  const exports: any[] = []
  let holdSave: Promise<void> | null = null
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/me') return route.fulfill({ headers: { 'Set-Cookie': 'clipper_csrf=test-token; Path=/; SameSite=Lax' }, json: { id: 'test-user', email: 'test@example.invalid', csrf_token: 'test-token' } })
    if (path === `/api/v1/clips/${clip.id}`) {
      if (route.request().method() === 'PATCH') {
        const body = route.request().postDataJSON()
        saves.push(body)
        if (holdSave) { const pending = holdSave; holdSave = null; await pending }
        if (conflict || body.expected_revision !== clip.revision.revision) return route.fulfill({ status: 409, json: { code: 'REVISION_CONFLICT', message: 'Klip sudah berubah.' } })
        clip = { ...clip, revision: { ...clip.revision, ...body, id: `revision-${clip.revision.revision + 1}`, revision: clip.revision.revision + 1 } }
      }
      return route.fulfill({ json: clip })
    }
    if (path === `/api/v1/clips/${clip.id}/subtitles/generate`) {
      const body = route.request().postDataJSON()
      generations.push(body)
      if (body.expected_revision !== clip.revision.revision) return route.fulfill({ status: 409, json: { code: 'REVISION_CONFLICT', message: 'Klip sudah berubah.' } })
      return route.fulfill({ json: job })
    }
    if (path === `/api/v1/jobs/${job.id}`) return route.fulfill({ json: job })
    if (path === `/api/v1/clips/${clip.id}/exports`) {
      exports.push(route.request().postDataJSON())
      return route.fulfill({ json: { id: 'mock-export', status: 'queued' } })
    }
    if (path === `/api/v1/projects/${clip.project_id}/exports`) return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 100 } })
    return route.fulfill({ status: 404, json: { message: 'Unexpected test request' } })
  })
  await page.setViewportSize({ width: 1366, height: 900 })
  await page.goto(`/clips/${clip.id}`)
  await expect(page.getByLabel('Judul klip', { exact: true })).toHaveValue('Percakapan')
  return {
    saves, generations, exports,
    holdNextSave() { let release!: () => void; holdSave = new Promise<void>(resolve => { release = resolve }); return release },
    async finish() {
      clip = { ...clip, revision: { ...clip.revision, id: `revision-${clip.revision.revision + 1}`, revision: clip.revision.revision + 1,
        cues: [{ start_ms: 0, end_ms: 1200, text }],
        source_words: [
          { word: ' dan', start_ms: 10000, end_ms: 10200 },
          { word: ' berhenti', start_ms: 10300, end_ms: 10500 },
          { word: ' dan', start_ms: 10600, end_ms: 10700 },
          { word: ' berbicara', start_ms: 10800, end_ms: 11200 },
        ] } }
      job.status = 'succeeded'
      job.result_json = { cues: 1, message: '1 subtitle berhasil dibuat dari audio klip.' }
      await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
    },
  }
}

async function settings(page: Page) {
  await page.getByRole('tab', { name: 'Tampilan', exact: true }).click()
  await page.getByRole('button', { name: 'Gaya subtitle', exact: true }).click()
}

test('Podcast warning recovers zero-duration words from export and refreshes timing without changing bounds', async ({ page }) => {
  const fixture = await recoveryFixture(page)
  await page.getByRole('button', { name: 'Ekspor', exact: true }).click()
  const exportDialog = page.getByRole('dialog', { name: 'Ekspor klip', exact: true })
  await expect(exportDialog.getByText(/Highlight kata belum memiliki timestamp/)).toBeVisible()
  await expect(exportDialog.getByRole('button', { name: 'Mulai ekspor', exact: true })).toBeDisabled()
  await exportDialog.getByRole('button', { name: 'Perbaiki dari audio', exact: true }).click()
  await expect(exportDialog).not.toBeVisible()
  const audio = page.getByRole('dialog', { name: 'Buat ulang subtitle dari audio?' })
  await expect(audio).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden')
  await expect.poll(() => audio.evaluate(el => el.contains(document.activeElement))).toBe(true)
  expect(fixture.generations).toEqual([])
  await page.screenshot({ path: test.info().outputPath('podcast-audio-recovery-dialog.png') })
  await audio.getByRole('button', { name: 'Ganti subtitle dari audio', exact: true }).click()
  await expect.poll(() => fixture.generations).toEqual([{ expected_revision: 2, language: 'auto', replace_existing: true }])
  expect(fixture.saves).toEqual([])
  await expect(page.getByRole('button', { name: 'Buat subtitle dari audio', exact: true })).toBeDisabled()
  await fixture.finish()
  await expect(page.getByText('Revisi 3', { exact: true })).toBeVisible()
  await page.getByLabel('Posisi playback video sumber', { exact: true }).evaluate((el: HTMLInputElement) => {
    el.value = '10400'; el.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await expect(page.locator('[data-caption-template="podcast"] [data-active="true"]')).toHaveText('berhenti')
  await page.getByRole('button', { name: 'Ekspor', exact: true }).click()
  await expect(exportDialog.getByRole('button', { name: 'Perbaiki dari audio', exact: true })).toHaveCount(0)
  await exportDialog.getByRole('button', { name: 'Mulai ekspor', exact: true }).click()
  await expect.poll(() => fixture.exports).toEqual([{ revision: 3, resolution: 1080 }])
})

test('dirty Podcast style and manual edits are saved before audio replacement with the new revision', async ({ page }) => {
  const fixture = await recoveryFixture(page, false)
  await page.getByLabel('Teks subtitle 1', { exact: true }).fill('Koreksi manual saya')
  await settings(page)
  await page.getByRole('button', { name: 'Preset Podcast kuning', exact: true }).click()
  await page.getByRole('button', { name: 'Perbaiki dari audio', exact: true }).click()
  const audio = page.getByRole('dialog', { name: 'Buat ulang subtitle dari audio?' })
  await expect(audio.getByText(/Perubahan Anda akan disimpan dahulu/)).toBeVisible()
  await audio.getByRole('button', { name: 'Batal', exact: true }).click()
  expect(fixture.saves).toEqual([])
  expect(fixture.generations).toEqual([])
  await page.getByRole('button', { name: 'Perbaiki dari audio', exact: true }).click()
  const release = fixture.holdNextSave()
  await audio.getByRole('button', { name: 'Simpan dan buat ulang subtitle', exact: true }).click()
  await expect.poll(() => fixture.saves.length).toBe(1)
  expect(fixture.saves[0]).toMatchObject({ expected_revision: 2, cues: [{ text: 'Koreksi manual saya' }], subtitle_style_json: { renderer: 'remotion', remotion_template: 'podcast' } })
  expect(fixture.generations).toEqual([])
  await expect(audio.getByRole('button', { name: 'Batal', exact: true })).toBeDisabled()
  await expect(audio.getByRole('button', { name: 'Menyimpan perubahan...', exact: true })).toBeDisabled()
  release()
  await expect.poll(() => fixture.generations).toEqual([{ expected_revision: 3, language: 'auto', replace_existing: true }])
  await fixture.finish()
  await expect(page.getByText('Revisi 4', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Teks subtitle 1', { exact: true })).toHaveValue('dan berhenti dan berbicara')
  await settings(page)
  await expect(page.getByRole('combobox', { name: 'Template Remotion', exact: true })).toContainText('Podcast kuning')
  await expect(page.getByRole('button', { name: 'Perbaiki dari audio', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeDisabled()
})

test('save conflict stops audio recovery and preserves unsaved Podcast edits', async ({ page }) => {
  const fixture = await recoveryFixture(page, false, true)
  await page.getByLabel('Teks subtitle 1', { exact: true }).fill('Koreksi yang belum tersimpan')
  await settings(page)
  await page.getByRole('button', { name: 'Preset Podcast kuning', exact: true }).click()
  await page.getByRole('button', { name: 'Perbaiki dari audio', exact: true }).click()
  await page.getByRole('button', { name: 'Simpan dan buat ulang subtitle', exact: true }).click()
  const conflict = page.getByRole('dialog', { name: 'Revisi sudah berubah', exact: true })
  await expect(conflict).toBeVisible()
  await expect(page.getByRole('dialog', { name: 'Buat ulang subtitle dari audio?' })).not.toBeVisible()
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('hidden')
  await expect.poll(() => conflict.evaluate(el => el.contains(document.activeElement))).toBe(true)
  expect(fixture.generations).toEqual([])
  await conflict.getByRole('button', { name: 'Kembali ke perubahan saya', exact: true }).click()
  await expect.poll(() => page.evaluate(() => document.body.style.overflow)).toBe('')
  await expect(page.getByRole('combobox', { name: 'Template Remotion', exact: true })).toContainText('Podcast kuning')
  await page.getByRole('tab', { name: 'Subtitle 1', exact: true }).click()
  await expect(page.getByLabel('Teks subtitle 1', { exact: true })).toHaveValue('Koreksi yang belum tersimpan')
  await expect(page.getByRole('button', { name: 'Simpan', exact: true })).toBeEnabled()
})
