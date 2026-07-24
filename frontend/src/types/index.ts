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

export interface AIRuntimeStatus {
  provider: string
  chat_model: string
  chat_mode: 'remote' | 'mock'
  embedding_mode: 'remote' | 'local'
  is_mock: boolean
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
export type RecommendationCategory = 'all' | 'task' | 'mastery' | 'resource' | 'plan' | 'report'
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
  category: Exclude<RecommendationCategory, 'all'>
  category_label: string
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
  category_counts: Record<RecommendationCategory, number>
  selection: { mode: 'diverse' | 'category'; returned: number; candidate_total: number }
}

export interface RecommendationHistoryItem {
  record_id: number
  item_type: RecommendationType
  category: Exclude<RecommendationCategory, 'all'>
  category_label: string
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

export interface WeeklyReportDailyItem {
  date: string
  learning_minutes: number
  scheduled_tasks: number
  completed_tasks: number
}

export interface WeeklyReportCourseBreakdown {
  course_id: number
  course_name: string
  learning_minutes: number
  scheduled_tasks: number
  completed_tasks: number
  completion_rate: number
}

export interface WeeklyReportWeakPoint {
  knowledge_point: string
  score: number
  knowledge_point_id?: number
  course_id?: number
  course_name?: string
  attempts?: number
  confidence?: number
}

export interface WeeklyReportResult {
  range_start: string
  range_end: string
  total_learning_minutes: number
  study_days: number
  scheduled_tasks: number
  completed_tasks: number
  completion_rate: number
  weak_points: WeeklyReportWeakPoint[]
  summary: string
  report_schema_version?: number
  timezone?: string
  scope_label?: string
  course_names?: string[]
  daily?: WeeklyReportDailyItem[]
  course_breakdown?: WeeklyReportCourseBreakdown[]
}

export function normalizeWeeklyReport(value: Record<string, unknown> | null): WeeklyReportResult | null {
  if (!value || typeof value.range_start !== 'string' || typeof value.range_end !== 'string' || typeof value.summary !== 'string') return null
  const number = (key: string) => typeof value[key] === 'number' ? value[key] : 0
  const weakPoints = Array.isArray(value.weak_points) ? value.weak_points.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object').filter(item => typeof item.knowledge_point === 'string').map(item => ({ knowledge_point: String(item.knowledge_point), score: typeof item.score === 'number' ? item.score : 0, ...(typeof item.knowledge_point_id === 'number' ? { knowledge_point_id: item.knowledge_point_id } : {}), ...(typeof item.course_id === 'number' ? { course_id: item.course_id } : {}), ...(typeof item.course_name === 'string' ? { course_name: item.course_name } : {}), ...(typeof item.attempts === 'number' ? { attempts: item.attempts } : {}), ...(typeof item.confidence === 'number' ? { confidence: item.confidence } : {}) })) : []
  const daily = Array.isArray(value.daily) ? value.daily.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object' && typeof item.date === 'string').map(item => ({ date: String(item.date), learning_minutes: typeof item.learning_minutes === 'number' ? item.learning_minutes : 0, scheduled_tasks: typeof item.scheduled_tasks === 'number' ? item.scheduled_tasks : 0, completed_tasks: typeof item.completed_tasks === 'number' ? item.completed_tasks : 0 })) : undefined
  const breakdown = Array.isArray(value.course_breakdown) ? value.course_breakdown.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object' && typeof item.course_id === 'number' && typeof item.course_name === 'string').map(item => ({ course_id: Number(item.course_id), course_name: String(item.course_name), learning_minutes: typeof item.learning_minutes === 'number' ? item.learning_minutes : 0, scheduled_tasks: typeof item.scheduled_tasks === 'number' ? item.scheduled_tasks : 0, completed_tasks: typeof item.completed_tasks === 'number' ? item.completed_tasks : 0, completion_rate: typeof item.completion_rate === 'number' ? item.completion_rate : 0 })) : undefined
  const courseNames = Array.isArray(value.course_names) ? value.course_names.filter((item): item is string => typeof item === 'string') : undefined
  return { range_start: value.range_start, range_end: value.range_end, total_learning_minutes: number('total_learning_minutes'), study_days: number('study_days'), scheduled_tasks: number('scheduled_tasks'), completed_tasks: number('completed_tasks'), completion_rate: number('completion_rate'), weak_points: weakPoints, summary: value.summary, ...(typeof value.report_schema_version === 'number' ? { report_schema_version: value.report_schema_version } : {}), ...(typeof value.timezone === 'string' ? { timezone: value.timezone } : {}), ...(typeof value.scope_label === 'string' ? { scope_label: value.scope_label } : {}), ...(courseNames ? { course_names: courseNames } : {}), ...(daily ? { daily } : {}), ...(breakdown ? { course_breakdown: breakdown } : {}) }
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

export interface StatisticsDailyPoint { date:string; actual_learning_seconds:number; planned_minutes:number; task_total:number; task_completed:number; practice_attempts:number; practice_correct:number; practice_accuracy:number|null }
export interface StatisticsCourseDistribution { course_id:number; course_name:string; learning_seconds:number; percentage:number }
export interface StatisticsHeatmapDay { date:string; learning_seconds:number }
export interface StatisticsEfficientPeriod { label:string; start_hour:number; end_hour:number; attempts:number; correct:number; accuracy:number }
export interface StatisticsInsight { code:string; title:string; detail:string; evidence:Record<string, unknown>|string }
export interface StatisticsOverview { range:{start_date:string;end_date:string;days:number;timezone:string}; scope:{course_id:number|null;course_name:string|null}; summary:{total_learning_seconds:number;previous_total_learning_seconds:number|null;learning_seconds_change:number|null;learning_days:number;longest_streak_days:number;task_total:number;task_completed:number;task_completion_rate:number|null;previous_task_completion_rate:number|null;task_completion_rate_change:number|null;practice_attempts:number;practice_correct:number;practice_wrong:number;practice_accuracy:number|null;previous_practice_accuracy:number|null;practice_accuracy_change:number|null;efficient_period:StatisticsEfficientPeriod|null}; daily:StatisticsDailyPoint[]; course_distribution:StatisticsCourseDistribution[]; heatmap:StatisticsHeatmapDay[]; insights:StatisticsInsight[] }

export interface CalendarEventItem { id:number; title:string; start_at:string; end_at:string; provider:string; sync_status:string; study_task_id:number|null; course_id:number|null; course_name:string|null; task_type:string|null; created_at:string; updated_at:string }
export interface CalendarEventListResponse { items:CalendarEventItem[]; total:number; timezone:string }
export interface CalendarAvailabilitySlot { start_at:string; end_at:string; source:string }
export interface CalendarPlanSyncRequest { start_date:string; end_date:string; course_id?:number; daily_start_time:string; gap_minutes:number }
export interface CalendarPlanSyncPreviewItem { task_id:number; course_id:number; course_name:string; title:string; task_type:string; scheduled_date:string; estimated_minutes:number; start_at:string; end_at:string; status:'ready'|'conflict'|'already_synced'|'outside_day'; reason:string|null; conflict_with:{event_id:number;title:string;start_at:string;end_at:string}|null; existing_event_id:number|null; idempotency_key:string }
export interface CalendarPlanSyncPreview { timezone:string; scope:CalendarPlanSyncRequest; items:CalendarPlanSyncPreviewItem[]; ready_count:number; conflict_count:number; already_synced_count:number; outside_day_count:number; confirmation_token:string; expires_in_seconds:number }
export interface CalendarPlanSyncConfirmResult { created_count:number; replayed_count:number; event_ids:number[]; items:CalendarPlanSyncPreviewItem[]; idempotent_replay:boolean }
export interface CalendarEventCreateRequest { title:string; start_at:string; end_at:string; study_task_id?:number|null; idempotency_key?:string }
export interface CalendarEventUpdateRequest { title?:string; start_at?:string; end_at?:string }
export interface CalendarEventPreview { status:string; preview:Record<string, unknown>; confirmation_token:string; expires_in_seconds?:number }
export interface MCPToolInfo { name:string; is_write:boolean; requires_confirmation:boolean; description:string }
export interface MCPToolCallItem { id:number; agent_run_id:string; tool_name:string; status:string; duration_ms:number; error_message:string|null; created_at:string }
export interface MCPToolCallListResponse { items:MCPToolCallItem[]; total:number }
