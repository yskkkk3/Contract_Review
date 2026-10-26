import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import ts from 'typescript'
import { parse } from '@vue/compiler-sfc'

const transpile = (source) => ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText

const source = await readFile(new URL('../src/utils/sse.ts', import.meta.url), 'utf8')
const { openSse } = await import(`data:text/javascript;base64,${Buffer.from(transpile(source)).toString('base64')}`)

for (const kind of ['chat', 'review']) {
  test(`${kind}: normal completion, split UTF-8 and CRLF frames`, async (t) => {
    const terminal = kind === 'chat' ? { type: 'done' } : { event: 'end' }
    const bytes = new TextEncoder().encode(`data: {"content":"合同"}\r\n\r\ndata: ${JSON.stringify(terminal)}`)
    t.mock.method(globalThis, 'fetch', async () => new Response(new ReadableStream({
      start(controller) {
        for (const byte of bytes) controller.enqueue(Uint8Array.of(byte))
        controller.close()
      },
    })))
    const events = []
    openSse({ url: '/test', kind, token: '', onEvent: (event) => events.push(event) })
    await setImmediate()
    assert.deepEqual(events, [{ content: '合同' }, terminal])
  })

  test(`${kind}: EOF without completion reports an error`, async (t) => {
    t.mock.method(globalThis, 'fetch', async () => new Response('data: {"content":"部分结果"}\n\n'))
    const events = []
    openSse({ url: '/test', kind, token: '', onEvent: (event) => events.push(event) })
    await setImmediate()
    assert.equal(events.at(-1).type, 'error')
    assert.equal(events.at(-1).event, 'error')
    assert.match(events.at(-1).message, /未收到完成结果/)
  })
}

test('manual abort is silent and removes the external listener', async (t) => {
  t.mock.method(globalThis, 'fetch', (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
  }))
  const external = new AbortController()
  const remove = t.mock.method(external.signal, 'removeEventListener')
  const events = []
  const abort = openSse({ url: '/test', kind: 'chat', token: '', signal: external.signal, onEvent: (event) => events.push(event) })
  abort()
  await setImmediate()
  assert.deepEqual(events, [])
  assert.equal(remove.mock.callCount(), 1)
})

const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

