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
  request_id?: string
}
