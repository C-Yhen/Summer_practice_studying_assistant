import { ApiEnvelopeError, apiClient, mockEnabled, unwrapApiResponse, withMockFallback } from './client'
import { asyncTasks, courses, todayTasks } from '@/data/mock'
import type {
  AsyncTask,
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
  CourseListItem,
  CourseListResult,
  DocumentListResponse,
  DocumentUploadResponse,
  LatestDocumentTaskResponse,
  RagCitation,
  StudyTask,
} from '@/types'

const DEFAULT_COURSE_COLOR = '#5b6cf9'

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

function parseTask(value: unknown): BackendAsyncTask {
  if (
    !isRecord(value)
    || typeof value.task_id !== 'string'
    || typeof value.task_type !== 'string'
    || typeof value.status !== 'string'
    || typeof value.progress !== 'number'
    || (value.current_step !== null && typeof value.current_step !== 'string')
    || (value.result_data !== null && !isRecord(value.result_data))
    || (value.error_message !== null && typeof value.error_message !== 'string')
    || typeof value.retry_count !== 'number'
    || typeof value.cancel_requested !== 'boolean'
    || typeof value.created_at !== 'string'
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
const mockChatSessions: ChatSession[] = []
const mockChatMessages = new Map<string, ChatMessage[]>()

export const courseApi = {
  async list(): Promise<CourseListResult> {
    if (mockEnabled) {
      await mockDelay()
      return parseCourseList({ items: structuredClone(mockCourseRecords), total: mockCourseRecords.length })
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
        status: 'success',
        progress: 100,
        current_step: 'completed',
        result_data: { document_id: documentId, version: 1, chunk_count: file.size ? 1 : 0 },
        error_message: null,
        retry_count: 0,
        cancel_requested: false,
        created_at: timestamp,
      }
      mockDocuments.unshift(document)
      mockTasks.set(taskId, task)
      mockDocumentTaskIds.set(documentId, taskId)
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
}

export const asyncTaskApi = {
  async get(taskId: string): Promise<BackendAsyncTask> {
    if (mockEnabled) {
      await mockDelay()
      const task = mockTasks.get(taskId)
      if (!task) throw new ApiEnvelopeError('演示任务不存在')
      return structuredClone(task)
    }
    return parseTask(unwrapApiResponse<unknown>(await apiClient.get(`/async-tasks/${encodeURIComponent(taskId)}`)))
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

export const learningApi = {
  getCourses: () => courseApi.list(),
  getTodayTasks: () => withMockFallback<StudyTask[]>(apiClient.get('/study-tasks/today'), todayTasks),
  getAsyncTasks: () => withMockFallback<AsyncTask[]>(apiClient.get('/async-tasks'), asyncTasks),
}
