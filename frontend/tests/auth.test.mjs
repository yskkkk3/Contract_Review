import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'

// Run the real view handlers with store/router stubs, without credentials or network.
async function authSetup(store = {}) {
  const source = await readFile(new URL('../src/views/LoginView.vue', import.meta.url), 'utf8')
  const messages = []
  const routes = []
  const context = createContext({})
  const imports = {
    vue: { ref: (value) => ({ value }), reactive: (value) => value, onMounted() {}, onUnmounted() {} },
    'vue-router': { useRouter: () => ({ push: (path) => routes.push(path) }) },
    'element-plus': { ElMessage: {
      success: (message) => messages.push(['success', message]),
      warning: (message) => messages.push(['warning', message]),
    } },
    '@element-plus/icons-vue': { Connection: {}, DocumentChecked: {}, Search: {} },
    '@/stores/auth': { useAuthStore: () => store },
    '@/composables/useReveal': { useReveal: () => ({ value: undefined }) },
  }
  const setup = parse(source).descriptor.scriptSetup.content
  const module = new SourceTextModule(ts.transpileModule(`${setup}\nexport { onLogin, onRegister, identifier, password, reg, tab, loading }`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  }).outputText, { context })
  await module.link((name) => {
    const exports = imports[name] ?? { default: {} }
    return new SyntheticModule(Object.keys(exports), function () {
      for (const [key, value] of Object.entries(exports)) this.setExport(key, value)
    }, { context })
  })
  await module.evaluate()
  return { ...module.namespace, messages, routes }
}

test('login keeps the original payload, loading state, success message and dashboard route', async () => {
  const calls = []
  let finish
  const view = await authSetup({ login: (...args) => {
    calls.push(args)
    return new Promise((resolve) => { finish = resolve })
  } })
  view.identifier.value = 'example@example.test'
  view.password.value = 'example-password'
  const pending = view.onLogin()
  assert.equal(view.loading.value, true)
  assert.deepEqual(calls, [['example@example.test', 'example-password']])
  finish()
  await pending
  assert.equal(view.loading.value, false)
  assert.deepEqual(view.routes, ['/dashboard'])
  assert.deepEqual(view.messages, [['success', '登录成功']])
})

test('registration keeps the existing validation and does not submit invalid fields', async () => {
  const view = await authSetup({ register() { assert.fail('Invalid registration must not submit') } })
  view.reg.username = '  '
  await view.onRegister()
  view.reg.username = 'example'
  view.reg.password = '12345'
  await view.onRegister()
  assert.deepEqual(view.messages, [['warning', '请输入用户名'], ['warning', '密码至少需要 6 位']])
  assert.equal(view.loading.value, false)
  assert.equal(view.tab.value, 'login')
})

test('registration returns to login and prefills the original username without changing credentials', async () => {
  const calls = []
  const view = await authSetup({ register: async (...args) => { calls.push(args) } })
  view.tab.value = 'register'
  view.reg.username = ' example '
  view.reg.password = '123456'
  await view.onRegister()
  assert.deepEqual(calls, [[' example ', '123456']])
  assert.equal(view.tab.value, 'login')
  assert.equal(view.identifier.value, ' example ')
  assert.equal(view.loading.value, false)
  assert.deepEqual(view.routes, [])
  assert.deepEqual(view.messages, [['success', '注册成功，请登录']])
})

for (const action of ['onLogin', 'onRegister']) {
  test(`${action}: store failure clears loading and does not navigate or show success`, async () => {
    const error = new Error('Mock API failure')
    const reject = async () => { throw error }
    const view = await authSetup({ login: reject, register: reject })
    view.reg.username = 'example'
    view.reg.password = '123456'
    await assert.rejects(view[action](), (caught) => caught === error)
    assert.equal(view.loading.value, false)
    assert.deepEqual(view.routes, [])
    assert.deepEqual(view.messages, [])
  })
}
