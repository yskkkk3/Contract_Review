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
  role: string
  is_active?: boolean
  created_at?: string | null
}

export interface ContractFile {
  id: number
  title: string
  file_type: string
  parse_status: string
  party_a: string
  party_b: string
  amount: number
  contract_type_id: number | null
  review_position: number
  is_accepted: number
  created_at: string | null
}

export interface SessionInfo {
  session_id: number
  title: string
  session_type: 'review' | 'compare' | 'chat'
  file_id: number | null
  created_at: string | null
}

export interface MessageInfo {
  id: number
  session_id: number
  role: 'user' | 'assistant'
  content: string
  parent_id: number | null
  message_index: number
  created_at: string
}

/** 审阅 SSE 事件 */
export interface RiskPoint {
  id?: number
  task_id?: number
  session_id?: number
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
  metrics?: {
    total_ms: number
    risk_point_count: number
  }
}

export type ReviewEvent =
  | { event: 'meta'; data: { task_id: number; session_id: number; chunk_count: number } }
  | { event: 'message'; data: RiskPoint }
  | { event: 'end'; data: ReviewSummary }
  | { event: 'error'; data: { message: string } }

/** 聊天 SSE 事件 */
export type ChatEvent =
  | { type: 'content'; content: string; session_id: number }
  | {
      type: 'done'
      message_id: number
      full_content: string
      metrics: {
        ttft_ms: number
        total_ms: number
        completion_tokens: number | null
        tokens_per_sec: number
      }
    }
  | { type: 'error'; message: string }

export interface CharDiff {
  operation: 'equal' | 'replace' | 'insert' | 'delete'
  std_text: string
  cmp_text: string
}

export interface ParagraphDiff {
  operation: string
  std_index: number | null
  cmp_index: number | null
  standard_text: string
  comparison_text: string
  char_diff: CharDiff[]
}

export interface ComparisonResult {
  task_id: number
  session_id: number
  diff_summary: {
    standard_paragraphs: number
    comparison_paragraphs: number
    difference_count: number
  }
  diffs: ParagraphDiff[]
  standard_file: { file_id: number; title: string; file_type: string; download_url: string }
  comparison_file: { file_id: number; title: string; file_type: string; download_url: string }
}

export interface DashboardOverview {
  reviewed_contracts: number
  service_departments: number
  users_count: number
  served_faculty_students: number
  total_reviewed_amount: number
}

export interface TrendPoint {
  date: string
  total: number
  service: number
  goods: number
  infrastructure: number
}

export interface DepartmentUsage {
  department_name: string
  contract_review: number
  contract_verification: number
  contract_comparison: number
  total: number
}

export interface ContractType {
  id: number
  name: string
  description: string
  is_active: number
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
  is_default: number
  status: string
  create_time: string | null
  update_time: string | null
}

export interface PromptTemplate {
  id: number
  level: string
  contract_type_id: number | null
  base_prompt_id: number | null
  organization_id: number | null
  prompt_name: string
  prompt_content: string
  is_active: number
}
