import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getApiErrorMessage } from '@/api/client'
import { profileApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import type { UserPreferences } from '@/types'

export const CURRENT_ONBOARDING_VERSION = 1

export const useOnboardingStore = defineStore('onboarding', () => {
  const preferences = ref<UserPreferences | null>(null)
  const loadedUserId = ref<number | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const welcomeOpen = ref(false)
  const automaticEligible = computed(() => (
    preferences.value !== null
    && preferences.value.onboarding_seen_version < CURRENT_ONBOARDING_VERSION
  ))

  async function initialize() {
    const auth = useAuthStore()
    const userId = auth.user?.id ?? null
    if (!userId) {
      reset()
      return
    }
    if (loadedUserId.value === userId && preferences.value) return

    loading.value = true
    error.value = ''
    try {
      const profile = await profileApi.get()
      if (auth.user?.id !== userId) return
      loadedUserId.value = userId
      preferences.value = profile.preferences
      welcomeOpen.value = profile.preferences.onboarding_seen_version < CURRENT_ONBOARDING_VERSION
    } catch (cause) {
      if (auth.user?.id === userId) error.value = getApiErrorMessage(cause, '新手引导状态加载失败')
    } finally {
      if (auth.user?.id === userId) loading.value = false
    }
  }

  function openManually() {
    welcomeOpen.value = true
    error.value = ''
  }

  async function recordSkip() {
    if (saving.value) return false
    saving.value = true
    error.value = ''
    try {
      preferences.value = await profileApi.updateOnboarding({
        onboarding_seen_version: CURRENT_ONBOARDING_VERSION,
      })
      welcomeOpen.value = false
      return true
    } catch (cause) {
      error.value = getApiErrorMessage(cause, '暂时无法保存引导状态，请重试')
      return false
    } finally {
      saving.value = false
    }
  }

  async function recordCompletion() {
    if (saving.value) return false
    saving.value = true
    error.value = ''
    try {
      preferences.value = await profileApi.updateOnboarding({
        onboarding_seen_version: CURRENT_ONBOARDING_VERSION,
        onboarding_completed: true,
      })
      welcomeOpen.value = false
      return true
    } catch (cause) {
      error.value = getApiErrorMessage(cause, '暂时无法保存引导状态，请重试')
      return false
    } finally {
      saving.value = false
    }
  }

  function closeWelcomeLocally() {
    welcomeOpen.value = false
  }

  function reset() {
    preferences.value = null
    loadedUserId.value = null
    loading.value = false
    saving.value = false
    error.value = ''
    welcomeOpen.value = false
  }

  return {
    preferences,
    loadedUserId,
    loading,
    saving,
    error,
    welcomeOpen,
    automaticEligible,
    initialize,
    openManually,
    recordSkip,
    recordCompletion,
    closeWelcomeLocally,
    reset,
  }
})
