import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import ts from 'typescript'

test('shell navigation preserves the existing route names, paths, labels and admin restriction', async () => {
  const source = await readFile(new URL('../src/components/layout/navigation.ts', import.meta.url), 'utf8')
  const context = createContext({})
  const module = new SourceTextModule(ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  }).outputText, { context })
  const icons = ['ChatDotRound', 'CopyDocument', 'DocumentChecked', 'FolderOpened', 'Odometer', 'Setting']
  await module.link(() => new SyntheticModule(icons, function () {
    for (const icon of icons) this.setExport(icon, {})
  }, { context }))
  await module.evaluate()
  const items = Array.from(module.namespace.APP_NAVIGATION, ({ name, path, label, adminOnly }) => [name, path, label, !!adminOnly])
  assert.deepEqual(items, [
    ['dashboard', '/dashboard', '工作台', false],
    ['contracts', '/contracts', '合同管理', false],
    ['review', '/review', '智能审阅', false],
    ['review-history', '/review-history', '审阅历史', false],
    ['compare', '/compare', '合同比对', false],
    ['chat', '/chat', '智能问答', false],
    ['admin', '/admin', '系统配置', true],
  ])
})

test('fixed branding copy is school-neutral in login and design preview', async () => {
  for (const path of ['../src/views/LoginView.vue', '../src/preview/DesignSystemDemo.vue']) {
    const source = await readFile(new URL(path, import.meta.url), 'utf8')
    assert.doesNotMatch(source, /深圳大学|深大/)
    assert.match(source, /采购合同管理场景/)
  }
})
