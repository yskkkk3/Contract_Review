import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/utils/review-scope.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
const { scopeRows } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const checks = [{ id: 'common.identity', title: '主体', risk_dim: '主体资格与合规' },
  { id: 'technology.data', title: '数据处理', risk_dim: '知识产权与保密' }]

test('configured scope is displayed as directions, not completed verification', () => {
  const rows = scopeRows({ checks, checklist_status: 'configured' })
  assert.ok(rows.every((row) => row.label === '检查方向'))
  assert.ok(rows.every((row) => row.reason === ''))
})

test('specialty states display individually without labelling common directions verified', () => {
  for (const [status, label] of [['reviewed', '已核对'], ['not_applicable', '不适用'], ['needs_material', '待补材料'], ['unverified', '待核对']]) {
    const rows = scopeRows({ checks, check_results: [{ check_id: 'technology.data', status, reason: '具体核对记录' }] })
    assert.equal(rows[0].label, '检查方向')
    assert.equal(rows[1].label, label)
    assert.equal(rows[1].reason, '具体核对记录')
  }
})

test('read-only rendering preserves persisted scope and ignores unrelated records', () => {
  const scope = { checks, check_results: [{ check_id: 'lease.costs', status: 'reviewed', reason: 'other' }] }
  const before = JSON.stringify(scope)
  assert.ok(scopeRows(scope).every((row) => row.label === '检查方向'))
  assert.equal(JSON.stringify(scope), before)
})
