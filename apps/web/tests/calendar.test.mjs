import assert from 'node:assert/strict'
import test from 'node:test'
import { monthCells, moveMonth, localInput, utcInput, publicationReadiness, singlePublicationAccount } from '../app/utils/calendar.ts'
test('calendar keeps WITA times across UTC date boundaries and leap months', () => {
  assert.equal(utcInput('2027-01-02T00:15','Asia/Makassar'),'2027-01-01T16:15:00.000Z')
  assert.equal(localInput('2027-01-01T16:15:00Z','Asia/Makassar'),'2027-01-02T00:15')
  assert.equal(localInput('2027-01-01T16:15:00Z','Asia/Jakarta'),'2027-01-01T23:15')
  assert.equal(moveMonth('2026-12',1),'2027-01')
  assert.equal(moveMonth('2027-01',-1),'2026-12')
  const days=monthCells('2028-02')
  assert.equal(days.length,42)
  assert.ok(days.includes('2028-02-29'))
  assert.equal(new Date(days[0]+'T00:00Z').getUTCDay(),1)
})

test('connected accounts need a matching destination, not another OAuth connection', () => {
  const accounts = [{ id: 'yt1', platform: 'youtube' }, { id: 'ig1', platform: 'instagram' }]
  const platforms = [{ id: 'youtube', configured: true, publishing_ready: true }]
  const unselected = publicationReadiness('youtube', '', accounts, platforms)
  assert.equal(unselected.ready, false)
  assert.equal(unselected.manageConnection, false)
  assert.match(unselected.message, /Pilih Akun tujuan/)
  assert.equal(publicationReadiness('youtube', 'yt1', accounts, platforms).ready, true)
  assert.equal(publicationReadiness('youtube', 'ig1', accounts, platforms).ready, false)
  assert.equal(publicationReadiness('youtube', 'yt1', [{ ...accounts[0], connected: false }], platforms).manageConnection, true)
  assert.equal(singlePublicationAccount('youtube', accounts), 'yt1')
  assert.equal(singlePublicationAccount('youtube', [...accounts, { id: 'yt2', platform: 'youtube' }]), '')
  assert.equal(singlePublicationAccount('tiktok', accounts), '')
})

test('missing configuration, disconnected accounts and disabled publishing have separate explanations', () => {
  const accounts = [{ id: 'ig1', platform: 'instagram' }, { id: 'tk1', platform: 'tiktok' }]
  assert.match(publicationReadiness('youtube', '', [], []).message, /Konfigurasi/)
  assert.match(publicationReadiness('youtube', '', [], [{ id: 'youtube', configured: true, publishing_ready: true }]).message, /Belum ada akun/)
  assert.match(publicationReadiness('instagram', 'ig1', accounts, [{ id: 'instagram', configured: true, publishing_ready: false }]).message, /HTTPS/)
  assert.match(publicationReadiness('tiktok', 'tk1', accounts, [{ id: 'tiktok', configured: true, publishing_ready: false }]).message, /belum diaktifkan/)
})
