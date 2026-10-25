<template>
  <el-row :gutter="16">
    <el-col :span="8">
      <el-card shadow="hover">
        <template #header><div class="head"><span>选择合同并发起审阅</span><el-button link type="primary" @click="router.push({ name: 'review-history' })">审阅历史</el-button></div></template>
        <el-alert v-if="historyLoading" title="正在载入历史审阅配置…" type="info" :closable="false" />
        <el-select v-model="fileId" :disabled="running || historyLoading" placeholder="选择已解析合同" style="width: 100%" @change="onFileChange">
          <el-option v-for="f in files" :key="f.id" :label="contractLabel(f)" :value="f.id" />
        </el-select>
        <el-divider />
        <el-form label-width="90px" :disabled="running || historyLoading">
          <el-form-item label="合同类型">
            <el-select v-model="contractType" placeholder="合同类型" style="width: 100%">
              <el-option v-for="t in types" :key="t.id" :label="t.name" :value="t.name" />
            </el-select>
          </el-form-item>
          <el-form-item label="审阅立场">
            <el-radio-group v-model="stance">
              <el-radio-button value="甲方">甲方</el-radio-button>
              <el-radio-button value="乙方">乙方</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="审查尺度">
            <el-radio-group v-model="intensity">
              <el-radio-button value="严格">严格</el-radio-button>
              <el-radio-button value="标准">标准</el-radio-button>
              <el-radio-button value="宽松">宽松</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="审阅说明">
            <el-input v-model="description" type="textarea" :rows="3" placeholder="补充审阅重点（可选）" />
          </el-form-item>
        </el-form>
        <el-button type="primary" style="width: 100%" :loading="running" :disabled="historyLoading" @click="startReview">{{ running ? '正在后台审阅' : '开始审阅' }}</el-button>
        <el-button v-if="submitting || (selected && ['processing', 'cancelling'].includes(selected.status))" type="danger" plain style="width: 100%; margin: 12px 0 0" :loading="stopping || cancelRequested || selected?.status === 'cancelling'" @click="stopReview">{{ submitting ? '取消发起' : '停止审阅' }}</el-button>
        <p class="background-hint">审阅在后台进行，可以切换页面或关闭浏览器，稍后回来查看结果。</p>
      </el-card>
    </el-col>
    <el-col :span="16">
      <el-card shadow="hover">
        <template #header>
          <div class="head">
            <span>审阅进度与结果</span>
            <el-tag v-if="summary?.review_status === 'incomplete'" type="warning">审阅待补查</el-tag>
            <el-tag v-else-if="summary" :type="riskTag(summary.overall_risk)">整体风险：{{ summary.overall_risk }}</el-tag>
          </div>
        </template>
        <el-select v-if="jobs.length" :model-value="selectedId" placeholder="选择审阅记录" style="width: 100%; margin-bottom: 16px" :disabled="submitting" @change="review.select">
          <el-option v-for="job in jobs" :key="job.id" :value="job.id" :label="`${job.title} · ${statusLabel(job.status)} · ${new Date(job.created_at).toLocaleString()}`" />
        </el-select>
        <el-button size="small" style="margin-bottom: 12px" @click="review.refresh">刷新审阅记录</el-button>
        <el-alert v-if="connectionError" :title="connectionError" type="warning" :closable="false" style="margin-bottom: 12px" />
        <el-alert v-if="selected" :title="statusText" :type="selected.status === 'failed' ? 'error' : selected.status === 'completed' ? 'success' : 'info'" :closable="false" style="margin-bottom: 16px" />
        <el-empty v-if="!riskPoints.length && !running" :description="summary ? (summary.review_status === 'incomplete' ? '部分依据或意见未完成核验，暂不能判断合同风险' : '当前材料与审阅范围内未发现风险点') : '发起审阅后，风险点将实时展示在这里'" />
        <el-timeline v-if="riskPoints.length">
          <el-timeline-item
            v-for="(p, pointIndex) in riskPoints"
            :key="p.id || `preview-${pointIndex}`"
            :type="levelType(p.risk_level)"
            :hollow="p.risk_level === '低'"
            :timestamp="`第 ${p.index} 条 · ${p.risk_dim}`"
          >
            <div class="point">
              <div class="orig"><b>原条款：</b>{{ p.original_content }}</div>
              <div class="analysis"><b>风险分析：</b>{{ p.risk_analysis }}</div>
              <div class="suggest"><b>修改建议：</b>{{ p.suggested_content }}</div>
              <div class="actions">
                <el-tag :type="levelType(p.risk_level)" size="small">{{ p.risk_level }}</el-tag>
                <el-button
                  size="small"
                  :disabled="running || !p.id"
                  :type="p.is_accepted ? 'success' : 'default'"
                  @click="accept(p)"
                >
                  {{ p.is_accepted ? '已采纳' : '采纳' }}
                </el-button>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-alert v-if="summary" :title="`摘要：${summary.summary}`" :type="summary.review_status === 'incomplete' ? 'warning' : 'success'" :closable="false" style="margin-top: 16px" />
        <el-alert v-if="summary && summary.suggestion" :title="`建议：${summary.suggestion}`" type="info" :closable="false" style="margin-top: 8px" />
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/api/contract'
import { adminApi } from '@/api/dashboard'
import { reviewApi } from '@/api/review'
import { useAuthStore } from '@/stores/auth'
import { useReviewStore } from '@/stores/review'
import type { ContractFile, ContractType, ReviewJob, RiskPoint } from '@/types/api'

