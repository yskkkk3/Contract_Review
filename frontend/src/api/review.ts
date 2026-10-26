import { get, post } from './http'
import type { PageResponse, ReviewHistoryDetail, ReviewHistoryItem, ReviewJob, SessionInfo } from '@/types/api'

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
  createChat: (id: string) => post<SessionInfo>(`/reviews/history/${encodeURIComponent(id)}/chat`),
  start: (body: {
    session_id: number
    stance: string
    intensity: string
    description: string
    contract_type: string
    supplement_file_ids?: number[]
  }) => post<ReviewJob>('/reviews/jobs', body),
  cancel: (id: string) => post<ReviewJob>(`/reviews/jobs/${id}/cancel`),
  materialDecision: (
    id: string,
    decision: 'deferred' | 'supplemented',
    supplementFileIds: number[] = [],
  ) => post<ReviewJob>(`/reviews/jobs/${id}/materials`, {
    decision,
    supplement_file_ids: supplementFileIds,
  }),
}
