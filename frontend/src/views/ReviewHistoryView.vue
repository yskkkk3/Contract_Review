<template>
  <el-card shadow="hover">
    <template #header>
      <div class="history-heading">
        <span>合同审阅历史</span>
        <el-button type="primary" @click="router.push({ name: 'review' })">发起审阅</el-button>
      </div>
    </template>
    <el-alert v-if="fileId" title="当前仅展示所选合同的审阅记录" type="info" :closable="false" class="history-notice">
      <el-button link type="primary" @click="router.push({ name: 'review-history' })">查看全部合同</el-button>
    </el-alert>
    <el-form inline @submit.prevent="search">
      <el-form-item label="合同名称">
        <el-input v-model="filters.title" clearable placeholder="输入合同文件名" @keyup.enter="search" />
      </el-form-item>
      <el-form-item label="审阅状态">
        <el-select v-model="filters.status" clearable placeholder="全部状态" style="width: 140px">
          <el-option v-for="status in statuses" :key="status" :label="reviewStatusLabel(status)" :value="status" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </el-form-item>
    </el-form>
    <el-alert v-if="listError" :title="listError" type="error" :closable="false" class="history-notice" />
    <el-table v-loading="loading" :data="items" empty-text="暂无符合条件的审阅记录">
      <el-table-column prop="title" label="合同名称" min-width="200" show-overflow-tooltip />
      <el-table-column label="发起时间" min-width="175">
        <template #default="{ row }">{{ formatReviewTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><el-tag :type="reviewStatusType(row.status)">{{ reviewStatusLabel(row.status) }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="stance" label="立场" width="75" />
      <el-table-column prop="intensity" label="尺度" width="75" />
      <el-table-column label="风险点" width="90">
        <template #default="{ row }">{{ row.risk_point_count ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="整体风险" width="100">
        <template #default="{ row }">{{ reviewRiskLabel(row) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="165" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">查看详情</el-button>
          <el-button link :disabled="!row.can_repeat" @click="repeat(row.id)">再次审阅</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination v-model:current-page="page" v-model:page-size="pageSize" class="history-pager" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @current-change="load" @size-change="search" />
  </el-card>

  <el-drawer v-model="detailOpen" title="审阅记录详情" size="min(860px, 100vw)" @close="closeDetail">
    <div v-loading="detailLoading">
      <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" />
      <template v-if="detail">
        <h2>{{ detail.title }}</h2>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="审阅状态">{{ reviewStatusLabel(detail.status) }}</el-descriptions-item>
          <el-descriptions-item label="合同类型">{{ detail.contract_type || '未分类' }}</el-descriptions-item>
          <el-descriptions-item label="立场 / 尺度">{{ detail.stance }} / {{ detail.intensity }}</el-descriptions-item>
          <el-descriptions-item label="风险点">{{ detail.status === 'completed' ? detail.risk_points.length : '初步意见 ' + detail.risk_points.length + ' 条' }}</el-descriptions-item>
          <el-descriptions-item label="发起时间">{{ formatReviewTime(detail.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatReviewTime(detail.completed_at) }}</el-descriptions-item>
          <el-descriptions-item label="审阅说明" :span="2">{{ detail.description || '无' }}</el-descriptions-item>
        </el-descriptions>
        <div class="history-actions">
          <el-button @click="openDetail(detail.id)">刷新详情</el-button>
          <el-button v-if="!detail.id.startsWith('legacy-') && ['processing', 'cancelling'].includes(detail.status)" type="danger" plain :loading="stopping" :disabled="detail.status === 'cancelling'" @click="stopDetail">停止审阅</el-button>
          <el-button type="primary" :disabled="!detail.can_repeat" @click="repeat(detail.id)">按此配置再次审阅</el-button>
          <el-button v-if="detail.status === 'completed'" type="primary" plain :loading="creatingChat" @click="askAboutReview(detail.id)">审阅结果答疑</el-button>
        </div>
        <ReviewScopePanel :scope="detail.summary?.review_scope || detail.review_scope" />
        <MissingMaterialsPanel :materials="detail.summary?.review_scope?.missing_materials || []" />
        <el-alert v-if="detail.status !== 'completed'" title="本次审阅尚未形成完整结论，以下仅为已产生的初步意见。" type="warning" :closable="false" class="history-notice" />
        <el-alert v-if="detail.error || detail.notice" :title="detail.error || detail.notice" type="info" :closable="false" class="history-notice" />
        <template v-if="detail.summary">
          <el-alert :title="`摘要：${detail.summary.summary}`" :type="detail.summary.review_status === 'incomplete' ? 'warning' : 'success'" :closable="false" class="history-notice" />
          <el-alert v-if="detail.summary.suggestion" :title="`建议：${detail.summary.suggestion}`" type="info" :closable="false" class="history-notice" />
        </template>
        <el-empty v-if="!detail.risk_points.length" :description="emptyDescription" />
        <article v-for="(point, index) in detail.risk_points" :key="point.id || index" class="history-risk">
          <h3>第 {{ point.index }} 条 · {{ point.risk_dim || '风险意见' }} <el-tag :type="point.risk_level === '高' ? 'danger' : point.risk_level === '中' ? 'warning' : 'info'">{{ point.risk_level }}</el-tag></h3>
          <p><b>原条款：</b>{{ point.original_content }}</p>
          <p><b>风险分析：</b>{{ point.risk_analysis }}</p>
          <p><b>修改建议：</b>{{ point.suggested_content }}</p>
          <el-tag v-if="point.is_accepted" type="success">已采纳</el-tag>
        </article>
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { reviewApi } from '@/api/review'
import { useAuthStore } from '@/stores/auth'
import { useReviewStore } from '@/stores/review'
import ReviewScopePanel from '@/components/review/ReviewScopePanel.vue'
import MissingMaterialsPanel from '@/components/review/MissingMaterialsPanel.vue'
import { formatReviewTime, reviewRiskLabel, reviewStatusLabel, reviewStatusType } from '@/utils/review-history'
import type { ReviewHistoryDetail, ReviewHistoryItem } from '@/types/api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const review = useReviewStore()
const statuses: ReviewHistoryItem['status'][] = ['completed', 'processing', 'cancelling', 'cancelled', 'failed', 'pending']
const fileId = computed(() => {
  const value = Number(route.query.file_id)
  return Number.isSafeInteger(value) && value > 0 ? value : undefined
})
const filters = reactive({ title: '', status: undefined as ReviewHistoryItem['status'] | undefined })
const items = ref<ReviewHistoryItem[]>([])
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const loading = ref(false)
const listError = ref('')
const detail = ref<ReviewHistoryDetail | null>(null)
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const stopping = ref(false)
const creatingChat = ref(false)
let listSequence = 0
let detailSequence = 0
let disposed = false

const emptyDescription = computed(() => {
  if (detail.value?.status !== 'completed') return '本次尚未保存风险意见'
  if (!detail.value.summary) return '本次没有保存风险点，无法还原整体审阅结论'
  return detail.value.summary.review_status === 'incomplete' ? '依据核验未完成，暂不能判断合同风险' : '当前材料与审阅范围内未发现风险点'
})

async function load() {
  if (!auth.user || disposed) return
  const sequence = ++listSequence
  loading.value = true
  listError.value = ''
  try {
    const result = await reviewApi.history({
      title: filters.title.trim() || undefined, status: filters.status,
      file_id: fileId.value, page: page.value, page_size: pageSize.value,
    })
    if (disposed || sequence !== listSequence) return
    items.value = result.items
    total.value = result.total
  } catch {
    if (sequence === listSequence && !disposed) listError.value = '加载审阅历史失败，请重试'
  } finally {
    if (sequence === listSequence && !disposed) loading.value = false
  }
}

function search() { page.value = 1; void load() }
function reset() { filters.title = ''; filters.status = undefined; search() }

async function openDetail(id: string) {
  const sequence = ++detailSequence
  detailOpen.value = true
  detail.value = null
  detailLoading.value = true
  detailError.value = ''
  try {
    const result = await reviewApi.historyDetail(id)
    if (sequence === detailSequence && !disposed) detail.value = result
  } catch {
    if (sequence === detailSequence && !disposed) detailError.value = '加载详情失败，请刷新或重新选择记录'
  } finally {
    if (sequence === detailSequence && !disposed) detailLoading.value = false
  }
}

function closeDetail() { ++detailSequence; detail.value = null; detailLoading.value = false }
function repeat(id: string) { void router.push({ name: 'review', query: { repeat: id } }) }

async function askAboutReview(id: string) {
  if (creatingChat.value) return
  creatingChat.value = true
  try {
    const session = await reviewApi.createChat(id)
    await router.push({ name: 'chat', query: { session_id: String(session.session_id) } })
  } catch {
    ElMessage.error('创建审阅答疑会话失败，请重试')
  } finally {
    creatingChat.value = false
  }
}

async function stopDetail() {
  const id = detail.value?.id
  if (!id || stopping.value) return
  const owner = auth.user?.id
  const sequence = detailSequence
  stopping.value = true
  try {
    await reviewApi.cancel(id)
    if (disposed || owner !== auth.user?.id) return
    await Promise.all([load(), review.refresh()])
    if (sequence === detailSequence && detailOpen.value) await openDetail(id)
  } finally { if (!disposed && owner === auth.user?.id) stopping.value = false }
}

watch([() => auth.user?.id, fileId], () => {
  ++listSequence
  closeDetail()
  detailOpen.value = false
  items.value = []
  total.value = 0
  filters.title = ''
  filters.status = undefined
  page.value = 1
  loading.value = false
  listError.value = ''
  stopping.value = false
  void load()
}, { immediate: true, flush: 'sync' })
watch(() => review.jobs.map((job) => `${job.id}:${job.status}`).join('|'), () => {
  void load()
  const id = detail.value?.id
  if (id && detailOpen.value) void openDetail(id)
})
onUnmounted(() => { disposed = true; ++listSequence; ++detailSequence })
</script>

<style scoped>
.history-heading, .history-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.history-actions { justify-content: flex-start; margin: 16px 0; }
.history-notice { margin-bottom: 16px; }
.history-pager { margin-top: 20px; justify-content: flex-end; }
.history-risk { padding: 16px 0; border-top: 1px solid var(--el-border-color-light); line-height: 1.7; overflow-wrap: anywhere; }
.history-risk p { white-space: pre-wrap; }
</style>
