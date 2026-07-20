import { ApiEnvelopeError, apiClient, isApiError, mockEnabled, unwrapApiResponse, withMockFallback } from './client'
import { asyncTasks, courses, todayTasks } from '@/data/mock'
import { normalizeWeeklyReport } from '@/types'
import type {
  AsyncTask,
  AsyncTaskListParams,
  AsyncTaskListResponse,
  BackendAsyncTask,
  BackendCourse,
  BackendCourseListResponse,
  BackendDocument,
  ChatAnswerResponse,
  ChatAskRequest,
  ChatMessage,
  ChatMessageListResponse,
  ChatSession,
  ChatSessionCreateRequest,
  ChatSessionCreateResponse,
  ChatSessionListResponse,
  CourseCreateRequest,
  CourseUpdateRequest,
  CourseRecommendationItem,
  CourseRecommendationsResponse,
  CourseListItem,
  CourseListResult,
  CurrentStudyPlanResponse,
  DocumentListResponse,
  DocumentReparseResponse,
  DocumentUploadResponse,
  LatestDocumentTaskResponse,
  KnowledgeMasteryResponse,
  LearningRecordListResponse,
  RecommendationFeedbackAction,
  RecommendationCategory,
  RecommendationHistoryResponse,
  RagCitation,
  PlanConfirmRequest,
  PlanConfirmResponse,
  StudyPlanGenerateRequest,
  StudyPlanGenerateResponse,
  StudyPlanTask,
  StudyPlanVersion,
  StudyTask,
  TaskCompleteRequest,
  TaskCompleteResponse,
  WeeklyReportRequest,
  TodayTask,
  TodayTaskListResponse,
  BackendUser,
  UserPreferences,
  UserProfileResponse,
  UserProfileUpdate,
  PracticeQuestion,
  PracticeSummary,
  PracticeAttemptRequest,
  PracticeAttemptResult,
  WrongBookEntry,
  StatisticsOverview,
  CalendarEventListResponse,
  CalendarAvailabilitySlot,
  CalendarPlanSyncRequest,
  CalendarPlanSyncPreview,
  CalendarPlanSyncConfirmResult,
  CalendarEventCreateRequest,
  CalendarEventUpdateRequest,
  CalendarEventPreview,
  MCPToolInfo,
  MCPToolCallListResponse,
} from '@/types'

const DEFAULT_COURSE_COLOR = '#5b6cf9'
const mockRecommendationHistory = new Map<number, RecommendationHistoryResponse>()
const mockPracticeQuestions = new Map<number, PracticeQuestion[]>()
const mockPracticeAttempts = new Map<number, PracticeAttemptResult[]>()
const mockPracticeSubmissions = new Map<string, {
  courseId: number
  questionId: number
  payload: PracticeAttemptRequest
  result: PracticeAttemptResult
}>()
const mockWrongBookEntries = new Map<number, WrongBookEntry[]>()

function mockStatistics(days: number, courseId?: number): StatisticsOverview {
  const selected = courseId === undefined ? mockCourseRecords : mockCourseRecords.filter((course) => course.id === courseId)
  if (courseId !== undefined && !selected.length) throw new ApiEnvelopeError('课程不存在或无权访问', 404)
  const end = new Date(); const dates = Array.from({ length: days }, (_, index) => { const value = new Date(end); value.setDate(end.getDate() - days + index + 1); return value.toISOString().slice(0, 10) })
  const daily = dates.map((date, index) => ({ date, actual_learning_seconds: (index % 3) * 1800, planned_minutes: 60, task_total: index % 2, task_completed: index % 2, practice_attempts: index % 3, practice_correct: index % 3 ? Math.max(0, index % 3 - 1) : 0, practice_accuracy: index % 3 ? 0.5 : null }))
  const total = daily.reduce((sum, item) => sum + item.actual_learning_seconds, 0)
  const attempts = daily.reduce((sum, item) => sum + item.practice_attempts, 0); const correct = daily.reduce((sum, item) => sum + item.practice_correct, 0)
  const distribution = selected.slice(0, 3).map((course, index) => ({ course_id: course.id, course_name: course.name, learning_seconds: Math.max(0, total - index * 600), percentage: selected.length ? 1 / selected.length : 0 }))
  const heatmap = Array.from({ length: 49 }, (_, index) => { const value = new Date(end); value.setDate(end.getDate() - 48 + index); return { date: value.toISOString().slice(0, 10), learning_seconds: daily[Math.max(0, daily.length - 49 + index)]?.actual_learning_seconds || 0 } })
  return { range: { start_date: dates[0], end_date: dates[dates.length - 1], days, timezone: 'Asia/Shanghai' }, scope: { course_id: courseId ?? null, course_name: selected.length === 1 ? selected[0].name : null }, summary: { total_learning_seconds: total, previous_total_learning_seconds: null, learning_seconds_change: null, learning_days: daily.filter((item) => item.actual_learning_seconds > 0).length, longest_streak_days: 2, task_total: daily.reduce((sum, item) => sum + item.task_total, 0), task_completed: daily.reduce((sum, item) => sum + item.task_completed, 0), task_completion_rate: 1, previous_task_completion_rate: null, task_completion_rate_change: null, practice_attempts: attempts, practice_correct: correct, practice_wrong: attempts - correct, practice_accuracy: attempts ? correct / attempts : null, previous_practice_accuracy: null, practice_accuracy_change: null, efficient_period: null }, daily, course_distribution: distribution, heatmap, insights: total ? [{ code: 'demo', title: '规则洞察', detail: `演示模式：本周期共学习 ${Math.round(total / 60)} 分钟。`, evidence: { total } }] : [] }
}

function toCourseListItem(course: BackendCourse): CourseListItem {
  if (!Number.isInteger(course.id) || typeof course.name !== 'string' || !course.name.trim()) {
    throw new ApiEnvelopeError('后端返回的课程信息不完整')
  }
  return {
    id: course.id,
    name: course.name,
    code: course.code,
    description: course.description,
    examDate: course.exam_date,
    targetScore: course.target_score,
    color: course.color || DEFAULT_COURSE_COLOR,
    archived: course.archived,
    createdAt: course.created_at,
    updatedAt: course.updated_at,
  }
}

const now = new Date().toISOString()
const mockCourseRecords: BackendCourse[] = courses.map((course) => ({
  id: course.id,
  owner_id: 1,
  name: course.name,
  code: course.code || null,
  description: `${course.name}演示课程`,
  exam_date: course.examDate || null,
  target_score: course.targetScore,
  color: course.color || DEFAULT_COURSE_COLOR,
  archived: false,
  created_at: now,
  updated_at: now,
}))

async function mockDelay() {
  await new Promise((resolve) => window.setTimeout(resolve, 220))
}

function parseCourseList(data: BackendCourseListResponse): CourseListResult {
  if (!data || !Array.isArray(data.items) || typeof data.total !== 'number') {
    throw new ApiEnvelopeError('后端返回了无法识别的课程列表结构')
  }
  return { items: data.items.map(toCourseListItem), total: data.total }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseBackendUser(value: unknown): BackendUser {
  if (!isRecord(value) || !Number.isInteger(value.id) || typeof value.email !== 'string' || typeof value.display_name !== 'string' || typeof value.full_name !== 'string' || typeof value.timezone !== 'string' || typeof value.is_active !== 'boolean' || typeof value.created_at !== 'string' || typeof value.updated_at !== 'string') {
    throw new ApiEnvelopeError('后端返回的用户资料不完整')
  }
  return value as unknown as BackendUser
}

function parsePreferences(value: unknown): UserPreferences {
  const levels = ['basic', 'intermediate', 'advanced']
  const orders = ['explain_first', 'weakness_first']
  const difficulties = ['basic', 'adaptive', 'advanced']
  const resourceTypes = ['pdf', 'ppt', 'markdown', 'text']
  if (!isRecord(value) || !levels.includes(String(value.foundation_level)) || !orders.includes(String(value.learning_order)) || !difficulties.includes(String(value.preferred_difficulty)) || !Array.isArray(value.preferred_resource_types) || !value.preferred_resource_types.every((item) => resourceTypes.includes(String(item))) || !Number.isInteger(value.session_minutes) || !Number.isInteger(value.daily_minutes) || typeof value.needs_exam_focus !== 'boolean' || typeof value.needs_error_points !== 'boolean' || typeof value.needs_derivation !== 'boolean') {
    throw new ApiEnvelopeError('后端返回的学习偏好不完整')
  }
  return value as unknown as UserPreferences
}

function parseProfile(value: unknown): UserProfileResponse {
  if (!isRecord(value)) throw new ApiEnvelopeError('后端返回的个人资料结构无法识别')
  return { user: parseBackendUser(value.user), preferences: parsePreferences(value.preferences) }
}

function parseDocument(value: unknown): BackendDocument {
  if (
    !isRecord(value)
    || !Number.isInteger(value.id)
    || !Number.isInteger(value.course_id)
    || typeof value.title !== 'string'
    || typeof value.file_type !== 'string'
    || !Number.isInteger(value.current_version)
    || typeof value.status !== 'string'
    || (value.page_count !== null && !Number.isInteger(value.page_count))
    || (value.error_message !== null && typeof value.error_message !== 'string')
    || typeof value.created_at !== 'string'
    || typeof value.updated_at !== 'string'
  ) {
    throw new ApiEnvelopeError('后端返回的文档信息不完整')
  }
  return value as unknown as BackendDocument
}

function parseDocumentList(value: unknown): DocumentListResponse {
  if (!isRecord(value) || !Array.isArray(value.items) || typeof value.total !== 'number') {
    throw new ApiEnvelopeError('后端返回了无法识别的文档列表结构')
  }
  return { items: value.items.map(parseDocument), total: value.total }
}

function parseMastery(value: unknown): KnowledgeMasteryResponse {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new ApiEnvelopeError('后端返回了无法识别的掌握度结构')
  }
  const items = value.items.map((item) => {
    if (
      !isRecord(item)
      || !Number.isInteger(item.knowledge_point_id)
      || typeof item.knowledge_point !== 'string'
      || (item.score !== null && typeof item.score !== 'number')
      || (item.confidence !== null && typeof item.confidence !== 'number')
      || !Number.isInteger(item.attempts)
      || (item.trend !== null && typeof item.trend !== 'string')
      || typeof item.has_record !== 'boolean'
    ) throw new ApiEnvelopeError('后端返回的掌握度信息不完整')
    return item
  })
  return { items } as unknown as KnowledgeMasteryResponse
}

