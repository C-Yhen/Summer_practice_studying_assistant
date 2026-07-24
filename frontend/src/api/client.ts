import axios, { AxiosError, type AxiosResponse } from 'axios'
import type { ApiEnvelope } from '@/types'
import { notifySessionExpired } from '@/api/session-expiry'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 8000,
})

/** 用于 AI 调用的客户端，超时 120 秒（聊天 / 计划生成等耗时操作） */
export const aiApiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 120_000,
})

export class ApiEnvelopeError extends Error {
  constructor(
    message: string,
    readonly code?: number,
    readonly requestId?: string,
  ) {
    super(message)
    this.name = 'ApiEnvelopeError'
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function unwrapApiResponse<T>(response: AxiosResponse<unknown>): T {
  const body = response.data
  if (
    !isRecord(body)
    || typeof body.code !== 'number'
    || typeof body.message !== 'string'
    || typeof body.request_id !== 'string'
    || !Object.prototype.hasOwnProperty.call(body, 'data')
  ) {
    throw new ApiEnvelopeError('后端返回了无法识别的响应结构')
  }
  const envelope = body as unknown as ApiEnvelope<T>
  if (envelope.code !== 0) {
    throw new ApiEnvelopeError(envelope.message || '请求失败', envelope.code, envelope.request_id)
  }
  return envelope.data
}

export function isUnauthorizedError(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 401
}

export function isApiError(error: unknown, status: number, detail?: string): boolean {
  return axios.isAxiosError(error)
    && error.response?.status === status
    && (detail === undefined || readErrorDetail(error.response.data) === detail)
}

function readErrorDetail(data: unknown): string | undefined {
  if (!isRecord(data)) return undefined
  if (typeof data.detail === 'string') return data.detail
  if (!Array.isArray(data.detail)) return undefined
  const messages = data.detail
    .map((item) => {
      if (!isRecord(item) || typeof item.msg !== 'string') return undefined
      const location = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : undefined
      return typeof location === 'string' ? `${location}: ${item.msg}` : item.msg
    })
    .filter((message): message is string => Boolean(message))
  return messages.length ? messages.join('；') : undefined
}

export function getApiErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (error instanceof ApiEnvelopeError) return error.message
  if (!axios.isAxiosError(error)) return error instanceof Error ? error.message : fallback

  if (error.code === AxiosError.ETIMEDOUT || error.code === AxiosError.ECONNABORTED) {
    return '连接后端超时，请确认服务已启动'
  }
  if (!error.response) return '无法连接后端服务，请确认后端和数据库正常运行'

  const detail = readErrorDetail(error.response.data)
  const knownDetails: Record<string, string> = {
    'Email is already registered': '该邮箱已注册',
    FILE_EMPTY: '文件不能为空',
    FILE_TOO_LARGE: '文件大小超过后端限制',
    FILE_TYPE_UNSUPPORTED: '仅支持 PDF、TXT、MD 或 Markdown 文件',
    TASK_NOT_FOUND: '没有找到对应的处理任务',
    DOCUMENT_NOT_READY: '所选资料尚未处理完成，请刷新后重试',
    DOCUMENT_SCOPE_INVALID: '所选资料不属于当前课程或已不可用',
    SESSION_NOT_FOUND: '没有找到对应的问答会话',
    RAG_PROVIDER_UNAVAILABLE: '问答检索服务暂时不可用，请稍后重试',
    CHAT_PERSISTENCE_FAILED: '问答结果保存失败，请重新提问',
    PLAN_NOT_FOUND: '当前课程还没有学习计划',
    PLAN_VERSION_CONFLICT: '计划版本已变化，请刷新后重新确认',
    TASK_NOT_ACTIVE: '该任务所属计划尚未生效或已经失效',
    PLAN_GENERATION_FAILED: '学习计划生成失败，请稍后重试',
    TASK_COMPLETION_FAILED: '任务完成状态保存失败，请重试',
    IDEMPOTENCY_KEY_REUSED: '本次提交标识已被其他答案使用，请刷新题目后重试',
    PRACTICE_ATTEMPT_FAILED: '答题结果保存失败，请使用原提交重试',
  }
  if (detail && knownDetails[detail]) return knownDetails[detail]
  switch (error.response.status) {
    case 401:
      return '邮箱或密码错误'
    case 409:
      return detail || '请求与当前数据状态冲突'
    case 422:
      return detail ? `提交信息校验失败：${detail}` : '提交信息不符合要求'
    case 413:
      return '文件大小超过后端限制'
    case 415:
      return '仅支持 PDF、TXT、MD 或 Markdown 文件'
    default:
      return detail || fallback
  }
}

apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('studypilot_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  config.headers['X-Client-Version'] = 'frontend-mvp/0.1'
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const requestUrl = error.config?.url || ''
    const headers = error.config?.headers
    const authorization = typeof headers?.get === 'function'
      ? headers.get('Authorization')
      : headers?.Authorization
    const storedToken = window.sessionStorage.getItem('studypilot_token')
    const isCurrentSession = Boolean(storedToken && authorization === `Bearer ${storedToken}`)
    const isAuthRequest = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/register')
    if (error.response?.status === 401 && isCurrentSession && !isAuthRequest) {
      const redirect = `${window.location.pathname}${window.location.search}${window.location.hash}`
      void notifySessionExpired(redirect).catch(() => undefined)
    }
    return Promise.reject(error)
  },
)

// ---- aiApiClient 复用相同的拦截器 ----

aiApiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('studypilot_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  config.headers['X-Client-Version'] = 'frontend-mvp/0.1'
  return config
})

aiApiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const requestUrl = error.config?.url || ''
    const headers = error.config?.headers
    const authorization = typeof headers?.get === 'function'
      ? headers.get('Authorization')
      : headers?.Authorization
    const storedToken = window.sessionStorage.getItem('studypilot_token')
    const isCurrentSession = Boolean(storedToken && authorization === `Bearer ${storedToken}`)
    const isAuthRequest = requestUrl.includes('/auth/login') || requestUrl.includes('/auth/register')
    if (error.response?.status === 401 && isCurrentSession && !isAuthRequest) {
      const redirect = `${window.location.pathname}${window.location.search}${window.location.hash}`
      void notifySessionExpired(redirect).catch(() => undefined)
    }
    return Promise.reject(error)
  },
)

export const mockEnabled = import.meta.env.VITE_ENABLE_MOCK === 'true'

export async function withMockFallback<T>(
  request: Promise<AxiosResponse<unknown>>,
  fallback: T,
): Promise<T> {
  try {
    return unwrapApiResponse<T>(await request)
  } catch (error) {
    if (!mockEnabled) throw error
    await new Promise((resolve) => window.setTimeout(resolve, 280))
    return structuredClone(fallback)
  }
}
