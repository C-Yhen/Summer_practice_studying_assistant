import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiClient, mockEnabled } from '@/api/client'

type User = { id: number; name: string; email: string; avatar?: string }

export const useAuthStore = defineStore('auth', () => {
  const token = ref(sessionStorage.getItem('studypilot_token') || '')
  const user = ref<User | null>(token.value ? { id: 1, name: '林知夏', email: 'lin.zhixia@university.edu' } : null)
  const loading = ref(false)

  async function login(email: string, password: string) {
    loading.value = true
    try {
      const { data } = await apiClient.post('/auth/login', { email, password })
      token.value = data.data?.access_token || data.access_token
      user.value = data.data?.user || data.user
    } catch (error) {
      if (!mockEnabled) throw error
      await new Promise((resolve) => window.setTimeout(resolve, 450))
      token.value = 'demo.jwt.token'
      user.value = { id: 1, name: '林知夏', email }
    } finally {
      sessionStorage.setItem('studypilot_token', token.value)
      loading.value = false
    }
  }

  async function register(name: string, email: string, password: string) {
    if (!mockEnabled) await apiClient.post('/auth/register', { name, email, password })
    await login(email, password)
    if (user.value) user.value.name = name
  }

  function logout() {
    token.value = ''
    user.value = null
    sessionStorage.removeItem('studypilot_token')
  }

  return { token, user, loading, login, register, logout }
})