function parseLearningRecords(value: unknown): LearningRecordListResponse {
  if (
    !isRecord(value)
    || !Array.isArray(value.items)
    || typeof value.total !== 'number'
    || !isRecord(value.summary)
    || typeof value.summary.minutes !== 'number'
  ) throw new ApiEnvelopeError('后端返回了无法识别的学习记录结构')
  const items = value.items.map((item) => {
    if (
      !isRecord(item)
      || !Number.isInteger(item.id)
      || (item.task_id !== null && !Number.isInteger(item.task_id))
      || (item.task_title !== null && typeof item.task_title !== 'string')
      || (item.knowledge_point_id !== null && !Number.isInteger(item.knowledge_point_id))
      || (item.knowledge_point !== null && typeof item.knowledge_point !== 'string')
      || typeof item.record_type !== 'string'
      || !Number.isInteger(item.duration_seconds)
      || typeof item.completed !== 'boolean'
      || typeof item.occurred_at !== 'string'
    ) throw new ApiEnvelopeError('后端返回的学习记录信息不完整')
    return item
  })
  return {
    items,
    total: value.total,
    summary: { minutes: value.summary.minutes },
  } as unknown as LearningRecordListResponse
}

function parseTask(value: unknown): BackendAsyncTask {
  if (
    !isRecord(value)
    || typeof value.task_id !== 'string'
    || typeof value.task_type !== 'string'
    || (value.resource_type !== null && typeof value.resource_type !== 'string')
    || (value.resource_id !== null && typeof value.resource_id !== 'string')
    || typeof value.status !== 'string'
    || typeof value.progress !== 'number'
    || (value.current_step !== null && typeof value.current_step !== 'string')
    || !isRecord(value.input_data)
    || (value.result_data !== null && !isRecord(value.result_data))
    || (value.error_message !== null && typeof value.error_message !== 'string')
    || typeof value.retry_count !== 'number'
    || typeof value.cancel_requested !== 'boolean'
    || typeof value.created_at !== 'string'
    || typeof value.updated_at !== 'string'
    || (value.started_at !== null && typeof value.started_at !== 'string')
    || (value.finished_at !== null && typeof value.finished_at !== 'string')
    || typeof value.can_cancel !== 'boolean'
    || typeof value.can_retry !== 'boolean'
  ) {
    throw new ApiEnvelopeError('后端返回的任务信息不完整')
  }
  return value as unknown as BackendAsyncTask
}

function parseCitation(value: unknown): RagCitation {
  if (
    !isRecord(value)
    || typeof value.source_id !== 'string'
    || !Number.isInteger(value.chunk_id)
    || !Number.isInteger(value.document_id)
    || typeof value.document_name !== 'string'
    || !Number.isInteger(value.document_version)
    || (value.page_number !== null && !Number.isInteger(value.page_number))
    || (value.chapter_name !== null && typeof value.chapter_name !== 'string')
    || typeof value.quote !== 'string'
    || typeof value.score !== 'number'
  ) {
    throw new ApiEnvelopeError('后端返回的引用信息不完整')
  }
  return value as unknown as RagCitation
}

function parseChatSession(value: unknown): ChatSession {
  if (
    !isRecord(value)
    || typeof value.session_id !== 'string'
    || !Number.isInteger(value.course_id)
    || typeof value.title !== 'string'
    || !['basic', 'exam', 'strict', 'teacher'].includes(String(value.mode))
    || !Array.isArray(value.document_ids)
    || !value.document_ids.every(Number.isInteger)
    || typeof value.created_at !== 'string'
    || typeof value.updated_at !== 'string'
  ) {
    throw new ApiEnvelopeError('后端返回的会话信息不完整')
  }
  return value as unknown as ChatSession
}

function parseChatMessage(value: unknown): ChatMessage {
  if (
    !isRecord(value)
    || typeof value.id !== 'string'
    || !['user', 'assistant'].includes(String(value.role))
    || typeof value.content !== 'string'
    || !Array.isArray(value.citations)
    || (value.sufficient_evidence !== null && typeof value.sufficient_evidence !== 'boolean')
    || typeof value.created_at !== 'string'
  ) {
    throw new ApiEnvelopeError('后端返回的消息信息不完整')
  }
  return {
    id: value.id,
    role: value.role as 'user' | 'assistant',
    content: value.content,
    citations: value.citations.map(parseCitation),
    sufficient_evidence: value.sufficient_evidence,
    created_at: value.created_at,
  }
}

function parseChatAnswer(value: unknown): ChatAnswerResponse {
  if (
    !isRecord(value)
    || typeof value.message_id !== 'string'
    || typeof value.answer !== 'string'
    || typeof value.sufficient_evidence !== 'boolean'
    || !Array.isArray(value.citations)
  ) {
    throw new ApiEnvelopeError('后端返回了无法识别的问答结果')
  }
  return {
    message_id: value.message_id,
    answer: value.answer,
    sufficient_evidence: value.sufficient_evidence,
    citations: value.citations.map(parseCitation),
  }
}

function parseStudyPlanTask(value: unknown): StudyPlanTask {
  if (
    !isRecord(value)
    || !Number.isInteger(value.id)
    || typeof value.scheduled_date !== 'string'
    || (value.knowledge_point_id !== null && !Number.isInteger(value.knowledge_point_id))
    || typeof value.title !== 'string'
    || typeof value.task_type !== 'string'
    || !Number.isInteger(value.estimated_minutes)
    || (value.actual_minutes !== null && !Number.isInteger(value.actual_minutes))
    || typeof value.priority !== 'number'
    || typeof value.difficulty !== 'string'
    || typeof value.status !== 'string'
  ) {
    throw new ApiEnvelopeError('后端返回的计划任务信息不完整')
  }
  return value as unknown as StudyPlanTask
}

function parseStudyPlanVersion(value: unknown): StudyPlanVersion {
  if (
    !isRecord(value)
    || !Number.isInteger(value.version)
    || typeof value.status !== 'string'
    || (value.reason !== null && typeof value.reason !== 'string')
    || (value.summary !== null && typeof value.summary !== 'string')
    || !Array.isArray(value.risks)
    || !value.risks.every((risk) => typeof risk === 'string')
    || !isRecord(value.diff)
    || !Array.isArray(value.tasks)
  ) {
    throw new ApiEnvelopeError('后端返回的计划版本信息不完整')
  }
  return {
    version: value.version as number,
    status: value.status,
    reason: value.reason as string | null,
    summary: value.summary as string | null,
    risks: value.risks as string[],
    diff: value.diff,
    tasks: value.tasks.map(parseStudyPlanTask),
  }
}

function parseGeneratedPlan(value: unknown): StudyPlanGenerateResponse {
  if (
    !isRecord(value)
    || typeof value.async_task_id !== 'string'
    || !Number.isInteger(value.plan_id)
    || !Number.isInteger(value.course_id)
    || typeof value.goal !== 'string'
    || typeof value.start_date !== 'string'
    || typeof value.end_date !== 'string'
    || !Number.isInteger(value.expected_base_version)
    || typeof value.confirmation_token !== 'string'
  ) {
    throw new ApiEnvelopeError('后端返回的候选计划信息不完整')
  }
  return {
    async_task_id: value.async_task_id,
    plan_id: value.plan_id as number,
    course_id: value.course_id as number,
    goal: value.goal,
    start_date: value.start_date,
    end_date: value.end_date,
    expected_base_version: value.expected_base_version as number,
    candidate_version: parseStudyPlanVersion(value.candidate_version),
    confirmation_token: value.confirmation_token,
  }
}

