import { ApiEnvelopeError, apiClient, isApiError, mockEnabled, unwrapApiResponse, withMockFallback } from './client'
import { asyncTasks, courses, todayTasks } from '@/data/mock'
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
} from '@/types'

const DEFAULT_COURSE_COLOR = '#5b6cf9'
const mockRecommendationHistory = new Map<number, RecommendationHistoryResponse>()

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
let mockPlanId = 2000
let mockPlanTaskId = 3000

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
        estimated_minutes: payload.session_minutes,
        actual_minutes: null,
        priority: Number((0.9 - index * 0.1).toFixed(2)),
        difficulty: index === 0 ? 'basic' : 'intermediate',
        status: 'todo',
      }))
      const risks = tasks.length ? [] : ['可学习日期为空，无法安排任务。']
      const version: StudyPlanVersion = { version: 1, status: 'candidate', reason: '首次生成', summary: `共安排 ${tasks.length} 项任务。`, risks, diff: {}, tasks }
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
  if (!isRecord(value) || !isRecord(value.course) || !Number.isInteger(value.course.id) || typeof value.course.name !== 'string' || typeof value.target_date !== 'string' || typeof value.algorithm_version !== 'string' || typeof value.strategy_summary !== 'string' || !Array.isArray(value.items)) {
    throw new ApiEnvelopeError('后端返回的推荐数据结构不完整')
  }
  const items = value.items as CourseRecommendationItem[]
  if (items.some((item) => !item || typeof item.recommendation_key !== 'string' || !Number.isFinite(item.score) || !Array.isArray(item.signals) || !item.action)) {
    throw new ApiEnvelopeError('后端返回的推荐条目不完整')
  }
  return value as unknown as CourseRecommendationsResponse
}

function parseRecommendationHistory(value: unknown): RecommendationHistoryResponse {
  if (!isRecord(value) || !Array.isArray(value.items) || typeof value.total !== 'number' || !isRecord(value.metrics)) {
    throw new ApiEnvelopeError('后端返回的推荐历史结构不完整')
  }
  return value as unknown as RecommendationHistoryResponse
}

function mockRecommendations(courseId: number): CourseRecommendationsResponse {
  const course = mockCourseRecords.find((item) => item.id === courseId && !item.archived)
  if (!course) throw new ApiEnvelopeError('课程不存在或无权访问', 404)
  const item: CourseRecommendationItem = {
    recommendation_key: `rule-v2:${courseId}:create_plan:${courseId}`,
    item_type: 'create_plan', item_id: courseId, course_id: courseId,
    title: '创建学习计划', subtitle: '演示课程尚无生效学习计划', score: 55,
    reason: '演示模式：当前课程尚无生效学习计划，建议先生成一份学习计划。', estimated_minutes: null,
    knowledge_point: null, signals: [{ code: 'rule_base', label: '规则基础分', value: 1, contribution: 55 }], score_breakdown: { rule_base: 55 }, action: { type: 'open_plan', label: '创建计划' },
  }
  return { course: { id: courseId, name: course.name }, target_date: new Date().toISOString().slice(0, 10), algorithm_version: 'rule-v2', strategy_summary: '演示模式：基于演示课程状态生成规则建议。', items: [item] }
}

export const recommendationApi = {
  async list(courseId: number, params: { target_date?: string; limit?: number } = {}): Promise<CourseRecommendationsResponse> {
    if (mockEnabled) { await mockDelay(); return mockRecommendations(courseId) }
    const query = new URLSearchParams()
    if (params.target_date) query.set('target_date', params.target_date)
    if (params.limit) query.set('limit', String(params.limit))
    return parseRecommendations(unwrapApiResponse<unknown>(await apiClient.get(`/courses/${encodeURIComponent(String(courseId))}/recommendations${query.size ? `?${query}` : ''}`)))
  },
  async feedback(courseId: number, payload: { recommendation_key: string; action: RecommendationFeedbackAction }): Promise<{ record_id: number; accepted: boolean; action: RecommendationFeedbackAction }> {
    if (mockEnabled) {
      await mockDelay(); const recommendation = mockRecommendations(courseId).items.find((item) => item.recommendation_key === payload.recommendation_key)
      if (!recommendation) throw new ApiEnvelopeError('推荐不存在', 404)
      const history = mockRecommendationHistory.get(courseId) || { items: [], total: 0, metrics: { clicked: 0, saved: 0, skipped: 0 } }
      if (!history.items.some((item) => item.item_type === recommendation.item_type && item.item_id === recommendation.item_id && item.feedback_action === payload.action)) {
        history.items.unshift({ record_id: Date.now(), item_type: recommendation.item_type, item_id: recommendation.item_id, title: recommendation.title, score: recommendation.score, reason: recommendation.reason, feedback_action: payload.action, created_at: new Date().toISOString() }); history.total += 1; history.metrics[payload.action] += 1
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
