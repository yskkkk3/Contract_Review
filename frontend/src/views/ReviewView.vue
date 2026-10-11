<template>
  <el-row :gutter="16">
    <el-col :span="8">
      <el-card shadow="hover">
        <template #header>选择合同并发起审阅</template>
        <el-select v-model="fileId" placeholder="选择已解析合同" style="width: 100%" @change="onFileChange">
          <el-option v-for="f in files" :key="f.file_id" :label="`${f.title} (${f.contract_type || '未分类'})`" :value="f.file_id" />
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
            <el-tag v-if="summary" :type="riskTag(summary.overall_risk)">整体风险：{{ summary.overall_risk }}</el-tag>
          </div>
        </template>
        <el-empty v-if="!riskPoints.length && !running" description="发起审阅后，风险点将实时展示在这里" />
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
                <el-button size="small" :type="acceptedMap[p.id] ? 'success' : 'default'" @click="accept(p)">
                  {{ acceptedMap[p.id] ? '已采纳' : '采纳' }}
                </el-button>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-alert v-if="summary" :title="`摘要：${summary.summary}`" type="success" :closable="false" style="margin-top: 16px" />
        <el-alert v-if="summary && summary.suggestion" :title="`建议：${summary.suggestion}`" type="info" :closable="false" style="margin-top: 8px" />
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
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
  const data = await api.list(1, 100)
  files.value = data.items.filter((f) => f.parse_status === 'parsed')
  types.value = await adminApi.contractTypes()
})

async function onFileChange() {
  contractType.value = ''
}

async function startReview() {
  if (!fileId.value) return ElMessage.warning('请先选择合同')
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
    onEvent: (payload) => {
      const ev = payload as { event: string; data: unknown } & { type?: string }
      if (ev.event === 'message') {
        riskPoints.value.push(ev.data as RiskPoint)
      } else if (ev.event === 'end') {
        summary.value = ev.data as ReviewSummary
        running.value = false
      } else if (ev.event === 'error') {
        ElMessage.error((ev.data as { message: string }).message)
        running.value = false
      }
    },
  })
}

function accept(p: RiskPoint) {
  acceptedMap.value[p.id] = !acceptedMap.value[p.id]
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