function parseCurrentPlan(value: unknown): CurrentStudyPlanResponse {
  if (
    !isRecord(value)
    || !Number.isInteger(value.plan_id)
    || !Number.isInteger(value.course_id)
    || typeof value.goal !== 'string'
    || typeof value.start_date !== 'string'
    || typeof value.end_date !== 'string'
    || !Number.isInteger(value.active_version)
    || typeof value.plan_status !== 'string'
    || (value.expected_base_version !== null && !Number.isInteger(value.expected_base_version))
    || (value.confirmation_token !== null && typeof value.confirmation_token !== 'string')
  ) {
    throw new ApiEnvelopeError('后端返回的当前计划信息不完整')
  }
  return {
    plan_id: value.plan_id as number,
    course_id: value.course_id as number,
    goal: value.goal,
    start_date: value.start_date,
    end_date: value.end_date,
    active_version: value.active_version as number,
    plan_status: value.plan_status,
    expected_base_version: value.expected_base_version as number | null,
    confirmation_token: value.confirmation_token as string | null,
    ...parseStudyPlanVersion(value),
  }
}

function parsePlanConfirmation(value: unknown): PlanConfirmResponse {
  if (
    !isRecord(value)
    || !Number.isInteger(value.plan_id)
    || !Number.isInteger(value.active_version)
    || !Number.isInteger(value.previous_version)
    || typeof value.status !== 'string'
    || typeof value.version_status !== 'string'
  ) {
    throw new ApiEnvelopeError('后端返回的计划确认结果不完整')
  }
  return value as unknown as PlanConfirmResponse
}

function parseTodayTask(value: unknown): TodayTask {
  if (
    !isRecord(value)
    || !Number.isInteger(value.id)
    || !Number.isInteger(value.course_id)
    || (value.knowledge_point_id !== null && !Number.isInteger(value.knowledge_point_id))
    || typeof value.title !== 'string'
    || typeof value.task_type !== 'string'
    || !Number.isInteger(value.estimated_minutes)
    || (value.actual_minutes !== null && !Number.isInteger(value.actual_minutes))
    || typeof value.priority !== 'number'
    || typeof value.difficulty !== 'string'
    || typeof value.status !== 'string'
    || typeof value.scheduled_date !== 'string'
  ) {
    throw new ApiEnvelopeError('后端返回的今日任务信息不完整')
  }
  return value as unknown as TodayTask
}

function parseTodayTaskList(value: unknown): TodayTaskListResponse {
  if (!isRecord(value) || !Array.isArray(value.items) || typeof value.total !== 'number') {
    throw new ApiEnvelopeError('后端返回的今日任务列表结构无法识别')
  }
  return { items: value.items.map(parseTodayTask), total: value.total }
}

function parseTaskCompletion(value: unknown): TaskCompleteResponse {
  if (
    !isRecord(value)
    || !Number.isInteger(value.task_id)
    || typeof value.status !== 'string'
    || (value.actual_minutes !== null && !Number.isInteger(value.actual_minutes))
    || (value.mastery_score !== null && typeof value.mastery_score !== 'number')
    || typeof value.idempotent_replay !== 'boolean'
  ) {
    throw new ApiEnvelopeError('后端返回的任务完成结果不完整')
  }
  return value as unknown as TaskCompleteResponse
}

const mockDocuments: BackendDocument[] = [{
  id: 1001,
  course_id: mockCourseRecords[0]?.id || 1,
  title: '演示课程资料.md',
  file_type: 'md',
  current_version: 1,
  status: 'ready',
  page_count: 1,
  error_message: null,
  created_at: now,
  updated_at: now,
}]
const mockTasks = new Map<string, BackendAsyncTask>()
const mockDocumentTaskIds = new Map<number, string>()
const mockTaskDocumentIds = new Map<string, number>()
const mockChatSessions: ChatSession[] = []
const mockChatMessages = new Map<string, ChatMessage[]>()
const mockPlans = new Map<number, CurrentStudyPlanResponse>()
const mockTodayTaskItems: TodayTask[] = []
const mockProfile: UserProfileResponse = {
  user: { id: 1, email: 'demo@example.com', display_name: '演示学习者', full_name: '演示学习者', timezone: 'Asia/Shanghai', is_active: true, created_at: now, updated_at: now },
  preferences: { foundation_level: 'basic', learning_order: 'explain_first', preferred_difficulty: 'adaptive', preferred_resource_types: ['pdf', 'markdown'], session_minutes: 45, daily_minutes: 120, needs_exam_focus: true, needs_error_points: true, needs_derivation: false },
}
let mockPlanId = 2000
let mockPlanTaskId = 3000

export const profileApi = {
  async get(): Promise<UserProfileResponse> {
    if (mockEnabled) { await mockDelay(); return structuredClone(mockProfile) }
    return parseProfile(unwrapApiResponse<unknown>(await apiClient.get('/users/me/profile')))
  },
  async updateUser(payload: UserProfileUpdate): Promise<BackendUser> {
    if (mockEnabled) {
      await mockDelay()
      if (payload.display_name !== undefined) { mockProfile.user.display_name = payload.display_name.trim(); mockProfile.user.full_name = mockProfile.user.display_name }
      if (payload.timezone !== undefined) mockProfile.user.timezone = payload.timezone
      mockProfile.user.updated_at = new Date().toISOString()
      return structuredClone(mockProfile.user)
    }
    return parseBackendUser(unwrapApiResponse<unknown>(await apiClient.patch('/users/me', payload)))
  },
  async updatePreferences(payload: Partial<UserPreferences>): Promise<UserPreferences> {
    if (mockEnabled) { await mockDelay(); Object.assign(mockProfile.preferences, payload); return structuredClone(mockProfile.preferences) }
    return parsePreferences(unwrapApiResponse<unknown>(await apiClient.patch('/users/me/preferences', payload)))
  },
}

export const courseApi = {
  async list(): Promise<CourseListResult> {
    if (mockEnabled) {
      await mockDelay()
      const items = mockCourseRecords.filter((course) => !course.archived)
      return parseCourseList({ items: structuredClone(items), total: items.length })
    }
    const data = unwrapApiResponse<BackendCourseListResponse>(await apiClient.get('/courses'))
    return parseCourseList(data)
  },

  async create(payload: CourseCreateRequest): Promise<CourseListItem> {
    if (mockEnabled) {
      await mockDelay()
      const timestamp = new Date().toISOString()
      const created: BackendCourse = {
        id: Date.now(),
        owner_id: 1,
        name: payload.name.trim(),
        code: payload.code || null,
        description: payload.description || null,
        exam_date: payload.exam_date || null,
        target_score: payload.target_score ?? 85,
        color: payload.color || DEFAULT_COURSE_COLOR,
        archived: false,
        created_at: timestamp,
        updated_at: timestamp,
      }
      mockCourseRecords.unshift(created)
      return toCourseListItem(structuredClone(created))
    }
    const data = unwrapApiResponse<BackendCourse>(await apiClient.post('/courses', payload))
    return toCourseListItem(data)
  },

  async get(courseId: number): Promise<CourseListItem> {
    if (mockEnabled) {
      await mockDelay()
      const course = mockCourseRecords.find((item) => item.id === courseId && !item.archived)
      if (!course) throw new ApiEnvelopeError('课程不存在或无权访问', 404)
      return toCourseListItem(structuredClone(course))
    }
    return toCourseListItem(
      unwrapApiResponse<BackendCourse>(await apiClient.get(`/courses/${courseId}`)),
    )
  },

  async update(courseId: number, payload: CourseUpdateRequest): Promise<CourseListItem> {
    if (mockEnabled) {
      await mockDelay()
      const course = mockCourseRecords.find((item) => item.id === courseId && !item.archived)
      if (!course) throw new ApiEnvelopeError('课程不存在或无权访问', 404)
      if (payload.name !== undefined) course.name = payload.name.trim()
      if (payload.code !== undefined) course.code = payload.code
      if (payload.description !== undefined) course.description = payload.description
      if (payload.exam_date !== undefined) course.exam_date = payload.exam_date
      if (payload.target_score !== undefined) course.target_score = payload.target_score
      if (payload.color !== undefined) course.color = payload.color
      course.updated_at = new Date().toISOString()
      return toCourseListItem(structuredClone(course))
    }
    return toCourseListItem(
      unwrapApiResponse<BackendCourse>(await apiClient.patch(`/courses/${courseId}`, payload)),
    )
  },

  async archive(courseId: number): Promise<void> {
    if (mockEnabled) {
      await mockDelay()
      const course = mockCourseRecords.find((item) => item.id === courseId && !item.archived)
      if (!course) throw new ApiEnvelopeError('课程不存在或无权访问', 404)
      course.archived = true
      course.updated_at = new Date().toISOString()
      return
    }
    unwrapApiResponse<unknown>(await apiClient.delete(`/courses/${courseId}`))
  },
}

