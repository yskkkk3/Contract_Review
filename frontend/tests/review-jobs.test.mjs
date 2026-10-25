import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { createPinia, defineStore, setActivePinia } from 'pinia'
import ts from 'typescript'

const source = await readFile(new URL('../src/stores/review.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText
const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}
const job = (status = 'processing', id = 'job-1') => ({
  id, file_id: 1, session_id: 2, title: '合同', stance: '甲方', intensity: '标准',
  description: '', contract_type: '采购', status, risk_points: [], summary: null,
  chunk_count: 3, error: '', created_at: '2026-10-25T01:00:00',
})

async function setup(review = {}, contract = {}) {
  setActivePinia(createPinia())
  const timers = new Set()
  const context = createContext({
    setTimeout: (fn) => { timers.add(fn); return fn },
    clearTimeout: (fn) => timers.delete(fn),
  })
  const imports = {
    pinia: { defineStore },
    '@/api/review': { reviewApi: { list: async () => [], ...review } },
    '@/api/contract': { api: {
      setType: async () => {}, createSession: async () => ({ session_id: 2 }), ...contract,
    } },
  }
  const module = new SourceTextModule(code, { context })
  await module.link((name) => new SyntheticModule(Object.keys(imports[name]), function () {
    for (const [key, value] of Object.entries(imports[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  return { store: module.namespace.useReviewStore(), timers }
}

test('restores background progress on login and polls independently of the review page', async () => {
  let status = 'processing'
  const { store, timers } = await setup({ list: async () => [job(status)] })
  await store.connect(1)
  assert.equal(store.selected.id, 'job-1')
  assert.equal(store.fileId, 1)
  assert.equal(store.running, true)
  assert.equal(timers.size, 1)
  status = 'completed'
  await store.refresh()
  assert.equal(store.selected.status, 'completed')
  assert.equal(store.running, false)
  assert.equal(timers.size, 0)
})

test('account switch clears results and ignores an old account response', async () => {
  const pending = deferred()
  let calls = 0
  const { store, timers } = await setup({ list: () => ++calls === 1 ? pending.promise : [] })
  const old = store.connect(1)
  await store.connect(2)
  pending.resolve([job()])
  await old
  assert.equal(store.ownerId, 2)
  assert.equal(store.jobs.length, 0)
  assert.equal(timers.size, 0)
})

test('logout clears progress without cancelling the server task', async () => {
  const { store, timers } = await setup({
    list: async () => [job()], cancel: () => assert.fail('logout must not cancel a background review'),
  })
  await store.connect(1)
  await store.connect(null)
  assert.equal(store.selected, undefined)
  assert.equal(store.jobs.length, 0)
  assert.equal(timers.size, 0)
})

test('manual stop requests server cancellation and waits for its status', async () => {
  let state = job()
  const cancelled = []
  const { store } = await setup({
    list: async () => [state],
    cancel: async (id) => { cancelled.push(id); state = job('cancelling'); return state },
  })
  await store.connect(1)
  await store.stop()
  assert.deepEqual(cancelled, ['job-1'])
  assert.equal(store.selected.status, 'cancelling')
  assert.equal(store.running, true)
  state = job('cancelled')
  await store.refresh()
  assert.equal(store.running, false)
})

test('double start is blocked during session preparation', async () => {
  const pending = deferred()
  let starts = 0
  const { store } = await setup({
    start: async () => { starts++; return job() },
  }, { createSession: () => pending.promise })
  await store.connect(1)
  store.fileId = 1
  const first = store.start([], [])
  await store.start([], [])
  assert.equal(store.submitting, true)
  pending.resolve({ session_id: 2 })
  await first
  assert.equal(starts, 1)
})

test('logout during preparation prevents starting a job for the previous account', async () => {
  const pending = deferred()
  const { store } = await setup({ start: () => assert.fail('stale start') }, {
    createSession: () => pending.promise,
  })
  await store.connect(1)
  store.fileId = 1
  const first = store.start([], [])
  await store.connect(null)
  pending.resolve({ session_id: 2 })
  await first
  assert.equal(store.jobs.length, 0)
  assert.equal(store.submitting, false)
})

test('manual cancel during preparation prevents launching inference', async () => {
  const pending = deferred()
  const { store } = await setup({ start: () => assert.fail('cancelled start') }, {
    createSession: () => pending.promise,
  })
  await store.connect(1)
  store.fileId = 1
  const first = store.start([], [])
  await store.stop()
  pending.resolve({ session_id: 2 })
  await first
  assert.equal(store.jobs.length, 0)
  assert.equal(store.submitting, false)
})

test('manual cancel while start is accepted stops the resulting server task', async () => {
  const pending = deferred()
  const accepted = deferred()
  const cancellations = []
  const { store } = await setup({
    start: () => { accepted.resolve(); return pending.promise },
    cancel: async (id) => { cancellations.push(id); return job('cancelling') },
  })
  await store.connect(1)
  store.fileId = 1
  const first = store.start([], [])
  await accepted.promise
  await store.stop()
  pending.resolve(job())
  await first
  assert.deepEqual(cancellations, ['job-1'])
})

test('lost start response restores the already accepted task', async () => {
  let accepted = false
  const { store } = await setup({
    list: async () => accepted ? [job()] : [],
    start: async () => { accepted = true; throw new Error('connection lost') },
  })
  await store.connect(1)
  store.fileId = 1
  await assert.rejects(store.start([], []), /connection lost/)
  assert.equal(store.selected.id, 'job-1')
  assert.equal(store.activeJobs.length, 1)
})

test('older polls cannot overwrite a newer completed result', async () => {
  const pending = deferred()
  let calls = 0
  const { store } = await setup({ list: () => ++calls === 2 ? pending.promise : [job('completed')] })
  await store.connect(1)
  const old = store.refresh()
  await store.refresh()
  pending.resolve([job('processing')])
  await old
  assert.equal(store.selected.status, 'completed')
})

test('a failed status fetch retains visible results and schedules a retry', async () => {
  let fail = false
  const { store, timers } = await setup({ list: async () => {
    if (fail) throw new Error('offline')
    return [job()]
  } })
  await store.connect(1)
  fail = true
  await store.refresh()
  assert.equal(store.jobs.length, 1)
  assert.ok(store.connectionError)
  assert.equal(timers.size, 1)
  await store.connect(null)
})

test('copying history prepares a draft and polling cannot overwrite its configuration', async () => {
  const { store } = await setup({ list: async () => [job()] })
  await store.connect(1)
  store.prepareFromHistory({ file_id: 7, contract_type: '服务', stance: '乙方', intensity: '严格', description: '历史重点' })
  assert.equal(store.selected, undefined)
  assert.equal(store.running, false)
  assert.equal(store.activeJobs.length, 1)
  await store.refresh()
  assert.equal(store.fileId, 7)
  assert.equal(store.stance, '乙方')
  assert.equal(store.description, '历史重点')
  assert.equal(store.selected, undefined)
  await store.connect(null)
})

test('starting a copied history creates a new session and preserves the previous record', async () => {
  const sessions = []
  let records = [job('completed')]
  const { store } = await setup({
    list: async () => records,
    start: async (body) => {
      assert.equal(body.session_id, 3)
      assert.equal(body.stance, '乙方')
      const fresh = { ...job('processing', 'new-job'), session_id: 3 }
      records = [fresh, ...records]
      return fresh
    },
  }, { createSession: async (...args) => { sessions.push(args); return { session_id: 3 } } })
  await store.connect(1)
  store.prepareFromHistory({ ...job('completed'), stance: '乙方' })
  await store.start([], [])
  assert.equal(sessions.length, 1)
  assert.equal(sessions[0][2], 1)
  assert.equal(store.jobs.length, 2)
  assert.equal(store.jobs[1].status, 'completed')
  assert.equal(store.selectedId, 'new-job')
  await store.connect(null)
})
