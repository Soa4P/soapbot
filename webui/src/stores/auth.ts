import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError, api, clearToken, getToken, setToken } from '@/api/client'
import type { AuthStatus } from '@/api/client'

/**
 * Session state for the panel.
 *
 * The backend allows two modes: a bearer token (works from anywhere) and a bare
 * loopback request (local single-operator convenience). The UI must not collapse them
 * into "logged in": an operator who is in loopback mode and then exposes the service
 * would otherwise have no clue that a token is now required.
 */
export const useAuthStore = defineStore('auth', () => {
  const status = ref<AuthStatus | null>(null)
  const error = ref('')
  const busy = ref(false)
  const dialogOpen = ref(false)

  const hasToken = computed(() => Boolean(getToken()))
  const mode = computed(() => status.value?.mode ?? 'none')
  const authenticated = computed(() => mode.value === 'token' || mode.value === 'loopback')
  const canLogin = computed(() => Boolean(status.value?.login_available))

  async function refresh(): Promise<void> {
    try {
      status.value = await api.authStatus()
    } catch (err) {
      // 401 here means the stored token is dead; the request layer already cleared it.
      status.value = null
      error.value = err instanceof ApiError ? err.message : String(err)
    }
  }

  async function login(initToken: string): Promise<boolean> {
    busy.value = true
    error.value = ''
    try {
      const result = await api.login(initToken.trim())
      setToken(result.access_token)
      dialogOpen.value = false
      await refresh()
      return true
    } catch (err) {
      error.value = err instanceof ApiError ? err.message : String(err)
      return false
    } finally {
      busy.value = false
    }
  }

  function logout(): void {
    clearToken()
    status.value = null
    void refresh()
  }

  function openDialog(): void {
    error.value = ''
    dialogOpen.value = true
  }

  function closeDialog(): void {
    dialogOpen.value = false
  }

  return {
    status,
    error,
    busy,
    dialogOpen,
    hasToken,
    mode,
    authenticated,
    canLogin,
    refresh,
    login,
    logout,
    openDialog,
    closeDialog,
  }
})