// Execute the actual setup script with API/lifecycle stubs; no network or UI test dependency.
async function chatSetup(sessionApi, query = {}) {
  const file = await readFile(new URL('../src/views/ChatView.vue', import.meta.url), 'utf8')
  const setup = parse(file).descriptor.scriptSetup.content
  const hooks = {}
  const streams = []
  const aborts = []
  const context = createContext({ localStorage: { getItem: () => '' } })
  const imports = {
    vue: {
      ref: (value) => ({ value }), nextTick: (callback) => Promise.resolve().then(callback),
      computed: (callback) => ({ get value() { return callback() } }),
      onMounted: (callback) => { hooks.mounted = callback },
      onUnmounted: (callback) => { hooks.unmounted = callback },
    },
    'vue-router': { useRoute: () => ({ query }) },
    'element-plus': { ElMessage: { error() {} } },
    '@/api/contract': { api: { list: async () => [] } },
    '@/api/session': { sessionApi },
    '@/api/http': { TOKEN_KEY: 'token' },
    '@/utils/sse': { openSse: (options) => { streams.push(options); return () => aborts.push(options) } },
  }
  const module = new SourceTextModule(transpile(`${setup}\nexport { send, stopReply, replyStatus, switchSession, newSession, input, messages, sending, currentId, loadingHistory }`), {
    context, initializeImportMeta: (meta) => { meta.env = {} },
  })
  await module.link((name) => new SyntheticModule(Object.keys(imports[name]), function () {
    for (const [key, value] of Object.entries(imports[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  return { ...module.namespace, hooks, streams, aborts }
}

test('a review-aware chat route opens the generated session and loads its history', async () => {
  const session = { session_id: 9, title: '审阅答疑', file_id: 3, source_review_id: 'review-1' }
  const chat = await chatSetup({
    list: async () => ({ items: [session] }),
    history: async () => [{ role: 'assistant', content: '已关联审阅结果' }],
  }, { session_id: '9' })
  await chat.hooks.mounted()
  assert.equal(chat.currentId.value, 9)
  assert.equal(chat.messages.value[0].content, '已关联审阅结果')
})

test('chat shows waiting/generating state and clears status on completion', async () => {
  const chat = await chatSetup({})
  chat.currentId.value = 1
  chat.input.value = '付款风险'
  await chat.send()
  assert.match(chat.replyStatus.value, /准备/)
  const stream = chat.streams[0]
  stream.onEvent({ type: 'start' })
  assert.match(chat.replyStatus.value, /等待/)
  stream.onEvent({ type: 'status', phase: 'analyzing' })
  assert.match(chat.replyStatus.value, /分析/)
  stream.onEvent({ type: 'content', content: 'partial' })
  assert.match(chat.replyStatus.value, /生成/)
  stream.onEvent({ type: 'done' })
  assert.equal(chat.sending.value, false)
  assert.equal(chat.replyStatus.value, '')
})

test('stopping keeps partial text and ignores stale callbacks after another send', async () => {
  const chat = await chatSetup({})
  chat.currentId.value = 1
  chat.input.value = '第一问'
  await chat.send()
  const old = chat.streams[0]
  old.onEvent({ type: 'content', content: 'partial' })
  chat.stopReply()
  assert.equal(chat.aborts.length, 1)
  assert.equal(chat.sending.value, false)
  assert.equal(chat.messages.value.at(-1).content, 'partial')
  assert.match(chat.replyStatus.value, /尚未完成/)
  chat.input.value = '第二问'
  await chat.send()
  old.onEvent({ type: 'done' })
  old.onEvent({ type: 'content', content: 'stale' })
  assert.equal(chat.sending.value, true)
  assert.equal(chat.messages.value.at(-1).role, 'user')
})

test('chat timeout reports incomplete answer and releases the send button', async () => {
  const chat = await chatSetup({})
  chat.currentId.value = 1
  chat.input.value = '付款风险'
  await chat.send()
  chat.streams[0].onEvent({ type: 'error', code: 'timeout', message: '回答超时，尚未完成' })
  assert.equal(chat.sending.value, false)
  assert.match(chat.replyStatus.value, /超时/)
})

test('rapid switching cannot overwrite the current history', async () => {
  const first = deferred()
  const second = deferred()
  const chat = await chatSetup({ history: (id) => id === 1 ? first.promise : second.promise })
  const a = chat.switchSession({ session_id: 1 })
  const b = chat.switchSession({ session_id: 2 })
  second.resolve([{ role: 'assistant', content: '第二个会话' }])
  await b
  first.resolve([{ role: 'assistant', content: '旧会话' }])
  await a
  assert.equal(chat.currentId.value, 2)
  assert.equal(chat.messages.value[0].content, '第二个会话')
  assert.equal(chat.loadingHistory.value, false)
})

test('session creation locks duplicate sends and stale streams are ignored', async () => {
  const pending = deferred()
  let creations = 0
  const chat = await chatSetup({
    create: () => { creations += 1; return pending.promise }, history: async () => [],
  })
  chat.input.value = '付款风险'
  const first = chat.send()
  await chat.send()
  assert.equal(creations, 1)
  assert.equal(chat.sending.value, true)
  pending.resolve({ session_id: 1 })
  await first
  assert.equal(chat.streams.length, 1)
  chat.newSession()
  chat.streams[0].onEvent({ type: 'content', content: '旧结果' })
  assert.equal(chat.messages.value.length, 0)
  assert.equal(chat.sending.value, false)
})

test('creating a new conversation invalidates a pending session creation', async () => {
  const pending = deferred()
  const chat = await chatSetup({ create: () => pending.promise })
  chat.input.value = '付款风险'
  const request = chat.send()
  chat.newSession()
  pending.resolve({ session_id: 1 })
  await request
  assert.equal(chat.currentId.value, undefined)
  assert.equal(chat.streams.length, 0)
})

test('dashboard unmount before API completion leaves no resize listener', async () => {
  const file = await readFile(new URL('../src/views/DashboardView.vue', import.meta.url), 'utf8')
  const pending = deferred()
  const hooks = {}
  const listeners = new Set()
  const context = createContext({ window: {
    addEventListener: (_name, listener) => listeners.add(listener),
    removeEventListener: (_name, listener) => listeners.delete(listener),
  } })
  const imports = {
    vue: {
      ref: (value) => ({ value }), computed: (callback) => ({ get value() { return callback() } }),
      nextTick: () => Promise.resolve(),
      onMounted: (callback) => { hooks.mounted = callback },
      onUnmounted: (callback) => { hooks.unmounted = callback },
    },
    'echarts/core': { use() {}, init() { assert.fail('Unmounted dashboard must not initialize charts') } },
    'echarts/charts': { LineChart: {}, PieChart: {} },
    'echarts/components': { GridComponent: {}, LegendComponent: {}, TooltipComponent: {} },
    'echarts/renderers': { CanvasRenderer: {} },
    '@element-plus/icons-vue': { Document: {}, Finished: {}, Warning: {}, Calendar: {} },
    '@/api/dashboard': { dashboardApi: {
      overview: () => pending.promise, trends: async () => [{ date: '2026-10-11', total: 1 }],
      departments: async () => [{ department_name: '示例', total: 1 }],
    } },
  }
  const module = new SourceTextModule(transpile(parse(file).descriptor.scriptSetup.content), { context })
  await module.link((name) => new SyntheticModule(Object.keys(imports[name]), function () {
    for (const [key, value] of Object.entries(imports[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  const mounting = hooks.mounted()
  assert.equal(listeners.size, 1)
  hooks.unmounted()
  pending.resolve({ reviewed_contracts: 1 })
  await mounting
  assert.equal(listeners.size, 0)
})

test('HTTP 401 logs out the in-memory auth store and redirects', async () => {
  const file = await readFile(new URL('../src/api/http.ts', import.meta.url), 'utf8')
  let rejectResponse
  let loggedOut = false
  let target
  const context = createContext({ localStorage: { getItem: () => null } })
  const imports = {
    axios: { default: { create: () => ({ interceptors: {
      request: { use() {} },
      response: { use: (_success, failure) => { rejectResponse = failure } },
    } }) } },
    'element-plus': { ElMessage: { error() {} } },
    '@/router': { default: { push: (path) => { target = path } } },
    '@/stores/auth': { useAuthStore: () => ({ logout: () => { loggedOut = true } }) },
  }
  const stub = (name) => new SyntheticModule(Object.keys(imports[name]), function () {
    for (const [key, value] of Object.entries(imports[name])) this.setExport(key, value)
  }, { context })
  const module = new SourceTextModule(transpile(file), {
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
  const error = { response: { status: 401 }, message: 'Unauthorized' }
  await assert.rejects(rejectResponse(error), (caught) => caught === error)
  assert.equal(loggedOut, true)
  assert.equal(target, '/login')
})
