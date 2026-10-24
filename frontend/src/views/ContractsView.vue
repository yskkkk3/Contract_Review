<template>
  <el-card shadow="hover">
    <template #header>
      <div class="head">
        <span>合同文件</span>
        <el-upload :show-file-list="false" :auto-upload="false" :on-change="onFileChange" accept=".pdf,.docx,.doc">
          <el-button type="primary">上传合同</el-button>
        </el-upload>
      </div>
    </template>
    <el-table :data="files" v-loading="loading">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="文件名" min-width="220" show-overflow-tooltip />
      <el-table-column label="类型" width="170">
        <template #default="{ row }">
          <el-select
            :model-value="row.contract_type_id || undefined"
            placeholder="选择类型"
            size="small"
            :loading="typeUpdating === row.id"
            @change="onTypeChange(row, $event)"
          >
            <el-option
              v-for="type in activeTypes"
              :key="type.id"
              :label="type.name"
              :value="type.id"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="party_a" label="甲方" width="140" show-overflow-tooltip />
      <el-table-column prop="party_b" label="乙方" width="140" show-overflow-tooltip />
      <el-table-column label="金额" width="110">
        <template #default="{ row }">{{ row.amount ? '¥' + row.amount.toLocaleString() : '-' }}</template>
      </el-table-column>
      <el-table-column label="解析状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.parse_status === 'parsed' ? 'success' : row.parse_status === 'pending' ? 'warning' : 'info'">
            {{ statusText(row.parse_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      class="pager"
      layout="prev, pager, next, total"
      :total="total"
      :page-size="pageSize"
      v-model:current-page="page"
      @current-change="load"
    />
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import { api } from '@/api/contract'
import { adminApi } from '@/api/dashboard'
import type { ContractFile, ContractType } from '@/types/api'

const files = ref<ContractFile[]>([])
const types = ref<ContractType[]>([])
const loading = ref(false)
const typeUpdating = ref<number>()
const page = ref(1)
const pageSize = 10
const total = ref(0)
const activeTypes = computed(() => types.value.filter((type) => Boolean(type.is_active)))

onMounted(load)

async function load() {
  loading.value = true
  try {
    const [data, contractTypes] = await Promise.all([api.list(), adminApi.contractTypes()])
    types.value = contractTypes
    total.value = data.length
    const maxPage = Math.max(1, Math.ceil(total.value / pageSize))
    if (page.value > maxPage) page.value = maxPage
    const start = (page.value - 1) * pageSize
    files.value = data.slice(start, start + pageSize)
  } finally {
    loading.value = false
  }
}

async function onFileChange(uploadFile: UploadFile) {
  if (!uploadFile.raw) return
  loading.value = true
  try {
    await api.upload(uploadFile.raw)
    ElMessage.success('上传成功，正在解析')
    page.value = 1
    await load()
  } finally {
    loading.value = false
  }
}

async function onDelete(row: ContractFile) {
  try {
    await ElMessageBox.confirm(`确定删除合同“${row.title}”吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  await api.remove(row.id)
  ElMessage.success('已删除')
  await load()
}

async function onTypeChange(row: ContractFile, typeId: number) {
  if (row.contract_type_id === typeId) return
  typeUpdating.value = row.id
  try {
    await api.setType(row.id, typeId, row.review_position === 1 ? 1 : 0)
    row.contract_type_id = typeId
    ElMessage.success(`已设置为${typeText(typeId)}`)
  } finally {
    typeUpdating.value = undefined
  }
}

function statusText(status: string) {
  return { parsed: '已解析', pending: '解析中', failed: '失败' }[status] || status
}

function typeText(typeId: number | null) {
  if (!typeId) return '未分类'
  return types.value.find((type) => type.id === typeId)?.name || `类型 #${typeId}`
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; }
.pager { margin-top: 16px; justify-content: flex-end; }
</style>
