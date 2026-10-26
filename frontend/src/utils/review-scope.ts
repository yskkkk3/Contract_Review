import type { ReviewScope } from '@/types/api'

export function scopeRows(scope: ReviewScope) {
  return scope.checks.map((check) => {
    const record = scope.check_results?.find((item) => item.check_id === check.id)
    const status = record?.status
    const label = status === 'reviewed' ? '已核对'
      : status === 'not_applicable' ? '不适用'
        : status === 'needs_material' ? '待补材料'
          : status === 'unverified' ? '待核对' : '检查方向'
    return { ...check, status, label, reason: record?.reason || '' }
  })
}
