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

    <el-form class="query-form" label-position="top" @submit.prevent>
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12" :lg="6">
          <el-form-item label="文件名">
            <el-input
              v-model="filters.title"
              clearable
              placeholder="输入合同文件名"
              @keyup.enter="onSearch"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-form-item label="合同方">
            <el-input
              v-model="filters.party"
              clearable
              placeholder="搜索甲方或乙方"
              @keyup.enter="onSearch"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-form-item label="合同类型">
            <el-select v-model="filters.contractTypeId" clearable placeholder="全部类型">
              <el-option label="未分类" :value="0" />
              <el-option
                v-for="type in activeTypes"
                :key="type.id"
                :label="type.name"
                :value="type.id"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-form-item label="解析状态">
            <el-select v-model="filters.parseStatus" clearable placeholder="全部状态">
              <el-option label="已解析" value="parsed" />
              <el-option label="已上传" value="uploaded" />
              <el-option label="解析中" value="pending" />
              <el-option label="解析失败" value="failed" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="8">
          <el-form-item label="合同金额">
            <div class="amount-range">
              <el-input-number
                v-model="filters.amountMin"
                :min="0"
                :controls="false"
                placeholder="最低金额"
              />
              <span class="amount-separator">至</span>
              <el-input-number
                v-model="filters.amountMax"
                :min="0"
                :controls="false"
                placeholder="最高金额"
              />
            </div>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="10">
          <el-form-item label="上传时间">
            <el-date-picker
              v-model="createdRange"
              type="daterange"
              value-format="YYYY-MM-DD"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              range-separator="至"
              clearable
            />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :lg="6" class="query-actions">
          <el-button type="primary" @click="onSearch">查询</el-button>
          <el-button @click="onReset">重置</el-button>
        </el-col>
      </el-row>
    </el-form>

    <el-table :data="files" v-loading="loading" empty-text="没有符合条件的合同">
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
      <el-table-column prop="party_a" label="甲方" width="150" show-overflow-tooltip />
      <el-table-column prop="party_b" label="乙方" width="150" show-overflow-tooltip />
      <el-table-column label="金额" width="120">
        <template #default="{ row }">{{ row.amount ? '¥' + row.amount.toLocaleString() : '-' }}</template>
      </el-table-column>
      <el-table-column label="解析状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.parse_status === 'parsed' ? 'success' : row.parse_status === 'pending' ? 'warning' : 'info'">
            {{ statusText(row.parse_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上传时间" width="170">
        <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      class="pager"
      layout="total, sizes, prev, pager, next"
      :total="total"
      :page-sizes="[10, 20, 50, 100]"
      v-model:page-size="pageSize"
      v-model:current-page="page"
      @size-change="onPageSizeChange"
      @current-change="load"
    />
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type UploadFile } from 'element-plus'
import { api } from '@/api/contract'
import { adminApi } from '@/api/dashboard'
import type { ContractFile, ContractType } from '@/types/api'

const files = ref<ContractFile[]>([])
const types = ref<ContractType[]>([])
const loading = ref(false)
const typeUpdating = ref<number>()
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const createdRange = ref<[string, string] | null>(null)
const filters = reactive({
  title: '',
  party: '',
  contractTypeId: undefined as number | undefined,
  parseStatus: undefined as string | undefined,
  amountMin: undefined as number | undefined,
  amountMax: undefined as number | undefined,
})
const activeTypes = computed(() => types.value.filter((type) => Boolean(type.is_active)))

onMounted(async () => {
  await Promise.all([loadTypes(), load()])
})

async function loadTypes() {
  types.value = await adminApi.contractTypes()
}

async function load() {
  loading.value = true
  try {
    const data = await api.search({
      title: filters.title.trim() || undefined,
      party: filters.party.trim() || undefined,
      contract_type_id: filters.contractTypeId,
      parse_status: filters.parseStatus,
      amount_min: filters.amountMin,
      amount_max: filters.amountMax,
      created_from: createdRange.value?.[0],
      created_to: createdRange.value?.[1],
      page: page.value,
      page_size: pageSize.value,
    })
    const maxPage = Math.max(1, Math.ceil(data.total / pageSize.value))
    if (page.value > maxPage) {
      page.value = maxPage
      await load()
      return
    }
    files.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function onSearch() {
  if (
    filters.amountMin !== undefined
    && filters.amountMax !== undefined
    && filters.amountMin > filters.amountMax
  ) {
    ElMessage.warning('最低金额不能大于最高金额')
    return
  }
  page.value = 1
  await load()
}

async function onReset() {
  filters.title = ''
  filters.party = ''
  filters.contractTypeId = undefined
  filters.parseStatus = undefined
  filters.amountMin = undefined
  filters.amountMax = undefined
  createdRange.value = null
  page.value = 1
  await load()
}

async function onPageSizeChange() {
  page.value = 1
  await load()
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
    if (filters.contractTypeId !== undefined) await load()
  } finally {
    typeUpdating.value = undefined
  }
}

function statusText(status: string) {
  return {
    parsed: '已解析',
    uploaded: '已上传',
    pending: '解析中',
    failed: '失败',
  }[status] || status
}

function typeText(typeId: number | null) {
  if (!typeId) return '未分类'
  return types.value.find((type) => type.id === typeId)?.name || `类型 #${typeId}`
}

function formatDate(value: string | null) {
  return value ? value.replace('T', ' ').slice(0, 19) : '-'
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; }
.query-form { margin-bottom: 16px; padding: 16px 16px 0; background: #f7f8fa; border-radius: 6px; }
.query-form :deep(.el-select), .query-form :deep(.el-date-editor) { width: 100%; }
.amount-range { display: flex; align-items: center; gap: 8px; width: 100%; }
.amount-range :deep(.el-input-number) { width: 100%; }
.amount-separator { flex: none; color: var(--el-text-color-secondary); }
.query-actions { display: flex; align-items: center; padding-top: 30px; }
.pager { margin-top: 16px; justify-content: flex-end; }
</style>
