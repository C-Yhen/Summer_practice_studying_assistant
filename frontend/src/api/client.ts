import axios, { AxiosError, type AxiosResponse } from 'axios'
import type { ApiEnvelope } from '@/types'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 8000,
  headers: { 'Content-Type': 'application/json' },
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
  switch (error.response.status) {
    case 401:
      return '邮箱或密码错误'
    case 409:
      return '该邮箱已注册'
    case 422:
      return detail ? `提交信息校验失败：${detail}` : '提交信息不符合要求'
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
  (error: AxiosError) => Promise.reject(error),
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
