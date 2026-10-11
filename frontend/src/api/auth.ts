import { get, post } from './http'
import type { LoginResult, UserInfo } from '@/types/api'

export const authApi = {
  register(username: string, password: string, displayName?: string, department?: string) {
    return post<UserInfo>('/users', {
      username,
      password,
      display_name: displayName,
      department,
    })
  },
  login(identifier: string, password: string) {
    return post<LoginResult>('/auth/login', { identifier, password })
  },
  me() {
    return get<UserInfo>('/auth/me')
  },
}
