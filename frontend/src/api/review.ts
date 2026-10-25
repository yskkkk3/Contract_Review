import { get, post } from './http'
import type { PageResponse, ReviewHistoryDetail, ReviewHistoryItem, ReviewJob } from '@/types/api'

export interface ReviewHistoryParams {
  title?: string
  status?: ReviewHistoryItem['status']
  file_id?: number
  page?: number
  page_size?: number
}

export const reviewApi = {
  list: () => get<ReviewJob[]>('/reviews/jobs', { silent: true }),
  history: (params: ReviewHistoryParams) => get<PageResponse<ReviewHistoryItem>>('/reviews/history', { params }),
  historyDetail: (id: string) => get<ReviewHistoryDetail>(`/reviews/history/${encodeURIComponent(id)}`),
  start: (body: {
    session_id: number
    stance: string
    intensity: string
    description: string
    contract_type: string
  }) => post<ReviewJob>('/reviews/jobs', body),
  cancel: (id: string) => post<ReviewJob>(`/reviews/jobs/${id}/cancel`),
}
