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
              <el-option v-for="f in files" :key="f.file_id" :label="f.title" :value="f.file_id" />
            </el-select>
          </el-col>
          <el-col :span="12">
            <el-select v-model="fileB" placeholder="选择对比合同" style="width: 100%" filterable>
              <el-option v-for="f in files" :key="f.file_id" :label="f.title" :value="f.file_id" />
            </el-select>
          </el-col>
        </el-row>
        <el-divider />
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
              <el-tag :type="row.level === '高' ? 'danger' : row.level === '中' ? 'warning' : 'info'">
                {{ row.level }}
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
import { TOKEN_KEY } from '@/api/http'
import { openSse } from '@/utils/sse'
import type { ContractFile } from '@/types/api'

interface Diff {
  field: string
  base: string
  target: string
  level: string
}

const files = ref<ContractFile[]>([])
const fileA = ref<number>()
const fileB = ref<number>()
const diffs = ref<Diff[]>([])
const running = ref(false)

onMounted(async () => {
  const data = await api.list(1, 100)
  files.value = data.items.filter((f) => f.parse_status === 'parsed')
})

async function compare() {
  if (!fileA.value || !fileB.value) return ElMessage.warning('请选择两份合同')
  if (fileA.value === fileB.value) return ElMessage.warning('请选择不同的合同')
  const session = await api.createSession(`比对-${Date.now()}`, 'compare', fileA.value, fileB.value)
  diffs.value = []
  running.value = true
  const url = `${import.meta.env.VITE_API_BASE || '/api'}/comparisons/compare`
  openSse({
    url,
    kind: 'review',
    token: localStorage.getItem(TOKEN_KEY) || '',
    onEvent: (payload) => {
      const ev = payload as { event: string; data: unknown } & { type?: string }
      if (ev.event === 'message' || ev.type === 'content') {
        const data = ev.data as { diff_type: string; base: string; target: string; level: string }
        diffs.value.push({
          field: data.diff_type || '条款差异',
          base: data.base || '',
          target: data.target || '',
          level: data.level || '中',
        })
      } else if (ev.event === 'end' || ev.type === 'done') {
        running.value = false
      } else if (ev.event === 'error' || ev.type === 'error') {
        ElMessage.error((ev.data as { message?: string })?.message || '比对失败')
        running.value = false
      }
    },
  })
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; }
.cell { white-space: pre-wrap; line-height: 1.6; }
.diff { color: #c4561d; }
</style>