export const documentApi = {
  async upload(courseId: number, file: File, title?: string): Promise<DocumentUploadResponse> {
    if (mockEnabled) {
      await mockDelay()
      if (!mockCourseRecords.some((course) => course.id === courseId)) {
        throw new ApiEnvelopeError('演示课程不存在')
      }
      const timestamp = new Date().toISOString()
      const documentId = Date.now()
      const extension = file.name.split('.').pop()?.toLowerCase() || 'txt'
      const document: BackendDocument = {
        id: documentId,
        course_id: courseId,
        title: title?.trim() || file.name,
        file_type: extension === 'markdown' ? 'md' : extension,
        current_version: 1,
        status: 'ready',
        page_count: 1,
        error_message: null,
        created_at: timestamp,
        updated_at: timestamp,
      }
      const taskId = `demo-document-task-${documentId}`
      const task: BackendAsyncTask = {
        task_id: taskId,
        task_type: 'document_parse',
        resource_type: 'document',
        resource_id: String(documentId),
        status: 'success',
        progress: 100,
        current_step: 'completed',
        input_data: { document_id: documentId, version: 1 },
        result_data: { document_id: documentId, version: 1, page_count: 1, chunk_count: file.size ? 1 : 0 },
        error_message: null,
        retry_count: 0,
        cancel_requested: false,
        created_at: timestamp,
        updated_at: timestamp,
        started_at: timestamp,
        finished_at: timestamp,
        can_cancel: false,
        can_retry: false,
      }
      mockDocuments.unshift(document)
      mockTasks.set(taskId, task)
      mockDocumentTaskIds.set(documentId, taskId)
      mockTaskDocumentIds.set(taskId, documentId)
      return structuredClone({ document, async_task_id: taskId })
    }

    const form = new FormData()
    form.append('file', file)
    if (title?.trim()) form.append('title', title.trim())
    const value = unwrapApiResponse<unknown>(await apiClient.post(`/courses/${courseId}/documents`, form))
    if (!isRecord(value) || typeof value.async_task_id !== 'string') {
      throw new ApiEnvelopeError('后端返回了无法识别的上传结果')
    }
    return { document: parseDocument(value.document), async_task_id: value.async_task_id }
  },

  async list(courseId: number): Promise<DocumentListResponse> {
    if (mockEnabled) {
      await mockDelay()
      const items = mockDocuments.filter((document) => document.course_id === courseId)
      return structuredClone({ items, total: items.length })
    }
    return parseDocumentList(unwrapApiResponse<unknown>(await apiClient.get(`/courses/${courseId}/documents`)))
  },

  async get(documentId: number): Promise<BackendDocument> {
    if (mockEnabled) {
      await mockDelay()
      const document = mockDocuments.find((item) => item.id === documentId)
      if (!document) throw new ApiEnvelopeError('演示文档不存在')
      return structuredClone(document)
    }
    return parseDocument(unwrapApiResponse<unknown>(await apiClient.get(`/documents/${documentId}`)))
  },

  async getLatestTask(documentId: number): Promise<LatestDocumentTaskResponse> {
    if (mockEnabled) {
      await mockDelay()
      const taskId = mockDocumentTaskIds.get(documentId)
      const task = taskId ? mockTasks.get(taskId) : undefined
      if (!task) throw new ApiEnvelopeError('演示文档暂无处理任务')
      return {
        task_id: task.task_id,
        status: task.status,
        progress: task.progress,
        current_step: task.current_step,
      }
    }
    const value = unwrapApiResponse<unknown>(await apiClient.get(`/documents/${documentId}/tasks/latest`))
    if (
      !isRecord(value)
      || typeof value.task_id !== 'string'
      || typeof value.status !== 'string'
      || typeof value.progress !== 'number'
      || (value.current_step !== null && typeof value.current_step !== 'string')
    ) {
      throw new ApiEnvelopeError('后端返回了无法识别的文档任务')
    }
    return value as unknown as LatestDocumentTaskResponse
  },

  async getTask(documentId: number, taskId: string): Promise<BackendAsyncTask> {
    if (mockEnabled) {
      await mockDelay()
      const task = mockTasks.get(taskId)
      if (!task || mockTaskDocumentIds.get(taskId) !== documentId) {
        throw new ApiEnvelopeError('任务不存在或不属于当前文档', 404)
      }
      return structuredClone(task)
    }
    return parseTask(unwrapApiResponse<unknown>(await apiClient.get(
      `/documents/${documentId}/tasks/${encodeURIComponent(taskId)}`,
    )))
  },

  async reparse(documentId: number): Promise<DocumentReparseResponse> {
    if (mockEnabled) {
      await mockDelay()
      const document = mockDocuments.find((item) => item.id === documentId)
      if (!document) throw new ApiEnvelopeError('演示文档不存在')
      document.current_version += 1
      document.status = 'ready'
      document.updated_at = new Date().toISOString()
      const taskId = `demo-document-task-${documentId}-${document.current_version}`
      mockTasks.set(taskId, {
        task_id: taskId,
        task_type: 'document_parse',
        resource_type: 'document',
        resource_id: String(documentId),
        status: 'success',
        progress: 100,
        current_step: 'completed',
        input_data: { document_id: documentId, version: document.current_version },
        result_data: { document_id: documentId, version: document.current_version, page_count: 1 },
        error_message: null,
        retry_count: 0,
        cancel_requested: false,
        created_at: document.updated_at,
        updated_at: document.updated_at,
        started_at: document.updated_at,
        finished_at: document.updated_at,
        can_cancel: false,
        can_retry: false,
      })
      mockDocumentTaskIds.set(documentId, taskId)
      mockTaskDocumentIds.set(taskId, documentId)
      return { document_id: documentId, version: document.current_version, async_task_id: taskId }
    }
    const value = unwrapApiResponse<unknown>(await apiClient.post(`/documents/${documentId}/reparse`))
    if (
      !isRecord(value)
      || !Number.isInteger(value.document_id)
      || !Number.isInteger(value.version)
      || typeof value.async_task_id !== 'string'
    ) throw new ApiEnvelopeError('后端返回了无法识别的重新解析结果')
    return value as unknown as DocumentReparseResponse
  },
}

