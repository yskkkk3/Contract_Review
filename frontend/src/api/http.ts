import axios, { type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import type { GenericResponse, LoginResult } from '@/types/api'

declare module 'axios' {
  interface AxiosRequestConfig {
    silent?: boolean
  }
}

export const TOKEN_KEY = 'contract_review_token'
const REFRESH_KEY = 'contract_review_refresh_token'
let refreshing: Promise<string> | null = null

export function refreshAccessToken(): Promise<string> {
  if (refreshing) return refreshing
  const refresh = localStorage.getItem(REFRESH_KEY)
  if (!refresh) return Promise.reject(new Error('登录已过期'))
  refreshing = (async () => {
    const response = await axios.post<GenericResponse<LoginResult>>(
      `${import.meta.env.VITE_API_BASE || '/api'}/auth/refresh`, { refresh_token: refresh }, { timeout: 30000 },
    )
    if (localStorage.getItem(REFRESH_KEY) !== refresh) throw new Error('登录状态已变更')
    const result = response.data.data
    if (response.data.code !== 200 || !result?.access_token || !result.refresh_token) throw new Error('刷新登录失败')
    localStorage.setItem(TOKEN_KEY, result.access_token)
    localStorage.setItem(REFRESH_KEY, result.refresh_token)
    const { useAuthStore } = await import('@/stores/auth')
    if (localStorage.getItem(REFRESH_KEY) === result.refresh_token) useAuthStore().token = result.access_token
    return result.access_token
  })().finally(() => { refreshing = null })
  return refreshing
}

export async function expireSession(access: string) {
  if (localStorage.getItem(TOKEN_KEY) !== access) return
  const { useAuthStore } = await import('@/stores/auth')
  if (localStorage.getItem(TOKEN_KEY) !== access) return
  useAuthStore().logout(false)
  router.push('/login')
}

function persistRenewedToken(headers?: Record<string, unknown>, sentToken?: unknown) {
  const token = headers?.['x-access-token']
  if (typeof token !== 'string' || !token) return
  if (sentToken !== `Bearer ${localStorage.getItem(TOKEN_KEY)}`) return
  localStorage.setItem(TOKEN_KEY, token)
  void import('@/stores/auth').then(({ useAuthStore }) => {
    const auth = useAuthStore()
    if (auth.token && localStorage.getItem(TOKEN_KEY) === token) auth.token = token
  })
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 120000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token && !config.headers.Authorization) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (resp) => {
    persistRenewedToken(resp.headers, resp.config?.headers?.Authorization)
    const body = resp.data as GenericResponse
    if (body && typeof body.code === 'number' && body.code !== 200) {
      if (!resp.config.silent) ElMessage.error(body.msg || '请求失败')
      return Promise.reject(new Error(body.msg))
    }
    return resp
  },
  async (error) => {
    if (error.response?.status === 401) {
      const config = error.config as (AxiosRequestConfig & { _retried?: boolean }) | undefined
      const refresh = localStorage.getItem(REFRESH_KEY)
      if (config && !config._retried && !/\/auth\/(login|refresh|logout)$/.test(config.url || '')) {
        config._retried = true
        try {
          const token = await refreshAccessToken()
          config.headers = { ...config.headers, Authorization: `Bearer ${token}` }
          return http.request(config)
        } catch {
          // Clear only the failed session; a newer login must survive stale responses.
        }
      }
      const { useAuthStore } = await import('@/stores/auth')
      if (refresh === localStorage.getItem(REFRESH_KEY) && !/\/auth\/logout$/.test(config?.url || '')) {
        useAuthStore().logout(false)
        router.push('/login')
      }
    }
    const msg = error.response?.data?.msg || error.message || '网络错误'
    if (!error.config?.silent) ElMessage.error(msg)
    return Promise.reject(error)
  },
)

export async function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const resp = await http.get<GenericResponse<T>>(url, config)
  return resp.data.data
}

export async function post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const resp = await http.post<GenericResponse<T>>(url, data, config)
  return resp.data.data
}

export async function put<T>(url: string, data?: unknown): Promise<T> {
  const resp = await http.put<GenericResponse<T>>(url, data)
  return resp.data.data
}

export async function del<T>(url: string): Promise<T> {
  const resp = await http.delete<GenericResponse<T>>(url)
  return resp.data.data
}

export default http
