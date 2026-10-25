import type { ReviewHistoryItem } from '@/types/api'

export const reviewStatusLabel = (status: string) => ({
  pending: '待开始', processing: '审阅中', cancelling: '停止中',
  completed: '已完成', cancelled: '已停止', failed: '未完成',
}[status] || status)

export function reviewStatusType(status: string): 'info' | 'primary' | 'warning' | 'success' | 'danger' {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'cancelling') return 'warning'
  if (status === 'processing') return 'primary'
  return 'info'
}

export function reviewRiskLabel(item: Pick<ReviewHistoryItem, 'status' | 'review_status' | 'overall_risk'>) {
  if (item.status !== 'completed') return '—'
  if (item.review_status === 'incomplete') return '待补查'
  return item.overall_risk || '未保存'
}

export function formatReviewTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { hour12: false })
}
