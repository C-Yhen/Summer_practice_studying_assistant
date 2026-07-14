import axios, { AxiosError, type AxiosResponse } from 'axios'
import type { ApiEnvelope } from '@/types'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 8000,
  headers: { 'Content-Type': 'application/json' },
})

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

export const mockEnabled = import.meta.env.VITE_ENABLE_MOCK !== 'false'

export async function withMockFallback<T>(
  request: Promise<AxiosResponse<ApiEnvelope<T> | T>>,
  fallback: T,
): Promise<T> {
  try {
    const response = await request
    const body = response.data
    if (body && typeof body === 'object' && 'data' in body) return (body as ApiEnvelope<T>).data
    return body as T
  } catch (error) {
    if (!mockEnabled) throw error
    await new Promise((resolve) => window.setTimeout(resolve, 280))
    return structuredClone(fallback)
  }
}
