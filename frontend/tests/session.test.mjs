import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import ts from 'typescript'

const transpile = (source) => ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText
const TOKEN = 'contract_review_token'
const REFRESH = 'contract_review_refresh_token'
const source = await readFile(new URL('../src/api/http.ts', import.meta.url), 'utf8')
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

async function setup(post) {
  const storage = new Map([[TOKEN, 'old'], [REFRESH, 'refresh']])
  const retries = [], logouts = [], routes = []
  const store = { token: 'old', logout: (revoke) => {
    logouts.push(revoke)
    store.token = ''
    storage.delete(TOKEN)
    storage.delete(REFRESH)
  } }
  const handlers = {}
  const http = {
    request: async (config) => { retries.push(config); return { data: 'retried' } },
    interceptors: {
      request: { use: (fn) => { handlers.request = fn } },
      response: { use: (success, failure) => { handlers.success = success; handlers.failure = failure } },
    },
  }
  const context = createContext({
    localStorage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) },
    AbortController, TextDecoder, DOMException,
  })
  const imports = {
    axios: { default: { create: () => http, post } },
    'element-plus': { ElMessage: { error() {} } },
    '@/router': { default: { push: (path) => routes.push(path) } },
    '@/stores/auth': { useAuthStore: () => store },
  }
  const stub = (name) => new SyntheticModule(Object.keys(imports[name]), function () {
    for (const [key, value] of Object.entries(imports[name])) this.setExport(key, value)
  }, { context })
  const module = new SourceTextModule(transpile(source), {
    context, initializeImportMeta: (meta) => { meta.env = {} },
    importModuleDynamically: async (name) => {
      const imported = stub(name)
      await imported.link(() => {})
      await imported.evaluate()
      return imported
    },
  })
  await module.link(stub)
  await module.evaluate()
  return { ...module.namespace, module, context, storage, retries, logouts, routes, store, handlers }
}

const unauthorized = () => ({ response: { status: 401 }, config: { url: '/contracts', headers: { Authorization: 'Bearer old' } }, message: 'Unauthorized' })
const refreshed = () => ({ data: { code: 200, data: { access_token: 'new', refresh_token: 'refresh' } } })

test('concurrent HTTP 401 refresh once and replay each request once', async () => {
  const pending = deferred()
  let calls = 0
  const app = await setup(async (url, body) => {
    calls++
    assert.equal(url, '/api/auth/refresh')
    assert.equal(body.refresh_token, 'refresh')
    return pending.promise
  })
  const first = app.handlers.failure(unauthorized())
  const second = app.handlers.failure(unauthorized())
  assert.equal(calls, 1)
  pending.resolve(refreshed())
  await Promise.all([first, second])
  assert.equal(app.retries.length, 2)
  assert.equal(app.retries[0].headers.Authorization, 'Bearer new')
  assert.equal(app.storage.get(TOKEN), 'new')
  assert.deepEqual(app.logouts, [])
})

test('refresh failure expires local session without sending logout or retrying refresh recursively', async () => {
  const app = await setup(async () => { throw new Error('refresh revoked') })
  const error = unauthorized()
  await assert.rejects(app.handlers.failure(error), (value) => value === error)
  assert.deepEqual(app.logouts, [false])
  assert.deepEqual(app.routes, ['/login'])
  assert.equal(app.storage.has(TOKEN), false)
  assert.equal(app.retries.length, 0)
})

for (const change of ['logout', 'new-login']) {
  test(`pending refresh cannot overwrite ${change}`, async () => {
    const pending = deferred()
    const app = await setup(() => pending.promise)
    const refreshing = app.refreshAccessToken()
    if (change === 'logout') {
      app.storage.delete(TOKEN)
      app.storage.delete(REFRESH)
    } else {
      app.storage.set(TOKEN, 'another-login')
      app.storage.set(REFRESH, 'another-refresh')
    }
    pending.resolve(refreshed())
    await assert.rejects(refreshing)
    assert.equal(app.storage.get(TOKEN), change === 'logout' ? undefined : 'another-login')
  })
}

test('late sliding-token response cannot restore logged-out session', async () => {
  const app = await setup()
  app.storage.delete(TOKEN)
  app.handlers.success({ headers: { 'x-access-token': 'late' }, config: { headers: { Authorization: 'Bearer old' } } })
  assert.equal(app.storage.has(TOKEN), false)
})

test('SSE refreshes only before streaming and receives completion after reconnect', async () => {
  let refreshCalls = 0
  const app = await setup(async () => { refreshCalls++; return refreshed() })
  const sent = []
  app.context.fetch = async (_url, options) => {
    sent.push(options.headers.Authorization)
    return sent.length === 1 ? new Response('{}', { status: 401 }) : new Response('data: {"type":"done"}\n\n')
  }
  const sseSource = await readFile(new URL('../src/utils/sse.ts', import.meta.url), 'utf8')
  const module = new SourceTextModule(transpile(sseSource), {
    context: app.context,
    importModuleDynamically: async () => app.module,
  })
  await module.link(() => {})
  await module.evaluate()
  const events = []
  module.namespace.openSse({ url: '/api/chats', kind: 'chat', token: 'old', onEvent: (event) => events.push(event) })
  await setImmediate()
  await setImmediate()
  assert.equal(refreshCalls, 1)
  assert.deepEqual(sent, ['Bearer old', 'Bearer new'])
  assert.equal(events.at(-1).type, 'done')
})

test('logout with expired access refreshes only to revoke the server session', async () => {
  const calls = []
  const context = createContext({})
  const code = await readFile(new URL('../src/api/auth.ts', import.meta.url), 'utf8')
  const imports = {
    './http': { get() {}, post() {} },
    axios: { default: {
      isAxiosError: () => true,
      post: async (url, body, config) => {
        calls.push([url, body, config?.headers?.Authorization])
        if (calls.length === 1) throw { response: { status: 401 } }
        return { data: { data: { access_token: 'renewed' } } }
      },
    } },
  }
  const module = new SourceTextModule(transpile(code), { context, initializeImportMeta: (meta) => { meta.env = {} } })
  await module.link((name) => new SyntheticModule(Object.keys(imports[name]), function () {
    for (const [key, value] of Object.entries(imports[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  await module.namespace.authApi.logout('expired', 'refresh')
  assert.deepEqual(calls.map(([url, , auth]) => [url, auth]), [
    ['/api/auth/logout', 'Bearer expired'], ['/api/auth/refresh', undefined], ['/api/auth/logout', 'Bearer renewed'],
  ])
})
