import axios, { type AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import type { GenericResponse } from '@/types/api'

export const TOKEN_KEY = 'contract_review_token'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 120000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (resp) => {
    const body = resp.data as GenericResponse
    if (body && typeof body.code === 'number' && body.code !== 200) {
      ElMessage.error(body.msg || '请求失败')
      return Promise.reject(new Error(body.msg))
    }
    return resp
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      router.push('/login')
    }
    const msg = error.response?.data?.msg || error.message || '网络错误'
    ElMessage.error(msg)
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