export const asyncTaskApi = {
  async list(params: AsyncTaskListParams = {}): Promise<AsyncTaskListResponse> {
    if (mockEnabled) {
      await mockDelay()
      const all = [...mockTasks.values()]
        .filter((task) => (!params.status || task.status === params.status) && (!params.task_type || task.task_type === params.task_type))
        .sort((left, right) => right.created_at.localeCompare(left.created_at))
      const offset = params.offset || 0
      const limit = params.limit || 50
      return structuredClone({ items: all.slice(offset, offset + limit), total: all.length })
    }
    const value = unwrapApiResponse<unknown>(await apiClient.get('/async-tasks', { params }))
    if (!isRecord(value) || !Array.isArray(value.items) || typeof value.total !== 'number') {
      throw new ApiEnvelopeError('后端返回了无法识别的任务列表结构')
    }
    return { items: value.items.map(parseTask), total: value.total }
  },

  async get(taskId: string): Promise<BackendAsyncTask> {
    if (mockEnabled) {
      await mockDelay()
      const task = mockTasks.get(taskId)
      if (!task) throw new ApiEnvelopeError('演示任务不存在')
      return structuredClone(task)
    }
    return parseTask(unwrapApiResponse<unknown>(await apiClient.get(`/async-tasks/${encodeURIComponent(taskId)}`)))
  },

  async createWeeklyReport(payload: WeeklyReportRequest): Promise<BackendAsyncTask> {
    if (mockEnabled) {
      await mockDelay()
      const timestamp = new Date().toISOString()
      const taskId = `demo-weekly-report-${Date.now()}`
      const task: BackendAsyncTask = {
        task_id: taskId, task_type: 'weekly_report', resource_type: payload.course_id ? 'course' : 'user', resource_id: payload.course_id ? String(payload.course_id) : '1',
        status: 'queued', progress: 0, current_step: 'queued', input_data: { ...payload }, result_data: null,
        error_message: null, retry_count: 0, cancel_requested: false, created_at: timestamp, updated_at: timestamp, started_at: null, finished_at: null, can_cancel: true, can_retry: false,
      }
      mockTasks.set(taskId, task)
      return structuredClone(task)
    }
    return parseTask(unwrapApiResponse<unknown>(await apiClient.post('/async-tasks', { task_type: 'weekly_report', input_data: payload })))
  },

  async cancel(taskId: string): Promise<BackendAsyncTask> {
    if (mockEnabled) {
      await mockDelay()
      const task = mockTasks.get(taskId)
      if (!task || !task.can_cancel) throw new ApiEnvelopeError('任务不可取消', 409)
      task.cancel_requested = true
      task.status = task.status === 'queued' ? 'cancelled' : 'cancelling'
      task.current_step = task.status === 'cancelled' ? 'cancelled_before_start' : 'cancellation_requested'
      task.finished_at = task.status === 'cancelled' ? new Date().toISOString() : null
      task.updated_at = new Date().toISOString()
      task.can_cancel = false
      task.can_retry = task.status === 'cancelled'
      return structuredClone(task)
    }
    return parseTask(unwrapApiResponse<unknown>(await apiClient.post(`/async-tasks/${encodeURIComponent(taskId)}/cancel`)))
  },

  async retry(taskId: string): Promise<BackendAsyncTask> {
    if (mockEnabled) {
      await mockDelay()
      const task = mockTasks.get(taskId)
      if (!task || !task.can_retry) throw new ApiEnvelopeError('任务不可重试', 409)
      task.retry_count += 1
      task.status = 'queued'
      task.progress = 0
      task.current_step = 'queued_for_retry'
      task.error_message = null
      task.result_data = null
      task.cancel_requested = false
      task.started_at = null
      task.finished_at = null
      task.updated_at = new Date().toISOString()
      task.can_cancel = true
      task.can_retry = false
      return structuredClone(task)
    }
    return parseTask(unwrapApiResponse<unknown>(await apiClient.post(`/async-tasks/${encodeURIComponent(taskId)}/retry`)))
  },

  async downloadWeeklyReport(taskId: string): Promise<{ blob: Blob; filename: string }> {
    if (mockEnabled) {
      await mockDelay()
      const task = mockTasks.get(taskId)
      if (!task || task.task_type !== 'weekly_report' || task.status !== 'success') throw new ApiEnvelopeError('周报尚未生成', 409)
      const report = normalizeWeeklyReport(task.result_data)
      if (!report) throw new ApiEnvelopeError('演示周报数据无法识别', 409)
      const scope = report.scope_label || (report.course_names?.length === 1 ? report.course_names[0] : '全部课程')
      const lines = ['# StudyPilot 学习周报', '', `- 周期：${report.range_start} 至 ${report.range_end}`, `- 范围：${scope}`, `- 时区：${report.timezone || 'UTC'}`, '', '## 总览', '', `- 学习时长：${report.total_learning_minutes} 分钟`, `- 学习天数：${report.study_days} 天`, `- 完成任务：${report.completed_tasks} / ${report.scheduled_tasks}`, report.scheduled_tasks ? `- 完成率：${(report.completion_rate * 100).toFixed(1)}%` : '- 当前周期没有生效计划任务']
      if (report.daily) lines.push('', '## 每日学习', '', '| 日期 | 分钟 | 完成 | 计划 |', '| --- | ---: | ---: | ---: |', ...report.daily.map(item => `| ${item.date} | ${item.learning_minutes} | ${item.completed_tasks} | ${item.scheduled_tasks} |`))
      if (report.course_breakdown) lines.push('', '## 课程分布', '', '| 课程 | 分钟 | 完成 | 计划 |', '| --- | ---: | ---: | ---: |', ...report.course_breakdown.map(item => `| ${item.course_name.replace(/\|/g, '\\|')} | ${item.learning_minutes} | ${item.completed_tasks} | ${item.scheduled_tasks} |`))
      if (report.weak_points.length) lines.push('', '## 薄弱知识点', '', ...report.weak_points.map(item => `- ${item.knowledge_point}：${(item.score * 100).toFixed(1)}%，${item.attempts || 0} 次真实尝试，置信度 ${((item.confidence || 0) * 100).toFixed(1)}%`))
      lines.push('', '## 总结', '', report.summary)
      return { blob: new Blob([`${lines.join('\n')}\n`], { type: 'text/markdown;charset=utf-8' }), filename: 'studypilot-weekly-report.md' }
    }
    const response = await apiClient.get(`/async-tasks/${encodeURIComponent(taskId)}/report.md`, { responseType: 'blob' })
    const header = response.headers['content-disposition']
    const filename = typeof header === 'string' ? /filename="?([^";]+)"?/i.exec(header)?.[1] : undefined
    return { blob: response.data as Blob, filename: filename || 'studypilot-weekly-report.md' }
  },
}

export const chatApi = {
  async listSessions(courseId: number): Promise<ChatSessionListResponse> {
    if (mockEnabled) {
      await mockDelay()
      const items = mockChatSessions.filter((session) => session.course_id === courseId)
      return structuredClone({ items, total: items.length })
    }
    const value = unwrapApiResponse<unknown>(await apiClient.get(`/courses/${courseId}/chat-sessions`))
    if (!isRecord(value) || !Array.isArray(value.items) || typeof value.total !== 'number') {
      throw new ApiEnvelopeError('后端返回了无法识别的会话列表')
    }
    return { items: value.items.map(parseChatSession), total: value.total }
  },

  async createSession(courseId: number, payload: ChatSessionCreateRequest): Promise<ChatSessionCreateResponse> {
    if (mockEnabled) {
      await mockDelay()
      const timestamp = new Date().toISOString()
      const session: ChatSession = {
        session_id: `demo-chat-${Date.now()}`,
        course_id: courseId,
        title: payload.title?.trim() || '新对话',
        mode: payload.mode || 'strict',
        document_ids: [...new Set(payload.document_ids || [])],
        created_at: timestamp,
        updated_at: timestamp,
      }
      mockChatSessions.unshift(session)
      mockChatMessages.set(session.session_id, [])
      return structuredClone(session)
    }
    return parseChatSession(unwrapApiResponse<unknown>(await apiClient.post(`/courses/${courseId}/chat-sessions`, payload)))
  },

  async listMessages(sessionId: string): Promise<ChatMessageListResponse> {
    if (mockEnabled) {
      await mockDelay()
      const items = mockChatMessages.get(sessionId)
      if (!items) throw new ApiEnvelopeError('演示会话不存在')
      return structuredClone({ items, next_cursor: null })
    }
    const value = unwrapApiResponse<unknown>(await apiClient.get(`/chat-sessions/${encodeURIComponent(sessionId)}/messages`))
    if (
      !isRecord(value)
      || !Array.isArray(value.items)
      || (value.next_cursor !== null && typeof value.next_cursor !== 'string')
    ) {
      throw new ApiEnvelopeError('后端返回了无法识别的消息列表')
    }
    return { items: value.items.map(parseChatMessage), next_cursor: value.next_cursor }
  },

  async ask(sessionId: string, payload: ChatAskRequest): Promise<ChatAnswerResponse> {
    if (mockEnabled) {
      await mockDelay()
      const session = mockChatSessions.find((item) => item.session_id === sessionId)
      const messages = mockChatMessages.get(sessionId)
      if (!session || !messages) throw new ApiEnvelopeError('演示会话不存在')
      const timestamp = new Date().toISOString()
      const scopedDocuments = mockDocuments.filter((document) => (
        document.course_id === session.course_id
        && document.status === 'ready'
        && (!(payload.document_ids?.length) || payload.document_ids.includes(document.id))
      ))
      const sufficient = scopedDocuments.length > 0 && !payload.question.includes('资料中不存在')
      const document = scopedDocuments[0]
      const citations: RagCitation[] = sufficient && document ? [{
        source_id: 'S1',
        chunk_id: 1,
        document_id: document.id,
        document_name: document.title,
        document_version: document.current_version,
        page_number: 1,
        chapter_name: '演示内容',
        quote: '这是显式 Mock 模式中的课程资料片段，用于演示问答和引用布局。',
        score: 0.92,
      }] : []
      const answer = sufficient
        ? `根据演示课程资料：${citations[0].quote}\n\n依据：[S1]`
        : '当前课程资料中没有找到足够证据，无法可靠回答这个问题。'
      messages.push(
        { id: `demo-user-${Date.now()}`, role: 'user', content: payload.question, citations: [], sufficient_evidence: null, created_at: timestamp },
        { id: `demo-assistant-${Date.now()}`, role: 'assistant', content: answer, citations, sufficient_evidence: sufficient, created_at: timestamp },
      )
      if (session.title === '新对话') session.title = payload.question.slice(0, 50)
      session.updated_at = timestamp
      return { message_id: messages[messages.length - 1].id, answer, sufficient_evidence: sufficient, citations }
    }
    return parseChatAnswer(unwrapApiResponse<unknown>(await apiClient.post(`/chat-sessions/${encodeURIComponent(sessionId)}/messages`, payload)))
  },
}

