import { del, get, post } from './http'
import type { ComparisonResult, ContractFile, PageResponse, SessionInfo } from '@/types/api'

export interface ContractSearchParams {
  title?: string
  party?: string
  contract_type_id?: number
  parse_status?: string
  amount_min?: number
  amount_max?: number
  created_from?: string
  created_to?: string
  page?: number
  page_size?: number
}

export const api = {
  upload(file: File) {
    const form = new FormData()
    form.append('file', file)
    return post<{ file_id: number }>('/contracts/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  list() {
    return get<ContractFile[]>('/contracts')
  },
  search(params: ContractSearchParams) {
    return get<PageResponse<ContractFile>>('/contracts/search', { params })
  },
  remove(fileId: number) {
    return del<null>(`/contracts/${fileId}`)
  },
  setType(fileId: number, contractTypeId: number, reviewPosition: 0 | 1) {
    return post<null>(`/contracts/${fileId}/type`, {
      contract_type_id: contractTypeId,
      review_position: reviewPosition,
    })
  },
  accept(fileId: number, isAccepted: boolean) {
    return post<boolean>('/reviews/contracts/accept', { file_id: fileId, is_accepted: isAccepted })
  },
  acceptRiskPoint(taskId: number, sessionId: number, index: number, isAccepted: boolean) {
    return post<boolean>('/reviews/risk-points/accept', {
      task_id: taskId,
      session_id: sessionId,
      index,
      is_accepted: isAccepted ? 1 : 0,
    })
  },
  createSession(title: string, sessionType: 'review' | 'compare' | 'chat', fileId?: number) {
    return post<SessionInfo>('/sessions', {
      title,
      session_type: sessionType,
      file_id: fileId,
    })
  },
  compare(standardFileId: number, comparisonFileId: number, title?: string) {
    return post<ComparisonResult>('/comparisons', {
      standard_file_id: standardFileId,
      comparison_file_id: comparisonFileId,
      title,
    })
  },
}
