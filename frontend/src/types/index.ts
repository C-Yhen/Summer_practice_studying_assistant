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

export type ChatMode = 'basic' | 'exam' | 'strict' | 'teacher'

export interface ChatSession {
  session_id: string
  course_id: number
  title: string
  mode: ChatMode
  document_ids: number[]
  created_at: string
  updated_at: string
}

export interface ChatSessionListResponse {
  items: ChatSession[]
  total: number
}

export interface ChatSessionCreateRequest {
  title?: string
  mode?: ChatMode
  document_ids?: number[]
}

export type ChatSessionCreateResponse = ChatSession

export interface ChatAskRequest {
  question: string
  mode?: ChatMode
  document_ids?: number[]
  top_k?: number
}

export interface RagCitation {
  source_id: string
  chunk_id: number
  document_id: number
  document_name: string
  document_version: number
  page_number: number | null
  chapter_name: string | null
  quote: string
  score: number
}

export interface ChatAnswerResponse {
  message_id: string
  answer: string
  sufficient_evidence: boolean
  citations: RagCitation[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: RagCitation[]
  sufficient_evidence: boolean | null
  created_at: string
}

export interface ChatMessageListResponse {
  items: ChatMessage[]
  next_cursor: string | null
}

export interface StudyPlanGenerateRequest {
  start_date: string
  end_date: string
  daily_availability: Record<string, number>
  unavailable_dates?: string[]
  session_minutes: number
  goal: string
}

export interface StudyPlanTask {
  id: number
  scheduled_date: string
  knowledge_point_id: number | null
  title: string
  task_type: string
  estimated_minutes: number
  actual_minutes: number | null
  priority: number
  difficulty: string
  status: string
}

export interface StudyPlanVersion {
  version: number
  status: string
  reason: string | null
  summary: string | null
  risks: string[]
  diff: Record<string, unknown>
  tasks: StudyPlanTask[]
}

export interface StudyPlanGenerateResponse {
  async_task_id: string
  plan_id: number
  course_id: number
  goal: string
  start_date: string
  end_date: string
  expected_base_version: number
  candidate_version: StudyPlanVersion
  confirmation_token: string
}

export interface CurrentStudyPlanResponse extends StudyPlanVersion {
  plan_id: number
  course_id: number
  goal: string
  start_date: string
  end_date: string
  active_version: number
  plan_status: string
  expected_base_version: number | null
  confirmation_token: string | null
}

export interface PlanConfirmRequest {
  expected_base_version: number
  confirmation_token: string
}

export interface PlanConfirmResponse {
  plan_id: number
  active_version: number
  previous_version: number
  status: string
  version_status: string
}

export interface TodayTask {
  id: number
  course_id: number
  knowledge_point_id: number | null
  title: string
  task_type: string
  estimated_minutes: number
  actual_minutes: number | null
  priority: number
  difficulty: string
  status: string
  scheduled_date: string
}

export interface TodayTaskListResponse {
  items: TodayTask[]
  total: number
}

export interface TaskCompleteRequest {
  actual_minutes: number
  completed_at?: string
}

export interface TaskCompleteResponse {
  task_id: number
  status: string
  actual_minutes: number | null
  mastery_score: number | null
  idempotent_replay: boolean
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