export const planApi = {
  async getCurrent(courseId: number): Promise<CurrentStudyPlanResponse | null> {
    if (mockEnabled) {
      await mockDelay()
      return structuredClone(mockPlans.get(courseId) || null)
    }
    try {
      return parseCurrentPlan(unwrapApiResponse<unknown>(await apiClient.get(`/courses/${courseId}/study-plans/current`)))
    } catch (error) {
      if (isApiError(error, 404, 'PLAN_NOT_FOUND')) return null
      throw error
    }
  },

  async generate(courseId: number, payload: StudyPlanGenerateRequest): Promise<StudyPlanGenerateResponse> {
    if (mockEnabled) {
      await mockDelay()
      const planId = ++mockPlanId
      const token = `mock-confirm-${planId}-${Date.now()}`
      const dates: string[] = []
      const unavailable = new Set(payload.unavailable_dates || [])
      const dailyMinutes = payload.daily_availability?.default_minutes ?? mockProfile.preferences.daily_minutes
      const sessionMinutes = payload.session_minutes ?? mockProfile.preferences.session_minutes
      const cursor = new Date(`${payload.start_date}T00:00:00`)
      const end = new Date(`${payload.end_date}T00:00:00`)
      while (cursor <= end) {
        const day = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}-${String(cursor.getDate()).padStart(2, '0')}`
        if (!unavailable.has(day)) dates.push(day)
        cursor.setDate(cursor.getDate() + 1)
      }
      const tasks: StudyPlanTask[] = dates.slice(0, 3).map((scheduledDate, index) => ({
        id: ++mockPlanTaskId,
        scheduled_date: scheduledDate,
        knowledge_point_id: index + 1,
        title: `演示规则任务 ${index + 1}`,
        task_type: index === 2 ? '间隔复习' : '学习新知识',
        estimated_minutes: sessionMinutes,
        actual_minutes: null,
        priority: Number((0.9 - index * 0.1).toFixed(2)),
        difficulty: index === 0 ? 'basic' : 'intermediate',
        status: 'todo',
      }))
      const risks = tasks.length ? [] : ['可学习日期为空，无法安排任务。']
      const version: StudyPlanVersion = { version: 1, status: 'candidate', reason: '首次生成', summary: `共安排 ${tasks.length} 项任务。`, risks, diff: { generation_context: { ...mockProfile.preferences, daily_minutes: dailyMinutes, session_minutes: sessionMinutes, overrides: { daily_minutes: payload.daily_availability?.default_minutes !== undefined, session_minutes: payload.session_minutes !== undefined } } }, tasks }
      mockPlans.set(courseId, {
        plan_id: planId,
        course_id: courseId,
        goal: payload.goal,
        start_date: payload.start_date,
        end_date: payload.end_date,
        active_version: 0,
        plan_status: 'draft',
        expected_base_version: 0,
        confirmation_token: token,
        ...version,
      })
      return { async_task_id: `mock-plan-task-${planId}`, plan_id: planId, course_id: courseId, goal: payload.goal, start_date: payload.start_date, end_date: payload.end_date, expected_base_version: 0, candidate_version: version, confirmation_token: token }
    }
    return parseGeneratedPlan(unwrapApiResponse<unknown>(await apiClient.post(`/courses/${courseId}/study-plans/generate`, payload)))
  },

  async confirm(planId: number, version: number, payload: PlanConfirmRequest): Promise<PlanConfirmResponse> {
    if (mockEnabled) {
      await mockDelay()
      const entry = [...mockPlans.values()].find((plan) => plan.plan_id === planId && plan.version === version)
      if (!entry || entry.status !== 'candidate' || entry.confirmation_token !== payload.confirmation_token || entry.active_version !== payload.expected_base_version) {
        throw new ApiEnvelopeError('演示计划已变化，请重新加载')
      }
      mockTodayTaskItems.splice(0, mockTodayTaskItems.length, ...mockTodayTaskItems.filter((task) => task.course_id !== entry.course_id))
      mockTodayTaskItems.push(...entry.tasks.map((task) => ({ ...task, course_id: entry.course_id })))
      entry.active_version = version
      entry.plan_status = 'active'
      entry.status = 'active'
      entry.expected_base_version = null
      entry.confirmation_token = null
      return { plan_id: planId, active_version: version, previous_version: payload.expected_base_version, status: 'active', version_status: 'active' }
    }
    return parsePlanConfirmation(unwrapApiResponse<unknown>(await apiClient.post(`/study-plans/${planId}/versions/${version}/confirm`, payload)))
  },
}

export const studyTaskApi = {
  async listToday(params: { target_date: string; course_id?: number }): Promise<TodayTaskListResponse> {
    if (mockEnabled) {
      await mockDelay()
      const items = mockTodayTaskItems.filter((task) => task.scheduled_date === params.target_date && (params.course_id === undefined || task.course_id === params.course_id))
      return structuredClone({ items, total: items.length })
    }
    const search = new URLSearchParams({ target_date: params.target_date })
    if (params.course_id !== undefined) search.set('course_id', String(params.course_id))
    return parseTodayTaskList(unwrapApiResponse<unknown>(await apiClient.get(`/study-tasks/today?${search.toString()}`)))
  },

  async complete(taskId: number, payload: TaskCompleteRequest): Promise<TaskCompleteResponse> {
    if (mockEnabled) {
      await mockDelay()
      const task = mockTodayTaskItems.find((item) => item.id === taskId)
      if (!task) throw new ApiEnvelopeError('演示任务不存在或尚未生效')
      if (task.status === 'completed') return { task_id: task.id, status: task.status, actual_minutes: task.actual_minutes, mastery_score: 0.45, idempotent_replay: true }
      task.status = 'completed'
      task.actual_minutes = payload.actual_minutes
      return { task_id: task.id, status: task.status, actual_minutes: task.actual_minutes, mastery_score: 0.45, idempotent_replay: false }
    }
    return parseTaskCompletion(unwrapApiResponse<unknown>(await apiClient.post(`/study-tasks/${taskId}/complete`, payload)))
  },
}

export const learningApi = {
  getCourses: () => courseApi.list(),
  getTodayTasks: () => withMockFallback<StudyTask[]>(apiClient.get('/study-tasks/today'), todayTasks),
  getAsyncTasks: () => withMockFallback<AsyncTask[]>(apiClient.get('/async-tasks'), asyncTasks),
  async getMastery(courseId: number): Promise<KnowledgeMasteryResponse> {
    if (mockEnabled) {
      await mockDelay()
      if (!mockCourseRecords.some((course) => course.id === courseId && !course.archived)) {
        throw new ApiEnvelopeError('课程不存在或无权访问', 404)
      }
      return { items: [] }
    }
    return parseMastery(
      unwrapApiResponse<unknown>(await apiClient.get(`/courses/${courseId}/knowledge-mastery`)),
    )
  },
  async getRecords(courseId: number): Promise<LearningRecordListResponse> {
    if (mockEnabled) {
      await mockDelay()
      if (!mockCourseRecords.some((course) => course.id === courseId && !course.archived)) {
        throw new ApiEnvelopeError('课程不存在或无权访问', 404)
      }
      return { items: [], total: 0, summary: { minutes: 0 } }
    }
    return parseLearningRecords(
      unwrapApiResponse<unknown>(await apiClient.get(`/courses/${courseId}/learning-records`)),
    )
  },
}

function parseRecommendations(value: unknown): CourseRecommendationsResponse {
  const categories = ['all', 'task', 'mastery', 'resource', 'plan', 'report']
  const itemCategories = ['task', 'mastery', 'resource', 'plan', 'report']
  const selectionModes = ['diverse', 'category']
  if (!isRecord(value)) throw new ApiEnvelopeError('后端返回的推荐数据结构不完整')
  const course = value.course
  const categoryCounts = value.category_counts
  const selection = value.selection
  if (!isRecord(course) || !Number.isInteger(course.id) || typeof course.name !== 'string' || typeof value.target_date !== 'string' || typeof value.algorithm_version !== 'string' || typeof value.strategy_summary !== 'string' || !Array.isArray(value.items) || !isRecord(categoryCounts) || !isRecord(selection) || !selectionModes.includes(String(selection.mode)) || !Number.isInteger(selection.returned) || !Number.isInteger(selection.candidate_total) || !categories.every((category) => typeof categoryCounts[category] === 'number')) {
    throw new ApiEnvelopeError('后端返回的推荐数据结构不完整')
  }
  const items = value.items as CourseRecommendationItem[]
  if (items.some((item) => !item || typeof item.recommendation_key !== 'string' || !itemCategories.includes(item.category) || typeof item.category_label !== 'string' || !Number.isFinite(item.score) || !Array.isArray(item.signals) || !item.action)) {
    throw new ApiEnvelopeError('后端返回的推荐条目不完整')
  }
  return value as unknown as CourseRecommendationsResponse
}

function parseRecommendationHistory(value: unknown): RecommendationHistoryResponse {
  const categories = ['task', 'mastery', 'resource', 'plan', 'report']
  if (!isRecord(value) || !Array.isArray(value.items) || typeof value.total !== 'number' || !isRecord(value.metrics) || value.items.some((item) => !isRecord(item) || !categories.includes(String(item.category)) || typeof item.category_label !== 'string')) {
    throw new ApiEnvelopeError('后端返回的推荐历史结构不完整')
  }
  return value as unknown as RecommendationHistoryResponse
}

function mockRecommendations(courseId: number, category: RecommendationCategory = 'all', limit = 6): CourseRecommendationsResponse {
  const course = mockCourseRecords.find((item) => item.id === courseId && !item.archived)
  if (!course) throw new ApiEnvelopeError('课程不存在或无权访问', 404)
  const items: CourseRecommendationItem[] = [
    { recommendation_key: `rule-v2:${courseId}:study_task:${courseId}`, item_type: 'study_task', category: 'task', category_label: '学习任务', item_id: courseId, course_id: courseId, title: '完成今日复习任务', subtitle: '今日任务 · 预计 30 分钟', score: 80, reason: '演示模式：当前有待完成的学习任务。', estimated_minutes: 30, knowledge_point: null, signals: [{ code: 'due_today', label: '今日到期', value: 1, contribution: 20 }], score_breakdown: { due_today: 20 }, action: { type: 'open_today_tasks', label: '进入今日任务' } },
    { recommendation_key: `rule-v2:${courseId}:mastery_review:${courseId}`, item_type: 'mastery_review', category: 'mastery', category_label: '薄弱点复习', item_id: courseId, course_id: courseId, title: '复习核心知识点', subtitle: '已有演示学习记录', score: 62, reason: '演示模式：该知识点需要复习。', estimated_minutes: null, knowledge_point: { id: courseId, name: '核心知识点', score: 0.4, attempts: 2 }, signals: [{ code: 'low_mastery', label: '掌握度偏低', value: 0.6, contribution: 24 }], score_breakdown: { low_mastery: 24 }, action: { type: 'open_mastery', label: '查看掌握度' } },
    { recommendation_key: `rule-v2:${courseId}:upload_document:${courseId}`, item_type: 'upload_document', category: 'resource', category_label: '资料与问答', item_id: courseId, course_id: courseId, title: '上传学习资料', subtitle: '当前课程没有就绪资料', score: 50, reason: '演示模式：上传资料后可用于课程问答。', estimated_minutes: null, knowledge_point: null, signals: [{ code: 'rule_base', label: '规则基础分', value: 1, contribution: 50 }], score_breakdown: { rule_base: 50 }, action: { type: 'open_upload', label: '上传课程资料' } },
    { recommendation_key: `rule-v2:${courseId}:create_plan:${courseId}`, item_type: 'create_plan', category: 'plan', category_label: '学习计划', item_id: courseId, course_id: courseId, title: '创建学习计划', subtitle: '演示课程尚无生效学习计划', score: 55, reason: '演示模式：当前课程尚无生效学习计划，建议先生成一份学习计划。', estimated_minutes: null, knowledge_point: null, signals: [{ code: 'rule_base', label: '规则基础分', value: 1, contribution: 55 }], score_breakdown: { rule_base: 55 }, action: { type: 'open_plan', label: '创建学习计划' } },
  ]
  const categoryCounts: Record<RecommendationCategory, number> = { all: items.length, task: 1, mastery: 1, resource: 1, plan: 1, report: 0 }
  const filtered = category === 'all' ? items : items.filter((item) => item.category === category)
  return { course: { id: courseId, name: course.name }, target_date: new Date().toISOString().slice(0, 10), algorithm_version: 'rule-v2', strategy_summary: category === 'all' ? '演示模式：混合展示可执行的下一步建议。' : '演示模式：显示当前分类的演示候选。', items: filtered.slice(0, limit), category_counts: categoryCounts, selection: { mode: category === 'all' ? 'diverse' : 'category', returned: Math.min(filtered.length, limit), candidate_total: items.length } }
}

export const recommendationApi = {
  async list(courseId: number, params: { target_date?: string; limit?: number; category?: RecommendationCategory } = {}): Promise<CourseRecommendationsResponse> {
    if (mockEnabled) { await mockDelay(); return mockRecommendations(courseId, params.category || 'all', params.limit || 6) }
    const query = new URLSearchParams()
    if (params.target_date) query.set('target_date', params.target_date)
    if (params.limit) query.set('limit', String(params.limit))
    if (params.category) query.set('category', params.category)
    return parseRecommendations(unwrapApiResponse<unknown>(await apiClient.get(`/courses/${encodeURIComponent(String(courseId))}/recommendations${query.size ? `?${query}` : ''}`)))
  },
  async feedback(courseId: number, payload: { recommendation_key: string; action: RecommendationFeedbackAction }): Promise<{ record_id: number; accepted: boolean; action: RecommendationFeedbackAction }> {
    if (mockEnabled) {
      await mockDelay(); const recommendation = mockRecommendations(courseId, 'all', 20).items.find((item) => item.recommendation_key === payload.recommendation_key)
      if (!recommendation) throw new ApiEnvelopeError('推荐不存在', 404)
      const history = mockRecommendationHistory.get(courseId) || { items: [], total: 0, metrics: { clicked: 0, saved: 0, skipped: 0 } }
      if (!history.items.some((item) => item.item_type === recommendation.item_type && item.item_id === recommendation.item_id && item.feedback_action === payload.action)) {
        history.items.unshift({ record_id: Date.now(), item_type: recommendation.item_type, category: recommendation.category, category_label: recommendation.category_label, item_id: recommendation.item_id, title: recommendation.title, score: recommendation.score, reason: recommendation.reason, feedback_action: payload.action, created_at: new Date().toISOString() }); history.total += 1; history.metrics[payload.action] += 1
      }
      mockRecommendationHistory.set(courseId, history); return { record_id: history.items[0].record_id, accepted: true, action: payload.action }
    }
    return unwrapApiResponse(await apiClient.post(`/courses/${encodeURIComponent(String(courseId))}/recommendations/feedback`, payload)) as { record_id: number; accepted: boolean; action: RecommendationFeedbackAction }
  },
  async history(courseId: number, params: { limit?: number; offset?: number; action?: RecommendationFeedbackAction; item_type?: string } = {}): Promise<RecommendationHistoryResponse> {
    if (mockEnabled) { await mockDelay(); return structuredClone(mockRecommendationHistory.get(courseId) || { items: [], total: 0, metrics: { clicked: 0, saved: 0, skipped: 0 } }) }
    const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)]))
    return parseRecommendationHistory(unwrapApiResponse<unknown>(await apiClient.get(`/courses/${encodeURIComponent(String(courseId))}/recommendations/history?${query}`)))
  },
}

export const practiceApi = {
  async bootstrap(courseId: number) {
    if (mockEnabled) {
      await mockDelay()
      const course = mockCourseRecords.find((item) => item.id === courseId && !item.archived)
      if (!course) throw new ApiEnvelopeError('课程不存在')
      const existing = mockPracticeQuestions.get(courseId) || []
      if (!existing.length) {
        mockPracticeQuestions.set(courseId, [{ id: courseId * 1000 + 1, knowledge_point_id: null, knowledge_point: `${course.name}基础知识`, question_type: 'single_choice', stem: `关于“${course.name}基础知识”，下列哪项表述正确？`, options: [{ key: 'A', text: '应结合课程资料理解核心概念。' }, { key: 'B', text: '无需学习即可掌握。' }], difficulty: 'basic', origin: 'rule_seed', source_document_id: null, source_page_number: null, source_quote: null }])
        return { created_count: 1, existing_count: 0, total: 1, reason: null }
      }
      return { created_count: 0, existing_count: existing.length, total: existing.length, reason: null }
    }
    return unwrapApiResponse<{created_count:number;existing_count:number;total:number;reason:string|null}>(await apiClient.post(`/courses/${courseId}/practice/questions/bootstrap`))
  },
  async questions(courseId: number, mode: 'all'|'wrong' = 'all') {
    if (mockEnabled) {
      await mockDelay()
      const course = mockCourseRecords.find((item) => item.id === courseId && !item.archived)
      if (!course) throw new ApiEnvelopeError('课程不存在')
      const all = mockPracticeQuestions.get(courseId) || []
      const wrong = mockWrongBookEntries.get(courseId) || []
      const items = mode === 'wrong' ? wrong.filter((entry) => entry.status === 'pending').map((entry) => entry.question) : all
      const attempts = mockPracticeAttempts.get(courseId) || []
      const correct = attempts.filter((item) => item.is_correct).length
      return structuredClone({ course: { id: course.id, name: course.name }, items, total: items.length, summary: { total_attempts: attempts.length, correct_attempts: correct, wrong_attempts: attempts.length - correct, accuracy: attempts.length ? correct / attempts.length : 0, pending_wrong_count: wrong.filter((entry) => entry.status === 'pending').length, knowledge_point_count: 0 } })
    }
    return unwrapApiResponse<{course:{id:number;name:string};items:PracticeQuestion[];total:number;summary:PracticeSummary}>(await apiClient.get(`/courses/${courseId}/practice/questions?mode=${mode}`))
  },
  async submit(courseId:number, questionId:number, payload:PracticeAttemptRequest) {
    if (mockEnabled) {
      await mockDelay()
      const replay = mockPracticeSubmissions.get(payload.submission_id)
      if (replay) {
        if (replay.courseId !== courseId || replay.questionId !== questionId || replay.payload.selected_option !== payload.selected_option || replay.payload.elapsed_seconds !== payload.elapsed_seconds) {
          throw new ApiEnvelopeError('本次提交标识已被其他答案使用，请刷新题目后重试')
        }
        return structuredClone({ ...replay.result, idempotent_replay: true })
      }
      const question = (mockPracticeQuestions.get(courseId) || []).find((item) => item.id === questionId)
      if (!question || !question.options.some((item) => item.key === payload.selected_option)) throw new ApiEnvelopeError('题目或选项不存在')
      const attempts = mockPracticeAttempts.get(courseId) || []
      const isCorrect = payload.selected_option === 'A'
      const correctAttempts = attempts.filter((item) => item.is_correct).length + Number(isCorrect)
      if (!isCorrect) {
        const entries = mockWrongBookEntries.get(courseId) || []; const current = entries.find((item) => item.question.id === questionId)
        if (current) { current.wrong_count += 1; current.last_selected_option = payload.selected_option; current.last_wrong_at = new Date().toISOString(); current.status = 'pending' }
        else entries.push({ id: courseId * 10000 + entries.length + 1, status: 'pending', wrong_count: 1, last_selected_option: payload.selected_option, last_wrong_at: new Date().toISOString(), question: { ...question, correct_option: 'A', explanation: '演示模式下的规则题解析。' }, mastery_score: 0.2 })
        mockWrongBookEntries.set(courseId, entries)
      }
      const pending = (mockWrongBookEntries.get(courseId) || []).filter((item) => item.status === 'pending').length
      const result: PracticeAttemptResult = { ...question, attempt_id: courseId * 10000 + attempts.length + 1, question_id: question.id, selected_option: payload.selected_option, is_correct: isCorrect, correct_option: 'A', explanation: '演示模式下的规则题解析。', mastery_score: isCorrect ? 0.42 : 0.2, wrong_book_updated: !isCorrect, idempotent_replay: false, summary: { total_attempts: attempts.length + 1, correct_attempts: correctAttempts, wrong_attempts: attempts.length + 1 - correctAttempts, accuracy: correctAttempts / (attempts.length + 1), pending_wrong_count: pending, knowledge_point_count: 0 } }
      attempts.push(result); mockPracticeAttempts.set(courseId, attempts); mockPracticeSubmissions.set(payload.submission_id, { courseId, questionId, payload: structuredClone(payload), result })
      return structuredClone(result)
    }
    return unwrapApiResponse<PracticeAttemptResult>(await apiClient.post(`/courses/${courseId}/practice/questions/${questionId}/attempts`,payload))
  },
  async wrongBook(courseId:number, status='all', q='') {
    if (mockEnabled) {
      await mockDelay(); const entries = mockWrongBookEntries.get(courseId) || []
      const items = entries.filter((item) => item.status !== 'removed' && (status === 'all' || item.status === status) && (!q || item.question.stem.includes(q) || (item.question.knowledge_point || '').includes(q)))
      return structuredClone({ items, total: items.length, summary: { pending: entries.filter((item) => item.status === 'pending').length, mastered: entries.filter((item) => item.status === 'mastered').length, repeated_wrong: entries.filter((item) => item.wrong_count > 1).length } })
    }
    return unwrapApiResponse<{items:WrongBookEntry[];total:number;summary:{pending:number;mastered:number;repeated_wrong:number}}>(await apiClient.get(`/courses/${courseId}/wrong-book?status=${status}&q=${encodeURIComponent(q)}`))
  },
  async updateWrong(courseId:number, entryId:number, status:'mastered'|'removed') {
    if (mockEnabled) {
      await mockDelay(); const entry = (mockWrongBookEntries.get(courseId) || []).find((item) => item.id === entryId)
      if (!entry) throw new ApiEnvelopeError('错题不存在'); entry.status = status; return { id: entry.id, status: entry.status }
    }
    return unwrapApiResponse<{id:number;status:string}>(await apiClient.patch(`/courses/${courseId}/wrong-book/${entryId}`,{status}))
  },
}

export const statisticsApi = {
  async getOverview(params: { days: number; course_id?: number; end_date?: string }): Promise<StatisticsOverview> {
    if (mockEnabled) { await mockDelay(); return mockStatistics(params.days, params.course_id) }
    return unwrapApiResponse<StatisticsOverview>(await apiClient.get('/statistics/overview', { params }))
  },
  async exportCsv(params: { days: number; course_id?: number; end_date?: string }): Promise<{ blob: Blob; filename: string }> {
    if (mockEnabled) {
      await mockDelay(); const overview = mockStatistics(params.days, params.course_id)
      const text = `日期,课程范围,实际学习分钟\n${overview.daily.map((item) => `${item.date},演示课程,${item.actual_learning_seconds / 60}`).join('\n')}`
      return { blob: new Blob(['\ufeff' + text], { type: 'text/csv;charset=utf-8' }), filename: 'study-statistics-demo.csv' }
    }
    const response = await apiClient.get('/statistics/export.csv', { params, responseType: 'blob' })
    const disposition = String(response.headers['content-disposition'] || '')
    const match = disposition.match(/filename="?([^";]+)"?/i)
    return { blob: response.data as Blob, filename: match?.[1] || 'study-statistics.csv' }
  },
}

export const calendarApi = {
  async list(params:{start_at?:string;end_at?:string;start_date?:string;end_date?:string;course_id?:number;limit?:number;offset?:number}) { return unwrapApiResponse<CalendarEventListResponse>(await apiClient.get('/calendar/events',{params})) },
  async availability(params:{start_at:string;end_at:string;minimum_minutes?:number}) { return unwrapApiResponse<{timezone:string;slots:CalendarAvailabilitySlot[]}>(await apiClient.get('/calendar/availability',{params})) },
  async previewPlanSync(payload:CalendarPlanSyncRequest) { return unwrapApiResponse<CalendarPlanSyncPreview>(await apiClient.post('/calendar/plan-sync/preview',payload)) },
  async confirmPlanSync(preview:CalendarPlanSyncPreview, token:string) { return unwrapApiResponse<CalendarPlanSyncConfirmResult>(await apiClient.post('/calendar/plan-sync/confirm',{preview},{headers:{'X-Confirmation-Token':token}})) },
  async previewEvent(payload:CalendarEventCreateRequest) { return unwrapApiResponse<CalendarEventPreview>(await apiClient.post('/calendar/events/preview',payload,{headers:payload.idempotency_key?{'Idempotency-Key':payload.idempotency_key}:{}})) },
  async createEvent(payload:CalendarEventCreateRequest, token:string) { return unwrapApiResponse<{event_id:number;idempotent_replay:boolean}>(await apiClient.post('/calendar/events',payload,{headers:{'X-Confirmation-Token':token,...(payload.idempotency_key?{'Idempotency-Key':payload.idempotency_key}:{})}})) },
  async previewUpdate(id:number, payload:CalendarEventUpdateRequest) { return unwrapApiResponse<CalendarEventPreview>(await apiClient.post(`/calendar/events/${id}/preview-update`,payload)) },
  async updateEvent(id:number, payload:CalendarEventUpdateRequest, token:string) { return unwrapApiResponse<{event:unknown}>(await apiClient.patch(`/calendar/events/${id}`,payload,{headers:{'X-Confirmation-Token':token}})) },
  async previewDelete(id:number) { return unwrapApiResponse<CalendarEventPreview>(await apiClient.post(`/calendar/events/${id}/preview-delete`)) },
  async deleteEvent(id:number, token:string) { return unwrapApiResponse<{id:number;deleted:boolean}>(await apiClient.delete(`/calendar/events/${id}`,{headers:{'X-Confirmation-Token':token}})) },
  async exportIcs(params:{start_at?:string;end_at?:string;start_date?:string;end_date?:string;course_id?:number}) { const response=await apiClient.get('/calendar/export.ics',{params,responseType:'blob'}); const name=String(response.headers['content-disposition']||'').match(/filename="?([^";]+)"?/i)?.[1]||'studypilot-calendar.ics'; return {blob:response.data as Blob,filename:name} },
}

export const mcpApi = {
  async listTools() { return unwrapApiResponse<{items:MCPToolInfo[]}>(await apiClient.get('/mcp/tools')) },
  async listCalls(params:{calendar_only?:boolean;limit?:number;offset?:number}={}) { return unwrapApiResponse<MCPToolCallListResponse>(await apiClient.get('/mcp/tool-calls',{params})) },
}
