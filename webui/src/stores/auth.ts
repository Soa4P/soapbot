import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError, api } from '@/api/client'
import type { AuthStatus } from '@/api/client'

/**
 * Session state for the panel.
 *
 * Login state comes from the server's /api/auth/status, which reads an HttpOnly
 * cookie. The store keeps no credential of its own. Loopback read access and a real
 * session are displayed differently: with strict auth on, the former cannot change
 * anything, and the UI must not make it look like a signed-in operator.
 */
export const useAuthStore = defineStore('auth', () => {
  const status = ref<AuthStatus | null>(null)
  const error = ref('')
  const busy = ref(false)
  const dialogOpen = ref(false)

  const hasToken = computed(() => mode.value === 'token')
  const mode = computed(() => status.value?.mode ?? 'none')
  const authenticated = computed(() => mode.value === 'token' || mode.value === 'loopback')
  const canLogin = computed(() => Boolean(status.value?.login_available))
  const role = computed(() => status.value?.role ?? 'anonymous')
  /**
   * Whether this session may change who holds which role.
   *
   * The server enforces it; this only decides whether to show an editable form. A
   * member who sees a working form that answers 403 reads the page as broken rather
   * than as a permission boundary.
   */
  const canEditAuthority = computed(
    () => role.value === 'admin' || role.value === 'owner',
  )
  /** Admin and above may delete a single memory row; the server enforces the same floor. */
  const canManageMemory = computed(
    () => role.value === 'admin' || role.value === 'owner',
  )

  async function refresh(): Promise<void> {
    try {
      status.value = await api.authStatus()
    } catch (err) {
      // 401 here means the stored token is dead; the request layer already cleared it.
      status.value = null
      error.value = err instanceof ApiError ? err.message : String(err)
    }
  }

  /**
   * Re-entrancy guard for the 401 handler.
   *
   * The handler's job is to call `refresh()`, and `refresh()` calls `/api/auth/status` —
   * which, when the session is genuinely gone, answers 401 and dispatches the very event
   * that started this. Without a guard that is an unbounded loop: every iteration is a
   * request, so an expired cookie turns one page load into a request storm against a
   * server that is already telling us to stop.
   *
   * A plain flag is enough because the loop is synchronous in its trigger: the nested
   * dispatch happens while the outer call is still awaiting, so the flag is still set.
   */
  const recovering = ref(false)

  /**
   * The single place that reacts to a 401.
   *
   * One refresh attempt, then either the session is back (transient expiry, clock skew)
   * or the login dialog opens. It never retries: a second automatic attempt would be
   * indistinguishable from the loop above, and the operator can always press the button.
   */
  async function handleUnauthorized(): Promise<void> {
    if (recovering.value) return
    recovering.value = true
    try {
      await refresh()
      if (!authenticated.value) openDialog()
    } finally {
      recovering.value = false
    }
  }

  async function login(initToken: string): Promise<boolean> {
    busy.value = true
    error.value = ''
    try {
      await api.login(initToken.trim())
      // The response still carries access_token for scripts. The panel ignores it:
      // login set the HttpOnly cookie, and /api/auth/status is the source of truth.
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

  /**
   * Sign out on the server, which revokes the token and clears both cookies.
   *
   * There is no local credential to delete any more, so a failed request leaves the
   * browser signed in — that is the honest outcome. `refresh()` still runs so the UI
   * reflects whatever the server actually decided.
   */
  async function logout(): Promise<void> {
    try {
      await api.logout()
    } catch {
      // fallback: server unreachable or the session was already dead. There is no
      // local credential to clear, so refresh() below shows whatever the server
      // actually decided instead of pretending the logout succeeded.
    } finally {
      status.value = null
      void refresh()
    }
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
    role,
    canEditAuthority,
    canManageMemory,
    refresh,
    handleUnauthorized,
    login,
    logout,
    openDialog,
    closeDialog,
  }
})
