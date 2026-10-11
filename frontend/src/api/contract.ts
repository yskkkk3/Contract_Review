import { get, post } from './http'
import type { ContractFile, SessionInfo, PageResponse } from '@/types/api'

export const api = {
  upload(file: File) {
    const form = new FormData()
    form.append('file', file)
    return post<{ file_id: number }>('/contracts/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  list(page = 1, pageSize = 10) {
    return get<PageResponse<ContractFile>>(`/contracts?page=${page}&page_size=${pageSize}`)
  },
  detail(fileId: number) {
    return get<ContractFile>(`/contracts/${fileId}`)
  },
  remove(fileId: number) {
    return post<boolean>(`/contracts/${fileId}/delete`)
  },
  setType(fileId: number, contractType: string) {
    return post<boolean>(`/contracts/${fileId}/type`, { contract_type: contractType })
  },
  accept(fileId: number, isAccepted: boolean) {
    return post<boolean>('/reviews/contracts/accept', { file_id: fileId, is_accepted: isAccepted })
  },
  createSession(title: string, sessionType: 'review' | 'compare' | 'chat', fileId?: number, fileId2?: number) {
    return post<SessionInfo>('/sessions', {
      title,
      session_type: sessionType,
      file_id: fileId,
      file_id_2: fileId2,
    })
  },
}
