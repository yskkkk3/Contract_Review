import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'

test('contract management exposes a persisted manual type selector', async () => {
  const source = await readFile(new URL('../src/views/ContractsView.vue', import.meta.url), 'utf8')
  assert.match(source, /@change="onTypeChange\(row, \$event\)"/)
  assert.match(source, /await api\.setType\(row\.id, typeId/)
  assert.match(source, /row\.contract_type_id = typeId/)
})

test('review persists the selected contract type before starting', async () => {
  const source = await readFile(new URL('../src/views/ReviewView.vue', import.meta.url), 'utf8')
  assert.match(source, /await api\.setType\(selectedFile\.id, selectedType\.id/)
  assert.match(source, /selectedFile\.contract_type_id = selectedType\.id/)
})
