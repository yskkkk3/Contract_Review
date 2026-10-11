<template>
  <div>
    <el-row :gutter="16" class="stat-row">
      <el-col v-for="card in statCards" :key="card.label" :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-body">
            <div class="stat-icon" :style="{ background: card.bg }">
              <el-icon :size="22" color="#fff"><component :is="card.icon" /></el-icon>
            </div>
            <div class="stat-text">
              <div class="stat-label">{{ card.label }}</div>
              <div class="stat-value">{{ card.value }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="16">
      <el-col :span="14">
        <el-card shadow="hover">
          <template #header>合同审阅趋势</template>
          <div v-if="!hasTrend" class="chart-empty"><el-empty description="暂无数据，完成审阅后展示趋势" :image-size="70" /></div>
          <div v-else ref="trendRef" class="chart" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="hover">
          <template #header>部门使用分布</template>
          <div v-if="!hasDepartments" class="chart-empty"><el-empty description="暂无部门使用数据" :image-size="70" /></div>
          <div v-else ref="departmentRef" class="chart" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Document, Finished, Warning, Calendar } from '@element-plus/icons-vue'

echarts.use([LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
import { dashboardApi } from '@/api/dashboard'
import type { DashboardOverview, DepartmentUsage, TrendPoint } from '@/types/api'

const overview = ref<DashboardOverview | null>(null)
const trendRef = ref<HTMLElement>()
const departmentRef = ref<HTMLElement>()
const hasTrend = ref(false)
const hasDepartments = ref(false)
let trendChart: ReturnType<typeof echarts.init> | null = null
let departmentChart: ReturnType<typeof echarts.init> | null = null

const statCards = computed(() => [
  { label: '已审阅合同', value: overview.value?.reviewed_contracts ?? 0, bg: 'linear-gradient(135deg,#3b82f6,#2563eb)', icon: Document },
  { label: '服务部门', value: overview.value?.service_departments ?? 0, bg: 'linear-gradient(135deg,#34d399,#059669)', icon: Finished },
  { label: '平台用户', value: overview.value?.users_count ?? 0, bg: 'linear-gradient(135deg,#fbbf24,#d97706)', icon: Warning },
  {
    label: '审阅合同金额',
    value: formatAmount(overview.value?.total_reviewed_amount ?? 0),
    bg: 'linear-gradient(135deg,#f87171,#dc2626)',
    icon: Calendar,
  },
])

onMounted(async () => {
  const [overviewData, trends, departments] = await Promise.all([
    dashboardApi.overview(),
    dashboardApi.trends('day'),
    dashboardApi.departments(),
  ])
  overview.value = overviewData
  if (trends.length) {
    hasTrend.value = true
    await nextTick()
    renderTrend(trends)
  }
  if (departments.length) {
    hasDepartments.value = true
    await nextTick()
    renderDepartments(departments)
  }
  window.addEventListener('resize', resizeCharts)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts)
  trendChart?.dispose()
  departmentChart?.dispose()
})

function renderTrend(trends: TrendPoint[]) {
  if (!trendRef.value) return
  trendChart = echarts.init(trendRef.value)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: trends.map((t) => t.date), axisLine: { lineStyle: { color: '#e2e8f0' } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#f1f5f9' } } },
    color: ['#2563eb'],
    series: [{ name: '审阅', type: 'line', smooth: true, areaStyle: { opacity: 0.12 }, data: trends.map((t) => t.total) }],
  })
}

function renderDepartments(departments: DepartmentUsage[]) {
  if (!departmentRef.value) return
  departmentChart = echarts.init(departmentRef.value)
  departmentChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, type: 'scroll' },
    color: ['#2563eb', '#7c3aed', '#0ea5e9', '#f59e0b', '#10b981', '#ef4444'],
    series: [
      {
        type: 'pie',
        radius: ['35%', '65%'],
        data: departments.map((department) => ({ name: department.department_name, value: department.total })),
        label: { formatter: '{b}: {c}' },
      },
    ],
  })
}

function resizeCharts() {
  trendChart?.resize()
  departmentChart?.resize()
}

function formatAmount(amount: number) {
  return `¥${amount.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`
}
</script>

<style scoped>
.stat-row {
  margin-bottom: 16px;
}

.stat-body {
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.15);
}

.stat-label {
  color: #64748b;
  font-size: 13px;
}

.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: #0f172a;
  margin-top: 2px;
}

.chart {
  height: 320px;
}

.chart-empty {
  height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
