import { ApiEnvelopeError, apiClient, mockEnabled, unwrapApiResponse, withMockFallback } from './client'
import { asyncTasks, citations, courses, todayTasks } from '@/data/mock'
import type {
  AsyncTask,
  BackendAsyncTask,
  BackendCourse,
  BackendCourseListResponse,
  BackendDocument,
  Citation,
  CourseCreateRequest,
  CourseListItem,
  CourseListResult,
  DocumentListResponse,
  DocumentUploadResponse,
  LatestDocumentTaskResponse,
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

const mockDocuments: BackendDocument[] = []
const mockTasks = new Map<string, BackendAsyncTask>()
const mockDocumentTaskIds = new Map<number, string>()

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

export const learningApi = {
  getCourses: () => courseApi.list(),
  getTodayTasks: () => withMockFallback<StudyTask[]>(apiClient.get('/study-tasks/today'), todayTasks),
  getAsyncTasks: () => withMockFallback<AsyncTask[]>(apiClient.get('/async-tasks'), asyncTasks),
  ask: (question: string, courseId = 1) =>
    withMockFallback<{ answer: string; citations: Citation[]; cached: boolean }>(
      apiClient.post('/chat/sessions/demo/messages', { question, course_id: courseId, top_k: 5 }),
      {
        answer: '第三范式（3NF）要求关系已经满足第二范式，并且每个非主属性都不传递依赖于候选码。直观地说：一张表中的普通字段应当直接由主键决定，而不是“通过另一个普通字段”间接决定。这样可以减少数据冗余，以及插入、更新和删除异常。',
        citations,
        cached: false,
      },
    ),
}
