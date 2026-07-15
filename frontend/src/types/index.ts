export interface Course {
  id: number
  name: string
  code: string
  teacher: string
  color: string
  examDate: string
  progress: number
  documentCount: number
  knowledgeCount: number
  targetScore: number
}

export interface BackendCourse {
  id: number
  owner_id: number
  name: string
  code: string | null
  description: string | null
  exam_date: string | null
  target_score: number
  color: string | null
  archived: boolean
  created_at: string
  updated_at: string
}

export interface BackendCourseListResponse {
  items: BackendCourse[]
  total: number
}

export interface CourseCreateRequest {
  name: string
  code?: string | null
  description?: string | null
  exam_date?: string | null
  target_score?: number
  color?: string | null
}

export interface CourseListItem {
  id: number
  name: string
  code: string | null
  description: string | null
  examDate: string | null
  targetScore: number
  color: string
  archived: boolean
  createdAt: string
  updatedAt: string
}

export interface CourseListResult {
  items: CourseListItem[]
  total: number
}

export interface BackendDocument {
  id: number
  course_id: number
  title: string
  file_type: string
  current_version: number
  status: string
  page_count: number | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface DocumentListResponse {
  items: BackendDocument[]
  total: number
}

export interface DocumentUploadResponse {
  document: BackendDocument
  async_task_id: string
}

export interface BackendAsyncTask {
  task_id: string
  task_type: string
  status: string
  progress: number
  current_step: string | null
  result_data: Record<string, unknown> | null
  error_message: string | null
  retry_count: number
  cancel_requested: boolean
  created_at: string
}

export interface LatestDocumentTaskResponse {
  task_id: string
  status: string
  progress: number
  current_step: string | null
}

export type TaskStatus = 'todo' | 'doing' | 'done'

export interface StudyTask {
  id: number
  title: string
  course: string
  type: '阅读' | '练习' | '复习' | '测试'
  duration: number
  priority: '高' | '中' | '低'
  status: TaskStatus
  knowledge: string
}

export interface Citation {
  id: number
  document: string
  page: number
  chapter: string
  snippet: string
  score: number
}

export interface AsyncTask {
  id: string
  name: string
  type: string
  status: 'queued' | 'processing' | 'retrying' | 'success' | 'failed'
  progress: number
  step: string
  createdAt: string
}

export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
  request_id: string
}

export interface BackendUser {
  id: number
  email: string
  display_name: string
  full_name: string
  timezone: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AuthUser {
  id: number
  email: string
  displayName: string
  fullName: string
  timezone: string
  isActive: boolean
  createdAt: string
  updatedAt: string
}

export interface AuthTokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: BackendUser
}
