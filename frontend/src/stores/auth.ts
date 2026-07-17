import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  apiClient,
  getApiErrorMessage,
  isUnauthorizedError,
  mockEnabled,
  unwrapApiResponse,
} from '@/api/client'
import type { AuthTokenResponse, AuthUser, BackendUser } from '@/types'

const TOKEN_KEY = 'studypilot_token'
const DEMO_USER_KEY = 'studypilot_demo_user'
const DEMO_TOKEN = 'demo.jwt.token'

function toAuthUser(user: BackendUser): AuthUser {
  const displayName = user.display_name?.trim() || user.full_name?.trim()
  if (!Number.isInteger(user.id) || !user.email || !displayName) {
    throw new Error('后端返回的用户信息不完整')
  }
  return {
    id: user.id,
    email: user.email,
    displayName,
    fullName: user.full_name,
    timezone: user.timezone,
    isActive: user.is_active,
    createdAt: user.created_at,
    updatedAt: user.updated_at,
  }
}

function createDemoUser(displayName: string, email: string): AuthUser {
  const now = new Date().toISOString()
  return {
    id: 1,
    email,
    displayName: displayName.trim() || '演示学习者',
    fullName: displayName.trim() || '演示学习者',
    timezone: 'Asia/Shanghai',
    isActive: true,
    createdAt: now,
    updatedAt: now,
  }
}

function readDemoUser(): AuthUser | null {
  const raw = sessionStorage.getItem(DEMO_USER_KEY)
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as Partial<AuthUser>
    if (!Number.isInteger(value.id) || !value.email || !value.displayName) return null
    return value as AuthUser
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(sessionStorage.getItem(TOKEN_KEY) || '')
  const user = ref<AuthUser | null>(null)
  const loading = ref(false)
  const initialized = ref(false)
  const restoreError = ref('')
  const authenticated = computed(() => Boolean(token.value && user.value))
  let initializationPromise: Promise<void> | null = null

  function clearSession() {
    token.value = ''
    user.value = null
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(DEMO_USER_KEY)
  }

  function saveSession(accessToken: string, authenticatedUser: AuthUser) {
    if (!accessToken) throw new Error('后端未返回访问令牌')
    token.value = accessToken
    user.value = authenticatedUser
    sessionStorage.setItem(TOKEN_KEY, accessToken)
    if (mockEnabled) sessionStorage.setItem(DEMO_USER_KEY, JSON.stringify(authenticatedUser))
    else sessionStorage.removeItem(DEMO_USER_KEY)
  }

  async function waitForDemo() {
    await new Promise((resolve) => window.setTimeout(resolve, 280))
  }

  async function login(email: string, password: string) {
    loading.value = true
    restoreError.value = ''
    clearSession()
    try {
      if (mockEnabled) {
        await waitForDemo()
        saveSession(DEMO_TOKEN, createDemoUser('演示学习者', email))
        return
      }
      const result = unwrapApiResponse<AuthTokenResponse>(
        await apiClient.post('/auth/login', { email, password }),
      )
      saveSession(result.access_token, toAuthUser(result.user))
    } finally {
      loading.value = false
    }
  }

  async function register(name: string, email: string, password: string) {
    loading.value = true
    restoreError.value = ''
    clearSession()
    try {
      if (mockEnabled) {
        await waitForDemo()
        saveSession(DEMO_TOKEN, createDemoUser(name, email))
        return
      }
      unwrapApiResponse<BackendUser>(
        await apiClient.post('/auth/register', { display_name: name, email, password }),
      )
      const result = unwrapApiResponse<AuthTokenResponse>(
        await apiClient.post('/auth/login', { email, password }),
      )
      saveSession(result.access_token, toAuthUser(result.user))
    } finally {
      loading.value = false
    }
  }

  async function restoreSession() {
    if (initialized.value) return
    if (initializationPromise) return initializationPromise

    initializationPromise = (async () => {
      restoreError.value = ''
      const storedToken = sessionStorage.getItem(TOKEN_KEY)
      if (!storedToken) {
        clearSession()
        return
      }
      token.value = storedToken

      if (mockEnabled) {
        const demoUser = storedToken === DEMO_TOKEN ? readDemoUser() : null
        if (demoUser) user.value = demoUser
        else clearSession()
        return
      }

      try {
        const backendUser = unwrapApiResponse<BackendUser>(await apiClient.get('/users/me'))
        user.value = toAuthUser(backendUser)
      } catch (error) {
        user.value = null
        if (isUnauthorizedError(error)) {
          clearSession()
          restoreError.value = '登录状态已失效，请重新登录'
        } else {
          restoreError.value = getApiErrorMessage(error, '暂时无法恢复登录状态')
        }
      }
    })().finally(() => {
      initialized.value = true
      initializationPromise = null
    })
    return initializationPromise
  }

  function logout() {
    clearSession()
    restoreError.value = ''
  }

  function updateCurrentUser(backendUser: BackendUser) {
    user.value = toAuthUser(backendUser)
    if (mockEnabled && user.value) sessionStorage.setItem(DEMO_USER_KEY, JSON.stringify(user.value))
  }

  return {
    token,
    user,
    loading,
    initialized,
    restoreError,
    authenticated,
    login,
    register,
    restoreSession,
    logout,
    updateCurrentUser,
  }
})
