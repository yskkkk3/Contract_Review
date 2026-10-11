import { del, get, post } from './http'
import type { ContractType, DashboardOverview, ModelConfig, PromptTemplate, RiskDimStat, TrendPoint } from '@/types/api'

export const dashboardApi = {
  overview() {
    return get<DashboardOverview>('/dashboard/overview')
  },
  trends(period = 'month') {
    return get<TrendPoint[]>(`/dashboard/trends?period=${period}`)
  },
  riskDims() {
    return get<RiskDimStat[]>('/dashboard/risk-dims')
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
  prompts() {
    return get<PromptTemplate[]>('/prompts')
  },
}
