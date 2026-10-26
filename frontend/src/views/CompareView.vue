<template>
  <el-row :gutter="16">
    <el-col :span="24">
      <el-card shadow="hover">
        <template #header>
          <div class="head">
            <span>合同比对</span>
            <div class="toolbar">
              <el-button :loading="loadingFiles" :disabled="running" @click="loadFiles">刷新合同</el-button>
              <el-button type="primary" :loading="running" :disabled="loadingFiles" @click="compare">开始比对</el-button>
            </div>
          </div>
        </template>
        <el-alert title="支持 DOCX 以及已解析的 PDF、DOC，按合同正文进行比对。" type="info" :closable="false" style="margin-bottom: 16px" />
        <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" style="margin-bottom: 16px" />
        <el-row :gutter="16">
          <el-col :span="12">
            <el-select v-model="fileA" placeholder="选择基准合同" style="width: 100%" filterable clearable :disabled="running" :loading="loadingFiles" @visible-change="onDropdownVisible" @change="clearResult">
              <el-option v-for="f in files" :key="f.id" :label="f.title" :value="f.id" :disabled="!!comparisonUnavailableReason(f) || f.id === fileB">
                <span>{{ f.title }}</span><span class="option-reason">{{ comparisonUnavailableReason(f) || (f.id === fileB ? '已选为对比合同' : f.file_type.toUpperCase()) }}</span>
              </el-option>
              <template #empty><div class="select-empty">暂无合同，请先到合同管理上传</div></template>
            </el-select>
          </el-col>
          <el-col :span="12">
            <el-select v-model="fileB" placeholder="选择对比合同" style="width: 100%" filterable clearable :disabled="running" :loading="loadingFiles" @visible-change="onDropdownVisible" @change="clearResult">
              <el-option v-for="f in files" :key="f.id" :label="f.title" :value="f.id" :disabled="!!comparisonUnavailableReason(f) || f.id === fileA">
                <span>{{ f.title }}</span><span class="option-reason">{{ comparisonUnavailableReason(f) || (f.id === fileA ? '已选为基准合同' : f.file_type.toUpperCase()) }}</span>
              </el-option>
              <template #empty><div class="select-empty">暂无合同，请先到合同管理上传</div></template>
            </el-select>
          </el-col>
        </el-row>
        <el-divider />
        <el-alert
          v-if="summary"
          :title="`共发现 ${summary.difference_count} 处段落差异`"
          type="info"
          :closable="false"
          style="margin-bottom: 16px"
        />
        <el-table v-if="diffs.length" :data="diffs" border>
          <el-table-column prop="field" label="比对项" width="160" />
          <el-table-column :label="resultNames ? `基准：${resultNames.base}` : '基准合同'">
            <template #default="{ row }">
              <div class="cell">{{ row.base }}</div>
            </template>
          </el-table-column>
          <el-table-column :label="resultNames ? `对比：${resultNames.target}` : '对比合同'">
            <template #default="{ row }">
              <div class="cell diff">{{ row.target }}</div>
            </template>
          </el-table-column>
          <el-table-column label="差异类型" width="120">
            <template #default="{ row }">
              <el-tag :type="operationTag(row.operation)">
                {{ operationText(row.operation) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else-if="!running" :description="summary ? '两份合同正文未发现差异' : '选择两份合同后开始比对'" />
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/contract'
import { useAuthStore } from '@/stores/auth'
import { comparisonUnavailableReason } from '@/utils/comparison'
import type { ComparisonResult, ContractFile } from '@/types/api'

interface Diff {
  field: string
  base: string
  target: string
  operation: string
}

const files = ref<ContractFile[]>([])
const auth = useAuthStore()
const loadingFiles = ref(false)
const loadError = ref('')
const resultNames = ref<{ base: string; target: string } | null>(null)
const fileA = ref<number>()
const fileB = ref<number>()
const diffs = ref<Diff[]>([])
const running = ref(false)
const summary = ref<ComparisonResult['diff_summary'] | null>(null)
let sequence = 0
let generation = 0
let disposed = false
let lastLoadedAt = 0

onMounted(loadFiles)
onUnmounted(() => { disposed = true; ++sequence; ++generation })
watch(() => auth.user?.id, () => {
  ++generation
  ++sequence
  files.value = []
  fileA.value = undefined
  fileB.value = undefined
  loadingFiles.value = false
  loadError.value = ''
  lastLoadedAt = 0
  running.value = false
  clearResult()
  if (auth.user) void loadFiles()
}, { flush: 'sync' })

async function loadFiles() {
  const current = ++sequence
  loadingFiles.value = true
  loadError.value = ''
  try {
    const data = await api.list()
    if (disposed || current !== sequence) return
    files.value = data
    lastLoadedAt = Date.now()
    if (fileA.value && !data.some((file) => file.id === fileA.value && !comparisonUnavailableReason(file))) {
      fileA.value = undefined
      clearResult()
    }
    if (fileB.value && !data.some((file) => file.id === fileB.value && !comparisonUnavailableReason(file))) {
      fileB.value = undefined
      clearResult()
    }
  } catch {
    if (!disposed && current === sequence) loadError.value = '加载合同列表失败，请点击刷新合同重试'
  } finally {
    if (!disposed && current === sequence) loadingFiles.value = false
  }
}

function onDropdownVisible(visible: boolean) {
  if (visible && !loadingFiles.value && Date.now() - lastLoadedAt > 5000) void loadFiles()
}

function clearResult() {
  diffs.value = []
  summary.value = null
  resultNames.value = null
}

async function compare() {
  if (running.value || loadingFiles.value) return
  if (!fileA.value || !fileB.value) return ElMessage.warning('请选择两份合同')
  if (fileA.value === fileB.value) return ElMessage.warning('请选择不同的合同')
  const selected = [fileA.value, fileB.value].map((id) => files.value.find((file) => file.id === id))
  if (selected.some((file) => !file || comparisonUnavailableReason(file))) return ElMessage.warning('请选择可比对的合同，PDF 和 DOC 需先完成解析')
  const current = ++generation
  clearResult()
  running.value = true
  try {
    const result = await api.compare(fileA.value, fileB.value, `比对-${Date.now()}`)
    if (disposed || current !== generation) return
    summary.value = result.diff_summary
    resultNames.value = { base: result.standard_file.title, target: result.comparison_file.title }
    diffs.value = result.diffs
      .filter((item) => item.operation !== 'equal')
      .map((item, index) => ({
        field: `第 ${index + 1} 处`,
        base: item.standard_text,
        target: item.comparison_text,
        operation: item.operation,
      }))
  } finally {
    if (!disposed && current === generation) running.value = false
  }
}

function operationText(operation: string) {
  return { replace: '修改', insert: '新增', delete: '删除' }[operation] || operation
}

function operationTag(operation: string) {
  return { replace: 'warning', insert: 'success', delete: 'danger' }[operation] || 'info'
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; }
.toolbar { display: flex; gap: 8px; }
.option-reason { margin-left: 16px; color: var(--el-text-color-secondary); font-size: 12px; }
.select-empty { padding: 12px; text-align: center; color: var(--el-text-color-secondary); }
.cell { white-space: pre-wrap; line-height: 1.6; }
.diff { color: #c4561d; }
</style>
