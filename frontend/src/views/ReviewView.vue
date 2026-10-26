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
            <div class="result-actions">
              <el-tag v-if="summary?.review_status === 'incomplete'" type="warning">审阅待补查</el-tag>
              <el-tag v-else-if="summary" :type="riskTag(summary.overall_risk)">整体风险：{{ summary.overall_risk }}</el-tag>
              <el-button
                v-if="selected?.status === 'completed'"
                type="primary"
                plain
                size="small"
                :loading="creatingChat"
                @click="askAboutReview"
              >针对审阅结果提问</el-button>
            </div>
          </div>
        </template>
        <el-select v-if="jobs.length" :model-value="selectedId" placeholder="选择审阅记录" style="width: 100%; margin-bottom: 16px" :disabled="submitting" @change="review.select">
          <el-option v-for="job in jobs" :key="job.id" :value="job.id" :label="`${job.title} · ${statusLabel(job.status)} · ${new Date(job.created_at).toLocaleString()}`" />
        </el-select>
        <el-button size="small" style="margin-bottom: 12px" @click="review.refresh">刷新审阅记录</el-button>
        <el-alert v-if="connectionError" :title="connectionError" type="warning" :closable="false" style="margin-bottom: 12px" />
        <el-alert v-if="selected" :title="statusText" :type="selected.status === 'failed' ? 'error' : selected.status === 'completed' ? 'success' : 'info'" :closable="false" style="margin-bottom: 16px" />
        <ReviewScopePanel :scope="summary?.review_scope || selected?.review_scope" />
        <MissingMaterialsPanel
          :materials="missingMaterials"
          :decision="selected?.material_decision"
          :show-actions="selected?.status === 'completed' && !running"
          @supplement="openSupplementDialog"
          @defer="deferMissingMaterials"
        />
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

  <el-dialog v-model="supplementDialog" title="补充相关材料并重新审阅" width="min(640px, 92vw)" :close-on-click-modal="!supplementing">
    <el-alert title="补充材料会与主合同一起送入新的审阅任务；原审阅记录不会被覆盖。" type="info" :closable="false" />
    <el-form label-position="top" style="margin-top: 16px">
      <el-form-item label="选择已解析文件">
        <el-select v-model="supplementSelection" multiple :multiple-limit="10" filterable placeholder="可选择已上传的磋商文件、响应文件或附件" style="width: 100%">
          <el-option v-for="file in availableSupplementFiles" :key="file.id" :label="file.title" :value="file.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="或上传新材料">
        <input type="file" multiple accept=".pdf,.doc,.docx" :disabled="supplementing" @change="onSupplementFiles" />
        <div v-if="pendingSupplementFiles.length" class="pending-files">
          待上传：{{ pendingSupplementFiles.map((file) => file.name).join('、') }}
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button :disabled="supplementing" @click="supplementDialog = false">取消</el-button>
      <el-button
        type="primary"
        :loading="supplementing"
        :disabled="!supplementSelection.length && !pendingSupplementFiles.length"
        @click="confirmSupplement"
      >上传并重新审阅</el-button>
    </template>
  </el-dialog>
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
import ReviewScopePanel from '@/components/review/ReviewScopePanel.vue'
import MissingMaterialsPanel from '@/components/review/MissingMaterialsPanel.vue'
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
  selected, selectedId, jobs, submitting, cancelRequested, connectionError, supplementFileIds } = storeToRefs(review)
const files = ref<ContractFile[]>([])
const types = ref<ContractType[]>([])
const supplementDialog = ref(false)
const supplementSelection = ref<number[]>([])
const pendingSupplementFiles = ref<File[]>([])
const supplementing = ref(false)
const creatingChat = ref(false)
const riskPoints = computed(() => selected.value?.risk_points || [])
const summary = computed(() => selected.value?.summary || null)
const missingMaterials = computed(() => summary.value?.review_scope?.missing_materials || [])
const availableSupplementFiles = computed(() => files.value.filter(
  (file) => file.parse_status === 'parsed' && file.id !== selected.value?.file_id,
))
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
  supplementFileIds.value = []
}

function openSupplementDialog() {
  supplementSelection.value = [...(selected.value?.supplement_file_ids || [])]
  pendingSupplementFiles.value = []
  supplementDialog.value = true
}

function onSupplementFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const available = Math.max(0, 10 - new Set(supplementSelection.value).size)
  const selectedFiles = Array.from(input.files || [])
  pendingSupplementFiles.value = selectedFiles.slice(0, available)
  if (selectedFiles.length > available) ElMessage.warning('每次最多选择 10 份补充材料')
}

async function deferMissingMaterials() {
  const job = selected.value
  if (!job) return
  try {
    await review.recordMaterialDecision(job.id, 'deferred')
    ElMessage.success('已记录暂不补充；材料缺口会继续保留在本次审阅结果中')
  } catch {
    ElMessage.error('记录选择失败，请重试')
  }
}

async function confirmSupplement() {
  const source = selected.value
  if (!source || supplementing.value) return
  if (new Set(supplementSelection.value).size + pendingSupplementFiles.value.length > 10) {
    return ElMessage.warning('每次最多选择 10 份补充材料')
  }
  supplementing.value = true
  try {
    const ids = new Set(supplementSelection.value)
    for (const file of pendingSupplementFiles.value) {
      const uploaded = await api.upload(file)
      ids.add(uploaded.file_id)
    }
    const selectedIds = [...ids].filter((id) => id !== source.file_id)
    if (!selectedIds.length) return ElMessage.warning('请至少选择或上传一份补充材料')
    files.value = (await api.list()).filter((file) => file.parse_status === 'parsed')
    fileId.value = source.file_id
    contractType.value = source.contract_type
    stance.value = source.stance
    intensity.value = source.intensity
    description.value = source.description
    supplementFileIds.value = selectedIds
    await review.start(files.value, types.value)
    try {
      await review.recordMaterialDecision(source.id, 'supplemented', selectedIds)
    } catch {
      ElMessage.warning('新审阅已开始，但原记录的补充状态保存失败，可稍后重试')
    }
    supplementDialog.value = false
    ElMessage.success('补充材料已加入，新的后台审阅任务已开始')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '补充材料并重新审阅失败，请重试')
  } finally {
    supplementing.value = false
  }
}

async function askAboutReview() {
  const job = selected.value
  if (!job || creatingChat.value) return
  creatingChat.value = true
  try {
    const session = await reviewApi.createChat(job.id)
    await router.push({ name: 'chat', query: { session_id: String(session.session_id) } })
  } catch {
    ElMessage.error('创建审阅答疑会话失败，请重试')
  } finally {
    creatingChat.value = false
  }
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
.result-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.background-hint { color: #666; font-size: 13px; line-height: 1.6; }
.point { line-height: 1.6; }
.orig { color: #333; }
.analysis { color: #c4561d; margin-top: 4px; }
.suggest { color: #1d7a3f; margin-top: 4px; }
.actions { margin-top: 8px; display: flex; gap: 8px; align-items: center; }
.pending-files { margin-top: 8px; color: var(--el-text-color-secondary); line-height: 1.5; }
</style>
