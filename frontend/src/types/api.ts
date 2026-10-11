/** 与后端 OpenAPI 契约对应的类型定义（与 backend/app/schemas 对齐） */

export interface GenericResponse<T = unknown> {
  code: number
  msg: string
  data: T
}

export interface PageResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface LoginResult {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserInfo {
  id: number
  username: string
  display_name: string
  department: string
  role: string
  created_at: string
}

export interface ContractFile {
  file_id: number
  title: string
  file_type: string
  parse_status: string
  party_a: string
  party_b: string
  amount: number
  contract_type: string
  is_accepted: boolean
  created_at: string
}

export interface SessionInfo {
  session_id: number
  title: string
  session_type: 'review' | 'compare' | 'chat'
  status: string
  file_id: number | null
  file_id_2: number | null
  created_at: string
  updated_at: string
}

/** 审阅 SSE 事件 */
export interface RiskPoint {
  id: number
  task_id: number
  session_id: number
  index: number
  original_content: string
  risk_analysis: string
  risk_level: '高' | '中' | '低'
  suggested_content: string
  risk_dim: string
}

export interface ReviewSummary {
  summary: string
  suggestion: string
  overall_risk: '高' | '中' | '低'
}

export type ReviewEvent =
  | { event: 'message'; data: RiskPoint }
  | { event: 'end'; data: ReviewSummary }
  | { event: 'error'; data: { message: string } }

/** 聊天 SSE 事件 */
export type ChatEvent =
  | { type: 'content'; content: string; session_id: number }
  | { type: 'done'; message_id: number; full_content: string }
  | { type: 'error'; message: string }

export interface ComparisonResult {
  id: number
  session_id: number
  result_json: string
  created_at: string
}

export interface DashboardOverview {
  reviewed_contracts: number
  total_contracts: number
  risk_points: number
  avg_risk_level: string
  user_count: number
  today_reviews: number
  today_chats: number
}

export interface TrendPoint {
  date: string
  review_count: number
  chat_count: number
}

export interface RiskDimStat {
  risk_dim: string
  count: number
  high: number
  medium: number
  low: number
}

export interface ContractType {
  id: number
  name: string
  description: string
  is_active: boolean
  created_at: string
}

export interface ModelConfig {
  id: number
  model_name: string
  model_type: string
  provider: string
  api_endpoint: string
  temperature: number
  top_p: number
  max_tokens: number
  is_active: boolean
}

export interface PromptTemplate {
  id: number
  name: string
  prompt_type: string
  content: string
  scope: string
  is_active: boolean
}
