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

export interface CourseUpdateRequest {
  name?: string
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

export interface DocumentReparseResponse {
  document_id: number
  version: number
  async_task_id: string
}

export interface KnowledgeMasteryItem {
  knowledge_point_id: number
  knowledge_point: string
  score: number | null
  confidence: number | null
  attempts: number
  trend: string | null
  has_record: boolean
}

export interface KnowledgeMasteryResponse {
  items: KnowledgeMasteryItem[]
}

export interface LearningRecordItem {
  id: number
  task_id: number | null
  task_title: string | null
  knowledge_point_id: number | null
  knowledge_point: string | null
  record_type: string
  duration_seconds: number
  completed: boolean
  occurred_at: string
}

export interface LearningRecordListResponse {
  items: LearningRecordItem[]
  total: number
  summary: { minutes: number }
}

export type RecommendationType = 'study_task' | 'mastery_review' | 'course_chat' | 'create_plan' | 'upload_document' | 'weekly_report'
export type RecommendationFeedbackAction = 'clicked' | 'saved' | 'skipped'

export interface RecommendationSignal {
  code: string
  label: string
  value: number
  contribution: number
}

export interface CourseRecommendationItem {
  recommendation_key: string
  item_type: RecommendationType
  item_id: number
  course_id: number
  title: string
  subtitle: string
  score: number
  reason: string
  estimated_minutes: number | null
  knowledge_point: { id: number; name: string; score: number; attempts: number } | null
  signals: RecommendationSignal[]
  score_breakdown: Record<string, number>
  action: { type: string; label: string }
}

export interface CourseRecommendationsResponse {
  course: { id: number; name: string }
  target_date: string
  algorithm_version: string
  strategy_summary: string
  items: CourseRecommendationItem[]
}

export interface RecommendationHistoryItem {
  record_id: number
  item_type: RecommendationType
  item_id: number
  title: string
  score: number
  reason: string
  feedback_action: RecommendationFeedbackAction | null
  created_at: string
}

export interface RecommendationHistoryResponse {
  items: RecommendationHistoryItem[]
  total: number
  metrics: Record<RecommendationFeedbackAction, number>
}

export interface BackendAsyncTask {
  task_id: string
  task_type: string
  resource_type: string | null
  resource_id: string | null
  status: string
  progress: number
  current_step: string | null
  input_data: Record<string, unknown>
  result_data: Record<string, unknown> | null
  error_message: string | null
  retry_count: number
  cancel_requested: boolean
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
  can_cancel: boolean
  can_retry: boolean
}

export interface AsyncTaskListParams {
  status?: string
  task_type?: string
  limit?: number
  offset?: number
}

export interface AsyncTaskListResponse {
  items: BackendAsyncTask[]
  total: number
}

export interface WeeklyReportRequest {
  start_date: string
  end_date: string
  course_id?: number | null
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
  daily_availability?: Record<string, number>
  unavailable_dates?: string[]
  session_minutes?: number
  goal: string
}

export interface PracticeOption { key: string; text: string }
export interface PracticeQuestion { id:number; knowledge_point_id:number|null; knowledge_point:string|null; question_type:string; stem:string; options:PracticeOption[]; difficulty:string; origin:string; source_document_id:number|null; source_page_number:number|null; source_quote:string|null }
export interface PracticeSummary { total_attempts:number; correct_attempts:number; wrong_attempts:number; accuracy:number; pending_wrong_count:number; knowledge_point_count:number }
export interface PracticeAttemptRequest { submission_id:string; selected_option:string; elapsed_seconds:number }
export interface PracticeAttemptResult extends PracticeQuestion { attempt_id:number; question_id:number; selected_option:string; is_correct:boolean; correct_option:string; explanation:string; mastery_score:number|null; wrong_book_updated:boolean; summary:PracticeSummary; idempotent_replay:boolean }
export interface WrongBookEntry { id:number; status:'pending'|'mastered'|'removed'; wrong_count:number; last_selected_option:string; last_wrong_at:string; question:PracticeQuestion & {correct_option:string;explanation:string}; mastery_score:number|null }

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

export interface DashboardCourseFocus {
  id: number
  name: string
  code: string | null
  exam_date: string | null
  days_until_exam: number | null
  has_active_plan: boolean
}

export interface DashboardTodayTask {
  id: number
  course_id: number
  title: string
  task_type: string
  estimated_minutes: number
  actual_minutes: number | null
  priority: number
  difficulty: string
  status: string
  scheduled_date: string
}

export interface DashboardTodaySummary {
  items: DashboardTodayTask[]
  total_count: number
  completed_count: number
  pending_count: number
  planned_minutes: number
  actual_minutes: number
  completion_rate: number
}

export interface DashboardMetrics {
  today_focus_minutes: number
  today_completion_rate: number
  average_mastery: number | null
  active_course_count: number
  ready_document_count: number
  study_days_in_range: number
}

export interface DashboardTrendPoint {
  date: string
  label: string
  learning_minutes: number
  scheduled_tasks: number
  completed_tasks: number
  completion_rate: number
}

export interface DashboardWeakPoint {
  knowledge_point_id: number
  knowledge_point: string
  course_id: number
  course_name: string
  score: number
  attempts: number
  confidence: number
}

export interface DashboardNextAction {
  type: string
  title: string
  reason: string
  route: string
}

export interface DashboardAsyncTask {
  task_id: string
  task_type: string
  status: string
  progress: number
  current_step: string | null
  created_at: string
  finished_at: string | null
}

export interface DashboardOverview {
  target_date: string
  range_start: string
  range_end: string
  timezone: string
  course_count: number
  ready_document_count: number
  focus_course: DashboardCourseFocus | null
  today: DashboardTodaySummary
  metrics: DashboardMetrics
  trend: DashboardTrendPoint[]
  weak_points: DashboardWeakPoint[]
  next_action: DashboardNextAction
  recent_async_tasks: DashboardAsyncTask[]
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

export type FoundationLevel = 'basic' | 'intermediate' | 'advanced'
export type LearningOrder = 'explain_first' | 'weakness_first'
export type PreferredDifficulty = 'basic' | 'adaptive' | 'advanced'
export type PreferredResourceType = 'pdf' | 'ppt' | 'markdown' | 'text'

export interface UserPreferences {
  foundation_level: FoundationLevel
  learning_order: LearningOrder
  preferred_difficulty: PreferredDifficulty
  preferred_resource_types: PreferredResourceType[]
  session_minutes: number
  daily_minutes: number
  needs_exam_focus: boolean
  needs_error_points: boolean
  needs_derivation: boolean
}

export interface UserProfileResponse {
  user: BackendUser
  preferences: UserPreferences
}

export interface UserProfileUpdate {
  display_name?: string
  timezone?: string
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
