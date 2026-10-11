import http, { del, post } from './http'
import type { UserInfo } from '@/types/api'

const endpoint = '/users/me/avatar'

export const avatarApi = {
  async read() {
    const response = await http.get<Blob>(endpoint, { responseType: 'blob' })
    return response.data
  },
  upload(file: File) {
    const form = new FormData()
    form.append('file', file)
    return post<UserInfo>(endpoint, form)
  },
  remove() {
    return del<UserInfo>(endpoint)
  },
}
