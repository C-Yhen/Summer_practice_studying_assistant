import type { APIRequestContext, Page } from '@playwright/test'

const apiOrigin = process.env.E2E_API_ORIGIN || 'http://127.0.0.1:18000'

export interface E2EIdentity {
  displayName: string
  email: string
  password: string
}

export function randomIdentity(prefix = 'learner'): E2EIdentity {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return {
    displayName: `E2E ${prefix} ${suffix.slice(-6)}`,
    email: `${prefix}-${suffix}@example.com`,
    password: `E2e-${suffix}!`,
  }
}

export async function registerAndLogin(request: APIRequestContext, identity = randomIdentity()) {
  const registration = await request.post(`${apiOrigin}/api/v1/auth/register`, {
    data: {
      display_name: identity.displayName,
      email: identity.email,
      password: identity.password,
    },
  })
  if (!registration.ok()) throw new Error(`Registration failed: ${registration.status()} ${await registration.text()}`)
  const login = await request.post(`${apiOrigin}/api/v1/auth/login`, {
    data: { email: identity.email, password: identity.password },
  })
  if (!login.ok()) throw new Error(`Login failed: ${login.status()} ${await login.text()}`)
  const body = await login.json()
  return { identity, token: body.data.access_token as string, user: body.data.user }
}

export async function createCourse(request: APIRequestContext, token: string, name = `E2E Course ${Date.now()}`) {
  const response = await request.post(`${apiOrigin}/api/v1/courses`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name,
      code: `E2E-${Math.random().toString(16).slice(2, 8)}`,
      description: 'Round 17 isolated browser acceptance course',
      exam_date: null,
      target_score: 85,
      color: '#5b6cf9',
    },
  })
  if (!response.ok()) throw new Error(`Course creation failed: ${response.status()} ${await response.text()}`)
  return (await response.json()).data
}

export function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export async function apiData(
  request: APIRequestContext,
  token: string,
  method: 'get' | 'post' | 'patch' | 'delete',
  path: string,
  options: Record<string, unknown> = {},
) {
  const response = await request[method](`${apiOrigin}/api/v1${path}`, {
    headers: authHeaders(token),
    ...options,
  })
  if (!response.ok()) throw new Error(`${method.toUpperCase()} ${path} failed: ${response.status()} ${await response.text()}`)
  const contentType = response.headers()['content-type'] || ''
  if (!contentType.includes('application/json')) return response
  return (await response.json()).data
}

export function localDate(offset = 0) {
  const value = new Date()
  value.setDate(value.getDate() + offset)
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}

export async function uploadDocument(
  request: APIRequestContext,
  token: string,
  courseId: number,
  name = `round17-${Date.now()}.txt`,
) {
  return apiData(request, token, 'post', `/courses/${courseId}/documents`, {
    multipart: {
      file: {
        name,
        mimeType: 'text/plain',
        buffer: Buffer.from('事务隔离、数据库规范化、索引与查询优化是本课程的复习重点。'),
      },
      title: name.replace(/\.txt$/i, ''),
    },
  })
}

export async function createActivePlan(
  request: APIRequestContext,
  token: string,
  courseId: number,
  startDate = localDate(),
) {
  const generated = await apiData(request, token, 'post', `/courses/${courseId}/study-plans/generate`, {
    data: {
      start_date: startDate,
      end_date: startDate,
      daily_availability: { default_minutes: 90 },
      unavailable_dates: [],
      session_minutes: 30,
      goal: 'Round 17 browser acceptance',
    },
  })
  await apiData(
    request,
    token,
    'post',
    `/study-plans/${generated.plan_id}/versions/${generated.candidate_version.version}/confirm`,
    {
      data: {
        expected_base_version: generated.expected_base_version,
        confirmation_token: generated.confirmation_token,
      },
    },
  )
  return generated
}

export async function listTodayTasks(
  request: APIRequestContext,
  token: string,
  courseId?: number,
  targetDate = localDate(),
) {
  const query = new URLSearchParams({ target_date: targetDate })
  if (courseId) query.set('course_id', String(courseId))
  return apiData(request, token, 'get', `/study-tasks/today?${query}`)
}

export async function bootstrapPractice(request: APIRequestContext, token: string, courseId: number) {
  await apiData(request, token, 'post', `/courses/${courseId}/practice/questions/bootstrap`)
  return apiData(request, token, 'get', `/courses/${courseId}/practice/questions?mode=all`)
}

export async function submitPractice(
  request: APIRequestContext,
  token: string,
  courseId: number,
  questionId: number,
  selectedOption: string,
  submissionId = crypto.randomUUID(),
) {
  return apiData(request, token, 'post', `/courses/${courseId}/practice/questions/${questionId}/attempts`, {
    data: { submission_id: submissionId, selected_option: selectedOption, elapsed_seconds: 3 },
  })
}

export async function createLearningRecord(
  request: APIRequestContext,
  token: string,
  courseId: number,
  durationSeconds = 900,
) {
  return apiData(request, token, 'post', '/learning-records', {
    data: {
      course_id: courseId,
      duration_seconds: durationSeconds,
      record_type: 'study',
      completed: true,
      occurred_at: new Date().toISOString(),
    },
  })
}

export async function createCalendarEvent(
  request: APIRequestContext,
  token: string,
  payload: { title: string; start_at: string; end_at: string; idempotency_key: string; study_task_id?: number },
) {
  const preview = await apiData(request, token, 'post', '/calendar/events/preview', { data: payload })
  const response = await request.post(`${apiOrigin}/api/v1/calendar/events`, {
    headers: {
      ...authHeaders(token),
      'X-Confirmation-Token': preview.confirmation_token,
      'Idempotency-Key': payload.idempotency_key,
    },
    data: payload,
  })
  if (!response.ok()) throw new Error(`calendar event failed: ${response.status()} ${await response.text()}`)
  return (await response.json()).data
}

export async function authenticatePage(page: Page, token: string) {
  await page.goto('/login')
  await page.evaluate((accessToken) => {
    window.sessionStorage.setItem('studypilot_token', accessToken)
  }, token)
}
