import { get, post } from './http'
import type { LoginResult, UserInfo } from '@/types/api'
import axios from 'axios'

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
  async logout(token: string, refreshToken?: string | null) {
    const base = import.meta.env.VITE_API_BASE || '/api'
    const revoke = (access: string) => axios.post(`${base}/auth/logout`, undefined, {
      headers: { Authorization: `Bearer ${access}` }, timeout: 30000,
    })
    try {
      await revoke(token)
    } catch (error) {
      if (!axios.isAxiosError(error) || error.response?.status !== 401 || !refreshToken) throw error
      const response = await axios.post(`${base}/auth/refresh`, { refresh_token: refreshToken }, { timeout: 30000 })
      await revoke(response.data.data.access_token)
    }
  },
}
