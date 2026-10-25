import { del, get, post, put } from './http'
import type { ContractType, DashboardOverview, DepartmentUsage, ModelConfig, PromptTemplate, TrendPoint } from '@/types/api'

export const dashboardApi = {
  overview() {
    return get<DashboardOverview>('/dashboard/overview')
  },
  trends(period = 'month') {
    return get<TrendPoint[]>(`/dashboard/trends?period=${period}`)
  },
  departments() {
    return get<DepartmentUsage[]>('/dashboard/departments')
  },
}

export const adminApi = {
  contractTypes() {
    return get<ContractType[]>('/contract-types')
  },
  createContractType(name: string, description: string) {
    return post<ContractType>('/contract-types', { name, description })
  },
  toggleContractType(id: number, isActive: boolean) {
    return post<ContractType>(`/contract-types/${id}/activate?is_active=${isActive ? 1 : 0}`)
  },
  modelConfigs(modelType?: string) {
    return get<ModelConfig[]>(`/model-configs${modelType ? `?model_type=${modelType}` : ''}`)
  },
  createModelConfig(data: Partial<ModelConfig>) {
    return post<ModelConfig>('/model-configs', data)
  },
  deleteModelConfig(id: number) {
    return del<boolean>(`/model-configs/${id}`)
  },
  updateModelConfig(id: number, data: Partial<ModelConfig>) {
    return put<ModelConfig>(`/model-configs/${id}`, data)
  },
  prompts() {
    return get<PromptTemplate[]>('/prompts')
  },
  promptTemplates() {
    return get<{ name: string; content: string }[]>('/prompt-templates')
  },
  savePrompt(data: Partial<PromptTemplate>) {
    return data.id ? put<PromptTemplate>(`/prompts/${data.id}`, {
      prompt_content: data.prompt_content, is_active: data.is_active,
    }) : post<PromptTemplate>('/prompts', data)
  },
  deletePrompt(id: number) {
    return del<null>(`/prompts/${id}`)
  },
}