const review = useReviewStore()
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const ready = ref(false)
const historyLoading = ref(false)
let historySequence = 0
let disposed = false
const { fileId, contractType, stance, intensity, description, running, stopping,
  selected, selectedId, jobs, submitting, cancelRequested, connectionError } = storeToRefs(review)
const files = ref<ContractFile[]>([])
const types = ref<ContractType[]>([])
const riskPoints = computed(() => selected.value?.risk_points || [])
const summary = computed(() => selected.value?.summary || null)
const statusText = computed(() => {
  const job = selected.value
  if (!job) return ''
  if (job.status === 'processing') return `正在后台审阅，共 ${job.chunk_count || '…'} 个条款，已发现 ${job.risk_points.length} 条初步意见。可以继续使用其他功能。`
  if (job.status === 'cancelling') return '正在停止审阅，稍后即可重新发起。'
  if (job.status === 'cancelled') return '已停止审阅。下方仅保留停止前的初步意见，不代表完整审阅结论。'
  if (job.status === 'failed') return job.error || '本次审阅未完成，可以重新发起。'
  if (job.status === 'pending') return '这次审阅尚未开始，可以重新发起。'
  return '审阅已完成，结果已保存。'
})

onMounted(async () => {
  void review.refresh()
  const [contracts, contractTypes] = await Promise.all([api.list(), adminApi.contractTypes()])
  files.value = contracts.filter((f) => f.parse_status === 'parsed')
  types.value = contractTypes.filter((type) => Boolean(type.is_active))
  ready.value = true
})

watch([() => auth.user?.id, () => route.query.repeat, ready], async ([owner, id, loaded]) => {
  const sequence = ++historySequence
  historyLoading.value = false
  if (!owner || typeof id !== 'string' || !loaded) return
  historyLoading.value = true
  try {
    const detail = await reviewApi.historyDetail(id)
    if (disposed || sequence !== historySequence || auth.user?.id !== owner) return
    if (!detail.can_repeat || !files.value.some((file) => file.id === detail.file_id)) {
      ElMessage.warning('该合同当前无法重新审阅，请先查看审阅状态和合同解析状态')
      return
    }
    review.prepareFromHistory(detail)
    if (!types.value.some((type) => type.name === contractType.value)) contractType.value = ''
    ElMessage.success('已带入上次审阅配置，确认或调整后点击开始审阅')
    await router.replace({ name: 'review', query: { ...route.query, repeat: undefined } })
  } catch {
    if (!disposed && sequence === historySequence) ElMessage.error('载入历史配置失败，请重新选择记录')
  } finally {
    if (!disposed && sequence === historySequence) historyLoading.value = false
  }
}, { immediate: true })
onUnmounted(() => { disposed = true; ++historySequence })

function onFileChange() {
  const file = files.value.find((item) => item.id === fileId.value)
  contractType.value = types.value.find((type) => type.id === file?.contract_type_id)?.name || ''
}

async function startReview() {
  if (!fileId.value) return ElMessage.warning('请先选择合同')
  try {
    await review.start(files.value, types.value)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '启动审阅失败，请重试')
  }
}

async function stopReview() {
  await review.stop()
}

async function accept(point: RiskPoint) {
  await review.accept(point)
}

function statusLabel(status: ReviewJob['status']) {
  return { pending: '待开始', processing: '审阅中', cancelling: '停止中', completed: '已完成', cancelled: '已停止', failed: '未完成' }[status]
}

function contractLabel(file: ContractFile) {
  const typeName = types.value.find((type) => type.id === file.contract_type_id)?.name || '未分类'
  return `${file.title} (${typeName})`
}

function levelType(level: string) {
  return { 高: 'danger', 中: 'warning', 低: 'info' }[level] || 'info'
}

function riskTag(risk: string) {
  return { 高: 'danger', 中: 'warning', 低: 'success' }[risk] || 'info'
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; }
.background-hint { color: #666; font-size: 13px; line-height: 1.6; }
.point { line-height: 1.6; }
.orig { color: #333; }
.analysis { color: #c4561d; margin-top: 4px; }
.suggest { color: #1d7a3f; margin-top: 4px; }
.actions { margin-top: 8px; display: flex; gap: 8px; align-items: center; }
</style>
