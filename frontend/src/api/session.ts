import { del, get, post } from './http'
import type { MessageInfo, PageResponse, SessionInfo } from '@/types/api'

export const sessionApi = {
  list(sessionType: 'review' | 'compare' | 'chat', page = 1, pageSize = 50) {
    return get<PageResponse<SessionInfo>>(`/sessions?session_type=${sessionType}&page=${page}&page_size=${pageSize}`)
  },
  create(title: string, sessionType: 'review' | 'compare' | 'chat', fileId?: number) {
    return post<SessionInfo>('/sessions', { title, session_type: sessionType, file_id: fileId })
  },
  remove(sessionId: number) {
    return del<null>(`/sessions/${sessionId}`)
  },
  history(sessionId: number) {
    return get<MessageInfo[]>(`/sessions/${sessionId}/history`)
  },
}
