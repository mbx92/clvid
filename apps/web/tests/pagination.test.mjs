import assert from 'node:assert/strict'
import test from 'node:test'
import { usePaginatedList } from '../app/composables/usePaginatedList.ts'

test('older history remains expanded and updates when active jobs are polled', async () => {
  const records = Array.from({ length: 205 }, (_, index) => ({ id: String(index + 1), status: 'queued' }))
  const list = usePaginatedList(async (page, size) => ({
    items: records.slice((page - 1) * size, page * size).map(item => ({ ...item })), total: records.length,
  }))
  await list.refresh()
  assert.equal(list.items.value.length, 100)
  assert.equal(list.total.value, 205)
  await list.loadMore()
  assert.equal(list.items.value.length, 200)
  records[149].status = 'succeeded'
  await list.refresh()
  assert.equal(list.items.value.length, 200)
  assert.equal(list.items.value.find(item => item.id === '150').status, 'succeeded')
  await list.loadMore()
  assert.equal(list.items.value.at(-1).id, '205')
  assert.equal(list.hasMore.value, false)
})

test('a partial refresh failure preserves already visible export history', async () => {
  let failSecondPage = false
  const list = usePaginatedList(async (page, size) => {
    if (page === 2 && failSecondPage) throw new Error('connection interrupted')
    return { items: Array.from({ length: size }, (_, i) => ({ id: String((page - 1) * size + i) })), total: 200 }
  })
  await list.refresh()
  await list.loadMore()
  const previous = list.items.value
  failSecondPage = true
  await assert.rejects(list.refresh(), /connection interrupted/)
  assert.equal(list.items.value, previous)
  assert.equal(list.items.value.length, 200)
  assert.equal(list.loading.value, false)
})

test('new exports between page loads do not leave stale boundaries or duplicate rows', async () => {
  const records = [{ id: '3' }, { id: '2' }, { id: '1' }]
  const list = usePaginatedList(async (page, size) => ({ items: records.slice((page - 1) * size, page * size), total: records.length }), 2)
  await list.refresh()
  records.unshift({ id: '4' })
  await list.loadMore()
  assert.deepEqual(list.items.value.map(item => item.id), ['4', '3', '2', '1'])
  assert.equal(list.hasMore.value, false)
})
