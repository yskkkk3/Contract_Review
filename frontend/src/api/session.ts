import { get, post } from './http'
import type { PageResponse, SessionInfo } from '@/types/api'

export const sessionApi = {
  list(sessionType: 'review' | 'compare' | 'chat', page = 1, pageSize = 50) {
    return get<PageResponse<SessionInfo>>(`/sessions?session_type=${sessionType}&page=${page}&page_size=${pageSize}`)
  },
  create(title: string, sessionType: 'review' | 'compare' | 'chat', fileId?: number, fileId2?: number) {
    return post<SessionInfo>('/sessions', { title, session_type: sessionType, file_id: fileId, file_id_2: fileId2 })
  },
  remove(sessionId: number) {
    return post<boolean>(`/sessions/${sessionId}/delete`)
  },
}
