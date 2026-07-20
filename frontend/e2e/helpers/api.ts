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

export async function authenticatePage(page: Page, token: string) {
  await page.addInitScript((accessToken) => {
    window.sessionStorage.setItem('studypilot_token', accessToken)
  }, token)
}
