import { ApiEnvelopeError, apiClient, mockEnabled, unwrapApiResponse, withMockFallback } from './client'
import { asyncTasks, citations, courses, todayTasks } from '@/data/mock'
import type {
  AsyncTask,
  BackendCourse,
  BackendCourseListResponse,
  Citation,
  CourseCreateRequest,
  CourseListItem,
  CourseListResult,
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
