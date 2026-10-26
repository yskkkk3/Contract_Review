import type { ContractFile } from '@/types/api'

export function comparisonUnavailableReason(file: Pick<ContractFile, 'file_type' | 'parse_status'>) {
  const kind = file.file_type.trim().toLowerCase().replace(/^\.+/, '')
  if (kind === 'docx') return ''
  if (!['pdf', 'doc'].includes(kind)) return '暂不支持此格式'
  if (file.parse_status === 'parsed') return ''
  if (file.parse_status === 'pending') return '正在解析，稍后刷新'
  if (file.parse_status === 'failed') return '解析失败，请重新上传'
  return '尚未解析，请先到合同管理上传解析'
}
