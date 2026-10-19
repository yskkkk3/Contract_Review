<template>
  <el-row :gutter="16">
    <el-col :span="8">
      <el-card shadow="hover">
        <template #header>选择合同并发起审阅</template>
        <el-select v-model="fileId" placeholder="选择已解析合同" style="width: 100%" @change="onFileChange">
          <el-option v-for="f in files" :key="f.id" :label="contractLabel(f)" :value="f.id" />
        </el-select>
        <el-divider />
        <el-form label-width="90px">
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
          <el-button type="primary" style="width: 100%" :loading="running" @click="startReview">开始审阅</el-button>
        </el-form>
      </el-card>
    </el-col>
    <el-col :span="16">
      <el-card shadow="hover">
        <template #header>
          <div class="head">
            <span>审阅结果（SSE 实时流）</span>
            <el-tag v-if="summary?.review_status === 'incomplete'" type="warning">审阅待补查</el-tag>
            <el-tag v-else-if="summary" :type="riskTag(summary.overall_risk)">整体风险：{{ summary.overall_risk }}</el-tag>
          </div>
        </template>
        <el-empty v-if="!riskPoints.length && !running" :description="summary ? (summary.review_status === 'incomplete' ? '部分依据或意见未完成核验，暂不能判断合同风险' : '当前材料与审阅范围内未发现风险点') : '发起审阅后，风险点将实时展示在这里'" />
        <el-timeline v-if="riskPoints.length">
          <el-timeline-item
            v-for="p in riskPoints"
            :key="p.id"
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
                  :type="p.id && acceptedMap[p.id] ? 'success' : 'default'"
                  @click="accept(p)"
                >
                  {{ p.id && acceptedMap[p.id] ? '已采纳' : '采纳' }}
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
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/contract'
import { adminApi } from '@/api/dashboard'
import { TOKEN_KEY } from '@/api/http'
import { openSse } from '@/utils/sse'
import type { ContractFile, ContractType, ReviewSummary, RiskPoint } from '@/types/api'

const files = ref<ContractFile[]>([])
const types = ref<ContractType[]>([])
const fileId = ref<number>()
const contractType = ref('')
const stance = ref<'甲方' | '乙方'>('甲方')
const intensity = ref<'严格' | '标准' | '宽松'>('标准')
const description = ref('')
const running = ref(false)
const riskPoints = ref<RiskPoint[]>([])
const summary = ref<ReviewSummary | null>(null)
const acceptedMap = ref<Record<number, boolean>>({})
const abortRef = ref<(() => void) | null>(null)

onMounted(async () => {
  const [contracts, contractTypes] = await Promise.all([api.list(), adminApi.contractTypes()])
  files.value = contracts.filter((f) => f.parse_status === 'parsed')
  types.value = contractTypes.filter((type) => Boolean(type.is_active))
})

onUnmounted(() => abortRef.value?.())

function onFileChange() {
  const file = files.value.find((item) => item.id === fileId.value)
  contractType.value = types.value.find((type) => type.id === file?.contract_type_id)?.name || ''
}

async function startReview() {
  if (!fileId.value) return ElMessage.warning('请先选择合同')
  abortRef.value?.()
  const session = await api.createSession(`审阅-${Date.now()}`, 'review', fileId.value)
  riskPoints.value = []
  summary.value = null
  acceptedMap.value = {}
  running.value = true

  const url = `${import.meta.env.VITE_API_BASE || '/api'}/reviews/start`
  const token = localStorage.getItem(TOKEN_KEY) || ''
  abortRef.value = openSse({
    url,
    kind: 'review',
    token,
    body: {
      session_id: session.session_id,
      stance: stance.value,
      intensity: intensity.value,
      description: description.value || null,
      contract_type: contractType.value,
    },
    onEvent: (payload) => {
      const ev = payload as { event: string; data: unknown } & { type?: string }
      if (ev.event === 'message') {
        upsertRiskPoint(ev.data as RiskPoint)
      } else if (ev.event === 'end') {
        riskPoints.value = riskPoints.value.filter((point) => Boolean(point.id))
        summary.value = ev.data as ReviewSummary
        running.value = false
      } else if (ev.event === 'error') {
        ElMessage.error((ev.data as { message: string }).message)
        running.value = false
      }
    },
  })
}

async function accept(p: RiskPoint) {
  if (!p.id || !p.task_id || !p.session_id) return
  const accepted = !acceptedMap.value[p.id]
  await api.acceptRiskPoint(p.task_id, p.session_id, p.index, accepted)
  acceptedMap.value[p.id] = accepted
}

function upsertRiskPoint(point: RiskPoint) {
  if (point.id) {
    const persistedIndex = riskPoints.value.findIndex((item) => item.id === point.id)
    if (persistedIndex >= 0) {
      riskPoints.value[persistedIndex] = point
      return
    }
  }
  const streamedIndex = riskPoints.value.findIndex(
    (item) =>
      !item.id &&
      item.original_content === point.original_content &&
      item.risk_dim === point.risk_dim &&
      item.risk_analysis === point.risk_analysis,
  )
  if (streamedIndex >= 0 && point.id) riskPoints.value[streamedIndex] = point
  else if (streamedIndex < 0) riskPoints.value.push(point)
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
.point { line-height: 1.6; }
.orig { color: #333; }
.analysis { color: #c4561d; margin-top: 4px; }
.suggest { color: #1d7a3f; margin-top: 4px; }
.actions { margin-top: 8px; display: flex; gap: 8px; align-items: center; }
</style>
