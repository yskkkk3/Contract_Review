import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import ts from 'typescript'

const transpile = (source) => ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText
const validationSource = await readFile(new URL('../src/utils/avatar.ts', import.meta.url), 'utf8')
const { avatarFileError, MAX_AVATAR_BYTES } = await import(`data:text/javascript;base64,${Buffer.from(transpile(validationSource)).toString('base64')}`)

test('avatar validation accepts the 5 MB boundary and rejects oversized, empty and unsupported files', () => {
  for (const type of ['image/jpeg', 'image/png', 'image/webp']) {
    assert.equal(avatarFileError({ type, size: MAX_AVATAR_BYTES }), undefined)
    assert.match(avatarFileError({ type, size: MAX_AVATAR_BYTES + 1 }), /5 MB/)
    assert.equal(avatarFileError({ type, size: 0 }), '图片不能为空')
  }
  for (const type of ['image/svg+xml', 'image/gif', 'text/html', '']) {
    assert.equal(avatarFileError({ type, size: 100 }), '请选择 JPG、PNG 或 WebP 图片')
  }
})

async function authStore(avatarApi = {}, authApi = {}) {
  const source = await readFile(new URL('../src/stores/auth.ts', import.meta.url), 'utf8')
  const created = []
  const revoked = []
  const storage = new Map([['token', 'mock-access-token']])
  const context = createContext({
    URL: {
      createObjectURL: (blob) => { created.push(blob); return `blob:avatar-${created.length}` },
      revokeObjectURL: (url) => { revoked.push(url) },
    },
    localStorage: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) },
  })
  const imports = {
    pinia: { defineStore: (_name, options) => () => {
      const state = options.state()
      for (const [key, value] of Object.entries(options.actions)) state[key] = value.bind(state)
      return state
    } },
    '@/api/auth': { authApi },
    '@/api/avatar': { avatarApi },
    '@/api/http': { TOKEN_KEY: 'token' },
  }
  const module = new SourceTextModule(transpile(source), { context })
  await module.link((name) => new SyntheticModule(Object.keys(imports[name]), function () {
    for (const [key, value] of Object.entries(imports[name])) this.setExport(key, value)
  }, { context }))
  await module.evaluate()
  return { store: module.namespace.useAuthStore(), created, revoked, storage }
}

const profile = { id: 1, username: 'example', role: 'user', avatar_url: '/api/users/me/avatar' }

test('avatar downloads use blob URLs and release the previous URL on replacement and logout', async () => {
  const blob = new Blob(['image'])
  const { store, created, revoked, storage } = await authStore({ read: async () => blob })
  store.user = profile
  await store.loadAvatar()
  assert.equal(store.avatarUrl, 'blob:avatar-1')
  await store.loadAvatar()
  assert.deepEqual(revoked, ['blob:avatar-1'])
  assert.equal(created.length, 2)
  store.logout()
  assert.equal(store.avatarUrl, '')
  assert.equal(store.user, null)
  assert.equal(storage.has('token'), false)
  assert.deepEqual(revoked, ['blob:avatar-1', 'blob:avatar-2'])
})

test('a pending avatar download cannot restore an image after logout', async () => {
  let complete
  const { store, created } = await authStore({ read: () => new Promise((resolve) => { complete = resolve }) })
  store.user = profile
  const pending = store.loadAvatar()
  store.logout()
  complete(new Blob(['old image']))
  await pending
  assert.equal(store.avatarUrl, '')
  assert.equal(created.length, 0)
})

test('a pending download cannot overwrite a newly uploaded profile avatar', async () => {
  let complete
  let reads = 0
  const newImage = new Blob(['new'])
  const { store, created } = await authStore({ read: () => {
    reads += 1
    return reads === 1 ? new Promise((resolve) => { complete = resolve }) : Promise.resolve(newImage)
  } })
  store.user = profile
  const pending = store.loadAvatar()
  store.user = { ...profile }
  await store.loadAvatar()
  complete(new Blob(['old']))
  await pending
  assert.deepEqual(created, [newImage])
})

test('an avatar image failure does not reject profile loading or change authentication', async () => {
  const { store } = await authStore({ read: async () => { throw new Error('Missing image') } }, { me: async () => profile })
  await store.fetchMe()
  await setImmediate()
  assert.equal(store.user, profile)
  assert.equal(store.token, 'mock-access-token')
  assert.equal(store.avatarUrl, '')
})

test('upload refreshes the displayed avatar, and reset clears it after API success', async () => {
  const file = new Blob(['original'])
  const calls = []
  const { store, revoked } = await authStore({
    upload: async (received) => { calls.push(received); return profile },
    read: async () => new Blob(['normalized']),
    remove: async () => ({ ...profile, avatar_url: null }),
  })
  await store.uploadAvatar(file)
  assert.deepEqual(calls, [file])
  assert.equal(store.avatarUrl, 'blob:avatar-1')
  await store.removeAvatar()
  assert.equal(store.user.avatar_url, null)
  assert.equal(store.avatarUrl, '')
  assert.deepEqual(revoked, ['blob:avatar-1'])
})

test('failed avatar reset preserves the existing image', async () => {
  const error = new Error('Mock reset failure')
  const { store, revoked } = await authStore({ remove: async () => { throw error } })
  store.user = profile
  store.avatarUrl = 'blob:existing'
  await assert.rejects(store.removeAvatar(), (caught) => caught === error)
  assert.equal(store.avatarUrl, 'blob:existing')
  assert.equal(store.user, profile)
  assert.deepEqual(revoked, [])
})

for (const action of ['uploadAvatar', 'removeAvatar']) {
  test(`${action}: a pending request cannot restore a logged-out profile`, async () => {
    let complete
    const pendingResponse = () => new Promise((resolve) => { complete = resolve })
    const { store, created } = await authStore({ upload: pendingResponse, remove: pendingResponse })
    store.user = profile
    const pending = store[action](new Blob(['file']))
    store.logout()
    complete(profile)
    await pending
    assert.equal(store.user, null)
    assert.equal(store.avatarUrl, '')
    assert.deepEqual(created, [])
  })
}
