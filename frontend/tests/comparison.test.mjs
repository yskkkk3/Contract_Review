import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'
import { reactive, ref, watch } from 'vue'
import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'

const transpile = (source) => ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText
const helper = await readFile(new URL('../src/utils/comparison.ts', import.meta.url), 'utf8')
const { comparisonUnavailableReason } = await import(`data:text/javascript;base64,${Buffer.from(transpile(helper)).toString('base64')}`)
const file = (id, file_type = 'pdf', parse_status = 'parsed') => ({ id, title: `${id}.${file_type}`, file_type, parse_status })
const result = {
  diff_summary: { difference_count: 1 },
  diffs: [{ operation: 'replace', standard_text: '原条款', comparison_text: '新条款' }],
  standard_file: { title: '基准.pdf' }, comparison_file: { title: '对比.doc' },
}
const deferred = () => {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

async function setup(api = {}) {
  const auth = reactive({ user: { id: 1 } })
  const hooks = {}
  const watchers = []
  const warnings = []
  let now = 10000
  const imports = {
    vue: { ref, watch: (...args) => { const stop = watch(...args); watchers.push(stop); return stop },
      onMounted: (fn) => { hooks.mount = fn }, onUnmounted: (fn) => { hooks.unmount = fn } },
    'element-plus': { ElMessage: { warning: (text) => warnings.push(text) } },
    '@/api/contract': { api: { list: async () => [file(1), file(2, 'doc')], compare: async () => result, ...api } },
    '@/stores/auth': { useAuthStore: () => auth },
    '@/utils/comparison': { comparisonUnavailableReason },
  }
  const source = await readFile(new URL('../src/views/CompareView.vue', import.meta.url), 'utf8')
  const context = createContext({ Date: { now: () => now } })
  const module = new SourceTextModule(transpile(parse(source).descriptor.scriptSetup.content + `
    export { files, fileA, fileB, summary, diffs, running, resultNames, loadingFiles,
      loadError, loadFiles, compare, onDropdownVisible, clearResult };
  `), { context })
  await module.link((name) => new SyntheticModule(Object.keys(imports[name]), function () {
    for (const [key, value] of Object.entries(imports[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  await hooks.mount()
  return { view: module.namespace, auth, warnings, advance: (ms) => { now += ms },
    unmount: () => { hooks.unmount(); for (const stop of watchers) stop() } }
}

test('parsed PDF/DOC and raw DOCX are selectable while unavailable inputs explain why', () => {
  for (const kind of ['pdf', 'doc', '.PDF', 'DOC']) assert.equal(comparisonUnavailableReason(file(1, kind)), '')
  assert.equal(comparisonUnavailableReason(file(1, 'docx', 'uploaded')), '')
  assert.match(comparisonUnavailableReason(file(1, 'pdf', 'uploaded')), /尚未解析/)
  assert.match(comparisonUnavailableReason(file(1, 'doc', 'pending')), /正在解析/)
  assert.match(comparisonUnavailableReason(file(1, 'pdf', 'failed')), /解析失败/)
  assert.match(comparisonUnavailableReason(file(1, 'txt')), /暂不支持/)
})

test('all uploaded formats remain visible in the comparison list', async () => {
  const { view, unmount } = await setup({ list: async () => [file(1), file(2, 'doc'), file(3, 'docx'), file(4, 'pdf', 'uploaded')] })
  assert.equal(view.files.value.length, 4)
  assert.equal(view.files.value[0].file_type, 'pdf')
  unmount()
})

test('opening a dropdown refreshes uploads and clears only selections no longer available', async () => {
  let records = [file(1), file(2)]
  const { view, advance, unmount } = await setup({ list: async () => records })
  view.fileA.value = 1
  view.fileB.value = 2
  records = [file(1), file(3)]
  advance(6000)
  view.onDropdownVisible(true)
  await setImmediate()
  assert.equal(view.fileA.value, 1)
  assert.equal(view.fileB.value, undefined)
  assert.equal(view.files.value[1].id, 3)
  unmount()
})

test('PDF/DOC selections reach the comparison API and duplicate starts are blocked', async () => {
  const pending = deferred()
  const requests = []
  const { view, unmount } = await setup({ compare: (...args) => { requests.push(args); return pending.promise } })
  view.fileA.value = 1
  view.fileB.value = 2
  const first = view.compare()
  await view.compare()
  assert.equal(requests.length, 1)
  assert.equal(requests[0][0], 1)
  assert.equal(requests[0][1], 2)
  pending.resolve(result)
  await first
  assert.equal(view.summary.value.difference_count, 1)
  assert.equal(view.resultNames.value.base, '基准.pdf')
  assert.equal(view.running.value, false)
  unmount()
})

test('unparsed files and selecting the same contract cannot start a comparison', async () => {
  const { view, warnings, unmount } = await setup({
    list: async () => [file(1), file(2, 'pdf', 'uploaded')], compare: () => assert.fail('invalid selection'),
  })
  view.fileA.value = view.fileB.value = 1
  await view.compare()
  assert.match(warnings.at(-1), /不同/)
  view.fileB.value = 2
  await view.compare()
  assert.match(warnings.at(-1), /完成解析/)
  unmount()
})

test('a late list response cannot overwrite a newer refresh', async () => {
  const pending = deferred()
  let calls = 0
  const { view, unmount } = await setup({ list: () => ++calls === 2 ? pending.promise : [file(3)] })
  const old = view.loadFiles()
  await view.loadFiles()
  pending.resolve([file(1)])
  await old
  assert.equal(view.files.value[0].id, 3)
  unmount()
})

test('logout clears a loading list and ignores its pending response', async () => {
  const pending = deferred()
  let calls = 0
  const { view, auth, unmount } = await setup({ list: () => ++calls === 2 ? pending.promise : [file(1)] })
  const old = view.loadFiles()
  auth.user = null
  pending.resolve([file(1)])
  await old
  assert.equal(view.files.value.length, 0)
  assert.equal(view.loadingFiles.value, false)
  unmount()
})

test('switching accounts ignores an earlier comparison result', async () => {
  const pending = deferred()
  const { view, auth, unmount } = await setup({ compare: () => pending.promise })
  view.fileA.value = 1
  view.fileB.value = 2
  const old = view.compare()
  auth.user = { id: 2 }
  pending.resolve(result)
  await old
  assert.equal(view.summary.value, null)
  assert.equal(view.fileA.value, undefined)
  assert.equal(view.running.value, false)
  unmount()
})

test('leaving the page prevents a pending comparison from restoring results', async () => {
  const pending = deferred()
  const { view, unmount } = await setup({ compare: () => pending.promise })
  view.fileA.value = 1
  view.fileB.value = 2
  const old = view.compare()
  unmount()
  pending.resolve(result)
  await old
  assert.equal(view.summary.value, null)
})
