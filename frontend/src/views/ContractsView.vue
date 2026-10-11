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
      <el-table-column prop="file_id" label="ID" width="70" />
      <el-table-column prop="title" label="文件名" min-width="220" show-overflow-tooltip />
      <el-table-column prop="contract_type" label="类型" width="120" />
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
import { onMounted, ref } from 'vue'
import { ElMessage, type UploadFile } from 'element-plus'
import { api } from '@/api/contract'
import type { ContractFile } from '@/types/api'

const files = ref<ContractFile[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 10
const total = ref(0)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const data = await api.list(page.value, pageSize)
    files.value = data.items
    total.value = data.total
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
    await load()
  } finally {
    loading.value = false
  }
}

async function onDelete(row: ContractFile) {
  await api.remove(row.file_id)
  ElMessage.success('已删除')
  await load()
}

function statusText(status: string) {
  return { parsed: '已解析', pending: '解析中', failed: '失败' }[status] || status
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; }
.pager { margin-top: 16px; justify-content: flex-end; }
</style>
