import assert from 'node:assert/strict'
import test from 'node:test'
import { monthCells, moveMonth, localInput, utcInput } from '../app/utils/calendar.ts'
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
