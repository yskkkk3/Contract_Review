<template>
  <el-row :gutter="16">
    <el-col :span="24">
      <el-card shadow="hover">
        <template #header>
          <div class="head">
            <span>合同比对</span>
            <el-button type="primary" :loading="running" @click="compare">开始比对</el-button>
          </div>
        </template>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-select v-model="fileA" placeholder="选择基准合同" style="width: 100%" filterable>
              <el-option v-for="f in files" :key="f.id" :label="f.title" :value="f.id" />
            </el-select>
          </el-col>
          <el-col :span="12">
            <el-select v-model="fileB" placeholder="选择对比合同" style="width: 100%" filterable>
              <el-option v-for="f in files" :key="f.id" :label="f.title" :value="f.id" />
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
          <el-table-column label="基准合同">
            <template #default="{ row }">
              <div class="cell">{{ row.base }}</div>
            </template>
          </el-table-column>
          <el-table-column label="对比合同">
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
        <el-empty v-else-if="!running" description="选择两份合同后开始比对" />
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/contract'
import type { ComparisonResult, ContractFile } from '@/types/api'

interface Diff {
  field: string
  base: string
  target: string
  operation: string
}

const files = ref<ContractFile[]>([])
const fileA = ref<number>()
const fileB = ref<number>()
const diffs = ref<Diff[]>([])
const running = ref(false)
const summary = ref<ComparisonResult['diff_summary'] | null>(null)

onMounted(async () => {
  const data = await api.list()
  files.value = data.filter((file) => file.file_type === 'docx')
})

async function compare() {
  if (!fileA.value || !fileB.value) return ElMessage.warning('请选择两份合同')
  if (fileA.value === fileB.value) return ElMessage.warning('请选择不同的合同')
  diffs.value = []
  summary.value = null
  running.value = true
  try {
    const result = await api.compare(fileA.value, fileB.value, `比对-${Date.now()}`)
    summary.value = result.diff_summary
    diffs.value = result.diffs
      .filter((item) => item.operation !== 'equal')
      .map((item, index) => ({
        field: `第 ${index + 1} 处`,
        base: item.standard_text,
        target: item.comparison_text,
        operation: item.operation,
      }))
  } finally {
    running.value = false
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
.cell { white-space: pre-wrap; line-height: 1.6; }
.diff { color: #c4561d; }
</style>
