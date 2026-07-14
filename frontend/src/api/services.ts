import { apiClient, withMockFallback } from './client'
import { asyncTasks, citations, courses, todayTasks } from '@/data/mock'
import type { AsyncTask, Citation, Course, StudyTask } from '@/types'

export const learningApi = {
  getCourses: () => withMockFallback<Course[]>(apiClient.get('/courses'), courses),
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
