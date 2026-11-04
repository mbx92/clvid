import assert from 'node:assert/strict'
import test, { beforeEach, after } from 'node:test'
import { useApi, useSession, prepareCsrfToken } from '../app/composables/useApi.ts'

const state = new Map()
globalThis.useState = (key, init) => {
  if (!state.has(key)) state.set(key, { value: init() })
  return state.get(key)
}
beforeEach(() => {
  state.clear()
  globalThis.document = { cookie: '' }
})
after(() => {
  delete globalThis.document
  delete globalThis.useState
  delete globalThis.$fetch
})

test('export uses the current cookie after another tab rotates the token', async () => {
  useSession().csrf.value = 'old-page-token'
  document.cookie = 'unrelated=value; clipper_csrf=current-token'
  let calls = 0
  globalThis.$fetch = async (path, options) => {
    calls++
    assert.equal(path, '/api/v1/clips/clip-id/exports')
    assert.equal(options.headers['X-CSRF-Token'], 'current-token')
    assert.equal(options.headers['Idempotency-Key'], 'same-operation')
    assert.deepEqual(options.body, { revision: 2 })
    return { id: 'export-id' }
  }
  await useApi()('/clips/clip-id/exports', { method: 'POST', body: { revision: 2 }, headers: { 'Idempotency-Key': 'same-operation' } })
  assert.equal(calls, 1)
  assert.equal(useSession().csrf.value, 'current-token')
})

test('a missing cookie is recovered before a write rather than sending stale state', async () => {
  useSession().csrf.value = 'stale-token'
  const paths = []
  globalThis.$fetch = async (path, options) => {
    paths.push(path)
    if (path.endsWith('/csrf')) {
      assert.equal(options.cache, 'no-store')
      assert.equal(options.credentials, 'include')
      document.cookie = 'clipper_csrf=recovered-token'
      return { csrf_token: 'recovered-token' }
    }
    assert.equal(options.headers['X-CSRF-Token'], 'recovered-token')
    return {}
  }
  await useApi()('/projects', { method: 'POST' })
  assert.deepEqual(paths, ['/api/v1/auth/csrf', '/api/v1/projects'])
})

test('concurrent API and upload preparation share one missing-cookie recovery', async () => {
  let calls = 0
  globalThis.$fetch = async () => {
    calls++
    await new Promise(resolve => setImmediate(resolve))
    return { csrf_token: 'shared-token' }
  }
  assert.deepEqual(await Promise.all([prepareCsrfToken(), prepareCsrfToken()]), ['shared-token', 'shared-token'])
  assert.equal(calls, 1)
})

test('reads do not request or attach a CSRF token', async () => {
  globalThis.$fetch = async (path, options) => {
    assert.equal(path, '/api/v1/auth/me')
    assert.equal(options.headers['X-CSRF-Token'], undefined)
    return {}
  }
  await useApi()('/auth/me')
})

test('failed recovery can be retried and does not submit the write', async () => {
  let calls = 0
  globalThis.$fetch = async path => {
    assert.equal(path, '/api/v1/auth/csrf')
    if (++calls === 1) throw new Error('offline')
    return { csrf_token: 'recovered-token' }
  }
  await assert.rejects(useApi()('/projects', { method: 'POST' }), /offline/)
  assert.equal(await prepareCsrfToken(), 'recovered-token')
})

test('a rejected write is not replayed automatically', async () => {
  document.cookie = 'clipper_csrf=current-token'
  let calls = 0
  globalThis.$fetch = async () => {
    calls++
    throw Object.assign(new Error('Forbidden'), { status: 403, data: { code: 'CSRF_INVALID' } })
  }
  await assert.rejects(useApi()('/projects', { method: 'POST' }), /Forbidden/)
  assert.equal(calls, 1)
})
