import { get, post } from './http'
import type { LoginResult, UserInfo } from '@/types/api'

export const authApi = {
  register(username: string, password: string) {
    return post<UserInfo>('/users', { username, password })
  },
  login(identifier: string, password: string) {
    return post<LoginResult>('/auth/login', { identifier, password })
  },
  me() {
    return get<UserInfo>('/auth/me')
  },
}
