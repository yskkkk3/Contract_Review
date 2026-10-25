import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { computed, reactive, ref, watch } from 'vue'
import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'

const transpile = (source) => ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText
const helpers = await readFile(new URL('../src/utils/review-history.ts', import.meta.url), 'utf8')
const utils = await import(`data:text/javascript;base64,${Buffer.from(transpile(helpers)).toString('base64')}`)
const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}
const pageResult = (id) => ({ items: [{ id }], total: 1, page: 1, page_size: 10 })

async function setup(api = {}, query = {}) {
  const auth = reactive({ user: { id: 1 } })
  const route = reactive({ query })
  const review = reactive({ jobs: [], refresh: async () => {} })
  const unmounts = []
  const watchers = []
  const navigations = []
  const imports = {
    vue: { computed, reactive, ref, watch: (...args) => { const stop = watch(...args); watchers.push(stop); return stop },
      onUnmounted: (fn) => unmounts.push(fn) },
    'vue-router': { useRoute: () => route, useRouter: () => ({ push: (target) => navigations.push(target) }) },
    '@/api/review': { reviewApi: { history: async () => pageResult('initial'), ...api } },
    '@/stores/auth': { useAuthStore: () => auth },
    '@/stores/review': { useReviewStore: () => review },
    '@/utils/review-history': utils,
  }
  const source = await readFile(new URL('../src/views/ReviewHistoryView.vue', import.meta.url), 'utf8')
  const context = createContext({})
  const module = new SourceTextModule(transpile(parse(source).descriptor.scriptSetup.content + `
    export { items, total, page, pageSize, filters, loading, listError, load, search,
      openDetail, closeDetail, detail, detailLoading, detailError, repeat, emptyDescription };
  `), { context })
  await module.link((name) => new SyntheticModule(Object.keys(imports[name]), function () {
    for (const [key, value] of Object.entries(imports[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  await setImmediate()
  const unmount = () => { for (const fn of unmounts) fn(); for (const stop of watchers) stop() }
  return { view: module.namespace, auth, review, route, navigations, unmount }
}

test('history sends server pagination and contract filter and resets page on search', async () => {
  const requests = []
  const { view, unmount } = await setup({ history: async (params) => { requests.push(params); return pageResult('ok') } }, { file_id: '7' })
  assert.equal(requests[0].file_id, 7)
  view.page.value = 3
  view.pageSize.value = 20
  await view.load()
  assert.equal(requests.at(-1).page, 3)
  view.filters.title = '  采购合同  '
  view.filters.status = 'completed'
  view.search()
  await setImmediate()
  assert.equal(requests.at(-1).page, 1)
  assert.equal(requests.at(-1).page_size, 20)
  assert.equal(requests.at(-1).title, '采购合同')
  assert.equal(requests.at(-1).status, 'completed')
  unmount()
})

test('late search results cannot overwrite the current page', async () => {
  const pending = deferred()
  let calls = 0
  const { view, unmount } = await setup({ history: () => ++calls === 2 ? pending.promise : pageResult('latest') })
  const old = view.load()
  await view.load()
  pending.resolve(pageResult('old'))
  await old
  assert.equal(view.items.value[0].id, 'latest')
  unmount()
})

test('switching history details ignores a slower previous response', async () => {
  const pending = deferred()
  const { view, unmount } = await setup({ historyDetail: (id) => id === 'old' ? pending.promise : { id } })
  const old = view.openDetail('old')
  await view.openDetail('new')
  pending.resolve({ id: 'old' })
  await old
  assert.equal(view.detail.value.id, 'new')
  unmount()
})

test('closing details prevents an outstanding request from restoring old content', async () => {
  const pending = deferred()
  const { view, unmount } = await setup({ historyDetail: () => pending.promise })
  const old = view.openDetail('old')
  view.closeDetail()
  pending.resolve({ id: 'old' })
  await old
  assert.equal(view.detail.value, null)
  assert.equal(view.detailLoading.value, false)
  unmount()
})

test('account switch clears history and ignores the previous account response', async () => {
  const pending = deferred()
  let calls = 0
  const { view, auth, unmount } = await setup({ history: () => ++calls === 2 ? pending.promise : pageResult(`account-${calls}`) })
  const old = view.load()
  auth.user = { id: 2 }
  await setImmediate()
  pending.resolve(pageResult('private-old-record'))
  await old
  assert.equal(view.items.value[0].id, 'account-3')
  unmount()
})

test('unmount blocks pending detail updates and re-review navigates without inference', async () => {
  const pending = deferred()
  const { view, navigations, unmount } = await setup({ historyDetail: () => pending.promise })
  view.repeat('history-1')
  assert.equal(navigations[0].name, 'review')
  assert.equal(navigations[0].query.repeat, 'history-1')
  const old = view.openDetail('old')
  unmount()
  pending.resolve({ id: 'old' })
  await old
  assert.equal(view.detail.value, null)
})

test('incomplete and missing historical conclusions are never shown as low risk', () => {
  assert.equal(utils.reviewRiskLabel({ status: 'completed', review_status: 'incomplete', overall_risk: '低' }), '待补查')
  assert.equal(utils.reviewRiskLabel({ status: 'completed', review_status: null, overall_risk: null }), '未保存')
  assert.equal(utils.reviewRiskLabel({ status: 'cancelled', overall_risk: '低' }), '—')
  assert.equal(utils.formatReviewTime(null), '—')
  assert.equal(utils.formatReviewTime('invalid'), '—')
})

test('a background task status update refreshes the history list', async () => {
  let calls = 0
  const { view, review, unmount } = await setup({ history: async () => pageResult(`update-${++calls}`) })
  review.jobs = [{ id: 'active', status: 'completed' }]
  await setImmediate()
  assert.equal(view.items.value[0].id, 'update-2')
  unmount()
})
